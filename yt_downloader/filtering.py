from __future__ import annotations

from typing import Iterable, List, Tuple
from .models import VideoItem


class IndexRangeError(ValueError):
    pass


def parse_index_range(spec: str | None) -> Tuple[int | None, int | None]:
    if not spec:
        return None, None
    if ":" not in spec:
        raise IndexRangeError("Index range must contain colon")
    start_s, end_s = spec.split(":", 1)
    start = int(start_s) if start_s else None
    end = int(end_s) if end_s else None
    if start is not None and end is not None and end < start:
        raise IndexRangeError("End before start")
    return start, end


def apply_filters(
    videos: List[VideoItem], filters: Iterable[str] | None, index_range: str | None
) -> List[VideoItem]:
    terms = [f.lower() for f in (filters or []) if f.strip()]
    start, end = parse_index_range(index_range)
    out: List[VideoItem] = []
    for v in videos:
        if start is not None and v.index < start:
            continue
        # Treat provided end as inclusive (user-friendly vs python slicing)
        if end is not None and v.index > end:
            continue
        if terms:
            title_l = v.title.lower()
            if not any(t in title_l for t in terms):
                continue
        out.append(v)
    return out


__all__ = ["apply_filters", "parse_index_range", "IndexRangeError"]
