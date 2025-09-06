from __future__ import annotations

from typing import List, Dict, Any
from .models import VideoItem


class PlannedVideo:
    def __init__(self, video: VideoItem):
        self.video = video
        self.estimated_size = video.size_bytes
        self.fallback = video.fallback_applied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.video.index,
            "videoId": self.video.video_id,
            "title": self.video.title,
            "preferredQuality": self.video.preferred_quality,
            "selectedQuality": self.video.selected_quality,
            "fallback": self.fallback,
            "estimatedSize": self.estimated_size,
        }


def plan_playlist(videos: List[VideoItem]):
    return [PlannedVideo(v) for v in videos]


__all__ = ["PlannedVideo", "plan_playlist"]
