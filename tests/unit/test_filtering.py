import pytest
from yt_downloader.filtering import parse_index_range, apply_filters
from yt_downloader.models import VideoItem


def mk(idx, title):
    return VideoItem(index=idx, video_id=f"vid{idx}", title=title, preferred_quality="720p")

@pytest.mark.parametrize("spec,start,end", [
    ("1:10",1,10),("5:",5,None),(":7",None,7)
])
def test_parse_index_range_valid(spec,start,end):
    rng = parse_index_range(spec)
    assert rng == (start, end)

@pytest.mark.parametrize("spec", ["bad", "::", "a:1", "1:b"]) 
def test_parse_index_range_invalid(spec):
    with pytest.raises(ValueError):
        parse_index_range(spec)


def test_apply_filters_basic():
    items = [mk(1,"Alpha"), mk(2,"Beta test"), mk(3,"GAMMA"), mk(4,"delta")]
    out = apply_filters(items, ["a"], None)
    assert len(out) == 4  # All contain 'a' case-insensitive


def test_apply_filters_case_insensitive():
    items = [mk(1,"Foo"), mk(2,"bar"), mk(3,"Baz")] 
    out = apply_filters(items, ["BAR"], None)
    assert [v.title for v in out] == ["bar"]


def test_apply_filters_index_range():
    items = [mk(i, f"V{i}") for i in range(1,11)]
    out = apply_filters(items, None, "3:5")
    assert [v.index for v in out] == [3,4,5]
