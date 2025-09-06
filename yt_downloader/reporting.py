from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from .models import PlaylistSession, VideoItem

REPORT_FILENAME = "report.json"
SCHEMA_VERSION = "1.0.0"


def _video_summary(v: VideoItem) -> Dict[str, Any]:
    return {
        "videoId": v.video_id,
        "title": v.title,
        "status": v.status,
        "quality": v.selected_quality,
        "fallback": v.fallback_applied,
        "retries": v.retries,
        "sizeBytes": v.size_bytes,
    }


def build_session_report(session: PlaylistSession) -> Dict[str, Any]:
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
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "playlistUrl": session.playlist_url,
        "sessionId": session.session_id,
        "started": session.started.isoformat(),
        "ended": ended.isoformat(),
        "qualityOrder": session.quality_order,
        "configSnapshot": session.config_snapshot,
        "counts": session.counts,
        "failures": failures,
        "fallbacks": fallbacks,
        "videos": [_video_summary(v) for v in session.videos],
    }
    return report


def write_report(session: PlaylistSession, output_dir: Path) -> Path:
    report = build_session_report(session)
    path = output_dir / REPORT_FILENAME
    path.write_text(json.dumps(report, indent=2))
    return path


__all__ = ["build_session_report", "write_report", "REPORT_FILENAME", "SCHEMA_VERSION"]
