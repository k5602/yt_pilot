from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .models import PlaylistSession, VideoItem

REPORT_FILENAME = "report.json"
SCHEMA_VERSION = "1.1.0"


@dataclass
class Report:
    schema_version: str
    playlist_url: str
    session_id: str
    started: str
    ended: str
    quality_order: List[str]
    config_snapshot: Dict[str, Any]
    counts: Dict[str, int]
    failures: List[Dict[str, Any]]
    fallbacks: List[Dict[str, Any]]
    videos: List[Dict[str, Any]]

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)

    def save(self, output_dir: Path) -> Path:
        path = output_dir / REPORT_FILENAME
        path.write_text(self.to_json())
        return path


def _video_summary(v: VideoItem) -> Dict[str, Any]:
    return {
        "videoId": v.video_id,
        "title": v.title,
        "status": v.status,
        "quality": v.selected_quality,
        "fallback": v.fallback_applied,
        "retries": v.retries,
        "sizeBytes": v.size_bytes,
        "duration": v.duration,
        "resolution": v.resolution,
        "filepath": v.filepath,
        "captions": [asdict(c) for c in v.captions],
    }


def build_session_report(session: PlaylistSession) -> Report:
    ended = session.ended or datetime.utcnow()
    failures = [
        {"videoId": v.video_id, "reason": v.failure_reason or "unknown"}
        for v in session.videos
        if v.status == "failed"
    ]
    fallbacks = [
        {"videoId": v.video_id, "from": v.preferred_quality, "to": v.selected_quality}
        for v in session.videos
        if v.fallback_applied
    ]
    return Report(
        schema_version=SCHEMA_VERSION,
        playlist_url=session.playlist_url,
        session_id=session.session_id,
        started=session.started.isoformat(),
        ended=ended.isoformat(),
        quality_order=session.quality_order,
        config_snapshot=session.config_snapshot,
        counts=session.counts,
        failures=failures,
        fallbacks=fallbacks,
        videos=[_video_summary(v) for v in session.videos],
    )


def write_report(session: PlaylistSession, output_dir: Path) -> Path:
    report = build_session_report(session)
    return report.save(output_dir)


__all__ = [
    "build_session_report",
    "write_report",
    "Report",
    "REPORT_FILENAME",
    "SCHEMA_VERSION",
]
