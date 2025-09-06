from datetime import datetime
from yt_downloader.reporting import build_session_report
from yt_downloader.models import PlaylistSession, VideoItem


def make_session():
    s = PlaylistSession(
        playlist_url="pl",
        session_id="sid",
        started=datetime.utcnow(),
        quality_order=["720p", "480p"],
        audio_only=False,
        config_snapshot={},
    )
    v1 = VideoItem(index=1, video_id="v1", title="A", preferred_quality="720p")
    v1.status = "success"
    v1.selected_quality = "720p"
    v2 = VideoItem(index=2, video_id="v2", title="B", preferred_quality="720p")
    v2.status = "failed"
    v2.failure_reason = "No stream"
    v3 = VideoItem(index=3, video_id="v3", title="C", preferred_quality="720p")
    v3.status = "success"
    v3.selected_quality = "480p"
    v3.fallback_applied = True
    s.videos.extend([v1, v2, v3])
    return s


def test_build_session_report_shape():
    s = make_session()
    rep = build_session_report(s)
    for key in [
        "schemaVersion",
        "playlistUrl",
        "sessionId",
        "started",
        "ended",
        "qualityOrder",
        "videos",
    ]:
        assert key in rep
    # failures and fallbacks lists
    assert len(rep["failures"]) == 1
    assert rep["failures"][0]["videoId"] == "v2"
    assert len(rep["fallbacks"]) == 1
    assert rep["fallbacks"][0]["videoId"] == "v3"
