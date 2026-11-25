"""Bottom editor timeline: time ruler, clip track, playhead and drag-to-add.

Pixel-to-time mapping uses an 8 px gutter on each side so the track lines up
with the segment painting. Dragging on empty track space adds a manual range;
a plain click repositions the playhead.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ..tokens import PALETTE

_MARGIN = 8
_MIN_RANGE_SEC = 0.5


class TimelinePanel(QWidget):
    playhead_changed = Signal(float)
    range_added = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.segments: list = []
        self.duration = 1.0
        self._playhead = 0.0
        self._ranges: list[tuple[float, float]] = []
        self._drag_start_x: float | None = None
        self._drag_cur_x: float | None = None
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    # ---- geometry -------------------------------------------------------
    def set_segments(self, segments: list, duration: float) -> None:
        self.segments = list(segments)
        self.duration = max(1.0, float(duration))
        # Ranges are re-derived from the DB on every reload; clear stale ones
        # so old dragged ranges are not painted twice after _load_segments.
        self._ranges.clear()
        self.update()

    def _x_to_time(self, x: float) -> float:
        usable = max(1.0, self.width() - 2 * _MARGIN)
        frac = min(1.0, max(0.0, (float(x) - _MARGIN) / usable))
        return frac * self.duration

    def _time_to_x(self, t: float) -> int:
        usable = max(1.0, self.width() - 2 * _MARGIN)
        return _MARGIN + int((float(t) / self.duration) * usable)

    # ---- playhead -------------------------------------------------------
    def set_playhead(self, t: float) -> None:
        new = min(self.duration, max(0.0, float(t)))
        if abs(new - self._playhead) > 1e-6:
            self._playhead = new
            self.update()

    def playhead(self) -> float:
        return self._playhead

    def add_at_playhead(self) -> tuple[float, float]:
        start = min(self.duration, max(0.0, self._playhead))
        end = min(self.duration, start + 20.0)
        self._ranges.append((start, end))
        self.range_added.emit(start, end)
        self.update()
        return start, end

    # ---- painting -------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        try:
            w = self.width()
            h = self.height()
            p.fillRect(0, 0, w, h, QColor(PALETTE["card"]))
            y = 34
            track_h = max(24, h - 70)
            x0, x1 = _MARGIN, w - _MARGIN
            # track bed
            p.fillRect(x0, y, x1 - x0, track_h, QColor(PALETTE["elevated"]))
            # ruler ticks
            pen = QPen(QColor(PALETTE["text_dim"]))
            p.setPen(pen)
            for i in range(0, 11):
                tx = x0 + int((i / 10) * (x1 - x0))
                p.drawLine(tx, y - 6, tx, y)
            # detected/manual segments
            for seg in self.segments:
                sx = self._time_to_x(seg.start)
                ex = self._time_to_x(seg.end)
                p.fillRect(sx, y + 4, max(3, ex - sx), track_h - 8,
                           QColor(PALETTE["accent"]))
            # manual ranges dragged by the user
            for rs, re in self._ranges:
                sx = self._time_to_x(rs)
                ex = self._time_to_x(re)
                p.fillRect(sx, y + 8, max(3, ex - sx), track_h - 16,
                           QColor(PALETTE["accent_light"]))
            # playhead
            px = self._time_to_x(self._playhead)
            p.setPen(QPen(QColor(PALETTE["accent"]), 2))
            p.drawLine(px, y - 8, px, y + track_h + 8)
        finally:
            p.end()

    # ---- interaction ----------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        x = event.position().x()
        t = self._x_to_time(x)
        self._playhead = t
        self.playhead_changed.emit(t)
        self._drag_start_x = x
        self._drag_cur_x = x
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start_x is not None:
            self._drag_cur_x = event.position().x()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_start_x is None:
            return
        cur = event.position().x()
        a = self._x_to_time(self._drag_start_x)
        b = self._x_to_time(cur)
        self._drag_start_x = None
        self._drag_cur_x = None
        start, end = (a, b) if a <= b else (b, a)
        if end - start >= _MIN_RANGE_SEC:
            self._ranges.append((start, end))
            self.range_added.emit(start, end)
            self.update()
