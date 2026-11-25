"""Export page: single highlight compilation (default) and separate clips."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..clips.compilation_builder import (
    Segment, category_counts, kill_coverage, select_segments, total_duration,
)
from ..utils.logging import get_logger
from .video_player_dialog import VideoPlayerDialog
from .widgets.common import Card, empty_state, section
from .widgets.step_indicator import StepIndicator

log = get_logger("ui.compile")

CATEGORY_COLORS = {
    "KILL": QColor("#A3E635"),
    "MULTI_KILL": QColor("#B6FF3D"),
    "CLUTCH_CANDIDATE": QColor("#FFC542"),
    "KNOCK": QColor("#FF8A5B"),
    "KNOCK_CANDIDATE": QColor("#FFAB8A"),
    "COMBAT": QColor("#42C6FF"),
    "MANUAL": QColor("#FF5EDB"),
    "UNKNOWN": QColor("#9AA5AD"),
}


class CompilationTimeline(QWidget):
    """Visual overview of the selected segments on the match timeline."""

    segment_selected = Signal(int)
    segment_drag_created = Signal(float, float)
    drag_preview = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.segments: list[Segment] = []
        self.match_duration = 1.0
        self.selected = -1
        self._drag_start_x: float | None = None
        self._drag_cur_x: float | None = None
        self.setMinimumHeight(96)
        self.setMouseTracking(True)

    @staticmethod
    def range_from_drag(x1: float, x2: float, duration: float) -> tuple[float, float] | None:
        """Map two widget x positions to a clamped time range, or None if invalid."""
        duration = max(0.0, float(duration))
        start = min(max(0.0, float(x1)), duration)
        end = min(max(0.0, float(x2)), duration)
        if end < start:
            start, end = end, start
        if end - start <= 0.5 + 1e-9:
            return None
        return (start, end)

    def _x_to_time(self, x: float) -> float:
        return min(max(0.0, (x - 8) / max(1, self.width() - 16)), 1.0) * self.match_duration

    def set_data(self, segments: list[Segment], duration: float) -> None:
        self.segments = segments
        self.match_duration = max(1.0, duration)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#161B1E"))
        track_y, track_h = 34, 26
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#22282D"))
        p.drawRoundedRect(8, track_y, w - 16, track_h, 5, 5)
        for i, seg in enumerate(self.segments):
            x = 8 + int((seg.start / self.match_duration) * (w - 16))
            sw = max(4, int((seg.duration / self.match_duration) * (w - 16)))
            color = CATEGORY_COLORS.get(seg.category, CATEGORY_COLORS["UNKNOWN"])
            p.setBrush(color if i != self.selected else QColor("#FFFFFF"))
            p.drawRoundedRect(x, track_y, sw, track_h, 3, 3)
            if sw > 34:
                p.setPen(QColor("#10150A"))
                p.drawText(x + 4, track_y + 18, f"{seg.start:.0f}s")
        if self._drag_start_x is not None and self._drag_cur_x is not None:
            dx1, dx2 = sorted((self._drag_start_x, self._drag_cur_x))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 94, 219, 90))
            p.drawRect(int(dx1), track_y, max(2, int(dx2 - dx1)), track_h)
        p.setPen(QColor("#7E8A92"))
        p.drawText(8, 22, "Match start")
        p.drawText(w - 78, 22, f"{self.match_duration / 60:.1f} min")
        p.drawText(8, h - 8, "Selected moments (chronological)" if self.segments
                   else "No segments selected")
        p.end()

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        for i, seg in enumerate(self.segments):
            sx = 8 + int((seg.start / self.match_duration) * (self.width() - 16))
            sw = max(4, int((seg.duration / self.match_duration) * (self.width() - 16)))
            if sx <= x <= sx + sw:
                self.selected = i
                self.update()
                self.segment_selected.emit(i)
                return
        # Empty space: begin a drag-to-add selection.
        self.selected = -1
        self._drag_start_x = x
        self._drag_cur_x = x
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_x is not None:
            self._drag_cur_x = event.position().x()
            # Seek the preview player as the user drags so they can see the
            # footage they are selecting before they release the mouse.
            self.drag_preview.emit(self._x_to_time(self._drag_cur_x))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start_x is None:
            return
        cur = event.position().x()
        # Convert widget pixels to timeline seconds before validating — the
        # timeline is drawn with an 8px margin on each side (see paintEvent).
        rng = self.range_from_drag(self._x_to_time(self._drag_start_x),
                                   self._x_to_time(cur), self.match_duration)
        self._drag_start_x = None
        self._drag_cur_x = None
        self.update()
        if rng:
            self.segment_drag_created.emit(rng[0], rng[1])


class SegmentRow(QWidget):
    """Editable start/end controls for one compilation segment."""

    changed = Signal()
    remove_requested = Signal()
    # manual_id, new_start, new_end — emitted after a manual row is edited so
    # the page can persist the change to SQLite.
    edited = Signal(int, float, float)

    def __init__(self, index: int, segment: Segment, match_duration: float) -> None:
        super().__init__()
        self.segment = segment
        self.manual_id = (segment.evidence or {}).get("manual_id")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(8)
        color = CATEGORY_COLORS.get(segment.category, CATEGORY_COLORS["UNKNOWN"]).name()
        lbl = QLabel(f"{index:02d} · {segment.category.replace('_', ' ').title()}")
        lbl.setStyleSheet(f"color:{color}; font-weight:600; min-width:170px;")
        lay.addWidget(lbl)
        self.start_sb = QDoubleSpinBox()
        self.start_sb.setRange(0.0, match_duration)
        self.start_sb.setDecimals(1)
        self.start_sb.setSuffix(" s")
        self.start_sb.setValue(segment.start)
        self.end_sb = QDoubleSpinBox()
        self.end_sb.setRange(0.0, match_duration)
        self.end_sb.setDecimals(1)
        self.end_sb.setSuffix(" s")
        self.end_sb.setValue(segment.end)
        lay.addWidget(QLabel("Start")); lay.addWidget(self.start_sb)
        lay.addWidget(QLabel("End")); lay.addWidget(self.end_sb)
        dur = QLabel(f"{segment.duration:.1f}s")
        dur.setObjectName("muted")
        lay.addWidget(dur)
        rm = QPushButton("Remove")
        rm.setObjectName("danger")
        lay.addWidget(rm)
        self.start_sb.valueChanged.connect(self._on_start)
        self.end_sb.valueChanged.connect(self._on_end)
        rm.clicked.connect(self.remove_requested.emit)

    def _on_start(self, value: float) -> None:
        if value >= self.end_sb.value() - 1:
            self.start_sb.setValue(self.end_sb.value() - 1)
            return
        self.segment.start = round(value, 3)
        self.changed.emit()
        if self.manual_id is not None:
            self.edited.emit(self.manual_id, self.segment.start, self.segment.end)

    def _on_end(self, value: float) -> None:
        if value <= self.start_sb.value() + 1:
            self.end_sb.setValue(self.start_sb.value() + 1)
            return
        self.segment.end = round(value, 3)
        self.changed.emit()
        if self.manual_id is not None:
            self.edited.emit(self.manual_id, self.segment.start, self.segment.end)


class CompilePage(QWidget):
    """Export manager page for one-match-in / one-video-out workflow."""

    compilation_requested = Signal(dict)
    separate_requested = Signal(list)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.match_id: int | None = None
        self.segments: list[Segment] = []
        self.source_path = ""
        self.match_duration = 0.0
        self.has_audio = True
        self.last_output = ""

        # The whole review page scrolls. The embedded player plus timeline and
        # segment list are taller than a normal window; without a scroll area
        # the timeline was pushed below the viewport and could not be reached
        # to add manual clips (see regression tests/test_review_timeline_visible.py).
        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        self.page_scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.page_scroll)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self.title = QLabel("Step 3 — Review & export")
        self.title.setObjectName("pageTitle")
        sub = QLabel("Check your clips, add anything missed, then export")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(self.title); lay.addWidget(sub)
        self.step_indicator = StepIndicator(current=3)
        lay.addWidget(self.step_indicator)

        # Mode selector
        mode_card = Card()
        ml = QVBoxLayout(mode_card)
        ml.setContentsMargins(18, 14, 18, 14)
        ml.addWidget(section("Export mode"))
        self.mode = QComboBox()
        self.mode.addItems([
            "One combined video",
            "Separate video clips",
        ])
        self.mode.setCurrentIndex(0 if ctx.settings.export_mode == "compilation" else 1)
        self.mode.currentIndexChanged.connect(self._on_mode)
        ml.addWidget(self.mode)
        self.mode_hint = QLabel(
            "All selected moments are merged into one chronological MP4.")
        self.mode_hint.setObjectName("muted")
        ml.addWidget(self.mode_hint)
        lay.addWidget(mode_card)

        # Stats
        stats_card = Card()
        sl = QVBoxLayout(stats_card)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.addWidget(section("Selection summary"))
        self.stats_lbl = QLabel("No match analysed yet.")
        self.stats_lbl.setWordWrap(True)
        self.stats_lbl.setObjectName("muted")
        sl.addWidget(self.stats_lbl)
        lay.addWidget(stats_card)

        # Inline player: preview any moment of the match before exporting.
        # Sized for readable gameplay; the page scroll area keeps the timeline
        # reachable even on short windows or high-DPI scaling.
        self.player_host = QWidget()
        self.player_host.setMaximumHeight(360)
        player_lay = QVBoxLayout(self.player_host)
        player_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.player_host)
        self._player: VideoPlayerDialog | None = None

        # Timeline + segment editor
        self.timeline = CompilationTimeline()
        self.timeline.segment_selected.connect(self._focus_segment)
        self.timeline.segment_drag_created.connect(self._on_segment_drag)
        self.timeline.drag_preview.connect(self._preview_drag)
        lay.addWidget(self.timeline)

        self.segment_host = QWidget()
        self.segment_layout = QVBoxLayout(self.segment_host)
        self.segment_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setMaximumHeight(200)
        scroll.setWidget(self.segment_host)
        lay.addWidget(scroll)

        self.empty_lbl = QLabel("")
        self.empty_lbl.setObjectName("muted")
        lay.addWidget(self.empty_lbl)

        # Actions
        actions = QHBoxLayout()
        self.preview_btn = QPushButton("Preview")
        self.preview_btn.setObjectName("ghost")
        self.preview_btn.clicked.connect(lambda: self._export(preview=True))
        self.folder_btn = QPushButton("Change output folder")
        self.folder_btn.setObjectName("ghost")
        self.folder_btn.clicked.connect(self._browse_folder)
        self.add_range_btn = QPushButton("+ Add 20s here")
        self.add_range_btn.setObjectName("ghost")
        self.add_range_btn.setToolTip("Add the 20 seconds starting at the player position")
        self.add_range_btn.clicked.connect(self.add_current_range)
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(lambda: self._export(preview=False))
        actions.addWidget(self.preview_btn)
        actions.addWidget(self.add_range_btn)
        actions.addWidget(self.folder_btn)
        actions.addStretch()
        actions.addWidget(self.export_btn)
        lay.addLayout(actions)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setObjectName("muted")
        lay.addWidget(self.status_lbl)

        self.result_card = Card()
        rl = QHBoxLayout(self.result_card)
        rl.setContentsMargins(16, 12, 16, 12)
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        rl.addWidget(self.result_lbl, 1)
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setObjectName("ghost")
        self.play_btn = QPushButton("Play Video")
        self.play_btn.setObjectName("primary")
        self.open_folder_btn.clicked.connect(self._open_folder)
        self.play_btn.clicked.connect(self._play)
        rl.addWidget(self.open_folder_btn); rl.addWidget(self.play_btn)
        self.result_card.hide()
        lay.addWidget(self.result_card)

    # ---------- public API ----------
    def set_match(self, match_id: int) -> None:
        self.match_id = match_id
        m = self.ctx.db.get_match(match_id)
        if not m:
            return
        self.source_path = m.path
        self.match_duration = m.duration
        self.has_audio = bool(m.audio_codec)
        highlights = self.ctx.db.list_highlights(match_id)
        events = self.ctx.db.list_events(match_id)
        self.events = events
        self.segments = select_segments(highlights, events, self.ctx.settings, m.duration)
        # Manually added ranges are always kept, even past the automatic clip
        # cap — they exist precisely because the detector missed them.
        for row in self.ctx.db.list_manual_segments(match_id):
            self.segments.append(Segment(
                start=float(row["start"]), end=float(row["end"]),
                category="MANUAL", score=0.0, confidence=1.0,
                evidence={"manual_id": row["id"]},
                source_labels=["Added by you"],
            ))
        self._rebuild_player()
        self._rebuild_rows()
        self.refresh()

    def refresh(self) -> None:
        counts = category_counts(self.segments)
        covered, total_kills = kill_coverage(self.segments,
                                             getattr(self, "events", []))
        self.stats_lbl.setText(
            f"Selected segments: <b>{len(self.segments)}</b> &nbsp;•&nbsp; "
            f"<b style='color:#A3E635'>Kills covered: {covered}/{total_kills}</b> &nbsp;•&nbsp; "
            f"Confirmed kills: <b>{counts['confirmed_kills']}</b> &nbsp;•&nbsp; "
            f"Multi-kills: <b>{counts['multi_kills']}</b> &nbsp;•&nbsp; "
            f"Clutch candidates: <b>{counts['clutch_candidates']}</b> &nbsp;•&nbsp; "
            f"Knocks: <b>{counts['knocks']}</b> &nbsp;•&nbsp; "
            f"Other: <b>{counts['other']}</b><br>"
            f"Estimated duration: <b style='color:#A3E635'>{total_duration(self.segments):.0f} s</b>"
            f" ({total_duration(self.segments)/60:.1f} min) &nbsp;•&nbsp; "
            f"Output: <b>{self.ctx.settings.render.width}×{self.ctx.settings.render.height}</b>"
            f" @ {self.ctx.settings.render.fps} fps &nbsp;•&nbsp; "
            f"Folder: {self.ctx.settings.output_folder}"
        )
        self.stats_lbl.setTextFormat(Qt.RichText)
        self.timeline.set_data(self.segments, self.match_duration)
        self.empty_lbl.setText("" if self.segments else
                               "No highlights selected — analyse a recording first.")

    def set_progress(self, current: int, total: int, message: str) -> None:
        self.status_lbl.setText(f"{message} ({current}/{total})")

    def set_result(self, path: str, duration: float, failed: str = "") -> None:
        if failed:
            self.status_lbl.setText(f"Compilation failed: {failed}")
            self.result_card.hide()
            return
        self.last_output = path
        size_mb = Path(path).stat().st_size / 1e6 if Path(path).exists() else 0
        self.result_lbl.setText(
            f"<b style='color:#A3E635'>✓ Export complete</b><br>"
            f"{Path(path).name}<br>"
            f"Duration {duration:.1f}s &nbsp;•&nbsp; {size_mb:.1f} MB<br>"
            f"Saved to {Path(path).parent}"
        )
        self.result_lbl.setTextFormat(Qt.RichText)
        self.result_card.show()
        self.status_lbl.setText("")

    # ---------- internals ----------
    def _on_mode(self, index: int) -> None:
        compilation = index == 0
        self.mode_hint.setText(
            "All selected moments are merged into one chronological MP4."
            if compilation else
            "Each selected highlight is exported as its own MP4 file."
        )
        self.timeline.setVisible(compilation)
        self.segment_host.setVisible(compilation)
        self.export_btn.setText("Export compilation" if compilation else "Export clips")
        self.ctx.settings.export_mode = "compilation" if compilation else "separate"
        self.ctx.save_settings()

    def _rebuild_rows(self) -> None:
        while self.segment_layout.count():
            item = self.segment_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows: list[SegmentRow] = []
        for i, seg in enumerate(self.segments):
            row = SegmentRow(i + 1, seg, self.match_duration)
            row.changed.connect(self.refresh)
            if row.manual_id is not None:
                row.edited.connect(self._persist_manual_edit)
            row.remove_requested.connect(lambda idx=i: self._remove_segment(idx))
            self.segment_layout.addWidget(row)
            self._rows.append(row)

    def _remove_segment(self, index: int) -> None:
        if 0 <= index < len(self.segments):
            seg = self.segments.pop(index)
            manual_id = (seg.evidence or {}).get("manual_id")
            if manual_id is not None:
                self.ctx.db.delete_manual_segment(int(manual_id))
            self._rebuild_rows()
            self.refresh()

    def _persist_manual_edit(self, manual_id: int, start: float, end: float) -> None:
        """Save a manual segment's edited bounds to SQLite immediately."""
        try:
            self.ctx.db.update_manual_segment(int(manual_id), start, end)
        except Exception:
            log.exception("Could not persist manual segment edit")

    # ---------- manual review helpers ----------
    def _rebuild_player(self) -> None:
        """Embed a small player so any match moment can be previewed."""
        while self.player_host.layout().count():
            item = self.player_host.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._player = None
        if not self.source_path:
            return
        try:
            dlg = VideoPlayerDialog(self.source_path, parent=self)
            dlg.setWindowFlags(Qt.Widget)
            # Standalone dialogs want a tall video surface; keep a generous
            # embedded height too — the page scrolls so the timeline stays
            # reachable even when the player fills more vertical space.
            dlg.video_widget.setMinimumHeight(280)
            dlg.setMinimumHeight(0)
            self.player_host.setMaximumHeight(360)
            self.player_host.layout().addWidget(dlg)
            self._player = dlg
        except Exception:  # pragma: no cover - Qt backend failure
            log.exception("Could not create review player")

    def _on_segment_drag(self, start: float, end: float) -> None:
        """Persist a manually dragged range and reload the review list."""
        if self.match_id is None or end - start <= 0.5 + 1e-9:
            return
        self.ctx.db.add_manual_segment(self.match_id, start, end, "Added by you")
        self.set_match(self.match_id)

    def add_current_range(self) -> None:
        """Add ~20s from the player's current position (simple fallback)."""
        if self.match_id is None:
            return
        pos = self._player.position() if self._player else 0.0
        start = max(0.0, min(pos, self.match_duration))
        end = min(self.match_duration, start + 20.0)
        self._on_segment_drag(start, end)

    def _preview_drag(self, seconds: float) -> None:
        """Seek the inline player while the user drags on the timeline."""
        if self._player is not None:
            self._player.seek(seconds)

    def _focus_segment(self, index: int) -> None:
        for i, row in enumerate(getattr(self, "_rows", [])):
            row.setStyleSheet(
                "border:1px solid #A3E635; border-radius:6px;" if i == index else "")
        # Seek the player to the clicked marker so the user sees that moment.
        if 0 <= index < len(self.segments) and self._player is not None:
            self._player.seek(self.segments[index].start)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Output folder", self.ctx.settings.output_folder)
        if folder:
            self.ctx.settings.output_folder = folder
            self.ctx.save_settings()
            self.refresh()

    def _open_folder(self) -> None:
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output).parent)))

    def _play(self) -> None:
        if self.last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output))

    def _export(self, preview: bool = False) -> None:
        if self.ctx.settings.export_mode == "separate":
            hids = [sid for seg in self.segments for sid in seg.highlight_ids]
            if hids:
                self.separate_requested.emit(list(dict.fromkeys(hids)))
            return
        if not self.segments or not self.source_path:
            self.status_lbl.setText("No highlights selected to compile.")
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        name = f"PUBG_Highlights_{stamp}.mp4"
        out_dir = Path(self.ctx.settings.output_folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        output = str(out_dir / (("preview_" if preview else "") + name))
        self.compilation_requested.emit({
            "source_path": self.source_path,
            "segments": self.segments,
            "output_path": output,
            "source_has_audio": self.has_audio,
            "video_duration": self.match_duration,
            "preview": preview,
        })
