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
from .widgets.common import Card, empty_state, section

log = get_logger("ui.compile")

CATEGORY_COLORS = {
    "KILL": QColor("#7CFC00"),
    "MULTI_KILL": QColor("#B6FF3D"),
    "CLUTCH_CANDIDATE": QColor("#FFC542"),
    "KNOCK": QColor("#FF8A5B"),
    "KNOCK_CANDIDATE": QColor("#FFAB8A"),
    "COMBAT": QColor("#42C6FF"),
    "UNKNOWN": QColor("#9AA5AD"),
}


class CompilationTimeline(QWidget):
    """Visual overview of the selected segments on the match timeline."""

    segment_selected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.segments: list[Segment] = []
        self.match_duration = 1.0
        self.selected = -1
        self.setMinimumHeight(96)
        self.setMouseTracking(True)

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


class SegmentRow(QWidget):
    """Editable start/end controls for one compilation segment."""

    changed = Signal()
    remove_requested = Signal()

    def __init__(self, index: int, segment: Segment, match_duration: float) -> None:
        super().__init__()
        self.segment = segment
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

    def _on_end(self, value: float) -> None:
        if value <= self.start_sb.value() + 1:
            self.end_sb.setValue(self.start_sb.value() + 1)
            return
        self.segment.end = round(value, 3)
        self.changed.emit()


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

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        title = QLabel("Export")
        title.setObjectName("pageTitle")
        sub = QLabel("One match in — one finished highlight compilation out")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)

        # Mode selector
        mode_card = Card()
        ml = QVBoxLayout(mode_card)
        ml.setContentsMargins(18, 14, 18, 14)
        ml.addWidget(section("Export mode"))
        self.mode = QComboBox()
        self.mode.addItems([
            "Single Highlight Compilation",
            "Separate Individual Clips",
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

        # Timeline + segment editor
        self.timeline = CompilationTimeline()
        self.timeline.segment_selected.connect(self._focus_segment)
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
        self.preview_btn = QPushButton("Preview compilation")
        self.preview_btn.setObjectName("ghost")
        self.preview_btn.clicked.connect(lambda: self._export(preview=True))
        self.folder_btn = QPushButton("Change output folder")
        self.folder_btn.setObjectName("ghost")
        self.folder_btn.clicked.connect(self._browse_folder)
        self.export_btn = QPushButton("Export compilation")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(lambda: self._export(preview=False))
        actions.addWidget(self.preview_btn)
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
        self._rebuild_rows()
        self.refresh()

    def refresh(self) -> None:
        counts = category_counts(self.segments)
        covered, total_kills = kill_coverage(self.segments,
                                             getattr(self, "events", []))
        self.stats_lbl.setText(
            f"Selected segments: <b>{len(self.segments)}</b> &nbsp;•&nbsp; "
            f"<b style='color:#7CFC00'>Kills covered: {covered}/{total_kills}</b> &nbsp;•&nbsp; "
            f"Confirmed kills: <b>{counts['confirmed_kills']}</b> &nbsp;•&nbsp; "
            f"Multi-kills: <b>{counts['multi_kills']}</b> &nbsp;•&nbsp; "
            f"Clutch candidates: <b>{counts['clutch_candidates']}</b> &nbsp;•&nbsp; "
            f"Knocks: <b>{counts['knocks']}</b> &nbsp;•&nbsp; "
            f"Other: <b>{counts['other']}</b><br>"
            f"Estimated duration: <b style='color:#7CFC00'>{total_duration(self.segments):.0f} s</b>"
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
            f"<b style='color:#7CFC00'>✓ Export complete</b><br>"
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
            row.remove_requested.connect(lambda idx=i: self._remove_segment(idx))
            self.segment_layout.addWidget(row)
            self._rows.append(row)

    def _remove_segment(self, index: int) -> None:
        if 0 <= index < len(self.segments):
            self.segments.pop(index)
            self._rebuild_rows()
            self.refresh()

    def _focus_segment(self, index: int) -> None:
        for i, row in enumerate(getattr(self, "_rows", [])):
            row.setStyleSheet(
                "border:1px solid #7CFC00; border-radius:6px;" if i == index else "")

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
