"""Group audio windows into candidate combat activity windows."""
from __future__ import annotations

from dataclasses import dataclass

from .audio_analyzer import AudioWindow


@dataclass
class CombatWindow:
    start: float
    end: float
    peak_intensity: float
    mean_intensity: float
    spikes: int


def group_combat_windows(windows: list[AudioWindow], intensity_threshold: float = 0.5,
                         merge_gap: float = 2.0) -> list[CombatWindow]:
    """Merge consecutive high-intensity audio windows into combat candidates."""
    active: list[AudioWindow] = []
    result: list[CombatWindow] = []

    def flush(group: list[AudioWindow]) -> None:
        if not group:
            return
        result.append(CombatWindow(
            start=group[0].timestamp,
            end=group[-1].timestamp + group[-1].duration,
            peak_intensity=max(w.intensity for w in group),
            mean_intensity=sum(w.intensity for w in group) / len(group),
            spikes=sum(1 for w in group if w.is_spike),
        ))

    for w in windows:
        if w.intensity >= intensity_threshold:
            if active and w.timestamp - (active[-1].timestamp + active[-1].duration) > merge_gap:
                flush(active)
                active = []
            active.append(w)
        elif active:
            # Allow short gaps inside combat; longer gaps flush.
            if w.timestamp - (active[-1].timestamp + active[-1].duration) > merge_gap:
                flush(active)
                active = []
    flush(active)

    # Merge windows that overlap after creation.
    merged: list[CombatWindow] = []
    for cw in result:
        if merged and cw.start <= merged[-1].end + merge_gap:
            last = merged[-1]
            last.end = max(last.end, cw.end)
            last.peak_intensity = max(last.peak_intensity, cw.peak_intensity)
            last.mean_intensity = max(last.mean_intensity, cw.mean_intensity)
            last.spikes += cw.spikes
        else:
            merged.append(cw)
    return merged
