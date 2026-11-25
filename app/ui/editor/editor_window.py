"""Single-window editor shell.

Replaces the old stacked-page navigation with one editor workspace: a top bar,
a left Assets panel, a centre Preview, a right Inspector, and a bottom Timeline.
The workflow orchestration (analysis/export/compilation workers) lives in
``MainWindow`` which subclasses this shell.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)
from pathlib import Path

from ... import APP_NAME, __version__


class EditorWindow(QMainWindow):
    """The single editor workspace shell (five regions + workflow signals)."""

    import_requested = Signal()
    export_requested = Signal()
    settings_requested = Signal()
    about_requested = Signal()
    calibration_requested = Signal()
    search_changed = Signal(str)

    def __init__(self, ctx=None, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 640)
        central = QWidget(self)
        self.setCentralWidget(central)
        self._build_shell(central)

    def _build_shell(self, central: QWidget) -> None:
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Top bar ----
        self.topbar = QWidget(central)
        self.topbar.setObjectName("topbar")
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(16, 10, 16, 10)
        top.setSpacing(12)

        brand = QLabel(f"{APP_NAME}  ")
        brand.setObjectName("brand")
        top.addWidget(brand)

        self.search = QLineEdit(self.topbar)
        self.search.setObjectName("editorSearch")
        self.search.setPlaceholderText("Search clips…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.search_changed.emit)
        top.addWidget(self.search, 1)

        self.import_btn = QPushButton("Import", self.topbar)
        self.import_btn.setObjectName("ghost")
        self.import_btn.setToolTip("Import a PUBG match recording")
        self.import_btn.clicked.connect(self.import_requested.emit)
        top.addWidget(self.import_btn)

        self.settings_btn = QPushButton("Settings", self.topbar)
        self.settings_btn.setObjectName("ghost")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        top.addWidget(self.settings_btn)

        self.about_btn = QPushButton("About", self.topbar)
        self.about_btn.setObjectName("ghost")
        self.about_btn.clicked.connect(self.about_requested.emit)
        top.addWidget(self.about_btn)

        self.calibrate_btn = QPushButton("Calibrate", self.topbar)
        self.calibrate_btn.setObjectName("ghost")
        self.calibrate_btn.setToolTip("Set the kill-feed region")
        self.calibrate_btn.clicked.connect(self.calibration_requested.emit)
        top.addWidget(self.calibrate_btn)

        self.export_btn = QPushButton("EXPORT", self.topbar)
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.export_requested.emit)
        top.addWidget(self.export_btn)

        root.addWidget(self.topbar)

        # ---- Middle: three-panel splitter ----
        splitter = QSplitter(central)
        splitter.setObjectName("editorSplitter")
        splitter.setChildrenCollapsible(False)

        self.assets_panel = QWidget(splitter)
        self.assets_panel.setObjectName("assetsPanel")
        self.assets_panel.setMinimumWidth(240)
        splitter.addWidget(self.assets_panel)

        self.preview_panel = QWidget(splitter)
        self.preview_panel.setObjectName("previewPanel")
        self.preview_panel.setMinimumWidth(400)
        splitter.addWidget(self.preview_panel)

        self.inspector_panel = QWidget(splitter)
        self.inspector_panel.setObjectName("inspectorPanel")
        self.inspector_panel.setMinimumWidth(240)
        splitter.addWidget(self.inspector_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        root.addWidget(splitter, 1)

        # ---- Bottom: timeline ----
        self.timeline_panel = QWidget(central)
        self.timeline_panel.setObjectName("timelinePanel")
        self.timeline_panel.setMinimumHeight(200)
        self.timeline_panel.setMaximumHeight(240)
        root.addWidget(self.timeline_panel)

        # ---- Result card (hidden until an export finishes) ----
        self.result_card = QWidget(central)
        self.result_card.setObjectName("card")
        rc = QHBoxLayout(self.result_card)
        rc.setContentsMargins(14, 10, 14, 10)
        rc.setSpacing(12)
        self.result_label = QLabel("")
        self.result_label.setObjectName("muted")
        rc.addWidget(self.result_label, 1)
        self.result_play_btn = QPushButton("Play Video")
        self.result_play_btn.setObjectName("ghost")
        self.result_play_btn.clicked.connect(self._play_result)
        rc.addWidget(self.result_play_btn)
        self.result_folder_btn = QPushButton("Open Folder")
        self.result_folder_btn.setObjectName("ghost")
        self.result_folder_btn.clicked.connect(self._open_result_folder)
        rc.addWidget(self.result_folder_btn)
        self.result_back_btn = QPushButton("Back to workspace")
        self.result_back_btn.setObjectName("ghost")
        self.result_back_btn.clicked.connect(self._hide_result)
        rc.addWidget(self.result_back_btn)
        self.result_card.hide()
        root.addWidget(self.result_card)

        # Region placeholder labels — replaced by real panels in later tasks.
        for panel, caption in (
            (self.assets_panel, "Assets"),
            (self.preview_panel, "Preview"),
            (self.inspector_panel, "Inspector"),
            (self.timeline_panel, "Timeline"),
        ):
            lay = QVBoxLayout(panel)
            lay.setContentsMargins(12, 12, 12, 12)
            lbl = QLabel(caption)
            lbl.setObjectName("muted")
            lay.addWidget(lbl)

    def install_panel(self, region: QWidget, widget: QWidget) -> None:
        """Replace a placeholder region's contents with a real panel widget."""
        lay = region.layout()
        if lay is None:
            lay = QVBoxLayout(region)
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        lay.addWidget(widget)

    # ---- Export result + workflow hooks --------------------------------
    def export(self) -> None:
        """Trigger the export workflow (wired to MainWindow's worker path)."""
        self.export_requested.emit()

    def show_result(self, path: str, duration: float = 0.0) -> None:
        """Reveal the result card with Play / Open Folder / Back actions."""
        self._result_path = path
        if path:
            self.result_label.setText(
                f"Ready: {Path(path).name}" +
                (f"  •  {duration:.0f}s" if duration else ""))
        else:
            self.result_label.setText("Export failed — see the log for details.")
        self.result_card.show()

    def _play_result(self) -> None:
        path = getattr(self, "_result_path", "")
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_result_folder(self) -> None:
        path = getattr(self, "_result_path", "")
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _hide_result(self) -> None:
        self.result_card.hide()
