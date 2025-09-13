from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Optional, List, Any
from yt_dlp.utils import sanitize_filename
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

    # --- Helpers (naming / language canonicalization) ----------------
    def _caption_base_name(self, video: VideoItem) -> str:
        """
        Determine the base filename (without extension) for captions so that it
        matches the actual media filename:
          - If playlist logic assigned video.filename (templated), use its stem.
          - Otherwise fall back to sanitized video.title (single video mode).
        """
        if getattr(video, "filename", None):
            return sanitize_filename(Path(video.filename).stem)
        return sanitize_filename(video.title)

    def _canonical_lang(self, lang: str) -> str:
        """
        Canonicalize language codes:
          - en-US / en-GB -> en
          - keep regional for pt-BR
          - collapse other forms to primary subtag.
        """
        if not lang:
            return "en"
        l = lang.lower()
        overrides = {
            "en-us": "en",
            "en-gb": "en",
            "pt-br": "pt-BR",
        }
        if l in overrides:
            return overrides[l]
        if "-" in l:
            return l.split("-")[0]
        return l

    # --- Public API -------------------------------------------------
    def fetch_manual(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch manual (human) captions; broaden language search if needed."""
        log = get_logger()
        try:
            import yt_dlp

            # Store alongside video file (no separate captions directory)
            base_dir = self.output_dir
            base_name = self._caption_base_name(video)

            # Native attempt (skip media, write subtitles only)
            native_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": False,
                "subtitleslangs": self.languages,
                "subtitlesformat": "srt/best",
                "outtmpl": str(base_dir / "%(id)s"),
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
                    log.info("Native subtitles written for video %s", video.video_id)
            except Exception:
                native_written = False  # fall through to legacy path
                log.info("Native subtitles not written for video %s", video.video_id)

            if native_written:
                # Try requested languages first
                for lang in self.languages:
                    cand = base_dir / f"{video.video_id}.{lang}.srt"
                    if cand.exists():
                        lang_c = self._canonical_lang(lang)
                        canonical = base_dir / f"{base_name}.{lang_c}.manual.srt"
                        if cand != canonical:
                            try:
                                cand.rename(canonical)
                            except OSError:
                                canonical.write_text(
                                    cand.read_text(encoding="utf-8"), encoding="utf-8"
                                )
                        log.info("Native subtitle file found: %s", canonical)
                        return CaptionTrack(
                            video_id=video.video_id,
                            language=lang,
                            kind="manual",
                            format="srt",
                            path=str(canonical),
                        )
                # Broader fallback: pick any manual subtitle file if requested languages absent
                for path in base_dir.glob(f"{video.video_id}.*.srt"):
                    parts = path.name.split(".")
                    if len(parts) >= 3 and parts[-2] != "manual":
                        # path pattern: <id>.<lang>.srt (add manual tag)
                        raw_lang = parts[-2]
                        lang_c = self._canonical_lang(raw_lang)
                        canonical = base_dir / f"{base_name}.{lang_c}.manual.srt"
                        if path != canonical:
                            try:
                                path.rename(canonical)
                            except OSError:
                                canonical.write_text(
                                    path.read_text(encoding="utf-8"), encoding="utf-8"
                                )
                        log.info(
                            "Using fallback manual subtitle language '%s' for video %s",
                            lang,
                            video.video_id,
                        )
                        log.info("Native subtitle file found: %s", canonical)
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

            with yt_dlp.YoutubeDL(legacy_opts) as ydl:  # type: ignore
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video.video_id}", download=False
                )
            if not info:
                log.info("No info returned for manual subtitles (legacy path) for video %s", video.video_id)
                return None
            subs = info.get("subtitles") or {}
            log.info("Available subtitle languages for video %s: %s", video.video_id, list(subs.keys()) if subs else "None")
            if not subs:
                log.info("No manual subtitles advertised in metadata for video %s", video.video_id)
                return None

            # Try requested languages first
            for lang in self.languages:
                if lang not in subs:
                    log.info("Requested language %s not available for video %s", lang, video.video_id)
                    continue
                track = self._download_subtitle_entry(video, lang, subs[lang])
                if track:
                    log.info("Manual subtitle found and downloaded for lang %s", lang)
                    return track

            # Broaden to any available language if none matched
            for lang, entries in subs.items():
                log.info("Trying broadened language %s for video %s", lang, video.video_id)
                track = self._download_subtitle_entry(video, lang, entries)
                if track:
                    log.info(
                        "Broadened to available manual subtitle language '%s' for %s",
                        lang,
                        video.video_id,
                    )
                    return track

        except Exception as e:  # pragma: no cover
            log.debug("Manual caption fetch failed: %s", e)
            return None
        return None

    def _download_subtitle_entry(
        self, video: VideoItem, lang: str, entries, kind: str = "manual"
    ) -> Optional[CaptionTrack]:
        """Pick best entry (prefer srt/vtt) and store as caption of given kind (manual/auto)."""
        log = get_logger()
        log.info("Downloading subtitle entry for video %s lang %s (kind=%s)", video.video_id, lang, kind)
        best = None
        for sub in entries:
            if sub.get("ext") in ("srt", "vtt"):
                best = sub
                break
        if not best and entries:
            best = entries[0]
        if not best:
            return None
        try:
            with urllib.request.urlopen(best["url"]) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            log.error("Failed to download subtitle from %s for video %s: %s", best.get("url"), video.video_id, e)
            return None
        if best.get("ext") == "vtt":
            content = self._vtt_to_srt(content)
        base_name = self._caption_base_name(video)
        lang_c = self._canonical_lang(lang)
        path = self._write_caption(base_name, lang_c, kind, content)
        log.info("Subtitle file written: %s", path)
        return CaptionTrack(
            video_id=video.video_id,
            language=lang_c,
            kind=kind,
            format="srt",
            path=str(path),
        )

    def fetch_auto(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch auto captions via:
           1. yt-dlp automatic_captions metadata
           2. youtube-transcript-api (if available)
        """
        log = get_logger()
        log.info("Fetching auto captions for video %s", video.video_id)
        # --- Step 1: yt-dlp automatic_captions field
        try:
            import yt_dlp  # local import
            extract_opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "skip_unavailable_fragments": True,
                "extract_flat": False,
            }
            with yt_dlp.YoutubeDL(extract_opts) as ydl:  # type: ignore
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video.video_id}",
                    download=False,
                )
            if info:
                auto_map = info.get("automatic_captions") or {}
                log.info(
                    "Available automatic caption languages for video %s: %s",
                    video.video_id,
                    list(auto_map.keys()) if auto_map else "None",
                )
                search_langs = list(dict.fromkeys(self.languages + ["en"]))  # preserve order, ensure 'en' fallback
                for lang in search_langs:
                    if lang in auto_map:
                        log.info("Trying yt-dlp automatic captions lang=%s for %s", lang, video.video_id)
                        track = self._download_subtitle_entry(
                            video, lang, auto_map[lang], kind="auto"
                        )
                        if track:
                            log.info("Auto subtitle (yt-dlp) obtained for lang %s", lang)
                            return track
            else:
                log.info("No info object from yt-dlp for auto captions %s", video.video_id)
        except Exception as e:
            log.info("yt-dlp automatic caption phase failed for %s: %s", video.video_id, e)
        # --- Step 2: youtube-transcript-api fallback
        if YouTubeTranscriptApi is not None:
            try:
                # Build language preference list with fallback to English
                search_langs = list(dict.fromkeys(self.languages + ["en"]))
                for lang in search_langs:
                    log.info("Attempting youtube-transcript-api for %s lang=%s", video.video_id, lang)
                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(video.video_id, languages=[lang])  # type: ignore
                    except TranscriptsDisabled:  # type: ignore
                        log.info("Transcripts disabled for %s", video.video_id)
                        return None
                    except Exception:
                        continue
                    if transcript:
                        # Build SRT content
                        lines = []
                        for idx, seg in enumerate(transcript, start=1):
                            start = float(seg.get("start", 0.0))
                            end = start + float(seg.get("duration", 0.0))
                            lines.append(str(idx))
                            lines.append(f"{self._format_ts(start)} --> {self._format_ts(end)}")
                            text = seg.get("text", "").replace("\n", " ").strip()
                            if not text:
                                text = "[NO TEXT]"
                            lines.append(text)
                            lines.append("")
                        content = "\n".join(lines)
                        base_name = self._caption_base_name(video)
                        lang_c = self._canonical_lang(lang)
                        path = self._write_caption(base_name, lang_c, "auto", content)
                        log.info("Auto caption (transcript-api) written: %s", path)
                        return CaptionTrack(
                            video_id=video.video_id,
                            language=lang_c,
                            kind="auto",
                            format="srt",
                            path=str(path),
                        )
            except Exception as e:
                log.info("youtube-transcript-api fallback failed for %s: %s", video.video_id, e)
        else:
            log.info("youtube-transcript-api not available; skipping fallback auto captions for %s", video.video_id)
        log.info("No auto captions obtainable for video %s", video.video_id)
        return None

    def obtain(
        self, video: VideoItem, want_manual: bool, want_auto: bool
    ) -> List[CaptionTrack]:
        log = get_logger()
        log.info("Obtaining captions for video %s: manual=%s, auto=%s", video.video_id, want_manual, want_auto)
        tracks: List[CaptionTrack] = []
        manual_obtained = False
        if want_manual:
            manual = self.fetch_manual(video)
            if manual:
                tracks.append(manual)
                manual_obtained = True
                log.info("Manual caption obtained for %s", video.video_id)
            else:
                log.info("No manual caption for %s", video.video_id)
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
                log.info("Auto caption obtained for %s", video.video_id)
            else:
                log.info("No auto caption for %s", video.video_id)
        return tracks

    # --- Internal helpers -------------------------------------------
    def _write_caption(self, base_name: str, lang: str, kind: str, content: str) -> Path:
        base_dir = self.output_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{base_name}.{lang}.{kind}.srt"
        path = base_dir / filename
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
