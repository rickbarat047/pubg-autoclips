"""Clip editor: frame preview, timeline trimming and vertical preview."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..media.decoder import frame_at
from ..media.thumbnail import qimage_from_frame
from .widgets.common import Card, empty_state
from .tokens import PALETTE


class EditorPage(QWidget):
    export_requested = Signal(int, float, float)  # highlight_id, start, end

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.highlight = None
        self.video_path = ""
        self.duration = 0.0
        self.start = 0.0
        self.end = 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("Clip editor")
        title.setObjectName("pageTitle")
        sub = QLabel("Preview and adjust clip boundaries (simple trim only)")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)

        self.empty, _ = empty_state("✂️", "No clip loaded",
                                    "Choose Preview on a highlight card to load it here.")
        lay.addWidget(self.empty)

        self.body = QWidget()
        bl = QHBoxLayout(self.body)
        bl.setSpacing(16)
        self.preview_lbl = QLabel()
        self.preview_lbl.setMinimumSize(360, 220)
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        self.preview_lbl.setStyleSheet(f"background:{PALETTE['viewport']}; border-radius:8px;")
        self.preview_lbl.setText("No frame")
        bl.addWidget(self.preview_lbl, 3)

        self.vertical_lbl = QLabel()
        self.vertical_lbl.setFixedWidth(210)
        self.vertical_lbl.setMinimumHeight(370)
        self.vertical_lbl.setAlignment(Qt.AlignCenter)
        self.vertical_lbl.setStyleSheet(f"background:{PALETTE['viewport']}; border-radius:8px;")
        self.vertical_lbl.setText("Vertical\npreview")
        bl.addWidget(self.vertical_lbl, 1)
        lay.addWidget(self.body)
        self.body.hide()

        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.valueChanged.connect(self._on_scrub)
        lay.addWidget(self.timeline)

        ctrls = QHBoxLayout()
        ctrls.addWidget(QLabel("Start:"))
        self.start_sb = QDoubleSpinBox()
        self.start_sb.setSuffix(" s"); self.start_sb.setDecimals(2)
        self.start_sb.valueChanged.connect(self._on_start)
        ctrls.addWidget(self.start_sb)
        set_start = QPushButton("Set from playhead")
        set_start.setObjectName("ghost")
        set_start.clicked.connect(lambda: self.start_sb.setValue(self.current_time()))
        ctrls.addWidget(set_start)
        ctrls.addStretch()
        ctrls.addWidget(QLabel("End:"))
        self.end_sb = QDoubleSpinBox()
        self.end_sb.setSuffix(" s"); self.end_sb.setDecimals(2)
        self.end_sb.valueChanged.connect(self._on_end)
        ctrls.addWidget(self.end_sb)
        set_end = QPushButton("Set from playhead")
        set_end.setObjectName("ghost")
        set_end.clicked.connect(lambda: self.end_sb.setValue(self.current_time()))
        ctrls.addWidget(set_end)
        lay.addLayout(ctrls)

        self.dur_lbl = QLabel("Duration: —")
        self.dur_lbl.setObjectName("accent")
        lay.addWidget(self.dur_lbl)

        actions = QHBoxLayout()
        actions.addStretch()
        exp = QPushButton("Export this clip")
        exp.setObjectName("primary")
        exp.clicked.connect(self._export)
        actions.addWidget(exp)
        lay.addLayout(actions)

    def load_highlight(self, hid: int) -> None:
        h = self.ctx.db.get_highlight(hid)
        if not h:
            return
        m = self.ctx.db.get_match(h.match_id)
        if not m:
            return
        self.highlight = h
        self.video_path = m.path
        self.duration = m.duration
        self.start, self.end = h.start, h.end
        self.empty.hide(); self.body.show()
        for sb in (self.start_sb, self.end_sb):
            sb.setRange(0.0, self.duration)
        self.start_sb.setValue(self.start)
        self.end_sb.setValue(self.end)
        self.timeline.setValue(int(self.start / max(0.01, self.duration) * 1000))
        self._render_frame(self.start)

    def current_time(self) -> float:
        return self.timeline.value() / 1000.0 * self.duration

    def _on_scrub(self, _value: int) -> None:
        if self.video_path:
            self._render_frame(self.current_time())

    def _on_start(self, v: float) -> None:
        self.start = v
        if self.end <= v:
            self.end_sb.setValue(min(self.duration, v + 1))
        self._update_duration()

    def _on_end(self, v: float) -> None:
        self.end = v
        if self.start >= v:
            self.start_sb.setValue(max(0.0, v - 1))
        self._update_duration()

    def _update_duration(self) -> None:
        self.dur_lbl.setText(f"Duration: {max(0, self.end - self.start):.2f} s")

    def _render_frame(self, t: float) -> None:
        frame = frame_at(self.video_path, t)
        if frame is None:
            return
        qimg = qimage_from_frame(frame)
        pm = QPixmap.fromImage(qimg)
        self.preview_lbl.setPixmap(
            pm.scaled(self.preview_lbl.size() - QSize(20, 20),
                      Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.vertical_lbl.setPixmap(self._vertical_preview(pm))

    @staticmethod
    def _vertical_preview(pm: QPixmap) -> QPixmap:
        """Approximate blurred-background vertical layout for preview."""
        vw, vh = 180, 320
        canvas = QImage(vw, vh, QImage.Format_RGB32)
        canvas.fill(QColor(PALETTE['viewport']))
        painter = QPainter(canvas)
        # blurred, enlarged background
        bg = pm.scaled(vw, vh, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.setOpacity(0.25)
        painter.drawPixmap((vw - bg.width()) // 2, (vh - bg.height()) // 2, bg)
        painter.setOpacity(1.0)
        # foreground letterboxed
        fg = pm.scaled(vw, int(pm.height() * vw / max(1, pm.width())),
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap((vw - fg.width()) // 2, (vh - fg.height()) // 2, fg)
        painter.end()
        return QPixmap.fromImage(canvas)

    def _export(self) -> None:
        if self.highlight:
            self.export_requested.emit(self.highlight.id, self.start, self.end)
