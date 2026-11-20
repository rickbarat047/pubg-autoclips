"""Main application window: navigation and workflow orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..bootstrap import AppContext
from ..config import AppSettings
from ..core.task_queue import CancellationToken, CancelledError
from ..database.models import Highlight
from ..rendering.export_manager import ExportManager, ExportRequest
from ..utils.hardware import detect_hardware
from ..utils.logging import get_logger
from ..utils.paths import default_output_folder, resource_base
from ..workers.analysis_worker import AnalysisWorker
from ..workers.export_worker import ExportJob, ExportWorker
from .about_page import AboutPage
from .analysis_page import AnalysisPage
from .calibration_dialog import CalibrationDialog
from .clips_page import ClipsPage
from .dashboard import DashboardPage
from .editor_page import EditorPage
from .import_page import ImportPage
from .onboarding import OnboardingWizard
from .settings_page import SettingsPage

log = get_logger("ui.main")

NAV = [
    ("Dashboard", "▦"), ("Import", "⬇"), ("Analysis", "◉"),
    ("Highlights", "✦"), ("Editor", "✂"), ("Settings", "⚙"), ("About", "ⓘ"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)
        self._analysis_thread: QThread | None = None
        self._analysis_worker = None  # keep alive: Qt does not hold a Python ref
        self._export_thread: QThread | None = None
        self._export_worker = None
        self._analysis_token: CancellationToken | None = None
        self._export_token: CancellationToken | None = None
        self._current_job_id: int | None = None
        self.current_match_id: int | None = None

        self._build_ui()
        self._connect()

    def _build_ui(self) -> None:
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(8)
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        sub = QLabel("AUTOCLIP STUDIO")
        sub.setObjectName("brandSub")
        sl.addWidget(brand); sl.addWidget(sub)
        sl.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        self.pages: list[QWidget] = [
            DashboardPage(self.ctx), ImportPage(self.ctx), AnalysisPage(),
            ClipsPage(self.ctx), EditorPage(self.ctx), SettingsPage(self.ctx),
            AboutPage(),
        ]
        for i, (name, icon) in enumerate(NAV):
            b = QPushButton(f"  {icon}   {name}")
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(b, i)
            sl.addWidget(b)
            self.nav_buttons.append(b)
        self.nav_buttons[0].setChecked(True)
        sl.addStretch()

        try:
            hw = detect_hardware()
            info = QLabel(f"{hw.cpu.cores_logical} threads · "
                          f"{hw.memory.total_gb:.0f} GB RAM\n{hw.gpu.vendor or 'GPU'}")
            info.setObjectName("muted")
            info.setWordWrap(True)
            sl.addWidget(info)
        except Exception:
            pass
        sl.addWidget(QLabel(f"v{__version__} · local-first"))

        self.stack = QStackedWidget()
        self.stack.setObjectName("content")
        for p in self.pages:
            self.stack.addWidget(p)
        h.addWidget(sidebar, 0)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

    def _connect(self) -> None:
        self.nav_group.idClicked.connect(self.navigate)
        dash: DashboardPage = self.pages[0]
        imp: ImportPage = self.pages[1]
        self.analysis: AnalysisPage = self.pages[2]
        self.clips: ClipsPage = self.pages[3]
        self.editor: EditorPage = self.pages[4]
        self.settings_page: SettingsPage = self.pages[5]
        dash.import_requested.connect(lambda: self.navigate(1))
        imp.match_ready.connect(self.start_analysis)
        self.analysis.cancel_requested.connect(self.cancel_analysis)
        self.analysis.pause_requested.connect(self.pause_analysis)
        self.clips.preview_requested.connect(self.open_editor)
        self.clips.export_requested.connect(self.export_highlights)
        self.editor.export_requested.connect(self.export_edited)
        self.settings_page.calibrate_requested.connect(self.open_calibration)
        self.settings_page.settings_saved.connect(self._on_settings_saved)

    @Slot(int)
    def navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.pages[0].refresh()
        if index == 3:
            self.clips.set_match(self.current_match_id)

    def open_calibration(self) -> None:
        dlg = CalibrationDialog(self.ctx.settings.calibration, self)
        if dlg.exec() == QDialog.Accepted:
            r = dlg.region()
            if r:
                self.ctx.settings.calibration = r
                self.ctx.save_settings()
                self.settings_page.load()
                QMessageBox.information(self, "Calibration saved",
                                        "Kill-feed region saved successfully.")

    def _on_settings_saved(self) -> None:
        self.statusBar().showMessage("Settings saved")
        self.pages[0].refresh()

    # ---------- Analysis ----------
    @Slot(int, str, float)
    def start_analysis(self, match_id: int, path: str, duration: float) -> None:
        if self._analysis_thread and self._analysis_thread.isRunning():
            QMessageBox.warning(self, "Busy", "An analysis is already running.")
            return
        if not self.ctx.settings.ign:
            QMessageBox.warning(self, "IGN required",
                                "Set your in-game name in Settings before analysing.")
            self.navigate(5)
            return
        job = self.ctx.db.create_job(match_id)
        self._current_job_id = job.id
        token = CancellationToken()
        self.ctx.jobs.register(job.id, "analysis", match_id, token)
        self._analysis_token = token
        self.ctx.db.update_job(job.id, status="running", stage="starting")

        worker = AnalysisWorker(path, match_id, job.id, duration,
                                self.ctx.settings, self.ctx.db, token)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.analysis.update_progress)
        worker.finished.connect(self._analysis_done)
        worker.error.connect(self._analysis_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._analysis_thread = thread
        self._analysis_worker = worker  # MUST persist until the thread starts
        self.ctx.register_thread(thread)
        self.current_match_id = match_id
        name = Path(path).name
        self.analysis.start(name)
        self.navigate(2)
        thread.start()
        self.statusBar().showMessage(f"Analysing {name}")

    @Slot(object)
    def _analysis_done(self, result) -> None:
        self.analysis.finish()
        self.analysis.set_counts(len(result.events), len(result.clips))
        self.pages[0].refresh()
        self.clips.set_match(self.current_match_id)
        self.statusBar().showMessage(
            f"Analysis complete — {len(result.events)} events, {len(result.clips)} clips")
        if self._current_job_id is not None:
            self.ctx.jobs.unregister(self._current_job_id)
        if self.ctx.settings.auto_export and getattr(result, "highlight_ids", None):
            ids = result.highlight_ids[:self.ctx.settings.auto_export_max_clips]
            self.statusBar().showMessage(
                f"Auto-exporting top {len(ids)} clip(s) to "
                f"{self.ctx.settings.output_folder}")
            self._start_export([(hid, None, None) for hid in ids])

    @Slot(str, str)
    def _analysis_error(self, status: str, message: str) -> None:
        self.analysis.set_error(f"{status}: {message}")
        self.statusBar().showMessage("Analysis failed")
        QMessageBox.warning(self, "Analysis issue", message[:600])

    def cancel_analysis(self) -> None:
        if self._analysis_token:
            self._analysis_token.cancel()
            self.statusBar().showMessage("Cancelling analysis…")

    def pause_analysis(self, paused: bool) -> None:
        token = self._analysis_token
        if not token:
            return
        if paused:
            token.pause()
        else:
            token.resume()

    # ---------- Clips / export ----------
    @Slot(int)
    def open_editor(self, hid: int) -> None:
        self.editor.load_highlight(hid)
        self.navigate(4)

    def _make_export_request(self, hid: int, start: float | None = None,
                             end: float | None = None) -> ExportRequest | None:
        h: Highlight | None = self.ctx.db.get_highlight(hid)
        if not h:
            return None
        m = self.ctx.db.get_match(h.match_id)
        if not m:
            return None
        out_dir = self.ctx.settings.output_folder or default_output_folder()
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        name = f"{Path(m.name).stem}_clip_{h.start:.0f}s_{h.id}.mp4"
        return ExportRequest(
            video_path=m.path, start=start if start is not None else h.start,
            end=end if end is not None else h.end,
            output_path=str(Path(out_dir) / name),
            source_has_audio=bool(m.audio_codec),
        )

    @Slot(list)
    def export_highlights(self, hids: list[int]) -> None:
        self._start_export([(h, None, None) for h in hids])

    @Slot(int, float, float)
    def export_edited(self, hid: int, start: float, end: float) -> None:
        self._start_export([(hid, start, end)])

    def _start_export(self, items: list[tuple[int, float | None, float | None]]) -> None:
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Busy", "An export is already running.")
            return
        jobs: list[ExportJob] = []
        for hid, start, end in items:
            req = self._make_export_request(hid, start, end)
            if not req:
                continue
            rec = self.ctx.db.add_export(
                clip_id=hid, path=req.output_path, status="pending",
                layout=self.ctx.settings.render.layout)
            jobs.append(ExportJob(req, hid, rec.id))
        if not jobs:
            return
        token = CancellationToken()
        self._export_token = token
        manager = ExportManager(self.ctx.settings, self.ctx.settings.ffmpeg_path)
        worker = ExportWorker(jobs, self.ctx.settings, manager, token)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda c, t, m: self.statusBar().showMessage(m))
        worker.one_done.connect(self._export_one_done)
        worker.finished.connect(self._export_finished)
        worker.error.connect(lambda m: log.warning(m))
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._export_thread = thread
        self._export_worker = worker
        self.ctx.register_thread(thread)
        thread.start()
        self.statusBar().showMessage(f"Exporting {len(jobs)} clip(s)…")

    @Slot(int, str)
    def _export_one_done(self, export_id: int, path: str) -> None:
        size = Path(path).stat().st_size if Path(path).exists() else 0
        self.ctx.db.update_export(export_id, status="done", size_bytes=size)
        self.statusBar().showMessage(f"Exported {Path(path).name}")

    @Slot(int, int)
    def _export_finished(self, ok: int, failed: int) -> None:
        self.pages[0].refresh()
        QMessageBox.information(self, "Export complete",
                                f"Exported {ok} clip(s)." +
                                (f" {failed} failed." if failed else ""))

    def closeEvent(self, event) -> None:
        for thread in (self._analysis_thread, self._export_thread):
            if thread and thread.isRunning():
                reply = QMessageBox.question(
                    self, "Still working", "A task is still running. Cancel and quit?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
                thread.quit()
                thread.wait(3000)
        self.ctx.shutdown()
        event.accept()
