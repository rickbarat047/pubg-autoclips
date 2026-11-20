"""RapidOCR (ONNX Runtime) wrapper with preprocessing and lazy initialisation."""
from __future__ import annotations

import threading
from dataclasses import dataclass

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
                best_score = max(best_score, score)
        return OcrResult(" ".join(lines), best_score, lines)

    def is_ready(self) -> bool:
        return self._engine is not None
