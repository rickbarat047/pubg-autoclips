"""Kill-feed region calibration helpers (normalised coordinates)."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PixelRect:
    x: int
    y: int
    w: int
    h: int


def to_normalized(rect: PixelRect, frame_w: int, frame_h: int) -> tuple[float, float, float, float]:
    if frame_w <= 0 or frame_h <= 0:
        raise ValueError("Frame dimensions must be positive")
    return (
        round(rect.x / frame_w, 6),
        round(rect.y / frame_h, 6),
        round(rect.w / frame_w, 6),
        round(rect.h / frame_h, 6),
    )


def to_pixels(nx: float, ny: float, nw: float, nh: float,
              frame_w: int, frame_h: int) -> PixelRect:
    x = int(round(nx * frame_w))
    y = int(round(ny * frame_h))
    w = int(round(nw * frame_w))
    h = int(round(nh * frame_h))
    return PixelRect(max(0, x), max(0, y), max(1, w), max(1, h))


def clamp_rect(x1: int, y1: int, x2: int, y2: int,
               frame_w: int, frame_h: int) -> PixelRect:
    x1, x2 = sorted((max(0, min(x1, frame_w)), max(0, min(x2, frame_w))))
    y1, y2 = sorted((max(0, min(y1, frame_h)), max(0, min(y2, frame_h))))
    return PixelRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def draw_overlay(frame: np.ndarray, rect: PixelRect,
                 label: str = "Kill Feed Region") -> np.ndarray:
    out = frame.copy()
    x1, y1, x2, y2 = rect.x, rect.y, rect.x + rect.w, rect.y + rect.h
    overlay = out.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (124, 252, 0), -1)
    cv2.addWeighted(overlay, 0.18, out, 0.82, 0, out)
    cv2.rectangle(out, (x1, y1), (x2, y2), (124, 252, 0), 2)
    # Corner handles
    for cx, cy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
        cv2.circle(out, (cx, cy), 4, (255, 255, 255), -1)
    cv2.putText(out, label, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (124, 252, 0), 2, cv2.LINE_AA)
    return out
