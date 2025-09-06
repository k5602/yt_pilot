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
        self, playlist_url: str, audio_only: Optional[bool] = None
    ) -> List[VideoResult]:
        results: List[VideoResult] = []
        effective_audio = self.config.audio_only if audio_only is None else audio_only
        try:
            playlist = Playlist(playlist_url)
            out_dir = self.config.output_dir
            out_dir.mkdir(parents=True, exist_ok=True)

            with self.progress, ThreadPoolExecutor(
                max_workers=self.config.max_concurrency
            ) as executor:
                futures = []
                for video_url in playlist.video_urls:
                    futures.append(
                        executor.submit(
                            self._process_video, video_url, out_dir, effective_audio
                        )
                    )
                for f in futures:
                    res = f.result()
                    if res:
                        results.append(res)
        except Exception as e:  # broad catch to capture fatal
            # In an expanded architecture this would propagate a structured error
            from rich import print as rprint

            rprint(f"[bold red]Fatal playlist error: {e}[/bold red]")
        return results

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
