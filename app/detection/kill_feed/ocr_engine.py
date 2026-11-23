"""RapidOCR (ONNX Runtime) wrapper with preprocessing and lazy initialisation."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

from ...core.exceptions import OcrInitError
from ...utils.logging import get_logger

log = get_logger("detection.ocr")


@dataclass
class OcrResult:
    text: str
    confidence: float
    raw_lines: list[str]
    # Confidence of each individual line, parallel to ``raw_lines``. The
    # region-level ``confidence`` is the max of these, but a kill-feed event
    # must use the confidence of the line that actually matched the IGN —
    # otherwise a crisp HUD number can make a garbled name look certain.
    line_scores: list[float] = field(default_factory=list)


class OcrEngine:
    """Thread-safe lazy OCR engine.

    RapidOCR ships its own ONNX models; no download or network access is
    required at runtime.  Initialisation is deferred until first use so the
    GUI starts quickly.
    """

    def __init__(self, use_gpu: bool = False) -> None:
        self._engine = None
        self._lock = threading.Lock()
        self._use_gpu = use_gpu

    def _ensure(self) -> None:
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        self._engine = RapidOCR(use_cuda=self._use_gpu)
                        # Detection upscales small crops to a 736px MIN side by
                        # default, which is very slow on CPU. A max-side limit
                        # keeps 1080p kill-feed crops at native size (~2x faster
                        # with no loss of readable text). Text orientation
                        # classification is unnecessary for HUD text.
                        try:
                            self._engine.text_det.limit_side_len = 736
                            self._engine.text_det.limit_type = "max"
                        except Exception:  # pragma: no cover - API changed
                            pass
                        log.info("RapidOCR initialised (fast CPU settings)")
                    except Exception as exc:  # noqa: BLE001
                        raise OcrInitError(str(exc)) from exc

    @staticmethod
    def preprocess(region: np.ndarray, scale: float = 1.0) -> np.ndarray:
        """Light preprocessing only — detection handles its own resizing.

        Heavy upscaling + CLAHE made each crop take >1 s on CPU. Keeping the
        native crop and letting the detector resize to a max side of 736 is
        ~4x faster while still reading kill-feed text at 1080p.
        """
        if region is None or region.size == 0:
            return region
        if scale != 1.0:
            h, w = region.shape[:2]
            region = cv2.resize(region, (int(w * scale), int(h * scale)),
                                interpolation=cv2.INTER_AREA)
        return region

    def recognize(self, region: np.ndarray) -> OcrResult:
        self._ensure()
        enhanced = self.preprocess(region)
        try:
            # use_cls=False: kill-feed text is always upright; skipping the
            # classifier removes ~25% of inference time.
            result, _ = self._engine(enhanced, use_cls=False)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            raise OcrInitError(f"OCR inference failed: {exc}") from exc
        if not result:
            return OcrResult("", 0.0, [])
        lines: list[str] = []
        scores: list[float] = []
        best_score = 0.0
        for item in result:
            # RapidOCR returns [box, text, score]
            try:
                text = str(item[1])
                score = float(item[2])
            except (IndexError, TypeError, ValueError):
                continue
            if text.strip():
                lines.append(text.strip())
                scores.append(score)
                best_score = max(best_score, score)
        return OcrResult(" ".join(lines), best_score, lines, scores)

    def recognize_rows(self, region: np.ndarray) -> OcrResult:
        """OCR every bright text row separately, upscaled, and return them all.

        Knock-feed rows are dimmer and smaller than kill rows. Detecting the
        horizontal text bands and feeding enlarged strips to the recogniser
        recovers names that whole-region OCR misses. Returning *all* bands (not
        just the single most confident one) matters: the highest-confidence
        band is often the HUD alive-counter, while the IGN sits in a dimmer
        row above it. Dropping that row was a direct cause of missed knocks.
        """
        if region is None or region.size == 0:
            return OcrResult("", 0.0, [])
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        bright = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY)[1]
        projection = (bright > 0).sum(axis=1)
        height = region.shape[0]
        bands: list[tuple[int, int]] = []
        start: int | None = None
        for y, count in enumerate(projection):
            if count > 2 and start is None:
                start = y
            elif count <= 2 and start is not None:
                if y - start >= 7:
                    bands.append((start, y))
                start = None
        if start is not None and height - start >= 7:
            bands.append((start, height))
        if not bands:
            return OcrResult("", 0.0, [])

        all_lines: list[str] = []
        all_scores: list[float] = []
        for y1, y2 in bands[:10]:
            strip = region[max(0, y1 - 4):min(height, y2 + 4), :]
            if strip.size == 0:
                continue
            enlarged = cv2.resize(strip, None, fx=2.5, fy=2.5,
                                  interpolation=cv2.INTER_CUBIC)
            try:
                result = self.recognize(enlarged)
            except Exception:  # noqa: BLE001
                continue
            all_lines.extend(result.raw_lines)
            all_scores.extend(result.line_scores)
        if not all_lines:
            return OcrResult("", 0.0, [])
        return OcrResult(" ".join(all_lines), max(all_scores), all_lines, all_scores)

    def is_ready(self) -> bool:
        return self._engine is not None
