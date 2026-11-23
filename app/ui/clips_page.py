"""Highlight gallery: cards, filters, keep/discard, export selection."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGraphicsOpacityEffect, QGridLayout,
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..core.task_queue import CancellationToken
from ..database.db import DatabaseManager
from ..media.thumbnail import thumbnail_for_highlight
from ..utils.paths import thumbnails_dir
from ..workers.thumbnail_worker import ThumbJob, ThumbnailWorker
from .widgets.common import Card, empty_state

CATEGORY_FILTERS = ["All", "KILL", "MULTI_KILL", "CLUTCH_CANDIDATE", "COMBAT", "UNCERTAIN"]


class ClipCard(Card):
    play_requested = Signal(int)
    toggled_keep = Signal(int, bool)

    def __init__(self, highlight, video_path: str, parent=None) -> None:
        super().__init__(parent, hover=True)
        self.hid = highlight.id
        self.keep = bool(highlight.keep)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.thumb = QLabel()
        self.thumb.setFixedHeight(140)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#0F1214; border-radius:6px;")
        self.thumb.setText("No preview")
        lay.addWidget(self.thumb)

        cat = QLabel(highlight.category.replace("_", " ").title())
        cat.setObjectName("accent")
        cat.setStyleSheet("font-weight:700;")
        lay.addWidget(cat)
        t = f"{highlight.start:.0f}s → {highlight.end:.0f}s  ({highlight.duration:.0f}s)"
        tm = QLabel(t)
        tm.setObjectName("muted")
        lay.addWidget(tm)
        sc = QLabel(f"Score {highlight.score:.0f}")
        sc.setStyleSheet("color:#E8ECEF; font-weight:600;")
        lay.addWidget(sc)

        row = QHBoxLayout()
        self.export_chk = QCheckBox("Export")
        self.export_chk.setChecked(self.keep)
        self.play_button = QPushButton("▶ Play")
        self.play_button.setObjectName("primary")
        self.play_button.setToolTip("Play this clip from the original recording")
        self.play_button.clicked.connect(lambda: self.play_requested.emit(self.hid))
        row.addWidget(self.export_chk); row.addStretch(); row.addWidget(self.play_button)
        lay.addLayout(row)
        self.export_chk.toggled.connect(self._on_keep)

    def set_thumbnail(self, path: str) -> None:
        if not path:
            return
        pm = QPixmap(path)
        if not pm.isNull():
            self.thumb.setPixmap(pm.scaledToHeight(140, Qt.SmoothTransformation))

    def _on_keep(self, checked: bool) -> None:
        self.keep = checked
        self.toggled_keep.emit(self.hid, checked)

    def selected_for_export(self) -> bool:
        return self.export_chk.isChecked()


class ClipsPage(QWidget):
    play_requested = Signal(int)
    # Temporary alias: MainWindow still wires this to the old Editor page.
    # Task 7 removes both this signal and that connection.
    preview_requested = Signal(int)
    export_requested = Signal(list)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.cards: dict[int, ClipCard] = {}
        self.match_id: int | None = None
        self._thumb_thread: QThread | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("Highlights")
        title.setObjectName("pageTitle")
        sub = QLabel("Review detected highlights and choose clips to export")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)

        bar = QHBoxLayout()
        self.filter = QComboBox()
        self.filter.addItems(CATEGORY_FILTERS)
        self.filter.currentTextChanged.connect(self._apply_filter)
        bar.addWidget(QLabel("Filter:")); bar.addWidget(self.filter)
        bar.addStretch()
        self.export_btn = QPushButton("Export selected")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._export)
        bar.addWidget(self.export_btn)
        lay.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setAlignment(Qt.AlignTop)
        self.grid.setSpacing(16)
        self.scroll.setWidget(self.grid_host)
        lay.addWidget(self.scroll)
        self.refresh()

    def set_match(self, match_id: int) -> None:
        self.match_id = match_id
        self.refresh()

    def refresh(self) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.cards.clear()
        highlights = self.ctx.db.list_highlights(self.match_id)
        matches = {m.id: m for m in self.ctx.db.list_matches()}
        if not highlights:
            empty, _ = empty_state("✨", "No highlights yet",
                                   "Analyse a recording to detect highlight candidates.")
            self.grid.addWidget(empty, 0, 0)
            return
        jobs: list[ThumbJob] = []
        for i, h in enumerate(highlights):
            m = matches.get(h.match_id)
            if not m:
                continue
            card = ClipCard(h, m.path)
            card.play_requested.connect(self.play_requested.emit)
            card.play_requested.connect(self.preview_requested.emit)  # T7 removes
            card.toggled_keep.connect(self._on_keep)
            self.cards[h.id] = card
            self.grid.addWidget(card, i // 3, i % 3)
            out = str(thumbnails_dir() / f"m{h.match_id}_h{h.id}.jpg")
            try:
                thumbnail_for_highlight(h.match_id, h.id, m.path, (h.start + h.end) / 2)
            except Exception:
                pass
            card.set_thumbnail(out)
        self._apply_filter(self.filter.currentText())

    def _apply_filter(self, text: str) -> None:
        for hid, card in self.cards.items():
            h = self.ctx.db.get_highlight(hid)
            if not h:
                continue
            cat = h.category
            show = True
            if text == "UNCERTAIN":
                show = cat in ("UNKNOWN", "COMBAT")
            elif text != "All":
                show = cat == text
            card.setVisible(show)

    def _on_keep(self, hid: int, keep: bool) -> None:
        self.ctx.db.update_highlight(hid, keep=int(keep))

    def _export(self) -> None:
        selected = [hid for hid, c in self.cards.items() if c.selected_for_export()]
        if selected:
            self.export_requested.emit(selected)
