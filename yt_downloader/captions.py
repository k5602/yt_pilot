from __future__ import annotations

from pathlib import Path
from typing import Optional, List
from .models import VideoItem, CaptionTrack

try:  # youtube-transcript-api
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled  # type: ignore
except Exception:  # pragma: no cover
    YouTubeTranscriptApi = None  # type: ignore
    TranscriptsDisabled = Exception  # type: ignore


class CaptionsService:
    """Fetch manual and/or auto captions for a video.

    Strategy (refactored):
      1. Attempt yt-dlp native subtitle download (manual captions only) with `skip_download`.
         - Uses `writesubtitles=True`, `writeautomaticsub=False`, `subtitleslangs`.
         - If yt-dlp writes a subtitle file, normalize it to our naming convention.
      2. If native writing not successful (or file not produced), fallback to legacy logic:
         - Inspect `info["subtitles"]`, pick best (srt/vtt), fetch via urllib, convert if needed.
      3. Auto captions remain powered by youtube-transcript-api (since yt-dlp would require enabling auto writing).
    """

    def __init__(self, output_dir: Path, languages: Optional[List[str]] = None):
        self.output_dir = output_dir
        self.languages = languages or ["en"]

    # --- Public API -------------------------------------------------
    def fetch_manual(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch manual (human) captions using yt-dlp first, then fallback to legacy HTTP fetch."""
        try:
            import yt_dlp
            import urllib.request
            import os

            cap_dir = self.output_dir / "captions"
            cap_dir.mkdir(parents=True, exist_ok=True)

            # 1. Attempt native yt-dlp subtitle download (manual only)
            native_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": False,
                "subtitleslangs": self.languages,
                "subtitlesformat": "srt/best",  # prefer srt if available else best
                # outtmpl ensures subtitle file names are anchored under captions dir
                "outtmpl": str(cap_dir / "%(id)s"),
            }

            try:
                with yt_dlp.YoutubeDL(native_opts) as ydl:
                    info = ydl.extract_info(
                        f"https://www.youtube.com/watch?v={video.video_id}",
                        download=True,  # needed to trigger subtitle writing when skip_download=True
                    )
                # yt-dlp subtitle naming pattern: <base>.<lang>.<ext> (ext already srt per format request)
                for lang in self.languages:
                    candidate = cap_dir / f"{video.video_id}.{lang}.srt"
                    if candidate.exists():
                        # Normalize to our canonical naming (videoid.lang.manual.srt) if different
                        canonical = cap_dir / f"{video.video_id}.{lang}.manual.srt"
                        if candidate != canonical:
                            try:
                                candidate.rename(canonical)
                            except OSError:
                                canonical.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
                        return CaptionTrack(
                            video_id=video.video_id,
                            language=lang,
                            kind="manual",
                            format="srt",
                            path=str(canonical),
                        )
                    # Sometimes different extension if no srt available
                    for ext in ("vtt", "srv3", "srv2", "srv1"):
                        alt = cap_dir / f"{video.video_id}.{lang}.{ext}"
                        if alt.exists():
                            content = alt.read_text(encoding="utf-8")
                            if ext == "vtt":
                                content = self._vtt_to_srt(content)
                            canonical = cap_dir / f"{video.video_id}.{lang}.manual.srt"
                            canonical.write_text(content, encoding="utf-8")
                            return CaptionTrack(
                                video_id=video.video_id,
                                language=lang,
                                kind="manual",
                                format="srt",
                                path=str(canonical),
                            )
            except Exception:  # pragma: no cover - fallback to legacy
                pass

            # 2. Legacy fallback (previous implementation) - manual retrieval via info["subtitles"]
            legacy_opts = {
                "quiet": True,
                "no_warnings": True,
                "writesubtitles": False,  # just metadata
                "writeautomaticsub": False,
            }

            with yt_dlp.YoutubeDL(legacy_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video.video_id}", download=False
                )
                if not info or "subtitles" not in info:
                    return None

                for lang in self.languages:
                    if lang not in info["subtitles"]:
                        continue
                    subtitle_entries = info["subtitles"][lang]
                    # Prefer srt/vtt
                    best_sub = None
                    for sub in subtitle_entries:
                        if sub.get("ext") in ["vtt", "srt"]:
                            best_sub = sub
                            break
                    if not best_sub and subtitle_entries:
                        best_sub = subtitle_entries[0]

                    if not best_sub:
                        continue

                    with urllib.request.urlopen(best_sub["url"]) as response:
                        sub_content = response.read().decode("utf-8")

                    if best_sub.get("ext") == "vtt":
                        sub_content = self._vtt_to_srt(sub_content)

                    path = self._write_caption(video.video_id, lang, "manual", sub_content)
                    return CaptionTrack(
                        video_id=video.video_id,
                        language=lang,
                        kind="manual",
                        format="srt",
                        path=str(path),
                    )

        except Exception:  # pragma: no cover - tolerant
            return None
        return None

    def fetch_auto(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch automatic captions using youtube-transcript-api (retains previous logic)."""
        if YouTubeTranscriptApi is None:
            return None
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
                return None
            except Exception:
                continue
        return None

    def obtain(self, video: VideoItem, want_manual: bool, want_auto: bool) -> List[CaptionTrack]:
        tracks: List[CaptionTrack] = []
        if want_manual:
            manual = self.fetch_manual(video)
            if manual:
                tracks.append(manual)
        if want_auto and not tracks:  # only auto if no manual captured
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
