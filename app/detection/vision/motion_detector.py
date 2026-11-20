"""Frame-difference motion intensity (pure OpenCV/numpy functions)."""
from __future__ import annotations

import cv2
import numpy as np


def prepare(frame: np.ndarray, width: int = 320) -> np.ndarray:
    """Downscale to grayscale for cheap motion analysis."""
    h, w = frame.shape[:2]
    if max(h, w) > width:
        scale = width / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_AREA)
    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def motion_intensity(prev: np.ndarray | None, curr: np.ndarray,
                     blur: bool = True) -> float:
    """Return normalised 0..1 motion amount between two consecutive frames."""
    cur = prepare(curr)
    if prev is None:
        return 0.0
    a, b = prepare(prev), cur
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    if blur:
        a = cv2.GaussianBlur(a, (5, 5), 0)
        b = cv2.GaussianBlur(b, (5, 5), 0)
    diff = cv2.absdiff(a, b)
    # Fraction of noticeably changed pixels weighted by change magnitude.
    changed = (diff > 18).astype(np.float32)
    magnitude = np.clip(diff.astype(np.float32) / 80.0, 0, 1)
    score = float(changed.mean() * 0.6 + (magnitude * changed).mean() * 0.4)
    return float(np.clip(score, 0.0, 1.0))
