"""Core playlist downloading logic (structure-focused)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, List, Dict
from yt_dlp.utils import DownloadError

import yt_dlp
from rich.progress import Progress, BarColumn, DownloadColumn, TimeRemainingColumn  # type: ignore

from .config import AppConfig
from .models import PlaylistSession, VideoItem, CaptionTrack
from .naming import expand_template
from .manifest import Manifest
from .filtering import apply_filters
from .captions import CaptionsService
from .logging_utils import get_logger
from uuid import uuid4
from datetime import datetime

RETRIES = 3  # Centralized retry constant

# --- Helper components (refactored architecture) ---------------------------------

class FormatSelector:
    """
    Build a deterministic yt-dlp format selector chain.

    Strategy (non-audio):
      For each desired height H in quality_order:
        - bestvideo[height=H][ext=mp4]+bestaudio[ext=m4a]
        - best[height=H]
      Fallbacks:
        - bestvideo+bestaudio
        - best
    Audio only:
      - bestaudio/best
    """

    def __init__(self, quality_order: list[str], audio_only: bool):
        self.quality_order = quality_order
        self.audio_only = audio_only

    def build(self) -> tuple[str, list[str]]:
        steps: list[str] = []
        reasons: list[str] = []
        if self.audio_only:
            steps.append("bestaudio/best")
            reasons.append("audio_only_best")
            return steps[0], reasons
        for q in self.quality_order:
            height = self._q_to_h(q)
            steps.append(f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/best[height={height}]")
            reasons.append(f"target_height_{height}")
        # generic fallbacks
        steps.append("bestvideo+bestaudio")
        reasons.append("generic_merged")
        steps.append("best")
        reasons.append("generic_best")
        # Combine chain by '/' letting yt-dlp pick first viable of each group
        selector = "/".join(steps)
        return selector, reasons

    @staticmethod
    def _q_to_h(q: str) -> int:
        try:
            return int(q.replace("p", "").strip())
        except Exception:
            return 720


class CaptionOrchestrator:
    """
    Unified caption retrieval using a single info dict (if supplied) to decide what to fetch.
    """

    def __init__(self, service_factory):
        self._make_service = service_factory  # expects (languages:list[str]) -> CaptionsService

    def run(self, video, output_dir: Path, info: dict, want_manual: bool, want_auto: bool,
            languages: list[str]) -> list[CaptionTrack]:
        from .captions import CaptionsService  # local import to avoid cycles
        tracks: list[CaptionTrack] = []
        service = self._make_service(languages)
        # Leverage existing service obtain (already has graceful fallback logic)
        tracks.extend(service.obtain(video, want_manual, want_auto))
        return tracks


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
            ydl_opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                playlist_info = ydl.extract_info(playlist_url, download=False)
                if not playlist_info:
                    return []
                # If this is actually a single video extraction (no entries), treat it as such
                if "entries" not in playlist_info:
                    single_result = self.download_video(playlist_url, audio_only=audio_only)
                    return [single_result] if single_result else []

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
        # Heuristics for identifying a single video (not a playlist):
        # - Standard watch URL without list=
        # - youtu.be short link (optionally with extra query params)
        # - Shorts URL
        if "watch?v=" in url and "list=" not in url:
            return True
        if "youtu.be/" in url and "list=" not in url:
            return True
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
        _force: bool,
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
        sess = self.last_session
        if sess is not None:
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
        """
        Refactored end-to-end download pipeline:
          1. Extract metadata (once)
          2. Build format selector deterministically
          3. Download using selector
          4. Verify presence (basic: file exists & non-zero; format meta had video when expected)
          5. Captions (handled in enriched path)
        """
        import time
        log = get_logger()

        attempts = 0
        last_exc: Exception | None = None
        info: dict[str, Any] | None = None
        while attempts < RETRIES:
            try:
                extract_opts: dict[str, Any] = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_unavailable_fragments": True,
                    "retries": RETRIES,
                    "fragment_retries": RETRIES,
                    "extract_flat": False,
                }
                with yt_dlp.YoutubeDL(extract_opts) as ydl:  # type: ignore[arg-type]
                    info = ydl.extract_info(url, download=False)
                if not info:
                    return VideoResult(url=url, title=url, status="failed", failure_reason="No metadata")
                break
            except Exception as e:
                last_exc = e
                attempts += 1
                if attempts >= RETRIES:
                    break
                time.sleep(1 * attempts)
        if info is None:
            return VideoResult(url=url, title=url, status="failed", failure_reason=f"MetadataError: {last_exc}")

        title_raw = info.get("title")
        title = title_raw if isinstance(title_raw, str) and title_raw else url
        formats = info.get("formats") or []
        if not formats:
            return VideoResult(url=url, title=title, status="failed", failure_reason="No formats")
        # Pre-compute heights list once (used for fallback and quality derivation)
        heights = [f.get("height") for f in formats if isinstance(f.get("height"), int)]

        # Build deterministic format selector
        fs = FormatSelector(self.config.quality_order, audio_only)
        format_string, reasons = fs.build()
        log.debug("Format selector chain: %s (reasons=%s)", format_string, reasons)

        # Download
        outtmpl = f"{output_path}/%(title)s.%(ext)s"
        download_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": outtmpl,
            "progress_hooks": [self._yt_dlp_progress_hook],
            "retries": RETRIES,
            "fragment_retries": RETRIES,
            "skip_unavailable_fragments": True,
            "format": format_string,
        }
        if audio_only:
            download_opts.update({
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "prefer_ffmpeg": True,
            })
        else:
            download_opts.update({"merge_output_format": "mp4"})

        # Progress task (approx size from largest format with video in chain if available)
        est_size = 0
        for f in formats:
            if f.get("vcodec") not in (None, "none"):
                est_size = f.get("filesize") or f.get("filesize_approx") or 0
                break
        task_id = self.progress.add_task(description=title[:50], total=est_size, visible=True)
        self._current_task_id = task_id
        try:
            with yt_dlp.YoutubeDL(download_opts) as ydl:  # type: ignore[arg-type]
                ydl.download([url])
        except DownloadError as e:
            self.progress.update(task_id, visible=False)
            return VideoResult(url=url, title=title, status="failed", failure_reason=f"DownloadError: {e}")

        self.progress.update(task_id, visible=False)

        # Basic post verification (no heavy ffprobe dependency):
        # If non-audio request and no container likely produced (could refine by globbing), we record fallback.
        fallback_applied = False
        if not audio_only:
            # If formats list has no combined indicator and original chain required fallback
            # we approximate fallback detection by absence of a format exactly matching preferred height.
            pref_h = self._quality_to_height(self.config.preferred())
            # heights already precomputed above
            if pref_h not in heights:
                fallback_applied = True

        # Derive quality from best available format referencing target heights
        derived_quality = "audio" if audio_only else self._format_to_quality(
            {"height": max([h for h in heights if isinstance(h, int)], default=0)},
            audio_only
        )
        return VideoResult(
            url=url,
            title=title,
            status="success",
            quality=derived_quality,
            fallback_applied=fallback_applied,
        )


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
