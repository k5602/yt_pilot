from __future__ import annotations

from pathlib import Path
from typing import Optional, List
from .models import VideoItem, CaptionTrack

try:  # optional import safety
    from pytube import YouTube  # type: ignore
except Exception:  # pragma: no cover
    YouTube = None  # type: ignore

try:  # youtube-transcript-api
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled  # type: ignore
except Exception:  # pragma: no cover
    YouTubeTranscriptApi = None  # type: ignore
    TranscriptsDisabled = Exception  # type: ignore


class CaptionsService:
    """Fetch manual and/or auto captions for a video.

    Manual captions are pulled via pytube's captions (if present). Auto captions
    fallback uses youtube-transcript-api which hits YouTube transcript endpoints.
    """

    def __init__(self, output_dir: Path, languages: Optional[List[str]] = None):
        self.output_dir = output_dir
        self.languages = languages or ["en"]

    def fetch_manual(self, video: VideoItem) -> Optional[CaptionTrack]:
        if YouTube is None:  # dependency missing
            return None
        try:
            yt = YouTube(f"https://www.youtube.com/watch?v={video.video_id}")
            if not yt.captions:
                return None
            # try preferred languages ordered
            for lang in self.languages:
                caption = yt.captions.get_by_language_code(lang)
                if caption:
                    srt = caption.generate_srt_captions()
                    path = self._write_caption(video.video_id, lang, "manual", srt)
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
                transcript = YouTubeTranscriptApi.get_transcript(
                    video.video_id, languages=[lang]
                )
                # Convert to a basic SRT-like format
                lines = []
                for i, entry in enumerate(transcript, start=1):
                    start = entry["start"]
                    dur = entry.get("duration", 0)
                    end = start + dur
                    lines.append(str(i))
                    lines.append(f"{self._format_ts(start)} --> {self._format_ts(end)}")
                    lines.append(entry["text"])
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


__all__ = ["CaptionsService"]
