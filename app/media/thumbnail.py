"""Generate JPEG/PNG thumbnails for highlights and match cards."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..utils.logging import get_logger
from ..utils.paths import thumbnails_dir
from .decoder import frame_at

log = get_logger("media.thumbnail")


def make_thumbnail(video_path: str, timestamp: float, out_path: str | Path,
                   width: int = 320) -> bool:
    frame = frame_at(video_path, timestamp)
    if frame is None:
        return False
    h, w = frame.shape[:2]
    new_h = int(h * width / w)
    thumb = cv2.resize(frame, (width, new_h), interpolation=cv2.INTER_AREA)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(out), thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        log.warning("cv2.imwrite failed for %s", out)
    return ok


def thumbnail_for_highlight(match_id: int, highlight_id: int, video_path: str,
                            timestamp: float) -> str:
    out = thumbnails_dir() / f"m{match_id}_h{highlight_id}.jpg"
    if out.exists():
        return str(out)
    make_thumbnail(video_path, timestamp, out)
    return str(out) if out.exists() else ""


def qimage_from_frame(frame: np.ndarray):
    """Convert a BGR numpy frame to QImage for Qt display."""
    from PySide6.QtGui import QImage
    if frame is None or frame.size == 0:
        return QImage()
    if frame.ndim == 2:
        h, w = frame.shape
        return QImage(frame.data, w, h, w, QImage.Format_Grayscale8).copy()
    h, w, ch = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    bytes_per_line = ch * w
    return QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
