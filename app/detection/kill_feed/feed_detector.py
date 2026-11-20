"""Kill-feed detection: sample frames, run OCR, match IGN, deduplicate."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np

from ...config import AppSettings, NormalizedRegion
from ...core.task_queue import CancellationToken
from ...media.frame_extractor import FrameSample
from ...media.video_reader import VideoReader
from ...utils.logging import get_logger
from .ign_matcher import classify_feed_line, looks_like_knock, normalize_text
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

        for idx, (t, frame) in enumerate(frames):
            if token:
                token.check()
            h, w = frame.shape[:2]
            x, y, rw, rh = region.to_pixels(w, h)
            crop = frame[y:y + rh, x:x + rw]
            if crop.size == 0:
                continue
            try:
                ocr_res = self.ocr.recognize(crop)
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
                    ocr_res = self.ocr.recognize(crop)
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

    def _process(self, t: float, text: str, ocr_conf: float, lines: list[str],
                 candidates: dict, last_emit: dict, cfg) -> FeedEvent | None:
        """Confirm IGN sightings and emit at most one event per cooldown window.

        The whole OCR line is deliberately NOT used as a dedup key: PUBG's
        alive-counter and compass digits inside the same region change every
        second, so a persistent kill-feed row never produces two identical
        strings. We key on the (stable) IGN instead and use a time cooldown.
        """
        if not text:
            return None
        classification = classify_feed_line(text, self.settings.ign)
        if classification not in ("confirmed", "possible"):
            return None
        knock = looks_like_knock(text)
        key = normalize_text(self.settings.ign) or "ign"
        info = candidates.setdefault(
            key, {"count": 0, "last": t, "emitted_at": -1e9})

        if t - info["emitted_at"] < cfg.duplicate_window_sec:
            return None
        if t - info["last"] > max(3.0, cfg.sample_interval_sec * 2):
            info["count"] = 0  # a gap breaks the consecutive-observation run
        info["last"] = t
        info["count"] += 1
        if info["count"] < cfg.min_observations:
            return None

        info["emitted_at"] = t
        last_emit[key] = t
        category = "confirmed" if classification == "confirmed" else "uncertain"
        if classification == "confirmed" and knock:
            category = "knock"
        ev_conf = min(1.0, ocr_conf * (0.85 + 0.15 * min(info["count"], 4) / 4))
        return FeedEvent(
            timestamp=t, category=category, confidence=ev_conf,
            recognised_text=text[:200], ocr_confidence=ocr_conf,
            observations=info["count"], signature=key,
            evidence={"classification": classification, "knock_indicator": knock,
                      "ign": self.settings.ign, "lines": lines},
        )

    @staticmethod
    def _decay(candidates: dict, now: float, window: float) -> None:
        for k in [k for k, v in candidates.items() if now - v["last"] > window]:
            candidates.pop(k, None)

    @staticmethod
    def _report(cb: ProgressCb | None, fraction: float, message: str) -> None:
        if cb:
            cb(max(0.0, min(1.0, fraction)), message)
