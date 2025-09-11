from __future__ import annotations

from pathlib import Path
from typing import Optional, List
from .models import VideoItem, CaptionTrack
from .logging_utils import get_logger

try:  # youtube-transcript-api
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled  # type: ignore
except Exception:  # pragma: no cover
    YouTubeTranscriptApi = None  # type: ignore
    TranscriptsDisabled = Exception  # type: ignore


class CaptionsService:
    """Fetch manual and/or auto captions for a video.

    Enhanced strategy:
      1. Attempt yt-dlp native subtitle download (manual captions) with `skip_download`.
         - Uses `writesubtitles=True`, `writeautomaticsub=False`, `subtitleslangs`.
         - If native files appear, normalize naming.
      2. If none produced for requested languages, broaden to ANY available manual subtitle
         if present (language fallback).
      3. If still none AND caller only requested manual (--captions) but not auto,
         fallback automatically to auto captions (graceful upgrade).
      4. Auto captions via youtube-transcript-api.
    """

    def __init__(self, output_dir: Path, languages: Optional[List[str]] = None):
        self.output_dir = output_dir
        self.languages = languages or ["en"]

    # --- Public API -------------------------------------------------
    def fetch_manual(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch manual (human) captions; broaden language search if needed."""
        log = get_logger()
        try:
            import yt_dlp
            import urllib.request

            cap_dir = self.output_dir / "captions"
            cap_dir.mkdir(parents=True, exist_ok=True)

            # Native attempt (skip media, write subtitles only)
            native_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": False,
                "subtitleslangs": self.languages,
                "subtitlesformat": "srt/best",
                "outtmpl": str(cap_dir / "%(id)s"),
            }

            native_written = False
            try:
                with yt_dlp.YoutubeDL(native_opts) as ydl:
                    # extract_info first (metadata), then explicit download to trigger subtitle write
                    ydl.extract_info(
                        f"https://www.youtube.com/watch?v={video.video_id}",
                        download=False,
                    )
                    # Trigger subtitle write without media (skip_download True)
                    ydl.download([f"https://www.youtube.com/watch?v={video.video_id}"])
                    native_written = True
            except Exception:
                native_written = False  # fall through to legacy path

            if native_written:
                # Try requested languages first
                for lang in self.languages:
                    cand = cap_dir / f"{video.video_id}.{lang}.srt"
                    if cand.exists():
                        canonical = cap_dir / f"{video.video_id}.{lang}.manual.srt"
                        if cand != canonical:
                            try:
                                cand.rename(canonical)
                            except OSError:
                                canonical.write_text(cand.read_text(encoding="utf-8"), encoding="utf-8")
                        return CaptionTrack(
                            video_id=video.video_id,
                            language=lang,
                            kind="manual",
                            format="srt",
                            path=str(canonical),
                        )
                # Broader fallback: pick any manual subtitle file if requested languages absent
                for path in cap_dir.glob(f"{video.video_id}.*.srt"):
                    parts = path.name.split(".")
                    if len(parts) >= 3 and parts[-2] != "manual":
                        # path pattern: <id>.<lang>.srt (add manual tag)
                        lang = parts[-2]
                        canonical = cap_dir / f"{video.video_id}.{lang}.manual.srt"
                        if path != canonical:
                            try:
                                path.rename(canonical)
                            except OSError:
                                canonical.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                        log.info("Using fallback manual subtitle language '%s' for video %s", lang, video.video_id)
                        return CaptionTrack(
                            video_id=video.video_id,
                            language=lang,
                            kind="manual",
                            format="srt",
                            path=str(canonical),
                        )

            # Legacy metadata-based retrieval
            legacy_opts = {
                "quiet": True,
                "no_warnings": True,
                "writesubtitles": False,
                "writeautomaticsub": False,
            }

            with yt_dlp.YoutubeDL(legacy_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video.video_id}", download=False
                )
            if not info:
                log.debug("No info returned for manual subtitles (legacy path)")
                return None
            subs = info.get("subtitles") or {}
            if not subs:
                log.debug("No manual subtitles advertised in metadata")
                return None

            # Try requested languages first
            for lang in self.languages:
                if lang not in subs:
                    continue
                track = self._download_subtitle_entry(video, lang, subs[lang])
                if track:
                    return track

            # Broaden to any available language if none matched
            for lang, entries in subs.items():
                track = self._download_subtitle_entry(video, lang, entries)
                if track:
                    log.info("Broadened to available manual subtitle language '%s' for %s", lang, video.video_id)
                    return track

        except Exception as e:  # pragma: no cover
            log.debug("Manual caption fetch failed: %s", e)
            return None
        return None

    def _download_subtitle_entry(self, video: VideoItem, lang: str, entries) -> Optional[CaptionTrack]:
        """Pick best entry (prefer srt/vtt) and store as manual."""
        import urllib.request
        best = None
        for sub in entries:
            if sub.get("ext") in ("srt", "vtt"):
                best = sub
                break
        if not best and entries:
            best = entries[0]
        if not best:
            return None
        with urllib.request.urlopen(best["url"]) as resp:
            content = resp.read().decode("utf-8")
        if best.get("ext") == "vtt":
            content = self._vtt_to_srt(content)
        path = self._write_caption(video.video_id, lang, "manual", content)
        return CaptionTrack(
            video_id=video.video_id,
            language=lang,
            kind="manual",
            format="srt",
            path=str(path),
        )

    def fetch_auto(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch automatic captions using youtube-transcript-api (retains previous logic)."""
        if YouTubeTranscriptApi is None:
            return None
        log = get_logger()
        for lang in self.languages:
            try:
                ytt_api = YouTubeTranscriptApi()
                transcript = ytt_api.fetch(video.video_id, languages=[lang])
                lines = []
                for i, entry in enumerate(transcript, start=1):
                    start = entry.start
                    dur = entry.duration
                    end = start + dur
                    lines.append(str(i))
                    lines.append(f"{self._format_ts(start)} --> {self._format_ts(end)}")
                    lines.append(entry.text)
                    lines.append("")
                content = "\n".join(lines)
                path = self._write_caption(video.video_id, lang, "auto", content)
                return CaptionTrack(
                    video_id=video.video_id,
                    language=lang,
                    kind="auto",
                    format="srt",
                    path=str(path),
                )
            except TranscriptsDisabled:  # pragma: no cover
                log.debug("Transcripts disabled for video %s", video.video_id)
                return None
            except Exception:
                continue
        return None

    def obtain(self, video: VideoItem, want_manual: bool, want_auto: bool) -> List[CaptionTrack]:
        """Obtain captions with graceful auto fallback if only manual requested but missing."""
        tracks: List[CaptionTrack] = []
        manual_obtained = False
        if want_manual:
            manual = self.fetch_manual(video)
            if manual:
                tracks.append(manual)
                manual_obtained = True
        # Implicit auto fallback when only --captions supplied and no manual found
        if not manual_obtained and want_manual and not want_auto:
            auto = self.fetch_auto(video)
            if auto:
                tracks.append(auto)
                return tracks
        if want_auto and not manual_obtained:
            auto = self.fetch_auto(video)
            if auto:
                tracks.append(auto)
        return tracks

    # --- Internal helpers -------------------------------------------
    def _write_caption(self, video_id: str, lang: str, kind: str, content: str) -> Path:
        cap_dir = self.output_dir / "captions"
        cap_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{video_id}.{lang}.{kind}.srt"
        path = cap_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def _format_ts(self, seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    def _vtt_to_srt(self, vtt_content: str) -> str:
        """Convert WebVTT format to SRT format."""
        import re
        lines = vtt_content.split("\n")
        srt_lines = []
        counter = 1
        for i, line in enumerate(lines):
            if "-->" in line:
                timestamp_line = re.sub(
                    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})", r"\1:\2:\3,\4", line
                )
                srt_lines.append(str(counter))
                srt_lines.append(timestamp_line)
                text_lines = []
                j = i + 1
                while j < len(lines) and lines[j].strip() and "-->" not in lines[j]:
                    text_lines.append(lines[j].strip())
                    j += 1
                if text_lines:
                    srt_lines.extend(text_lines)
                    srt_lines.append("")
                    counter += 1
        return "\n".join(srt_lines)


__all__ = ["CaptionsService"]
