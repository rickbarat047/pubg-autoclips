"""Rank, filter and de-duplicate scored events."""
from __future__ import annotations

from .event_scorer import ScoredEvent


def rank_events(events: list[ScoredEvent], min_score: float = 0.0,
                max_events: int | None = None,
                min_gap_sec: float = 0.8) -> list[ScoredEvent]:
    """Sort by score descending, drop exact duplicates and low scores.

    The gap is deliberately small: distinct eliminations can occur within a
    couple of seconds and must survive ranking.
    """
    ordered = sorted(events, key=lambda e: (-e.score, e.timestamp))
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
