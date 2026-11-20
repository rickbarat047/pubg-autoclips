"""Pure helpers for computing valid clip boundaries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClipBoundary:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def make_boundary(event_time: float, video_duration: float, pre: float, post: float,
                  min_duration: float, max_duration: float) -> ClipBoundary:
    """Build a clip around an event, respecting min/max duration and media bounds."""
    video_duration = max(0.0, video_duration)
    start = max(0.0, event_time - pre)
    end = min(video_duration, event_time + post)

    # Expand to reach the minimum duration when possible.
    if end - start < min_duration:
        needed = min_duration - (end - start)
        start = max(0.0, start - needed / 2)
        end = min(video_duration, end + needed / 2)
        if end - start < min_duration:
            if start == 0.0:
                end = min(video_duration, min_duration)
            else:
                start = max(0.0, end - min_duration)

    # Clamp to maximum duration, keeping the event inside.
    if end - start > max_duration:
        # Prefer keeping pre-event context, trim the tail.
        end = start + max_duration
        if end > video_duration:
            end = video_duration
            start = max(0.0, end - max_duration)

    start = round(max(0.0, start), 3)
    end = round(min(video_duration, max(start + 1.0, end)), 3)
    return ClipBoundary(start, end)


def clamp_boundary(start: float, end: float, video_duration: float) -> ClipBoundary:
    s = max(0.0, min(start, video_duration))
    e = max(s + 0.5, min(end, video_duration))
    return ClipBoundary(round(s, 3), round(e, 3))
