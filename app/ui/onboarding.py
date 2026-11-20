"""First-launch onboarding wizard."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from .calibration_dialog import CalibrationDialog
from .widgets.common import Card


class OnboardingWizard(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Welcome to PUBG AutoClips")
        self.resize(720, 460)
        self.region = ctx.settings.calibration

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self.step_lbl = QLabel("Step 1 of 3")
        self.step_lbl.setObjectName("accent")
        lay.addWidget(self.step_lbl)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.stack.addWidget(self._page_ign())
        self.stack.addWidget(self._page_calibration())
        self.stack.addWidget(self._page_output())

        btns = QHBoxLayout()
        self.back = QPushButton("Back")
        self.next = QPushButton("Next")
        self.next.setObjectName("primary")
        btns.addStretch(); btns.addWidget(self.back); btns.addWidget(self.next)
        lay.addLayout(btns)
        self.back.clicked.connect(self._prev)
        self.next.clicked.connect(self._next)
        self._update()

    def _page(self, title: str, desc: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 8, 4, 8)
        h = QLabel(title); h.setObjectName("pageTitle")
        d = QLabel(desc); d.setObjectName("muted"); d.setWordWrap(True)
        lay.addWidget(h); lay.addWidget(d); lay.addSpacing(10)
        return w, lay

    def _page_ign(self) -> QWidget:
        w, lay = self._page("Your in-game name",
                            "Enter the exact PUBG nickname shown in the kill feed.")
        self.ign_edit = QLineEdit(self.ctx.settings.ign)
        self.ign_edit.setPlaceholderText("e.g. ProPlayer42")
        card = Card(); cl = QVBoxLayout(card); cl.setContentsMargins(18, 16, 18, 16)
        cl.addWidget(QLabel("PUBG IGN")); cl.addWidget(self.ign_edit)
        lay.addWidget(card); lay.addStretch()
        return w

    def _page_calibration(self) -> QWidget:
        w, lay = self._page("Calibrate the kill feed",
                            "Load a PUBG screenshot, draw a rectangle around the kill "
                            "feed, run the OCR test and confirm. This region is stored "
                            "in normalised coordinates so it works at any resolution.")
        self.cal_btn = QPushButton("Open calibration tool…")
        self.cal_btn.clicked.connect(self._calibrate)
        self.cal_lbl = QLabel("No region set yet")
        self.cal_lbl.setObjectName("muted")
        card = Card(); cl = QVBoxLayout(card); cl.setContentsMargins(18, 16, 18, 16)
        cl.addWidget(self.cal_btn); cl.addWidget(self.cal_lbl)
        lay.addWidget(card); lay.addStretch()
        return w

    def _page_output(self) -> QWidget:
        w, lay = self._page("Output folder",
                            "Choose where exported vertical clips will be saved.")
        self.out_edit = QLineEdit(self.ctx.settings.output_folder)
        b = QPushButton("Browse…"); b.clicked.connect(self._browse)
        h = QHBoxLayout(); h.addWidget(self.out_edit); h.addWidget(b)
        card = Card(); cl = QVBoxLayout(card); cl.setContentsMargins(18, 16, 18, 16)
        cl.addWidget(QLabel("Exported clips folder")); cl.addLayout(h)
        lay.addWidget(card); lay.addStretch()
        return w

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if d:
            self.out_edit.setText(d)

    def _calibrate(self) -> None:
        dlg = CalibrationDialog(self.ctx.settings.calibration, self)
        if dlg.exec() == QDialog.Accepted:
            r = dlg.region()
            if r:
                self.region = r
                self.cal_lbl.setText(
                    f"✓ Region saved: x={r.x:.3f} y={r.y:.3f} w={r.w:.3f} h={r.h:.3f}")
                self.cal_lbl.setStyleSheet("color:#7CFC00;")

    def _prev(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update()

    def _next(self) -> None:
        if self.stack.currentIndex() < self.stack.count() - 1:
            self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
            self._update()
        else:
            self._finish()

    def _update(self) -> None:
        i = self.stack.currentIndex()
        self.step_lbl.setText(f"Step {i+1} of {self.stack.count()}")
        self.back.setEnabled(i > 0)
        self.next.setText("Finish" if i == self.stack.count() - 1 else "Next")

    def _finish(self) -> None:
        s = self.ctx.settings
        s.ign = self.ign_edit.text().strip()
        s.calibration = self.region
        s.output_folder = self.out_edit.text().strip()
        s.onboarding_complete = True
        self.ctx.save_settings()
        self.accept()
