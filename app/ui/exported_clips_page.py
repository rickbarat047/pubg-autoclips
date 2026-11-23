"""Exported Clips page — the only entry point for finished videos."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..database.models import Export
from .video_player_dialog import VideoPlayerDialog
from .widgets.common import Card, empty_state, section


class ExportedClipsPage(QWidget):
    """Lists finished compilations and individual clips."""

    review_requested = Signal(int)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.export_rows: list[QWidget] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel("Exported Clips")
        title.setObjectName("pageTitle")
        sub = QLabel("Finished videos, ready to watch or share")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title)
        lay.addWidget(sub)

        header = QHBoxLayout()
        self.review_btn = QPushButton("Review latest match")
        self.review_btn.setObjectName("primary")
        self.review_btn.setEnabled(False)
        self._latest_match: int | None = None
        self.review_btn.clicked.connect(self._on_review_clicked)
        header.addWidget(self.review_btn)
        header.addStretch()
        lay.addLayout(header)

        self.host = QWidget()
        self.host_lay = QVBoxLayout(self.host)
        self.host_lay.setContentsMargins(0, 0, 0, 0)
        self.host_lay.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self.host)
        lay.addWidget(scroll)

        empty, _ = empty_state(
            "▤", "No exported clips yet",
            "Analyse a match and export a compilation — it will appear here.",
        )
        self.empty_label = empty
        lay.addWidget(self.empty_label)

    def refresh(self) -> None:
        for row in self.export_rows:
            row.setParent(None)
            row.deleteLater()
        self.export_rows.clear()

        exports: list[Export] = list(self.ctx.db.list_exports(limit=100))
        self.empty_label.setVisible(not exports)

        latest_match: int | None = None
        for exp in exports:
            if exp.status != "done":
                continue
            if exp.match_id is not None and latest_match is None:
                latest_match = exp.match_id
            self.export_rows.append(self._make_row(exp))
        self._latest_match = latest_match
        self.review_btn.setEnabled(latest_match is not None)

    def _on_review_clicked(self) -> None:
        if self._latest_match is not None:
            self.review_requested.emit(self._latest_match)

    def _make_row(self, exp: Export) -> QWidget:
        card = Card()
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 12, 16, 12)

        info = QVBoxLayout()
        name = QLabel(exp.path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
        name.setObjectName("cardTitle")
        info.addWidget(name)
        detail = QLabel(self._describe(exp))
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        info.addWidget(detail)
        row.addLayout(info, 1)

        play = QPushButton("▶ Play")
        play.setObjectName("primary")
        play.clicked.connect(lambda: self._play(exp.path))
        row.addWidget(play)

        folder = QPushButton("Open Folder")
        folder.setObjectName("ghost")
        folder.clicked.connect(lambda: self._open_folder(exp.path))
        row.addWidget(folder)

        self.host_lay.addWidget(card)
        return card

    @staticmethod
    def _describe(exp: Export) -> str:
        bits: list[str] = []
        if exp.export_type == "compilation":
            bits.append("Highlight compilation")
        else:
            bits.append("Individual clip")
        if exp.duration:
            bits.append(f"{exp.duration:.0f}s")
        if exp.segment_count:
            bits.append(f"{exp.segment_count} highlights")
        bits.append(f"{exp.size_bytes / 1_048_576:.1f} MB")
        return "  •  ".join(bits)

    def _play(self, path: str) -> None:
        if not Path(path).exists():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "File not found",
                f"This export is no longer on disk:\n{path}",
            )
            return
        self._player = VideoPlayerDialog(path, parent=self)
        self._player.show()

    @staticmethod
    def _open_folder(path: str) -> None:
        folder = Path(path).parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
