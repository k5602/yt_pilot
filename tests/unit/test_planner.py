from yt_downloader.planner import plan_playlist
from yt_downloader.models import VideoItem


def test_plan_playlist_basic():
    vids = [
        VideoItem(index=i, video_id=f"v{i}", title=f"T{i}", preferred_quality="720p")
        for i in range(1, 4)
    ]
    out = plan_playlist(vids)
    assert len(out) == 3
    d0 = out[0].to_dict()
    assert d0["index"] == 1 and d0["videoId"] == "v1"
