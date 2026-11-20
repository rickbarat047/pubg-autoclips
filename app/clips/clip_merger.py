"""Merge overlapping or adjacent clip boundaries."""
from __future__ import annotations

from .clip_boundaries import ClipBoundary


def merge_overlaps(clips: list[ClipBoundary], gap: float = 0.0) -> list[ClipBoundary]:
    """Merge clips that overlap or are separated by at most ``gap`` seconds."""
    if not clips:
        return []
    ordered = sorted(clips, key=lambda c: c.start)
    merged: list[ClipBoundary] = [ClipBoundary(ordered[0].start, ordered[0].end)]
    for c in ordered[1:]:
        last = merged[-1]
        if c.start <= last.end + gap:
            last.end = max(last.end, c.end)
        else:
            merged.append(ClipBoundary(c.start, c.end))
    return merged
