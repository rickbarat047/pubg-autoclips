"""Settings page: IGN, calibration, detection, clip, render and system settings."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..rendering.ffmpeg_runner import detect_amf_support
from ..utils.hardware import detect_hardware
from .widgets.common import Card, ToastLabel


def section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sectionTitle")
    return lbl


def row(label: str, widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    l = QLabel(label)
    l.setMinimumWidth(210)
    lay.addWidget(l); lay.addWidget(widget, 1)
    return w


class SettingsPage(QWidget):
    calibrate_requested = Signal()
    settings_saved = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._loading = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(12)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        sub = QLabel("All settings are stored locally on this computer")
        sub.setObjectName("pageSubtitle")
        outer.addWidget(title); outer.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setSpacing(14)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        # --- Profile ---
        profile = Card(); pl = QVBoxLayout(profile); pl.setContentsMargins(20, 18, 20, 18)
        pl.addWidget(section("Player profile"))
        self.ign = QLineEdit()
        pl.addWidget(row("PUBG in-game name (IGN)", self.ign))
        outrow = QHBoxLayout()
        self.output = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        outrow.addWidget(self.output); outrow.addWidget(browse)
        out_widget = QWidget()
        out_widget.setLayout(outrow)
        pl.addWidget(row("Output folder", out_widget))
        cal = QPushButton("Calibrate kill-feed region…")
        cal.clicked.connect(self.calibrate_requested.emit)
        pl.addWidget(row("Kill-feed calibration", cal))
        self.cal_lbl = QLabel("")
        self.cal_lbl.setObjectName("muted")
        pl.addWidget(row("Current region", self.cal_lbl))
        lay.addWidget(profile)

        # --- Detection ---
        det = Card(); dl = QVBoxLayout(det); dl.setContentsMargins(20, 18, 20, 18)
        dl.addWidget(section("Detection"))
        self.ocr_conf = self._double(0, 1, 0.01)
        dl.addWidget(row("OCR confidence threshold", self.ocr_conf))
        self.ocr_interval = self._double(0.25, 10, 0.25)
        dl.addWidget(row("Kill-feed sample interval (s)", self.ocr_interval))
        self.obs = self._spin(1, 10)
        dl.addWidget(row("Consecutive observations to confirm", self.obs))
        self.audio_on = QCheckBox()
        dl.addWidget(row("Enable audio analysis", self.audio_on))
        self.audio_sens = self._double(0, 1, 0.05)
        dl.addWidget(row("Audio sensitivity", self.audio_sens))
        self.visual_on = QCheckBox()
        dl.addWidget(row("Enable visual analysis", self.visual_on))
        self.visual_interval = self._double(0.25, 10, 0.25)
        dl.addWidget(row("Visual sample interval (s)", self.visual_interval))
        lay.addWidget(det)

        # --- Clips ---
        clips = Card(); cl = QVBoxLayout(clips); cl.setContentsMargins(20, 18, 20, 18)
        cl.addWidget(section("Clip generation"))
        self.min_dur = self._double(5, 300, 1)
        self.max_dur = self._double(10, 600, 1)
        self.pre = self._double(0, 60, 1)
        self.post = self._double(0, 60, 1)
        self.max_clips = self._spin(1, 100)
        self.sens = self._double(0, 1, 0.05)
        self.min_score = self._double(0, 500, 1)
        for label, w in [
            ("Minimum duration (s)", self.min_dur), ("Maximum duration (s)", self.max_dur),
            ("Seconds before event", self.pre), ("Seconds after event", self.post),
            ("Maximum clips per match", self.max_clips),
            ("Highlight sensitivity", self.sens), ("Minimum event score", self.min_score),
        ]:
            cl.addWidget(row(label, w))
        lay.addWidget(clips)

        # --- Rendering ---
        rend = Card(); rl = QVBoxLayout(rend); rl.setContentsMargins(20, 18, 20, 18)
        rl.addWidget(section("Export / rendering"))
        self.layout = QComboBox()
        self.layout.addItems(["blurred", "crop", "pillarbox"])
        rl.addWidget(row("Vertical layout preset", self.layout))
        self.fps = self._spin(15, 60)
        self.crf = self._spin(17, 28)
        self.audio_br = self._spin(64, 320)
        self.hw = QCheckBox()
        self.auto_export = QCheckBox()
        self.auto_export_max = QSpinBox()
        self.auto_export_max.setRange(1, 20)
        rl.addWidget(row("Export FPS", self.fps))
        rl.addWidget(row("Video quality (CRF, lower = better)", self.crf))
        rl.addWidget(row("Audio bitrate (kbps)", self.audio_br))
        rl.addWidget(row("AMD AMF hardware encoding (if supported)", self.hw))
        rl.addWidget(row("Auto-export top clips after analysis", self.auto_export))
        rl.addWidget(row("Max clips to auto-export", self.auto_export_max))
        lay.addWidget(rend)

        # --- System ---
        sysc = Card(); sl = QVBoxLayout(sysc); sl.setContentsMargins(20, 18, 20, 18)
        sl.addWidget(section("System"))
        self.preset = QComboBox()
        self.preset.addItems(["fast", "balanced", "accurate"])
        sl.addWidget(row("Processing preset", self.preset))
        self.ffmpeg_edit = QLineEdit()
        sl.addWidget(row("ffmpeg.exe path (blank = auto)", self.ffmpeg_edit))
        self.ffprobe_edit = QLineEdit()
        sl.addWidget(row("ffprobe.exe path (blank = auto)", self.ffprobe_edit))
        try:
            hw = detect_hardware()
            info = (f"{hw.cpu.name} • {hw.memory.total_gb} GB RAM • "
                    f"GPU: {hw.gpu.name}\nFFmpeg: {hw.ffmpeg_version or 'not detected'}")
        except Exception:
            info = "Hardware information unavailable"
        hw_lbl = QLabel(info)
        hw_lbl.setObjectName("muted")
        hw_lbl.setWordWrap(True)
        sl.addWidget(row("Detected hardware", hw_lbl))
        lay.addWidget(sysc)

        self.toast = ToastLabel()
        lay.addWidget(self.toast)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.setMaximumWidth(200)
        lay.addWidget(save, alignment=Qt.AlignLeft)
        lay.addStretch()
        save.clicked.connect(self.save)
        self.load()
        self._loading = False

    def _double(self, lo, hi, step):
        w = QDoubleSpinBox(); w.setRange(lo, hi); w.setSingleStep(step)
        w.setDecimals(2)
        return w

    def _spin(self, lo, hi):
        w = QSpinBox(); w.setRange(lo, hi)
        return w

    def _browse_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output.text())
        if d:
            self.output.setText(d)

    def load(self) -> None:
        s = self.ctx.settings
        self.ign.setText(s.ign)
        self.output.setText(s.output_folder)
        c = s.calibration
        self.cal_lbl.setText(f"x={c.x:.3f}, y={c.y:.3f}, w={c.w:.3f}, h={c.h:.3f}")
        self.ocr_conf.setValue(s.kill_feed.confidence_threshold)
        self.ocr_interval.setValue(s.kill_feed.sample_interval_sec)
        self.obs.setValue(s.kill_feed.min_observations)
        self.audio_on.setChecked(s.audio.enabled)
        self.audio_sens.setValue(s.audio.sensitivity)
        self.visual_on.setChecked(s.visual.enabled)
        self.visual_interval.setValue(s.visual.sample_interval_sec)
        self.min_dur.setValue(s.clips.min_duration_sec)
        self.max_dur.setValue(s.clips.max_duration_sec)
        self.pre.setValue(s.clips.pre_event_sec)
        self.post.setValue(s.clips.post_event_sec)
        self.max_clips.setValue(s.clips.max_clips_per_match)
        self.sens.setValue(s.clips.sensitivity)
        self.min_score.setValue(s.scoring.min_event_score)
        idx = self.layout.findText(s.render.layout)
        self.layout.setCurrentIndex(max(0, idx))
        self.fps.setValue(s.render.fps)
        self.crf.setValue(s.render.crf)
        self.audio_br.setValue(s.render.audio_bitrate_kbps)
        self.hw.setChecked(s.render.hardware_encoding)
        self.auto_export.setChecked(s.auto_export)
        self.auto_export_max.setValue(s.auto_export_max_clips)
        try:
            amf = detect_amf_support()
            self.hw.setEnabled(amf)
            self.hw.setToolTip(
                "h264_amf encoder available" if amf else
                "h264_amf not available in this FFmpeg build — CPU encoding is used.")
        except Exception:
            self.hw.setEnabled(False)
        self.preset.setCurrentText(s.processing.preset)
        self.ffmpeg_edit.setText(s.ffmpeg_path)
        self.ffprobe_edit.setText(s.ffprobe_path)

    def save(self) -> None:
        s = self.ctx.settings
        s.ign = self.ign.text().strip()
        s.output_folder = self.output.text().strip()
        s.kill_feed.confidence_threshold = self.ocr_conf.value()
        s.kill_feed.sample_interval_sec = self.ocr_interval.value()
        s.kill_feed.min_observations = self.obs.value()
        s.audio.enabled = self.audio_on.isChecked()
        s.audio.sensitivity = self.audio_sens.value()
        s.visual.enabled = self.visual_on.isChecked()
        s.visual.sample_interval_sec = self.visual_interval.value()
        s.clips.min_duration_sec = self.min_dur.value()
        s.clips.max_duration_sec = self.max_dur.value()
        s.clips.pre_event_sec = self.pre.value()
        s.clips.post_event_sec = self.post.value()
        s.clips.max_clips_per_match = self.max_clips.value()
        s.clips.sensitivity = self.sens.value()
        s.scoring.min_event_score = self.min_score.value()
        s.render.layout = self.layout.currentText()
        s.render.fps = self.fps.value()
        s.render.crf = self.crf.value()
        s.render.audio_bitrate_kbps = self.audio_br.value()
        s.render.hardware_encoding = self.hw.isChecked()
        s.auto_export = self.auto_export.isChecked()
        s.auto_export_max_clips = self.auto_export_max.value()
        s.processing.preset = self.preset.currentText()
        s.ffmpeg_path = self.ffmpeg_edit.text().strip()
        s.ffprobe_path = self.ffprobe_edit.text().strip()
        try:
            s.apply_preset(s.processing.preset)
            self.ctx.save_settings()
            self.toast.show_message("Settings saved.")
            self.settings_saved.emit()
        except Exception as exc:  # noqa: BLE001
            self.toast.show_message(f"Could not save: {exc}", error=True)
