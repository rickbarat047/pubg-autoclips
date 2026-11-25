"""Main application window: navigation and workflow orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from .editor.assets_panel import AssetsPanel
from .editor.editor_window import EditorWindow
from .editor.preview_panel import PreviewPanel
from .editor.inspector_panel import InspectorPanel
from .editor.timeline_panel import TimelinePanel

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
from ..workers.compilation_worker import CompilationWorker
from ..workers.export_worker import ExportJob, ExportWorker
from .about_page import AboutPage
from .analysis_page import AnalysisPage
from .calibration_dialog import CalibrationDialog
from .clips_page import ClipsPage
from .compile_page import CompilePage
from .dashboard import DashboardPage
from .editor_page import EditorPage
from .exported_clips_page import ExportedClipsPage
from .import_page import ImportPage
from .onboarding import OnboardingWizard
from .settings_page import SettingsPage
from .video_player_dialog import VideoPlayerDialog

log = get_logger("ui.main")

# Page indices (kept as constants to avoid magic-number bugs).
PAGE_DASHBOARD, PAGE_IMPORT, PAGE_ANALYSIS = 0, 1, 2
PAGE_CLIPS, PAGE_EDITOR, PAGE_EXPORT = 3, 4, 5
PAGE_SETTINGS, PAGE_ABOUT = 6, 7
PAGE_EXPORTED = 8

NAV = [
    ("Dashboard", "▦"), ("Import", "⬇"), ("Exported Clips", "▤"),
]
# Sidebar buttons map to stack pages; the other pages are reached
# programmatically after analysis and are intentionally not in the sidebar.
NAV_TARGETS = (PAGE_DASHBOARD, PAGE_IMPORT, PAGE_EXPORTED)


class MainWindow(EditorWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self._analysis_thread: QThread | None = None
        self._analysis_worker = None  # keep alive: Qt does not hold a Python ref
        self._export_thread: QThread | None = None
        self._export_worker = None
        self._compilation_thread: QThread | None = None
        self._compilation_worker = None
        self._compilation_token: CancellationToken | None = None
        self._analysis_token: CancellationToken | None = None
        self._export_token: CancellationToken | None = None
        self._current_job_id: int | None = None
        self.current_match_id: int | None = None

        # The visible shell (topbar / panels / timeline) is built by
        # EditorWindow.__init__.  Old page widgets are kept as hidden workflow
        # helpers so the analysis/export/compilation orchestration keeps working
        # until the editor panels are wired in the following tasks.
        self.pages: list[QWidget] = [
            DashboardPage(self.ctx), ImportPage(self.ctx), AnalysisPage(),
            ClipsPage(self.ctx), EditorPage(self.ctx), CompilePage(self.ctx),
            SettingsPage(self.ctx), AboutPage(), ExportedClipsPage(self.ctx),
        ]
        for p in self.pages:
            p.hide()
        self._dialogs: list[QDialog] = []

        # Wire the real Assets panel into the shell and keep a ref alive.
        self.assets = AssetsPanel(self.ctx)
        self.install_panel(self.assets_panel, self.assets)
        self.search_changed.connect(self.assets.filter)
        self.assets.clip_selected.connect(self._on_asset_clip_selected)

        # Wire the real centre preview panel into the shell.
        self.preview = PreviewPanel(self)
        self.install_panel(self.preview_panel, self.preview)
        # Wire inspector + timeline panels into the shell.
        self.inspector = InspectorPanel(self)
        self.install_panel(self.inspector_panel, self.inspector)
        self.timeline = TimelinePanel(self)
        self.install_panel(self.timeline_panel, self.timeline)
        self.preview.position_changed.connect(self.timeline.set_playhead)
        self.timeline.playhead_changed.connect(self.preview.seek)
        self.timeline.range_added.connect(self._on_manual_range_added)
        self.inspector.bounds_changed.connect(self._on_manual_bounds_changed)
        self.inspector.add_at_playhead.connect(self._on_add_at_playhead)
        self.inspector.remove_requested.connect(self._on_remove_segment)
        self.inspector.split_requested.connect(self._on_split_segment)
        self._connect()

    def _connect(self) -> None:
        dash: DashboardPage = self.pages[0]
        self.dash = dash
        imp: ImportPage = self.pages[1]
        self.analysis: AnalysisPage = self.pages[PAGE_ANALYSIS]
        self.clips: ClipsPage = self.pages[PAGE_CLIPS]
        self.editor: EditorPage = self.pages[PAGE_EDITOR]
        self.compile: CompilePage = self.pages[PAGE_EXPORT]
        self.settings_page: SettingsPage = self.pages[PAGE_SETTINGS]
        self.exported: ExportedClipsPage = self.pages[PAGE_EXPORTED]
        dash.import_requested.connect(self.open_import)
        dash.review_requested.connect(self.open_review)
        dash.highlights_requested.connect(self.open_highlights)
        dash.settings_requested.connect(self.open_settings)
        dash.about_requested.connect(self.open_about)
        self.exported.review_requested.connect(self.open_review)
        imp.match_ready.connect(self.start_analysis)
        self.analysis.cancel_requested.connect(self.cancel_analysis)
        self.analysis.pause_requested.connect(self.pause_analysis)
        self.cancel_analysis_requested.connect(self.cancel_analysis)
        self.pause_analysis_requested.connect(self.pause_analysis)
        self.clips.play_requested.connect(self.open_player_for_highlight)
        self.clips.export_requested.connect(self.export_highlights)
        self.editor.export_requested.connect(self.export_edited)
        self.compile.compilation_requested.connect(self.start_compilation)
        self.compile.separate_requested.connect(self.export_highlights)
        self.settings_page.calibrate_requested.connect(self.open_calibration)
        self.settings_page.settings_saved.connect(self._on_settings_saved)

        # Top-bar shell signals.
        self.import_requested.connect(self.open_import)
        self.settings_requested.connect(self.open_settings)
        self.about_requested.connect(self.open_about)
        self.calibration_requested.connect(self.open_calibration)
        self.export_requested.connect(self._shell_export)
        self.search_changed.connect(self._shell_search)

    # ---------- Shell-driven navigation (dialogs, no stacked pages) ----------
    def open_import(self) -> None:
        """Bring the (hidden) import page forward as a dialog for file picking."""
        page = self.pages[PAGE_IMPORT]
        page.setParent(self, Qt.Dialog)
        page.show()

    def _show_page_dialog(self, page: QWidget, title: str) -> QDialog:
        """Host a legacy page inside a real QDialog so it is modal-safe."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        page.setParent(dlg)
        lay.addWidget(page)
        dlg.resize(720, 640)
        self._dialogs.append(dlg)
        dlg.show()
        return dlg

    def open_settings(self) -> None:
        self._show_page_dialog(self.pages[PAGE_SETTINGS], "Settings")

    def open_about(self) -> None:
        self._show_page_dialog(self.pages[PAGE_ABOUT], "About")

    def open_highlights(self) -> None:
        page = self.clips
        if self.current_match_id is not None:
            page.set_match(self.current_match_id)
        page.setParent(self, Qt.Dialog)
        page.show()

    def _shell_export(self) -> None:
        """Export the current match's compilation from the top-bar button."""
        if self.current_match_id is not None:
            self.compile.set_match(self.current_match_id)
            self.start_compilation(self._compilation_request())

    def _shell_search(self, text: str) -> None:
        """Filter the hidden clip gallery; the real Assets panel takes over in T5."""
        if hasattr(self.clips, "filter_text"):
            self.clips.filter_text(text)

    @Slot(float, float)
    def _on_manual_range_added(self, start: float, end: float) -> None:
        """Persist a manual clip range dragged on the timeline."""
        if self.current_match_id is None or end - start < 0.5:
            return
        sid = self.ctx.db.add_manual_segment(self.current_match_id, start, end,
                                             "Added by you")
        self._load_segments_into_shell()

    @Slot(int, float, float)
    def _on_manual_bounds_changed(self, manual_id: int, start: float,
                                  end: float) -> None:
        """Persist an edited manual segment's start/end."""
        if manual_id:
            self.ctx.db.update_manual_segment(int(manual_id), start, end)
            self._load_segments_into_shell()

    @Slot()
    def _on_add_at_playhead(self) -> None:
        self.timeline.add_at_playhead()

    @Slot()
    def _on_remove_segment(self) -> None:
        """Remove the manual clip currently selected in the Inspector."""
        mid = getattr(self.inspector, "_manual_id", None)
        if mid is None:
            QMessageBox.information(self, "Remove clip",
                                    "Only clips you added can be removed here.")
            return
        self.ctx.db.delete_manual_segment(int(mid))
        self.inspector.set_segment(None)
        self._load_segments_into_shell()

    @Slot()
    def _on_split_segment(self) -> None:
        """Split the selected manual clip into two at the timeline playhead."""
        seg = getattr(self.inspector, "_segment", None)
        mid = getattr(self.inspector, "_manual_id", None)
        if seg is None or mid is None:
            QMessageBox.information(self, "Split clip",
                                    "Select a clip you added, then position the playhead.")
            return
        playhead = self.timeline.playhead()
        if not (seg.start + 0.5 < playhead < seg.end - 0.5):
            QMessageBox.information(self, "Split clip",
                                    "Move the playhead inside the clip to split it.")
            return
        self.ctx.db.update_manual_segment(int(mid), seg.start, playhead)
        self.ctx.db.add_manual_segment(self.current_match_id, playhead, seg.end,
                                       "Split clip")
        self._load_segments_into_shell()

    def _load_segments_into_shell(self) -> None:
        """Populate every visible editor panel from the current match.

        The single-window editor's Assets, Preview, Timeline and Inspector are
        the real UI (T4-T8); the legacy pages are hidden workflow helpers.  This
        method is the one place that feeds all four from the database so nothing
        depends on a hidden page being shown.
        """
        if self.current_match_id is None:
            return
        m = self.ctx.db.get_match(self.current_match_id)
        if not m:
            return
        # Assets: all matches + this match's highlights.
        self.assets.set_matches(self.ctx.db.list_matches())
        highlights = self.ctx.db.list_highlights(self.current_match_id)
        self.assets.set_highlights(highlights)
        # Preview: source the recording and bound it to the first kept clip.
        self.preview.set_source(m.path)
        kept = [h for h in highlights if getattr(h, "keep", True)]
        if kept:
            first = kept[0]
            self.preview.set_bounds(first.start, first.end)
        # Timeline + Inspector from the compiled segments.
        self.compile.set_match(self.current_match_id)
        segments = getattr(self.compile, "segments", [])
        self.timeline.set_segments(segments, m.duration)
        if segments:
            self.inspector.set_segment(segments[0])

    @Slot(int)
    def _on_asset_clip_selected(self, hid: int) -> None:
        """Load a clip chosen in the Assets panel into the centre preview.

        Keeps playback in the single editor window instead of opening a
        separate player dialog (the dialog remains only for legacy pages).
        """
        h = self.ctx.db.get_highlight(hid)
        if h is None:
            return
        m = self.ctx.db.get_match(h.match_id)
        if m is None:
            return
        self.current_match_id = m.id
        self.preview.set_source(m.path)
        self.preview.set_bounds(h.start, h.end)
        self.preview.seek(h.start)
        seg = next((s for s in getattr(self.compile, "segments", [])
                    if hid in (getattr(s, "highlight_ids", []) or [])), None)
        self.inspector.set_segment(seg)

    def navigate(self, index: int) -> None:
        """Compatibility no-op: the editor is one window, not a stacked page set."""
        if index == PAGE_DASHBOARD:
            self.pages[PAGE_DASHBOARD].refresh()
        elif index == PAGE_EXPORTED:
            self.exported.refresh()
        elif index == PAGE_CLIPS and self.current_match_id is not None:
            self.clips.set_match(self.current_match_id)
        elif index == PAGE_EXPORT and self.current_match_id is not None:
            self.compile.set_match(self.current_match_id)

    @Slot(int)
    def open_review(self, match_id: int) -> None:
        """Open the Review & Export page for a match (not in the sidebar)."""
        self.current_match_id = match_id
        self.navigate(PAGE_EXPORT)
        self._load_segments_into_shell()

    @Slot(int)
    def open_player_for_highlight(self, hid: int) -> None:
        """Play a single highlight from the original recording."""
        h = self.ctx.db.get_highlight(hid)
        if h is None:
            return
        m = self.ctx.db.get_match(h.match_id)
        if m is None or not m.path:
            QMessageBox.warning(self, "Video not found",
                                "The source recording for this highlight is missing.")
            return
        dlg = VideoPlayerDialog(m.path, start=h.start, end=h.end, parent=self)
        dlg.setWindowTitle(f"Clip preview — {Path(m.name).stem}")
        dlg.show()
        self._player_dialog = dlg  # keep a reference alive

    def open_calibration(self) -> None:
        dlg = CalibrationDialog(self.ctx.settings.calibration, self)
        self._dialogs.append(dlg)
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
            self.navigate(PAGE_SETTINGS)
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
        worker.progress.connect(self._shell_progress)
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
        self.navigate(PAGE_ANALYSIS)
        thread.start()
        self.statusBar().showMessage(f"Analysing {name}")
        self.pause_btn.setChecked(False)
        self.pause_btn.show()
        self.cancel_btn.show()
        self.analysis_status.setText(f"Analysing {name}")

    @Slot(object)
    def _analysis_done(self, result) -> None:
        self.analysis.finish()
        self.analysis.set_counts(len(result.events), len(result.clips))
        self.pages[PAGE_DASHBOARD].refresh()
        self.clips.set_match(self.current_match_id)
        self.compile.set_match(self.current_match_id)
        self.statusBar().showMessage(
            f"Analysis complete — {len(result.events)} events, {len(result.clips)} candidates")
        self.pause_btn.hide()
        self.cancel_btn.hide()
        self.analysis_status.setText("Analysis complete")
        if self._current_job_id is not None:
            self.ctx.jobs.unregister(self._current_job_id)
        # Always land on the review step so the user can play and adjust clips.
        # Explicit auto-export (advanced setting) still runs in the background.
        if self.current_match_id is not None:
            self.open_review(self.current_match_id)
        if self.ctx.settings.auto_export and getattr(result, "highlight_ids", None):
            if self.ctx.settings.export_mode == "compilation":
                self.statusBar().showMessage("Auto-building highlight compilation…")
                self.navigate(PAGE_EXPORT)
                self.start_compilation(self._compilation_request())
            else:
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

    @Slot(float, str, str)
    def _shell_progress(self, fraction, stage=None, message=None) -> None:
        """Mirror analysis progress into the single-window top bar."""
        stage = stage or ""
        message = message or ""
        pct = int(max(0.0, min(1.0, float(fraction))) * 100)
        self.analysis_status.setText(f"Analysis {pct}% — {stage or message}".strip())

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

    # ---------- Compilation (one match -> one MP4) ----------
    def _compilation_request(self) -> dict:
        """Build a compilation request from the current match's highlights."""
        segs = self.compile.segments
        return {
            "source_path": self.compile.source_path,
            "segments": segs,
            "output_path": str(Path(self.ctx.settings.output_folder) /
                               self._compilation_filename()),
            "source_has_audio": self.compile.has_audio,
            "video_duration": self.compile.match_duration,
            "preview": False,
        }

    @staticmethod
    def _compilation_filename() -> str:
        return f"PUBG_Highlights_{datetime.now().strftime('%Y-%m-%d_%H%M')}.mp4"

    @Slot(dict)
    def start_compilation(self, request: dict) -> None:
        if self._compilation_thread and self._compilation_thread.isRunning():
            QMessageBox.warning(self, "Busy", "A compilation is already running.")
            return
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Busy", "An export is already running.")
            return
        segments = request["segments"]
        if not segments:
            self.compile.status_lbl.setText("No highlights selected to compile.")
            return
        token = CancellationToken()
        self._compilation_token = token
        preview = request.get("preview", False)
        export_rec = None
        if not preview:
            export_rec = self.ctx.db.add_export(
                clip_id=None, match_id=self.current_match_id,
                export_type="compilation", path=request["output_path"],
                status="pending", layout=self.ctx.settings.render.layout,
            )
        self._compilation_export_id = export_rec.id if export_rec else None
        worker = CompilationWorker(
            source_path=request["source_path"],
            segments=segments,
            output_path=request["output_path"],
            settings=self.ctx.settings,
            token=token,
            source_has_audio=request.get("source_has_audio", True),
            video_duration=request.get("video_duration", 0.0),
            preview=preview,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.started.connect(lambda: self.statusBar().showMessage("Building compilation…"))
        worker.progress.connect(self.compile.set_progress)
        worker.progress.connect(
            lambda c, t, m: self.statusBar().showMessage(m))
        worker.finished.connect(self._compilation_done)
        worker.failed.connect(self._compilation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._compilation_thread = thread
        self._compilation_worker = worker  # keep Python reference alive
        self.ctx.register_thread(thread)
        thread.start()

    @Slot(str, float, int)
    def _compilation_done(self, path: str, duration: float, count: int) -> None:
        from app.media.probe import MediaProbe
        meta = MediaProbe().probe(path)
        if getattr(self, "_compilation_export_id", None):
            self.ctx.db.update_export(
                self._compilation_export_id, status="done",
                size_bytes=meta.file_size, duration=duration, segment_count=count)
        self.compile.set_result(path, duration)
        self.show_result(path, duration)
        self.pages[PAGE_DASHBOARD].refresh()
        self.statusBar().showMessage(
            f"Compilation ready: {Path(path).name} ({duration:.0f}s)")
        if not Path(path).name.startswith("preview_"):
            QMessageBox.information(
                self, "Compilation complete",
                f"Your highlight compilation is ready:\n\n{path}\n\n"
                f"Duration: {duration:.0f} s\nSize: {meta.file_size / 1e6:.1f} MB")

    @Slot(str)
    def _compilation_failed(self, message: str) -> None:
        if getattr(self, "_compilation_export_id", None):
            self.ctx.db.update_export(
                self._compilation_export_id, status="failed", error=message[:500])
        self.compile.set_result("", 0, failed=message)
        self.show_result("", 0)
        self.statusBar().showMessage("Compilation failed")
        QMessageBox.warning(self, "Compilation failed", message[:600])

    def cancel_compilation(self) -> None:
        if self._compilation_token:
            self._compilation_token.cancel()

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
            self.ctx.jobs.register(rec.id, "export", self.current_match_id,
                                   CancellationToken())
        if not jobs:
            return
        self._export_ids = [j.export_id for j in jobs]
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
        self.ctx.jobs.unregister(export_id)
        self.statusBar().showMessage(f"Exported {Path(path).name}")

    @Slot(int, int)
    def _export_finished(self, ok: int, failed: int) -> None:
        # Any export from this batch left 'pending' did not succeed — mark it
        # failed and clear its job so the UI never shows a stuck pending item.
        from ..rendering.export_manager import finalize_failed_export
        for eid in getattr(self, "_export_ids", []):
            rec = self.ctx.db.get_export(eid)
            if rec is not None and rec.status == "pending":
                finalize_failed_export(self.ctx.db, self.ctx.jobs, eid,
                                       "Export did not complete")
        self.pages[0].refresh()
        QMessageBox.information(self, "Export complete",
                                f"Exported {ok} clip(s)." +
                                (f" {failed} failed." if failed else ""))

    def closeEvent(self, event) -> None:
        for thread in (self._analysis_thread, self._export_thread,
                       self._compilation_thread):
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
