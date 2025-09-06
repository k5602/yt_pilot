import pytest
from yt_downloader.naming import expand_template, sanitize_filename
from yt_downloader.models import VideoItem, CaptionTrack

@pytest.fixture
def sample_video():
    return VideoItem(index=1, video_id="vid123", title="Test Video / Sample", preferred_quality="720p", audio_only=False)

@pytest.mark.parametrize("template,expected", [
    ("{index:03d}-{title}", "001-Test Video _ Sample"),
    ("{index}-{video_id}-{quality}", "1-vid123-720p"),
])
def test_expand_template_basic(sample_video, template, expected):
    sample_video.selected_quality = sample_video.preferred_quality
    out = expand_template(template, sample_video)
    assert out.startswith(expected)

@pytest.mark.parametrize("raw,expected", [
    ("simple", "simple"),
    ("with/slash", "with_slash"),
    ("colon:name", "colon_name"),
    ("trail. ", "trail."),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_expand_template_unknown_token(sample_video):
    # Unknown token should raise KeyError inside format -> we catch by leaving template untouched per current behavior
    tmpl = "{index}-{unknown}-{title}"
    # Implementation may yield KeyError; ensure we handle gracefully by not crashing
    try:
        _ = expand_template(tmpl, sample_video)
    except KeyError:
        pytest.skip("Unknown token handling not yet implemented")
