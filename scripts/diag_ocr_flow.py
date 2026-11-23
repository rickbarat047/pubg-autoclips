"""Diagnostic: replay OCR + feed detection on a real match with full tracing.

Logs every OCR read of the calibrated region, its IGN score/classification,
feed signature, and whether the detection logic emitted or suppressed it.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import AppSettings
from app.detection.kill_feed.feed_detector import KillFeedDetector
from app.detection.kill_feed.ign_matcher import (
    classify_feed_line, feed_entry_signature, ign_match_score,
)
from app.detection.kill_feed.ocr_engine import OcrEngine
from app.media.frame_extractor import extract_frames, cleanup_frames
from app.utils.paths import settings_path

VIDEO = "G:/GAMEPLAY/2026-11-18 21-23-06.mp4"
INTERVAL = 2.0

cfg = AppSettings.load()
print("IGN:", cfg.ign, "region:", cfg.calibration, "min_obs:", cfg.kill_feed.min_observations)

ocr = OcrEngine()
feed = KillFeedDetector(cfg, ocr)

calls = {"n": 0, "with_ign": 0, "confirmed": 0, "possible": 0}
orig_process = feed._process


def traced_process(t, text, ocr_conf, lines, candidates, last_emit, fcfg):
    if not text:
        return None
    cls = classify_feed_line(text, cfg.ign)
    score = ign_match_score(text, cfg.ign)
    sig = feed_entry_signature(text, cfg.ign)
    calls["n"] += 1
    if score >= 0.45:
        calls["with_ign"] += 1
    ev = orig_process(t, text, ocr_conf, lines, candidates, last_emit, fcfg)
    if cls in ("confirmed", "possible"):
        calls["confirmed" if cls == "confirmed" else "possible"] += 1
        print(
            f"t={t:7.1f} score={score:.2f} ocr={ocr_conf:.2f} cls={cls:<9} "
            f"sig={sig!r:<45} EMIT={bool(ev)}  {text[:70]!r}"
        )
    return ev


feed._process = traced_process

print("Extracting frames at", INTERVAL, "s ...")
fs = extract_frames(VIDEO, INTERVAL)
print("Frames:", len(fs))
import cv2
frames = []
for s in fs:
    img = cv2.imread(s.path)
    if img is not None:
        frames.append((s.timestamp, img))

t0 = time.time()
events = feed.detect_from_frames(frames)
print("OCR time: %.1fs" % (time.time() - t0))
print("CALL STATS:", calls)
print("EMITTED EVENTS:", len(events))
for e in events:
    print(f"  t={e.timestamp:7.1f} {e.category:<14} conf={e.confidence:.2f} {e.recognised_text[:60]!r}")
cleanup_frames(fs)
