"""Combine OCR, audio and visual signals into transparent event scores."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...config import AppSettings
from ...detection.audio.audio_analyzer import AudioWindow
from ...detection.audio.combat_detector import CombatWindow
from ...detection.kill_feed.feed_detector import FeedEvent
from ...detection.vision.activity_detector import ActivitySample

CATEGORY_KILL = "KILL"
CATEGORY_KNOCK = "KNOCK"
CATEGORY_KNOCK_CANDIDATE = "KNOCK_CANDIDATE"
CATEGORY_MULTI = "MULTI_KILL"
CATEGORY_CLUTCH = "CLUTCH_CANDIDATE"
CATEGORY_COMBAT = "COMBAT"
CATEGORY_LONGRANGE = "LONG_RANGE_CANDIDATE"
CATEGORY_FUNNY = "FUNNY_CANDIDATE"
CATEGORY_UNKNOWN = "UNKNOWN"


@dataclass
class ScoredEvent:
    timestamp: float
    category: str
    score: float
    confidence: float
    source: str
    recognised_text: str
    ocr_confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    breakdown: dict[str, float] = field(default_factory=dict)


def _audio_at(timestamp: float, windows: list[AudioWindow],
              radius: float = 4.0) -> tuple[float, float, bool]:
    nearby = [w for w in windows if abs((w.timestamp + w.duration / 2) - timestamp) <= radius]
    if not nearby:
        return 0.0, 0.0, False
    return (max(w.intensity for w in nearby),
            max(w.z_energy for w in nearby),
            any(w.is_spike for w in nearby))


def _visual_at(timestamp: float, samples: list[ActivitySample],
               radius: float = 3.0) -> tuple[float, bool]:
    nearby = [s for s in samples if abs(s.timestamp - timestamp) <= radius]
    if not nearby:
        return 0.0, False
    return max(s.motion for s in nearby), any(s.scene_change for s in nearby)


def _combat_at(timestamp: float, windows: list[CombatWindow]) -> tuple[bool, float]:
    for w in windows:
        if w.start - 1 <= timestamp <= w.end + 1:
            return True, w.peak_intensity
    return False, 0.0


class EventScorer:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.w = settings.scoring

    def score_feed_event(self, ev: FeedEvent, audio: list[AudioWindow],
                         combat: list[CombatWindow],
                         visual: list[ActivitySample]) -> ScoredEvent:
        b: dict[str, float] = {}
        confidence = float(ev.confidence)

        if ev.category == "confirmed":
            b["confirmed_kill"] = self.w.confirmed_kill
            category = CATEGORY_KILL
        elif ev.category == "knock":
            # Confirmed knock (feed text explicitly shows a knock indicator).
            b["confirmed_kill"] = self.w.confirmed_kill * 0.6
            category = CATEGORY_KNOCK
        elif ev.category == "knock_candidate":
            # Partial IGN match: likely a knock with garbled OCR. Never
            # presented as a confirmed elimination.
            b["confirmed_kill"] = self.w.confirmed_kill * 0.65
            category = CATEGORY_KNOCK_CANDIDATE
        elif ev.category == "possible":
            b["confirmed_kill"] = self.w.confirmed_kill * 0.35
            category = CATEGORY_KNOCK_CANDIDATE
        else:  # uncertain
            b["confirmed_kill"] = self.w.confirmed_kill * 0.2
            category = CATEGORY_UNKNOWN

        a_intensity, a_z, a_spike = _audio_at(ev.timestamp, audio)
        if a_intensity > 0:
            b["audio_intensity"] = round(self.w.audio_intensity * a_intensity, 2)
        if a_spike:
            b["audio_spike"] = round(self.w.audio_intensity * 0.25, 2)

        v_motion, v_scene = _visual_at(ev.timestamp, visual)
        if v_motion > 0:
            b["visual_activity"] = round(self.w.visual_activity * v_motion, 2)
        if v_scene:
            b["scene_context"] = self.w.scene_context

        in_combat, combat_peak = _combat_at(ev.timestamp, combat)
        if in_combat:
            b["sustained_combat"] = round(
                self.w.sustained_combat * max(0.5, combat_peak), 2)

        b["uncertainty_penalty"] = -round(
            self.w.uncertainty_penalty * (1.0 - confidence), 2)

        score = round(max(0.0, sum(b.values())), 2)
        return ScoredEvent(
            timestamp=ev.timestamp,
            category=category,
            score=score,
            confidence=confidence,
            source="kill_feed_ocr",
            recognised_text=ev.recognised_text,
            ocr_confidence=ev.ocr_confidence,
            evidence={
                **ev.evidence,
                "observations": ev.observations,
                "audio_intensity": round(a_intensity, 3),
                "audio_z": round(a_z, 3),
                "audio_spike": a_spike,
                "visual_motion": round(v_motion, 3),
                "scene_change": v_scene,
                "in_combat_window": in_combat,
            },
            breakdown=b,
        )

    def score_audio_only(self, window: CombatWindow) -> ScoredEvent:
        """Create a low-confidence combat candidate from audio alone.

        This is never treated as a confirmed kill; it supports other signals.
        """
        b = {
            "audio_intensity": round(self.w.audio_intensity * 1.3 * window.peak_intensity, 2),
            "sustained_combat": round(self.w.sustained_combat * 1.5 * min(1.0, window.spikes / 4), 2),
            "uncertainty_penalty": -self.w.uncertainty_penalty * 0.2,
        }
        score = round(max(0.0, sum(b.values())), 2)
        confidence = 0.3
        return ScoredEvent(
            timestamp=window.start,
            category=CATEGORY_COMBAT,
            score=score,
            confidence=confidence,
            source="audio",
            recognised_text="",
            ocr_confidence=0.0,
            evidence={"spikes": window.spikes, "peak_intensity": window.peak_intensity,
                      "note": "audio-only candidate — not a confirmed kill"},
            breakdown=b,
        )

    def score_visual_only(self, window) -> ScoredEvent:
        b = {
            "visual_activity": round(self.w.visual_activity * window.peak_motion, 2),
            "scene_context": self.w.scene_context if window.scene_changes else 0.0,
            "uncertainty_penalty": -self.w.uncertainty_penalty * 0.7,
        }
        score = round(max(0.0, sum(b.values())), 2)
        return ScoredEvent(
            timestamp=window.start,
            category=CATEGORY_UNKNOWN,
            score=score,
            confidence=0.25,
            source="visual",
            recognised_text="",
            ocr_confidence=0.0,
            evidence={"peak_motion": window.peak_motion,
                      "note": "visual-only candidate"},
            breakdown=b,
        )


# Public name used in the application architecture.
HighlightScoringEngine = EventScorer
