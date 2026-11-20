"""Remove duplicate/near-identical clip windows."""
from __future__ import annotations

from .clip_boundaries import ClipBoundary


def remove_duplicates(clips: list[ClipBoundary], tolerance: float = 1.5) -> list[ClipBoundary]:
    """Drop clips whose start and end are both within ``tolerance`` of a kept clip."""
    kept: list[ClipBoundary] = []
    for c in sorted(clips, key=lambda x: (x.start, -x.duration)):
        if any(abs(c.start - k.start) <= tolerance and
               abs(c.end - k.end) <= tolerance for k in kept):
            continue
        kept.append(c)
    return kept
