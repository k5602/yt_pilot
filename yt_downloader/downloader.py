"""Core playlist downloading logic (structure-focused)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import re

import yt_dlp
from rich.progress import Progress, BarColumn, DownloadColumn, TimeRemainingColumn  # type: ignore

from .config import AppConfig
from .models import PlaylistSession, VideoItem
from .naming import expand_template
from .manifest import Manifest
from .filtering import apply_filters
from .captions import CaptionsService
from .logging_utils import get_logger
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
        # Track last completed session + last selected format for enrichment
        self.last_session: PlaylistSession | None = None
        self._last_selected_format: dict | None = None

    def _normalize_video_url(self, url: str) -> str:
        # Strip time parameters & extra queries to stabilize requests
        if "watch?v=" in url:
            base, _, query = url.partition("?")
            if "watch?v=" in base:
                return url  # unusual but keep
            # Reconstruct canonical format
        if "&" in url:
            head, _, _ = url.partition("&")
            if "watch?v=" in head:
                return head
        if "?t=" in url:
            return url.split("?t=")[0]
        return url

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
            playlist_url = self._normalize_video_url(playlist_url)
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
        # Expose session for incremental counting in worker callbacks
        self.last_session = session
        results: List[VideoResult] = []
        effective_audio = session.audio_only
        try:
            # Use yt-dlp to extract playlist info
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(playlist_url, download=False)
                if not playlist_info or "entries" not in playlist_info:
                    return []

            out_dir = self.config.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest = Manifest.load(out_dir)
            manifest.set_playlist(playlist_url)
            skip_ids = set()
            if resume and not force:
                skip_ids = manifest.compute_skips(out_dir)

            # Build provisional video items
            items: List[VideoItem] = []
            for idx, entry in enumerate(playlist_info["entries"], start=1):
                if not entry:  # Sometimes entries can be None
                    continue

                video_url = (
                    entry.get("url") or f"https://www.youtube.com/watch?v={entry['id']}"
                )
                vid_id = entry["id"]

                if vid_id in skip_ids:
                    continue

                items.append(
                    VideoItem(
                        index=idx,
                        video_id=vid_id,
                        title=entry.get("title", video_url),
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
            # Backfill counts if incremental path was skipped (should rarely happen)
            if session.counts["total"] == 0:
                session.counts["total"] = len(results)
                session.counts["success"] = sum(1 for r in results if r.status == "success")
                session.counts["failed"] = sum(1 for r in results if r.status == "failed")
                session.counts["skipped"] = 0
                session.counts["fallbacks"] = sum(1 for r in results if r.fallback_applied)
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
        video_url = self._normalize_video_url(video_url)
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
            # Capture size if available from last selected format
            if getattr(self, "_last_selected_format", None):
                sf = self._last_selected_format
                if sf:
                    video.size_bytes = sf.get("filesize") or sf.get("filesize_approx")
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
        # Increment session counts (atomic per video result)
        if getattr(self, "last_session", None):
            sess = self.last_session
            if video.status == "success":
                sess.counts["success"] += 1
            elif video.status == "failed":
                sess.counts["failed"] += 1
            elif video.status == "skipped":
                sess.counts["skipped"] += 1
            sess.counts["total"] += 1
            if video.fallback_applied:
                sess.counts["fallbacks"] += 1
        return vr

    # Internal helpers
    def _process_video(
        self, url: str, output_path: Path, audio_only: bool
    ) -> Optional[VideoResult]:
        import time

        attempts = 0
        last_exc: Exception | None = None
        while attempts < 3:
            try:
                # Configure yt-dlp options
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": False,
                    "outtmpl": f"{output_path}/%(title)s.%(ext)s",
                    # Built-in retry handling (simplifies outer logic)
                    "retries": 3,
                    "fragment_retries": 3,
                    "skip_unavailable_fragments": True,
                }

                # Get video info first
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        return VideoResult(
                            url=url,
                            title=url,
                            status="failed",
                            failure_reason="No video info available",
                        )

                title = info.get("title", url)
                formats = info.get("formats", [])

                if not formats:
                    return VideoResult(
                        url=url,
                        title=title,
                        status="failed",
                        failure_reason="No streams available",
                    )

                # Simplified in-process selection (delegates merging to format selector)
                target_height = self._quality_to_height(self.config.preferred())
                selected_format = None
                if audio_only:
                    afmts = [
                        f for f in formats
                        if f.get("acodec") not in ["none", None] and f.get("vcodec") in ["none", None]
                    ]
                    if afmts:
                        afmts.sort(key=lambda f: f.get("abr") or 0, reverse=True)
                        selected_format = afmts[0]
                else:
                    candidates = [
                        f for f in formats
                        if f.get("height") and f.get("height") <= target_height
                        and f.get("vcodec") not in ["none", None]
                        and f.get("acodec") not in ["none", None]
                    ]
                    if candidates:
                        candidates.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
                        selected_format = candidates[0]
                    if not selected_format:
                        combined = [
                            f for f in formats
                            if f.get("vcodec") not in ["none", None]
                            and f.get("acodec") not in ["none", None]
                            and f.get("height")
                        ]
                        if combined:
                            combined.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
                            selected_format = combined[0]
                if not selected_format:
                    log = get_logger()
                    log.warning(f"No suitable format found for {title}. Available formats:")
                    for fmt in formats[:5]:
                        log.warning(
                            f"  Format {fmt.get('format_id')}: acodec={fmt.get('acodec')}, "
                            f"vcodec={fmt.get('vcodec')}, abr={fmt.get('abr')}, height={fmt.get('height')}"
                        )
                    return VideoResult(
                        url=url,
                        title=title,
                        status="failed",
                        failure_reason="No suitable format found",
                    )
                # Stash for enrichment
                self._last_selected_format = selected_format

                # Set up download options with smart format selector
                download_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "outtmpl": f"{output_path}/%(title)s.%(ext)s",
                    "progress_hooks": [self._yt_dlp_progress_hook],
                    "retries": 3,
                    "fragment_retries": 3,
                    "skip_unavailable_fragments": True,
                }

                if audio_only:
                    download_opts.update({
                        "format": "bestaudio/best",
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }],
                        "prefer_ffmpeg": True,
                    })
                else:
                    quality_height = self._quality_to_height(self.config.preferred())

                    # Prefer best video <= target + best audio, fallback to any best
                    format_selector = f"bestvideo[height<={quality_height}]+bestaudio/best[height<={quality_height}]/best"

                    download_opts.update({
                        "format": format_selector,
                        "merge_output_format": "mp4",  # Ensure we get mp4 with both video and audio
                    })

                # Create progress task
                filesize = selected_format.get("filesize") or selected_format.get(
                    "filesize_approx", 0
                )
                task_id = self.progress.add_task(
                    description=title[:50],
                    total=filesize,
                    visible=True,
                )
                self._current_task_id = task_id

                # Download the video
                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    ydl.download([url])

                self.progress.update(task_id, visible=False)

                # Determine quality and fallback status
                quality = self._format_to_quality(selected_format, audio_only)
                target_height = self._quality_to_height(self.config.preferred())
                fallback_applied = (
                    not audio_only
                    and isinstance(selected_format.get("height"), int)
                    and selected_format.get("height") is not None
                    and selected_format.get("height") < target_height
                )

                return VideoResult(
                    url=url,
                    title=title,
                    status="success",
                    quality=quality,
                    fallback_applied=fallback_applied,
                )

            except yt_dlp.DownloadError as e:
                last_exc = e
                error_str = str(e).lower()
                # Check if this is a permanent error that shouldn't be retried
                if any(
                    code in error_str
                    for code in ["400", "403", "404", "410", "private", "deleted"]
                ):
                    break
                attempts += 1
                if attempts >= 3:
                    break
                time.sleep(1 * attempts)  # simple backoff 1s,2s
            except Exception as e:  # transient or fatal
                last_exc = e
                error_str = str(e).lower()
                # Check if this is a permanent error that shouldn't be retried
                if any(code in error_str for code in ["400", "403", "404", "410"]):
                    break
                attempts += 1
                if attempts >= 3:
                    break
                time.sleep(1 * attempts)  # simple backoff 1s,2s

        if last_exc:
            return VideoResult(
                url=url,
                title=url,
                status="failed",
                failure_reason=f"{last_exc.__class__.__name__}: {last_exc}",
            )
        return None

    def _select_best_format(
        self, formats: List[Dict], audio_only: bool
    ) -> Optional[Dict]:
        """Select the best format based on quality preferences."""
        log = get_logger()

        if audio_only:
            log.debug(f"Selecting audio format from {len(formats)} available formats")

            # Find dedicated audio-only formats first (no video stream)
            audio_only_formats = [
                f
                for f in formats
                if f.get("acodec") != "none" and f.get("vcodec") in ["none", None]
            ]

            log.debug(f"Found {len(audio_only_formats)} dedicated audio-only formats")

            if audio_only_formats:
                # Sort by audio bitrate (higher is better)
                audio_only_formats.sort(key=lambda x: x.get("abr", 0) or 0, reverse=True)
                selected = audio_only_formats[0]
                log.debug(f"Selected audio-only format: {selected.get('format_id')} "
                         f"(acodec={selected.get('acodec')}, abr={selected.get('abr')})")
                return selected

            # Fallback: find any format with audio (including video+audio formats)
            audio_formats = [
                f for f in formats
                if f.get("acodec") not in ["none", None] and f.get("acodec")
            ]

            log.debug(f"Fallback: Found {len(audio_formats)} formats with audio")

            if audio_formats:
                # Prefer formats with higher audio bitrate and no video when possible
                audio_formats.sort(
                    key=lambda x: (
                        x.get("vcodec") in ["none", None],  # Prefer audio-only
                        x.get("abr", 0) or 0  # Then by audio bitrate
                    ),
                    reverse=True
                )
                selected = audio_formats[0]
                log.debug(f"Selected audio format: {selected.get('format_id')} "
                         f"(acodec={selected.get('acodec')}, vcodec={selected.get('vcodec')}, "
                         f"abr={selected.get('abr')})")
                return selected

            log.warning("No formats with audio found!")
        else:
            # Find best video format with audio
            target_height = self._quality_to_height(self.config.preferred())

            log.debug(f"Selecting video format for {target_height}p from {len(formats)} available formats")

            # First priority: combined formats with both video and audio at target quality
            combined_formats = [
                f for f in formats
                if (f.get("height") == target_height
                    and f.get("vcodec") not in ["none", None]
                    and f.get("acodec") not in ["none", None])
            ]

            if combined_formats:
                # Sort by filesize/quality indicators
                combined_formats.sort(key=lambda x: x.get("tbr", 0) or 0, reverse=True)
                selected = combined_formats[0]
                log.debug(f"Selected combined format: {selected.get('format_id')} "
                         f"(height={selected.get('height')}, has audio)")
                return selected

            # Second priority: try fallback qualities with audio
            for fallback_quality in self.config.quality_order[1:]:
                fallback_height = self._quality_to_height(fallback_quality)
                combined_fallback = [
                    f for f in formats
                    if (f.get("height") == fallback_height
                        and f.get("vcodec") not in ["none", None]
                        and f.get("acodec") not in ["none", None])
                ]

                if combined_fallback:
                    combined_fallback.sort(key=lambda x: x.get("tbr", 0) or 0, reverse=True)
                    selected = combined_fallback[0]
                    log.debug(f"Selected fallback combined format: {selected.get('format_id')} "
                             f"(height={selected.get('height')}, has audio)")
                    return selected

            # Third priority: any combined format (ignore quality preference)
            any_combined = [
                f for f in formats
                if (f.get("vcodec") not in ["none", None]
                    and f.get("acodec") not in ["none", None]
                    and f.get("height", 0) > 0)
            ]

            if any_combined:
                # Sort by height descending, then by bitrate
                any_combined.sort(key=lambda x: (x.get("height", 0) or 0, x.get("tbr", 0) or 0), reverse=True)
                selected = any_combined[0]
                log.debug(f"Selected any combined format: {selected.get('format_id')} "
                         f"(height={selected.get('height')}, has audio)")
                return selected

            # Last resort: let yt-dlp handle merging by returning None
            # This will trigger the smart format selection in download_opts
            log.warning("No combined video+audio formats found, will use yt-dlp smart selection")

        return None

    def _quality_to_height(self, quality: str) -> int:
        """Convert quality string to height in pixels."""
        quality_map = {
            "144p": 144,
            "240p": 240,
            "360p": 360,
            "480p": 480,
            "720p": 720,
            "1080p": 1080,
            "1440p": 1440,
            "2160p": 2160,
        }
        return quality_map.get(quality, 720)

    def _format_to_quality(self, format_item: Dict, audio_only: bool) -> str:
        """Convert format info back to quality string."""
        if audio_only:
            return "audio"

        height = format_item.get("height", 0)
        if height >= 2160:
            return "2160p"
        elif height >= 1440:
            return "1440p"
        elif height >= 1080:
            return "1080p"
        elif height >= 720:
            return "720p"
        elif height >= 480:
            return "480p"
        elif height >= 360:
            return "360p"
        elif height >= 240:
            return "240p"
        else:
            return "144p"

    def _yt_dlp_progress_hook(self, d):
        """Progress hook for yt-dlp downloads."""
        if hasattr(self, "_current_task_id") and self._current_task_id is not None:
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                if total > 0:
                    self.progress.update(
                        self._current_task_id, completed=downloaded, total=total
                    )
            elif d["status"] == "finished":
                self.progress.update(
                    self._current_task_id, completed=d.get("total_bytes", 0)
                )

    def _progress_callback(
        self, stream, chunk, bytes_remaining
    ):  # pragma: no cover - callback
        """Legacy progress callback - replaced by yt-dlp progress hook."""
        pass
