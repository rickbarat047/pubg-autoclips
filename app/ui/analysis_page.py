"""Analysis page: stage progress, counters, cancel/pause controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .widgets.common import Card, empty_state
from .widgets.step_indicator import StepIndicator
from .tokens import PALETTE


class AnalysisPage(QWidget):
    cancel_requested = Signal()
    pause_requested = Signal(bool)  # True=pause, False=resume

    def __init__(self) -> None:
        super().__init__()
        self._paused = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        title = QLabel("Step 2 — Analysing your match")
        title.setObjectName("pageTitle")
        sub = QLabel("Full-match gameplay analysis — runs in the background")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)
        self.step_indicator = StepIndicator(current=2)
        lay.addWidget(self.step_indicator)

        self.idle, _ = empty_state("🔍", "Nothing processing",
                                   "Import a recording and analysis will appear here.")
        lay.addWidget(self.idle)

        self.work = QWidget()
        wl = QVBoxLayout(self.work)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(14)
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 20, 22, 20)
        cl.setSpacing(12)
        self.stage_lbl = QLabel("Queued")
        self.stage_lbl.setObjectName("sectionTitle")
        self.msg_lbl = QLabel("")
        self.msg_lbl.setObjectName("muted")
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.overall.setValue(0)
        cl.addWidget(self.stage_lbl); cl.addWidget(self.msg_lbl); cl.addWidget(self.overall)
        wl.addWidget(card)

        self.details = Card()
        dl = QHBoxLayout(self.details)
        dl.setContentsMargins(22, 16, 22, 16)
        self.event_lbl = QLabel("Detected events: 0")
        self.clip_lbl = QLabel("Candidate clips: 0")
        dl.addWidget(self.event_lbl); dl.addStretch(); dl.addWidget(self.clip_lbl)
        wl.addWidget(self.details)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet(f"color:{PALETTE['soft_red']};")
        self.error_lbl.setWordWrap(True)
        wl.addWidget(self.error_lbl)

        btns = QHBoxLayout()
        btns.addStretch()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        btns.addWidget(self.pause_btn); btns.addWidget(self.cancel_btn)
        wl.addLayout(btns)
        lay.addWidget(self.work)
        self.work.hide()

    def start(self, name: str) -> None:
        self.idle.hide(); self.work.show()
        self.error_lbl.clear()
        self.stage_lbl.setText(f"Analysing — {name}")
        self.msg_lbl.setText("Preparing…")
        self.overall.setValue(0)
        self.event_lbl.setText("Detected events: 0")
        self.clip_lbl.setText("Candidate clips: 0")
        self._paused = False
        self.pause_btn.setText("Pause")

    def update_progress(self, fraction: float, stage: str, message: str) -> None:
        self.overall.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.stage_lbl.setText(f"Stage: {stage}")
        if message:
            self.msg_lbl.setText(message)

    def set_counts(self, events: int, clips: int) -> None:
        self.event_lbl.setText(f"Detected events: {events}")
        self.clip_lbl.setText(f"Candidate clips: {clips}")

    def set_error(self, text: str) -> None:
        self.error_lbl.setText(text)

    def finish(self) -> None:
        self.overall.setValue(1000)
        self.stage_lbl.setText("Analysis complete")
        self.msg_lbl.setText("Analysis complete — review and export your clips on the next screen.")

    def reset(self) -> None:
        self.work.hide(); self.idle.show()

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("Resume" if self._paused else "Pause")
        self.pause_requested.emit(self._paused)
