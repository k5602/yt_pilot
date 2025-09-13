from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

# Core data models aligned with data-model.md


@dataclass
class CaptionTrack:
    video_id: str
    language: str
    kind: str  # manual | auto
    format: str  # vtt | raw
    path: str


@dataclass
class VideoItem:
    index: int
    video_id: str
    title: str
    preferred_quality: str
    selected_quality: Optional[str] = None
    available_qualities: List[str] = field(default_factory=list)
    audio_only: bool = False
    status: str = "pending"  # pending|success|failed|skipped
    failure_reason: Optional[str] = None
    fallback_applied: bool = False
    retries: int = 0
    size_bytes: Optional[int] = None
    duration: Optional[float] = None
    resolution: Optional[str] = None
    filepath: Optional[str] = None
    captions: List[CaptionTrack] = field(default_factory=list)
    filename: Optional[str] = None


@dataclass
class ManifestEntry:
    video_id: str
    status: str
    quality: Optional[str]
    fallback: bool
    retries: int
    filename: Optional[str]
    updated: datetime


@dataclass
class PluginResult:
    name: str
    status: str  # success|failed
    error: Optional[str] = None


@dataclass
class PlaylistSession:
    playlist_url: str
    session_id: str
    started: datetime
    ended: Optional[datetime] = None
    quality_order: List[str] = field(default_factory=list)
    audio_only: bool = False
    counts: Dict[str, int] = field(
        default_factory=lambda: {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "fallbacks": 0,
        }
    )
    videos: List[VideoItem] = field(default_factory=list)
    plugin_results: List[PluginResult] = field(default_factory=list)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportSummary:
    session_id: str
    playlist_url: str
    started: datetime
    ended: datetime
    counts: Dict[str, int]
    failures: List[Dict[str, str]]
    fallbacks: List[Dict[str, str]]
    videos: List[Dict[str, Any]]


__all__ = [
    "CaptionTrack",
    "VideoItem",
    "ManifestEntry",
    "PluginResult",
    "PlaylistSession",
    "ReportSummary",
]
