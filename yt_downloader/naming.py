from __future__ import annotations

import re
import datetime as _dt
from .models import VideoItem
from typing import Any, Dict

SAFE_SUB = "_"
INVALID_CHARS = re.compile(r"[\\/:*?\"<>|]+")

ALLOWED_TOKENS = {"index", "title", "quality", "video_id", "date", "audio_only"}


class UnknownTokenWarning(UserWarning):
    pass


def sanitize_filename(name: str) -> str:
    name = INVALID_CHARS.sub(SAFE_SUB, name)
    # Preserve a single trailing period if intentional while trimming whitespace
    orig = name
    name = name.strip()
    if name.endswith(". "):
        name = name[:-2] + "."
    # If result becomes empty or only dots, fallback
    stripped = name.strip(".")
    if not stripped:
        name = "untitled"
    return name[:255]


def expand_template(
    template: str, video: VideoItem, date: _dt.date | None = None
) -> str:
    date = date or _dt.date.today()
    mapping: Dict[str, Any] = {
        "index": video.index,
        "title": video.title,
        "quality": video.selected_quality or video.preferred_quality,
        "video_id": video.video_id,
        "date": date.isoformat(),
        "audio_only": str(video.audio_only).lower(),
    }
    # Detect unknown tokens
    for match in re.findall(r"{([^{}]+)}", template):
        token = match.split(":", 1)[0]
        if token not in ALLOWED_TOKENS:
            import warnings

            warnings.warn(f"Unknown filename token '{token}'", UnknownTokenWarning)
    try:
        rendered = template.format(**mapping)
    except KeyError as e:  # should be prevented by detection
        token = str(e).strip("'")
        rendered = template.replace(f"{{{token}}}", "")
    return sanitize_filename(rendered)


__all__ = ["expand_template", "sanitize_filename", "UnknownTokenWarning"]
