"""Regression tests for missed knock/kill moments.

Each test targets one concrete root cause found in the 2026-11-23 investigation
(recorded in DEBUG_FINDINGS.md). These must not pass with the old code.
"""
from __future__ import annotations

import numpy as np

from app.config import AppSettings
from app.detection.kill_feed.feed_detector import KillFeedDetector
from app.detection.kill_feed.ign_matcher import (
    best_matching_line,
    feed_entry_signature,
    victim_of,
)
from app.detection.kill_feed.ocr_engine import OcrEngine, OcrResult
from app.detection.pipeline import compute_sample_interval
from app.detection.scoring.event_ranker import rank_events
from app.detection.scoring.event_scorer import ScoredEvent


class _FakeOcr:
    def recognize(self, region):  # pragma: no cover - not used by direct _process tests
        return OcrResult("", 0.0, [])


def _detector(settings: AppSettings) -> KillFeedDetector:
    # The shared `settings` fixture uses TESTPLAYER; these tests deliberately
    # exercise the real-world IGN and feed text captured during debugging.
    settings.ign = "rickbarat"
    settings.kill_feed.min_observations = 1
    settings.kill_feed.confidence_threshold = 0.45
    return KillFeedDetector(settings, _FakeOcr())


def _event(det, t, text, lines, scores, candidates, last_emit):
    return det._process(t, text, max(scores or [0.0]), lines, scores,
                        candidates, last_emit, det.settings.kill_feed)


# --- Root cause 2: recognize_rows returned only one band --------------------
def test_recognize_rows_returns_every_band(monkeypatch):
    region = np.zeros((80, 200, 3), dtype=np.uint8)
    region[10:25, :, :] = 255
    region[45:60, :, :] = 255

    calls = {"n": 0}
    script = [
        OcrResult("34 ALIVE 210", 0.99, ["34 ALIVE 210"], [0.99]),
        OcrResult("rickbarat X ENEMY1", 0.62, ["rickbarat X ENEMY1"], [0.62]),
    ]

    def fake_recognize(self, img):
        res = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        return res

    monkeypatch.setattr(OcrEngine, "recognize", fake_recognize)
    result = OcrEngine().recognize_rows(region)

    assert result.raw_lines == ["34 ALIVE 210", "rickbarat X ENEMY1"], result.raw_lines
    assert result.line_scores == [0.99, 0.62]
    assert result.confidence == 0.99


# --- Root cause 1: whole blob matched, wrong row confidence -----------------
def test_best_matching_line_uses_the_feed_row_not_the_hud():
    lines = ["34 ALIVE 210", "3[NTRS]rickbarat X Bennne50 MPSK"]
    scores = [0.99, 0.62]
    line, match_score, conf = best_matching_line("rickbarat", " ".join(lines), lines, scores)
    assert line == lines[1]
    assert match_score >= 0.72
    assert conf == 0.62  # NOT the HUD's 0.99


def test_signature_uses_the_matching_row_victim():
    blob = "34 ALIVE 210 3[NTRS]rickbarat X Bennne50 MPSK"
    row = "3[NTRS]rickbarat X Bennne50 MPSK"
    sig = feed_entry_signature(blob, "rickbarat", line=row)
    # normalize_text maps OCR confusions: 0->o and 5->s
    assert "bennneso" in sig
    assert "alive" not in sig
    assert victim_of(sig).startswith("bennneso")


# --- Root causes 3 & 4: global cooldown + fuzzy victim collapse -------------
def test_two_distinct_victims_seconds_apart_both_emit(settings):
    det = _detector(settings)
    cands: dict = {}
    emitted: dict = {}
    e1 = _event(det, 10.0, "40 ALIVE rickbarat X AlphaOne",
                ["40 ALIVE", "rickbarat X AlphaOne"], [0.9, 0.7], cands, emitted)
    e2 = _event(det, 13.0, "39 ALIVE rickbarat X BravoTwo",
                ["39 ALIVE", "rickbarat X BravoTwo"], [0.9, 0.7], cands, emitted)
    assert e1 is not None and e2 is not None
    assert e1.signature != e2.signature


def test_same_victim_jitter_is_suppressed(settings):
    det = _detector(settings)
    cands: dict = {}
    emitted: dict = {}
    _event(det, 10.0, "rickbarat X Bennne50", ["rickbarat X Bennne50"], [0.8],
           cands, emitted)
    e2 = _event(det, 12.0, "rickbarat X Bennne5O", ["rickbarat X Bennne5O"], [0.8],
                cands, emitted)
    assert e2 is None  # same row re-read, not a second kill


def test_garbled_knock_rows_without_victim_are_not_collapsed(settings):
    """Dim knock rows whose IGN is garbled have no victim token. They must be
    kept as separate knock candidates instead of all being suppressed as the
    same bare-IGN signature (the old 45 s fuzzy window killed them all)."""
    det = _detector(settings)
    cands: dict = {}
    emitted: dict = {}
    t1 = _event(det, 20.0, "85 ALIVE 210 compass rickbar",
                ["85 ALIVE 210", "rickbar"], [0.99, 0.50], cands, emitted)
    t2 = _event(det, 23.0, "84 ALIVE 195 compass rickba",
                ["84 ALIVE 195", "rickba"], [0.99, 0.50], cands, emitted)
    assert t1 is not None and t2 is not None


# --- Root cause 5: confidence threshold / matching-line confidence ----------
def test_low_confidence_matching_row_is_rejected(settings):
    det = _detector(settings)
    cands: dict = {}
    emitted: dict = {}
    ev = _event(det, 30.0, "34 ALIVE 210 33[NTRS]rickbaXENEMY",
                ["34 ALIVE 210", "33[NTRS]rickbaXENEMY"], [0.99, 0.20],
                cands, emitted)
    assert ev is None  # HUD is crisp but the IGN row reads at only 0.20


# --- Root cause 6: category-blind dedup in rank_events ----------------------
def test_confirmed_kill_survives_nearby_combat():
    # Old code sorted by score only, so a 65-point COMBAT window evicted a
    # 50-point confirmed KILL 0.2 s later. The KILL must win the dedup slot.
    kill = ScoredEvent(100.0, "KILL", 50, 0.9, "ocr", "rickbarat X ENEMY", 0.9)
    combat = ScoredEvent(100.2, "COMBAT", 65, 0.8, "audio", "", 0.0)
    result = rank_events([combat, kill])
    assert len(result) == 1
    assert result[0].category == "KILL"

    # A COMBAT event with no nearby kill must still survive.
    assert [e.category for e in rank_events([combat])] == ["COMBAT"]


# --- Root cause 7: coarse adaptive sampling --------------------------------
def test_compute_sample_interval_uses_finer_setting_and_caps_samples(settings):
    settings.kill_feed.sample_interval_sec = 1.0
    settings.visual.enabled = True
    settings.visual.sample_interval_sec = 2.0
    assert compute_sample_interval(settings, 600.0) == 1.0
    # 3600 s / 1800 = 2.0 s cap, coarse setting still respected for short clips
    assert compute_sample_interval(settings, 3600.0) == 2.0
