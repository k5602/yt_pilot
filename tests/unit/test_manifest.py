import json
from pathlib import Path
from yt_downloader.manifest import Manifest
from yt_downloader.models import VideoItem


def make_video(vid, status="success", fname="file.mp4"):
    v = VideoItem(index=1, video_id=vid, title="T", preferred_quality="720p")
    v.status = status
    v.filename = fname
    return v


def test_manifest_load_corrupted(tmp_path: Path):
    d = tmp_path
    (d / "manifest.json").write_text("not json")
    m = Manifest.load(d)
    assert m.data.get("videos", {}) == {}


def test_manifest_update_and_save(tmp_path: Path):
    m = Manifest.load(tmp_path)
    v = make_video("abc")
    m.update_video(v)
    m.save()
    loaded = json.loads((tmp_path / "manifest.json").read_text())
    assert "abc" in loaded["videos"]
    assert loaded["videos"]["abc"]["status"] == "success"


def test_manifest_compute_skips(tmp_path: Path):
    # create file to represent downloaded
    (tmp_path / "file.mp4").write_text("x")
    m = Manifest.load(tmp_path)
    v = make_video("abc")
    m.update_video(v)
    m.save()
    skips = m.compute_skips(tmp_path)
    assert "abc" in skips


def test_manifest_compute_skips_missing_file(tmp_path: Path):
    m = Manifest.load(tmp_path)
    v = make_video("abc")
    m.update_video(v)
    m.save()
    skips = m.compute_skips(tmp_path)
    assert "abc" not in skips
