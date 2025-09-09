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

    captions are pulled via yt-dlp's subtitles extraction (if present). Auto captions
    fallback uses youtube-transcript-api which hits YouTube transcript endpoints.
    """

    def __init__(self, output_dir: Path, languages: Optional[List[str]] = None):
        self.output_dir = output_dir
        self.languages = languages or ["en"]

    def fetch_manual(self, video: VideoItem) -> Optional[CaptionTrack]:
        """Fetch manual captions using yt-dlp."""
        try:
            import yt_dlp
            import urllib.request

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "writesubtitles": False,  # Don't write files, just extract info
                "writeautomaticsub": False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video.video_id}", download=False
                )

                if not info or "subtitles" not in info:
                    return None

                # Try preferred languages in order
                for lang in self.languages:
                    if lang in info["subtitles"]:
                        subtitle_entries = info["subtitles"][lang]
                        # Find the best subtitle format (prefer vtt or srt)
                        best_sub = None
                        for sub in subtitle_entries:
                            if sub.get("ext") in ["vtt", "srt"]:
                                best_sub = sub
                                break

                        if not best_sub and subtitle_entries:
                            best_sub = subtitle_entries[
                                0
                            ]  # fallback to first available

                        if best_sub:
                            # Download the subtitle content using urllib instead of private _opener
                            with urllib.request.urlopen(best_sub["url"]) as response:
                                sub_content = response.read().decode("utf-8")

                            # Convert to SRT if needed
                            if best_sub.get("ext") == "vtt":
                                sub_content = self._vtt_to_srt(sub_content)

                            path = self._write_caption(
                                video.video_id, lang, "manual", sub_content
                            )
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
        if YouTubeTranscriptApi is None:
            return None
        # Attempt languages sequentially
        for lang in self.languages:
            try:
                # Use the modern API pattern: instantiate YouTubeTranscriptApi and call fetch()
                ytt_api = YouTubeTranscriptApi()
                transcript = ytt_api.fetch(video.video_id, languages=[lang])

                # Convert to a basic SRT-like format
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
            except Exception:  # try next language
                continue
        return None

    def obtain(
        self, video: VideoItem, want_manual: bool, want_auto: bool
    ) -> List[CaptionTrack]:
        tracks: List[CaptionTrack] = []
        if want_manual:
            manual = self.fetch_manual(video)
            if manual:
                tracks.append(manual)
        if want_auto and not tracks:  # only fetch auto if no manual present
            auto = self.fetch_auto(video)
            if auto:
                tracks.append(auto)
        return tracks

    # Internal helpers
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
            # Look for timestamp lines (format: 00:00:01.000 --> 00:00:03.000)
            if "-->" in line:
                # Convert VTT timestamps to SRT format (replace . with ,)
                timestamp_line = re.sub(
                    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})", r"\1:\2:\3,\4", line
                )
                srt_lines.append(str(counter))
                srt_lines.append(timestamp_line)

                # Get the subtitle text (next non-empty lines until empty line or next timestamp)
                text_lines = []
                j = i + 1
                while j < len(lines) and lines[j].strip() and "-->" not in lines[j]:
                    text_lines.append(lines[j].strip())
                    j += 1

                if text_lines:
                    srt_lines.extend(text_lines)
                    srt_lines.append("")  # Empty line between subtitles
                    counter += 1

        return "\n".join(srt_lines)


__all__ = ["CaptionsService"]
