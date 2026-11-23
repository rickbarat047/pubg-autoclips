"""Rank, filter and de-duplicate scored events."""
from __future__ import annotations

from .event_scorer import ScoredEvent

# Higher priority wins when two detections land within the de-dup gap. A
# confirmed elimination must never be evicted by a generic audio COMBAT window
# simply because the audio event scored a fraction higher.
_PRIORITY: dict[str, int] = {
    "MULTI_KILL": 7,
    "CLUTCH_CANDIDATE": 7,
    "KILL": 6,
    "KNOCK": 5,
    "KNOCK_CANDIDATE": 4,
    "LONG_RANGE_CANDIDATE": 3,
    "FUNNY_CANDIDATE": 3,
    "COMBAT": 2,
    "UNKNOWN": 0,
}


def _priority(event: ScoredEvent) -> int:
    return _PRIORITY.get(getattr(event, "category", ""), 0)


def rank_events(events: list[ScoredEvent], min_score: float = 0.0,
                max_events: int | None = None,
                min_gap_sec: float = 0.8) -> list[ScoredEvent]:
    """Sort by evidence priority then score, drop close duplicates.

    The gap is deliberately small: distinct eliminations can occur within a
    couple of seconds and must survive ranking. When events do collide, the
    one with the stronger *category* wins — a KILL or KNOCK is more valuable
    than a COMBAT window even if the latter has a slightly higher score.
    """
    ordered = sorted(events, key=lambda e: (-_priority(e), -e.score, e.timestamp))
    kept: list[ScoredEvent] = []
    for e in ordered:
        if e.score < min_score:
            continue
        if any(abs(e.timestamp - k.timestamp) < min_gap_sec for k in kept):
            continue
        kept.append(e)
        if max_events and len(kept) >= max_events:
            break
    return sorted(kept, key=lambda e: e.timestamp)
