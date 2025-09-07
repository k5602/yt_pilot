from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Iterable, Any, TypedDict, Optional
from .models import ManifestEntry, VideoItem

MANIFEST_FILENAME = "manifest.json"


class _ManifestData(TypedDict, total=False):
    playlist_url: Optional[str]
    videos: Dict[str, Dict[str, Any]]


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data: _ManifestData = {"playlist_url": None, "videos": {}}

    @classmethod
    def load(cls, directory: Path) -> "Manifest":
        m = cls(directory / MANIFEST_FILENAME)
        if m.path.exists():
            try:
                m.data = json.loads(m.path.read_text())
            except Exception:
                # Corrupted manifest: start fresh
                m.data = {"playlist_url": None, "videos": {}}  # reset on corruption
        return m

    def set_playlist(self, url: str):
        self.data["playlist_url"] = url

    def update_video(self, video: VideoItem):
        if "videos" not in self.data or self.data["videos"] is None:  # type: ignore[truthy-bool]
            self.data["videos"] = {}
        self.data["videos"][video.video_id] = {  # type: ignore[index]
            "status": video.status,
            "quality": video.selected_quality,
            "fallback": video.fallback_applied,
            "retries": video.retries,
            "filename": video.filename,
        }

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def compute_skips(self, directory: Path) -> set[str]:
        skips = set()
        for vid, meta in self.data.get("videos", {}).items():
            if meta.get("status") == "success":
                fn = meta.get("filename")
                if fn and (directory / fn).exists():
                    skips.add(vid)
        return skips


__all__ = ["Manifest", "MANIFEST_FILENAME"]
