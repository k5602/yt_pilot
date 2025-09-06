"""Core playlist downloading logic (structure-focused)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

from pytube import Playlist, YouTube  # type: ignore
from pytube.exceptions import PytubeError  # type: ignore
from rich.progress import Progress, BarColumn, DownloadColumn, TimeRemainingColumn  # type: ignore

from .config import AppConfig
from .models import PlaylistSession, VideoItem
from .naming import expand_template
from .manifest import Manifest
from .filtering import apply_filters
from .captions import CaptionsService
from uuid import uuid4
from datetime import datetime


@dataclass
class VideoResult:
    url: str
    title: str
    status: str
    quality: Optional[str] = None
    failure_reason: Optional[str] = None
    fallback_applied: bool = False


class PlaylistDownloader:
    def __init__(self, config: AppConfig):
        self.config = config
        self.progress = Progress(
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TimeRemainingColumn(),
        )

    # Public API
    def download_playlist(
        self,
        playlist_url: str,
        audio_only: Optional[bool] = None,
        filters=None,
        index_range: str | None = None,
        resume: bool = False,
        captions: bool | None = None,
        captions_auto: bool | None = None,
        caption_langs: Optional[list[str]] = None,
        force: bool = False,
    ) -> List[VideoResult]:
        """Download all videos from a playlist.

        If the provided URL is detected to be a single video URL, delegate to
        download_video for a consistent API (allows callers to pass either).
        """
        if self._is_single_video_url(playlist_url):
            single_result = self.download_video(playlist_url, audio_only=audio_only)
            return [single_result] if single_result else []
        # New session assembly
        session = PlaylistSession(
            playlist_url=playlist_url,
            session_id=str(uuid4()),
            started=datetime.utcnow(),
            quality_order=self.config.quality_order,
            audio_only=self.config.audio_only if audio_only is None else audio_only,
            config_snapshot=self.config.__dict__.copy(),
        )
        results: List[VideoResult] = []
        effective_audio = session.audio_only
        try:
            playlist = Playlist(playlist_url)
            out_dir = self.config.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest = Manifest.load(out_dir)
            manifest.set_playlist(playlist_url)
            skip_ids = set()
            if resume and not force:
                skip_ids = manifest.compute_skips(out_dir)

            # Build provisional video items
            items: List[VideoItem] = []
            for idx, video_url in enumerate(playlist.video_urls, start=1):
                vid_id = video_url.split("=")[-1]
                if vid_id in skip_ids:
                    continue
                items.append(
                    VideoItem(
                        index=idx,
                        video_id=vid_id,
                        title=video_url,  # will be replaced after fetch
                        preferred_quality=self.config.preferred(),
                        audio_only=effective_audio,
                    )
                )
            # Filtering (by index_range & filters terms on title placeholder for now)
            items = apply_filters(items, filters, index_range)

            with (
                self.progress,
                ThreadPoolExecutor(max_workers=self.config.max_concurrency) as executor,
            ):
                futures = []
                batch_size = max(1, self.config.max_concurrency * 2)
                for idx, vid in enumerate(items, start=1):
                    futures.append(
                        executor.submit(
                            self._process_video_enriched,
                            vid,
                            out_dir,
                            effective_audio,
                            manifest,
                            captions or False,
                            captions_auto or False,
                            caption_langs or ["en"],
                            force,
                        )
                    )
                    if len(futures) >= batch_size:
                        for f in futures:
                            res = f.result()
                            if res:
                                results.append(res)
                        futures.clear()
                # drain remaining
                for f in futures:
                    res = f.result()
                    if res:
                        results.append(res)
            session.videos.extend(items)
            session.ended = datetime.utcnow()
            manifest.save()
        except Exception as e:  # broad catch
            from rich import print as rprint

            rprint(f"[bold red]Fatal playlist error: {e}[/bold red]")
        return results  # session retained internally (future: return session)

    def download_video(
        self, video_url: str, audio_only: Optional[bool] = None
    ) -> Optional[VideoResult]:
        """Download a single YouTube video (no playlist context).

        Parameters
        ----------
        video_url: str
            URL of the YouTube video.
        audio_only: Optional[bool]
            Override config audio_only for this call.
        """
        effective_audio = self.config.audio_only if audio_only is None else audio_only
        return self._process_video(video_url, self.config.output_dir, effective_audio)

    # --- URL helpers -------------------------------------------------
    def _is_single_video_url(self, url: str) -> bool:
        # Basic heuristic: contains 'watch?v=' and not a 'list=' query param
        if "watch?v=" in url and "list=" not in url:
            return True
        # Shorts format https://youtube.com/shorts/<id>
        if "/shorts/" in url:
            return True
        return False

    def _process_video_enriched(
        self,
        video: VideoItem,
        output_path: Path,
        audio_only: bool,
        manifest: Manifest,
        captions: bool,
        captions_auto: bool,
        caption_langs: list[str],
        force: bool,
    ):
        # Reuse existing logic minimally (call original _process_video) but adapt result into VideoItem
        vr = self._process_video(
            f"https://www.youtube.com/watch?v={video.video_id}", output_path, audio_only
        )
        if vr and vr.status == "success":
            video.status = "success"
            video.selected_quality = vr.quality
            video.fallback_applied = vr.fallback_applied
            # Create filename using naming template from config
            video.filename = expand_template(self.config.naming_template, video)
            if captions or captions_auto:
                cap_service = CaptionsService(output_path, caption_langs)
                tracks = cap_service.obtain(video, captions, captions_auto)
                if tracks:
                    video.captions.extend(tracks)
        elif vr:
            video.status = "failed"
            video.failure_reason = vr.failure_reason
        manifest.update_video(video)
        return vr

    # Internal helpers
    def _process_video(
        self, url: str, output_path: Path, audio_only: bool
    ) -> Optional[VideoResult]:
        try:
            yt = YouTube(url, on_progress_callback=self._progress_callback)
            streams = self._get_sorted_streams(yt)
            target_quality = self.config.preferred()
            selected = None
            fallback_applied = False

            if audio_only:
                selected = next(
                    (
                        s
                        for s in streams
                        if s["type"] == "audio" and "mp4" in s["mime_type"]
                    ),
                    None,
                )
                target_quality = "audio"
            else:
                selected = next(
                    (
                        s
                        for s in streams
                        if s["resolution"] == target_quality and s["type"] == "video"
                    ),
                    None,
                )
                if not selected:
                    for q in self.config.quality_order[1:]:
                        selected = next(
                            (
                                s
                                for s in streams
                                if s["resolution"] == q and s["type"] == "video"
                            ),
                            None,
                        )
                        if selected:
                            fallback_applied = True
                            target_quality = q
                            break
            if not selected:
                return VideoResult(
                    url=url, title=yt.title, status="failed", failure_reason="No stream"
                )

            task_id = self.progress.add_task(
                description=yt.title[:50],
                total=selected["filesize"],
                visible=not audio_only,
            )
            self._download_media(selected["stream"], output_path)
            self.progress.update(task_id, visible=False)
            return VideoResult(
                url=url,
                title=yt.title,
                status="success",
                quality=target_quality,
                fallback_applied=fallback_applied,
            )
        except PytubeError as e:
            return VideoResult(
                url=url, title=url, status="failed", failure_reason=str(e)
            )
        except Exception as e:  # pragma: no cover (catch-all)
            return VideoResult(
                url=url, title=url, status="failed", failure_reason=f"Unexpected: {e}"
            )

    def _get_sorted_streams(self, yt: YouTube) -> List[Dict[str, Any]]:
        return sorted(
            [
                {
                    "itag": stream.itag,
                    "resolution": stream.resolution,
                    "mime_type": stream.mime_type,
                    "type": "video" if stream.includes_video_track else "audio",
                    "filesize": getattr(stream, "filesize", 0),
                    "stream": stream,
                }
                for stream in yt.streams
            ],
            key=lambda x: (x["type"], x["resolution"] or "0"),
            reverse=True,
        )

    def _download_media(self, stream, output_path: Path) -> None:
        try:
            stream.download(output_path=output_path, skip_existing=True)
        except Exception as e:  # logging stub
            from rich import print as rprint

            rprint(f"[red]Error downloading: {e}[/red]")

    def _progress_callback(
        self, stream, chunk, bytes_remaining
    ):  # pragma: no cover - callback
        if self.progress.task_ids:
            task_id = self.progress.task_ids[0]
            self.progress.update(task_id, advance=len(chunk))
