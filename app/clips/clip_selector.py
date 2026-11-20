"""Select clip candidates from ranked highlights."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import AppSettings
from ..detection.scoring.event_scorer import ScoredEvent
from .clip_boundaries import ClipBoundary, make_boundary
from .clip_merger import merge_overlaps
from .duplicate_remover import remove_duplicates


@dataclass
class ClipCandidate:
    start: float
    end: float
    score: float
    category: str
    event: ScoredEvent
    merged_events: int = 1

    @property
    def duration(self) -> float:
        return self.end - self.start


class ClipSelector:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def select(self, events: list[ScoredEvent], video_duration: float) -> list[ClipCandidate]:
        cfg = self.settings.clips
        # Filter by sensitivity-derived score threshold.
        threshold = self.settings.scoring.min_event_score
        threshold = max(0.0, threshold - cfg.sensitivity * 15.0)
        eligible = [e for e in events if e.score >= threshold]
        eligible.sort(key=lambda e: e.timestamp)

        raw: list[tuple[ClipBoundary, ScoredEvent]] = []
        for e in eligible:
            b = make_boundary(e.timestamp, video_duration, cfg.pre_event_sec,
                              cfg.post_event_sec, cfg.min_duration_sec,
                              cfg.max_duration_sec)
            raw.append((b, e))

        boundaries = [b for b, _ in raw]
        merged = merge_overlaps(boundaries, gap=cfg.merge_gap_sec)
        merged = remove_duplicates(merged)

        candidates: list[ClipCandidate] = []
        for mb in merged:
            contributors = [e for b, e in raw
                            if b.start < mb.end and b.end > mb.start]
            if not contributors:
                continue
            lead = max(contributors, key=lambda e: e.score)
            candidates.append(ClipCandidate(
                start=mb.start, end=mb.end, score=round(lead.score +
                                                        (len(contributors) - 1) * 2.0, 2),
                category=lead.category, event=lead,
                merged_events=len(contributors),
            ))
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:cfg.max_clips_per_match]
