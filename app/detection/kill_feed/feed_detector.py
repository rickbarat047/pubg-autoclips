"""Kill-feed detection: sample frames, run OCR, match IGN, deduplicate."""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

import cv2
import numpy as np

from ...config import AppSettings, NormalizedRegion
from ...core.task_queue import CancellationToken
from ...media.frame_extractor import FrameSample
from ...media.video_reader import VideoReader
from ...utils.logging import get_logger
from .ign_matcher import (
    classify_feed_line, feed_entry_signature, ign_match_score, looks_like_knock,
)
from .ocr_engine import OcrEngine

log = get_logger("detection.kill_feed")


@dataclass
class FeedEvent:
    timestamp: float
    category: str  # confirmed | possible | knock | uncertain
    confidence: float
    recognised_text: str
    ocr_confidence: float
    observations: int
    signature: str
    evidence: dict = field(default_factory=dict)


ProgressCb = Callable[[float, str], None]


class KillFeedDetector:
    """Detect kill-feed entries involving the configured IGN."""

    def __init__(self, settings: AppSettings, ocr: OcrEngine | None = None) -> None:
        self.settings = settings
        self.ocr = ocr or OcrEngine()

    def detect(self, video_path: str, region: NormalizedRegion | None = None,
               token: CancellationToken | None = None,
               progress: ProgressCb | None = None) -> list[FeedEvent]:
        """Legacy path: seek through the video with OpenCV (slow on long files)."""
        return self._detect_seeking(video_path, region, token, progress)

    def detect_from_frames(self, frames: list[tuple[float, np.ndarray]],
                           region: NormalizedRegion | None = None,
                           token: CancellationToken | None = None,
                           progress: ProgressCb | None = None) -> list[FeedEvent]:
        """Fast path: analyse frames already decoded by FFmpeg in one pass."""
        cfg = self.settings.kill_feed
        if not cfg.enabled or not self.settings.ign:
            return []
        region = region or self.settings.calibration
        events: list[FeedEvent] = []
        candidates: dict[str, dict] = {}
        last_emit: dict[str, float] = {}
        total = max(1, len(frames))
        prev_small: np.ndarray | None = None

        for idx, (t, frame) in enumerate(frames):
            if token:
                token.check()
            h, w = frame.shape[:2]
            x, y, rw, rh = region.to_pixels(w, h)
            crop = frame[y:y + rh, x:x + rw]
            if crop.size == 0:
                continue
            try:
                ocr_res, prev_small = self._recognize_crop(crop, prev_small)
            except Exception as exc:  # noqa: BLE001
                log.warning("OCR failed at %.1fs: %s", t, exc)
                continue

            event = self._process(t, ocr_res.text, ocr_res.confidence,
                                  ocr_res.raw_lines, candidates, last_emit, cfg)
            if event:
                events.append(event)
            self._decay(candidates, t, cfg.duplicate_window_sec)
            if progress and idx % 4 == 0:
                progress(idx / total, f"OCR {t:.0f}s")
        self._report(progress, 1.0, "Kill-feed analysis complete")
        log.info("Kill-feed analysis produced %d event(s)", len(events))
        return events

    def _detect_seeking(self, video_path: str, region: NormalizedRegion | None,
                        token: CancellationToken | None,
                        progress: ProgressCb | None) -> list[FeedEvent]:
        cfg = self.settings.kill_feed
        if not cfg.enabled or not self.settings.ign:
            return []
        region = region or self.settings.calibration
        events: list[FeedEvent] = []
        candidates: dict[str, dict] = {}
        last_emit: dict[str, float] = {}
        prev_small: np.ndarray | None = None
        with VideoReader(video_path) as reader:
            total = max(1, int((reader.duration or 1) / cfg.sample_interval_sec))
            for idx, (t, frame) in enumerate(
                reader.sample(cfg.sample_interval_sec, token=token)
            ):
                if token:
                    token.check()
                h, w = frame.shape[:2]
                x, y, rw, rh = region.to_pixels(w, h)
                crop = frame[y:y + rh, x:x + rw]
                if crop.size == 0:
                    continue
                try:
                    ocr_res, prev_small = self._recognize_crop(crop, prev_small)
                except Exception as exc:  # noqa: BLE001
                    log.warning("OCR failed at %.1fs: %s", t, exc)
                    continue
                event = self._process(t, ocr_res.text, ocr_res.confidence,
                                      ocr_res.raw_lines, candidates, last_emit, cfg)
                if event:
                    events.append(event)
                self._decay(candidates, t, cfg.duplicate_window_sec)
                self._report(progress, idx / total, f"OCR {t:.0f}s")
        self._report(progress, 1.0, "Kill-feed analysis complete")
        return events

    def _recognize_crop(self, crop: np.ndarray, prev_small: np.ndarray | None):
        """OCR a feed crop, retrying per-row on dim/garbled text.

        Returns (OcrResult, small_gray_frame_for_next_change_check).
        """
        small = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (80, 40))
        result = self.ocr.recognize(crop)
        score = ign_match_score(result.text, self.settings.ign)
        changed = prev_small is None or float(
            np.mean(cv2.absdiff(small, prev_small))) > 2.0
        if changed and score < 0.55:
            try:
                rows = self.ocr.recognize_rows(crop)
                row_score = ign_match_score(rows.text, self.settings.ign)
                if row_score > score:
                    result = rows
            except Exception as exc:  # noqa: BLE001
                log.debug("Row OCR failed: %s", exc)
        return result, small

    def _process(self, t: float, text: str, ocr_conf: float, lines: list[str],
                 candidates: dict, last_emit: dict, cfg) -> FeedEvent | None:
        """Confirm sightings per kill-feed ROW, not per global IGN.

        A single global cooldown suppressed any second kill that happened
        within ``duplicate_window_sec`` (the classic "5th kill missing" bug).
        Each distinct feed row now has its own confirmation state: a new row
        emits as soon as it has been observed ``min_observations`` times, while
        a persistent row is emitted only once until it disappears.
        """
        if not text:
            return None
        classification = classify_feed_line(text, self.settings.ign)
        if classification not in ("confirmed", "possible"):
            return None
        knock = looks_like_knock(text)
        sig = feed_entry_signature(text, self.settings.ign)
        info = candidates.setdefault(
            sig, {"count": 0, "last": t, "emitted": False})

        if t - info["last"] > max(3.0, cfg.sample_interval_sec * 2):
            info["count"] = 0  # a gap breaks the consecutive-observation run
        info["last"] = t
        info["count"] += 1
        if info["count"] < cfg.min_observations or info["emitted"]:
            return None

        # A single feed row persists for several seconds and OCR reads its
        # victim token slightly differently on successive frames. Compare the
        # new row against recently emitted ones with fuzzy similarity: a
        # clearly different victim means a genuinely new kill, even seconds
        # later; the same row with jitter is suppressed.
        recent: list[tuple[float, str]] = last_emit.setdefault("__recent__", [])
        for prev_t, prev_sig in list(recent):
            if t - prev_t > 45.0:
                recent.remove((prev_t, prev_sig))
                continue
            victim = sig.split("|", 1)[1] if "|" in sig else sig
            prev_victim = prev_sig.split("|", 1)[1] if "|" in prev_sig else prev_sig
            if victim and prev_victim and (
                    SequenceMatcher(None, victim, prev_victim).ratio() >= 0.68):
                info["emitted"] = True
                return None
        recent.append((t, sig))

        # Guard against two near-identical detections in the same second.
        if t - last_emit.get("__any__", -1e9) < 1.5:
            return None

        info["emitted"] = True
        last_emit[sig] = t
        last_emit["__any__"] = t
        if classification == "confirmed":
            category = "knock" if knock else "confirmed"
        else:
            # Partial IGN match — usually a knock or a garbled row. Keep it as
            # a low-confidence candidate with the evidence attached.
            category = "knock_candidate"
        ev_conf = min(1.0, ocr_conf * (0.85 + 0.15 * min(info["count"], 4) / 4))
        if category == "knock_candidate":
            ev_conf *= 0.75
        return FeedEvent(
            timestamp=t, category=category, confidence=ev_conf,
            recognised_text=text[:200], ocr_confidence=ocr_conf,
            observations=info["count"], signature=sig,
            evidence={"classification": classification, "knock_indicator": knock,
                      "ign": self.settings.ign, "lines": lines,
                      "entry_signature": sig},
        )

    @staticmethod
    def _decay(candidates: dict, now: float, window: float) -> None:
        # An emitted row can stay on the HUD for 20-40 s. Keep its "emitted"
        # state much longer than a new candidate, otherwise the same kill is
        # reported again every few seconds.
        emitted_window = max(60.0, window * 4)
        for k, v in list(candidates.items()):
            limit = emitted_window if v.get("emitted") else window
            if now - v["last"] > limit:
                candidates.pop(k, None)

    @staticmethod
    def _report(cb: ProgressCb | None, fraction: float, message: str) -> None:
        if cb:
            cb(max(0.0, min(1.0, fraction)), message)
