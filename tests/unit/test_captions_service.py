from pathlib import Path
from yt_downloader.captions import CaptionsService
from yt_downloader.models import VideoItem, CaptionTrack

class DummyCap(CaptionsService):
    def __init__(self, manual=True, auto=True):
        super().__init__(Path("."))
        self._manual = manual
        self._auto = auto
    def fetch_manual(self, video: VideoItem):
        if self._manual:
            return CaptionTrack(video_id=video.video_id, language="en", kind="manual", format="srt", path="m.srt")
        return None
    def fetch_auto(self, video: VideoItem):
        if self._auto:
            return CaptionTrack(video_id=video.video_id, language="en", kind="auto", format="srt", path="a.srt")
        return None

def make_video():
    return VideoItem(index=1, video_id="vid", title="T", preferred_quality="720p")

def test_obtain_manual_preferred():
    svc = DummyCap(manual=True, auto=True)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks and tracks[0].kind == "manual"

def test_obtain_auto_when_no_manual():
    svc = DummyCap(manual=False, auto=True)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks and tracks[0].kind == "auto"

def test_obtain_none():
    svc = DummyCap(manual=False, auto=False)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks == []
