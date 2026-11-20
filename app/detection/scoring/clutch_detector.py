"""Multi-kill and clutch *candidate* grouping (no fabricated 1vX claims)."""
from __future__ import annotations

from dataclasses import dataclass

from .event_scorer import CATEGORY_CLUTCH, CATEGORY_KILL, CATEGORY_MULTI, ScoredEvent


@dataclass
class GroupingConfig:
    multi_window_sec: float = 12.0
    clutch_window_sec: float = 20.0
    min_clutch_kills: int = 3


def group_multi_kills(events: list[ScoredEvent], cfg: GroupingConfig | None = None
                      ) -> tuple[list[ScoredEvent], int]:
    """Upgrade tightly grouped confirmed kills to MULTI_KILL / CLUTCH_CANDIDATE.

    Returns (events, number_of_groups_found).  Only confirmed KILL events are
    considered.  Clutch candidates are explicitly *candidates* — without
    player-count evidence we never assert "1v3" etc.
    """
    cfg = cfg or GroupingConfig()
    confirmed = sorted(
        [e for e in events if e.category == CATEGORY_KILL and e.confidence >= 0.6],
        key=lambda e: e.timestamp,
    )
    events_by_id = {id(e): e for e in events}
    groups: list[list[ScoredEvent]] = []
    current: list[ScoredEvent] = []
    for e in confirmed:
        if current and e.timestamp - current[0].timestamp > cfg.multi_window_sec:
            groups.append(current)
            current = []
        current.append(e)
    if current:
        groups.append(current)

    promoted = 0
    for group in groups:
        if len(group) < 2:
            continue
        promoted += 1
        lead = group[0]
        if len(group) >= cfg.min_clutch_kills:
            lead.category = CATEGORY_CLUTCH
        else:
            lead.category = CATEGORY_MULTI
        extra = round(len(group) * 1.0, 2)
        lead.score = round(lead.score + extra, 2)
        lead.evidence = {
            **lead.evidence,
            "grouped_kill_timestamps": [round(e.timestamp, 2) for e in group],
            "confirmed_kill_count": len(group),
            "grouping_note": (
                f"{len(group)} confirmed eliminations within "
                f"{group[-1].timestamp - group[0].timestamp:.1f}s. "
                "Player-count evidence unavailable — label is a candidate only."
            ),
        }
        lead.breakdown = {**lead.breakdown, "multi_kill_bonus": extra}
        # Remove the absorbed kills so clips are not duplicated.
        for member in group[1:]:
            events.remove(member)
            events_by_id.pop(id(member), None)
    return events, promoted
