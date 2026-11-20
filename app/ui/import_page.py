"""Match import page with drag-and-drop, validation and metadata display."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget, QHBoxLayout,
)

from ..bootstrap import AppContext
from ..core.exceptions import DatabaseError
from ..core.project_manager import ProjectManager
from ..media.media_validator import MediaValidator
from ..utils.logging import get_logger
from .widgets.common import Card, ToastLabel

log = get_logger("ui.import")


class DropZone(QLabel):
    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__(
            "Drop your PUBG recording here\n\n"
            "or click to browse for an MP4 file"
        )
        self.setObjectName("dropZone")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(200)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self.styleSheet() + "font-size: 15px; color: #9AA5AD;")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setObjectName("dropZoneActive")
            self.style().unpolish(self); self.style().polish(self)

    def dragLeaveEvent(self, e) -> None:
        self.setObjectName("dropZone")
        self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, e: QDropEvent) -> None:
        self.setObjectName("dropZone")
        self.style().unpolish(self); self.style().polish(self)
        urls = e.mimeData().urls()
        if urls:
            self.file_dropped.emit(urls[0].toLocalFile())

    def mousePressEvent(self, e) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PUBG recording", "",
            "Video files (*.mp4 *.mkv *.mov *.m4v);;All files (*.*)")
        if path:
            self.file_dropped.emit(path)


class ImportPage(QWidget):
    match_ready = Signal(int, str, float)  # match_id, path, duration

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.validator = MediaValidator()
        self.projects = ProjectManager(ctx.db)
        self.current_path: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        title = QLabel("Import recording")
        title.setObjectName("pageTitle")
        sub = QLabel("Add a complete PUBG match recorded with OBS Studio")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)

        self.drop = DropZone()
        self.drop.file_dropped.connect(self.on_file)
        lay.addWidget(self.drop)

        self.info = Card()
        il = QVBoxLayout(self.info)
        il.setContentsMargins(18, 14, 18, 14)
        self.meta_lbl = QLabel("No file selected")
        self.meta_lbl.setObjectName("muted")
        self.meta_lbl.setWordWrap(True)
        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        il.addWidget(self.meta_lbl); il.addWidget(self.status_lbl)
        lay.addWidget(self.info)
        self.info.hide()

        self.toast = ToastLabel()
        lay.addWidget(self.toast)

        actions = QHBoxLayout()
        actions.addStretch()
        self.import_btn = QPushButton("Import & Analyse")
        self.import_btn.setObjectName("primary")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.do_import)
        actions.addWidget(self.import_btn)
        lay.addLayout(actions)
        lay.addStretch()

    def on_file(self, path: str) -> None:
        self.current_path = None
        self.import_btn.setEnabled(False)
        self.info.show()
        self.meta_lbl.setText(f"Checking <b>{Path(path).name}</b> …")
        self.status_lbl.setText("")
        result = self.validator.validate(path)
        if not result.valid:
            self.meta_lbl.setText(f"❌ {Path(path).name}")
            self.status_lbl.setStyleSheet("color:#FF8A8A;")
            self.status_lbl.setText("\n".join("• " + e for e in result.errors))
            return
        meta = result.metadata
        self.meta_lbl.setText(
            f"<b style='color:#7CFC00'>✓ {meta.name}</b><br>"
            f"Duration: {meta.duration/60:.1f} min ({meta.duration:.0f}s)<br>"
            f"Resolution: {meta.width}×{meta.height} &nbsp;•&nbsp; FPS: {meta.fps:.0f}<br>"
            f"Video: {meta.video_codec} &nbsp;•&nbsp; Audio: {meta.audio_codec or 'none'}<br>"
            f"Size: {meta.file_size/1e9:.2f} GB"
        )
        self.meta_lbl.setTextFormat(Qt.RichText)
        if result.warnings:
            self.status_lbl.setStyleSheet("color:#E8C56A;")
            self.status_lbl.setText("\n".join("⚠ " + w for w in result.warnings))
        else:
            self.status_lbl.setStyleSheet("color:#7CFC00;")
            self.status_lbl.setText("✓ Validation passed — ready to analyse.")
        self.current_path = path
        self.import_btn.setEnabled(True)

    def do_import(self) -> None:
        if not self.current_path:
            return
        try:
            m = self.projects.import_match(self.current_path)
            self.toast.show_message(f"Imported {m.name}")
            self.match_ready.emit(m.id, self.current_path, m.duration)
        except DatabaseError as exc:
            self.toast.show_message(exc.user_message(), error=True)
        except Exception as exc:  # noqa: BLE001
            log.exception("Import failed")
            self.toast.show_message(f"Import failed: {exc}", error=True)
