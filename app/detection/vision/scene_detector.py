"""Scene-change detection using histogram and pixel-difference heuristics."""
from __future__ import annotations

import cv2
import numpy as np

from .motion_detector import prepare


def hist_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compare two frames via normalised grayscale histogram correlation."""
    ga, gb = prepare(a), prepare(b)
    if ga.shape != gb.shape:
        gb = cv2.resize(gb, (ga.shape[1], ga.shape[0]))
    ha = cv2.calcHist([ga], [0], None, [64], [0, 256])
    hb = cv2.calcHist([gb], [0], None, [64], [0, 256])
    cv2.normalize(ha, ha)
    cv2.normalize(hb, hb)
    return float(1.0 - cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL))


def is_scene_change(prev: np.ndarray | None, curr: np.ndarray,
                    threshold: float = 0.35) -> bool:
    if prev is None:
        return False
    a, b = prepare(prev), prepare(curr)
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    diff = cv2.absdiff(a, b)
    frac = float((diff > 40).mean())
    return frac > threshold or hist_distance(a, b) > threshold
