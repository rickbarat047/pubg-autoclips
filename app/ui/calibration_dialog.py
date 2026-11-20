"""First-launch / settings calibration dialog for the kill-feed region."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog as QFD, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout,
)

from ..config import NormalizedRegion
from ..detection.kill_feed.ocr_engine import OcrEngine
from ..media.decoder import frame_at
from ..utils.logging import get_logger

log = get_logger("ui.calibration")


class RegionLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#0C0E10;")
        self._pixmap: QPixmap | None = None
        self._start: QPoint | None = None
        self._rect: QRect | None = None
        self._display_rect: QRect | None = None
        self._scale = 1.0

    def set_image(self, pm: QPixmap) -> None:
        self._pixmap = pm
        self._rect = None
        self._display_rect = None
        self.update()

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        if self._pixmap is None:
            return
        p = QPainter(self)
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
        ox = (self.width() - scaled.width()) // 2
        oy = (self.height() - scaled.height()) // 2
        p.drawPixmap(ox, oy, scaled)
        self._scale = scaled.width() / max(1, self._pixmap.width())
        if self._display_rect:
            pen = QPen(QColor("#7CFC00"))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(QColor(124, 252, 0, 40))
            p.drawRect(self._display_rect)
        p.end()

    def mousePressEvent(self, e) -> None:
        if self._pixmap is None:
            return
        self._start = e.position().toPoint()
        self._display_rect = QRect(self._start, self._start)

    def mouseMoveEvent(self, e) -> None:
        if self._start is not None:
            self._display_rect = QRect(self._start, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._start is None or self._pixmap is None:
            return
        self._display_rect = QRect(self._start, e.position().toPoint()).normalized()
        self._start = None
        self.update()

    def selected_pixels(self, orig_w: int, orig_h: int) -> tuple[int, int, int, int] | None:
        if not self._display_rect or self._scale <= 0:
            return None
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
        ox = (self.width() - scaled.width()) // 2
        oy = (self.height() - scaled.height()) // 2
        r = self._display_rect
        x = int((r.x() - ox) / self._scale)
        y = int((r.y() - oy) / self._scale)
        w = int(r.width() / self._scale)
        h = int(r.height() / self._scale)
        x = max(0, min(x, orig_w - 1)); y = max(0, min(y, orig_h - 1))
        w = max(1, min(w, orig_w - x)); h = max(1, min(h, orig_h - y))
        return x, y, w, h


class CalibrationDialog(QDialog):
    def __init__(self, initial_region: NormalizedRegion | None = None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Calibrate Kill-Feed Region")
        self.resize(980, 680)
        self.original_w = 0
        self.original_h = 0
        self.image = None
        self.ocr = OcrEngine()

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        load_img = QPushButton("Load screenshot…")
        load_img.clicked.connect(self.load_image)
        load_vid = QPushButton("Use frame from video…")
        load_vid.clicked.connect(self.load_video_frame)
        self.test_btn = QPushButton("Test OCR")
        self.test_btn.clicked.connect(self.test_ocr)
        top.addWidget(load_img); top.addWidget(load_vid)
        top.addStretch(); top.addWidget(self.test_btn)
        lay.addLayout(top)

        body = QHBoxLayout()
        self.region_lbl = RegionLabel()
        body.addWidget(self.region_lbl, 3)
        side = QVBoxLayout()
        side.addWidget(QLabel("Selected region:"))
        self.preview_lbl = QLabel("No region selected")
        self.preview_lbl.setMinimumSize(320, 180)
        self.preview_lbl.setStyleSheet("background:#0C0E10;")
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        side.addWidget(self.preview_lbl)
        self.result_lbl = QLabel("OCR result will appear here.")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setObjectName("muted")
        side.addWidget(self.result_lbl)
        hint = QLabel("Draw a rectangle tightly around the kill feed in the top-right "
                      "of the screenshot. Include all kill-feed rows.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        side.addWidget(hint)
        side.addStretch()
        body.addLayout(side, 1)
        lay.addLayout(body)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        if initial_region:
            self.result_lbl.setText(
                f"Current region: x={initial_region.x:.3f} y={initial_region.y:.3f} "
                f"w={initial_region.w:.3f} h={initial_region.h:.3f}")

    def load_image(self) -> None:
        path, _ = QFD.getOpenFileName(self, "Select PUBG screenshot", "",
                                      "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self.result_lbl.setText("Could not load that image.")
            return
        self._set_qimage(img)

    def load_video_frame(self) -> None:
        path, _ = QFD.getOpenFileName(self, "Select video", "",
                                      "Video files (*.mp4 *.mkv *.mov)")
        if not path:
            return
        frame = frame_at(path, 1.0)
        if frame is None:
            self.result_lbl.setText("Could not read a frame from that video.")
            return
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._set_qimage(img.copy())

    def _set_qimage(self, img: QImage) -> None:
        self.original_w, self.original_h = img.width(), img.height()
        self.image = img
        self.region_lbl.set_image(QPixmap.fromImage(img))
        self.result_lbl.setText(f"Loaded {img.width()}×{img.height()}. "
                                "Draw a rectangle around the kill feed.")

    def _crop_array(self):
        sel = self.region_lbl.selected_pixels(self.original_w, self.original_h)
        if not sel or self.image is None:
            return None, None
        x, y, w, h = sel
        self.preview_lbl.setPixmap(
            QPixmap.fromImage(self.image).copy(x, y, w, h).scaled(
                self.preview_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        import numpy as np
        qimg = self.image.copy(x, y, w, h).convertToFormat(QImage.Format_RGB888)
        ptr = qimg.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8, count=qimg.width() * qimg.height() * 3)
        rgb = arr.reshape(qimg.height(), qimg.width(), 3)
        import cv2
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (x, y, w, h)

    def test_ocr(self) -> None:
        crop, sel = self._crop_array()
        if crop is None:
            self.result_lbl.setText("Draw a region first.")
            return
        try:
            res = self.ocr.recognize(crop)
            self.result_lbl.setText(
                f"OCR text: <b>{res.text or '(none)'}</b><br>"
                f"Confidence: {res.confidence:.2f}<br>"
                f"Region: {sel}")
            self.result_lbl.setTextFormat(Qt.RichText)
        except Exception as exc:  # noqa: BLE001
            self.result_lbl.setText(f"OCR failed: {exc}")
            log.exception("Calibration OCR failed")

    def region(self) -> NormalizedRegion | None:
        sel = self.region_lbl.selected_pixels(self.original_w, self.original_h)
        if not sel:
            return None
        x, y, w, h = sel
        nx, ny, nw, nh = (x / self.original_w, y / self.original_h,
                          w / self.original_w, h / self.original_h)
        try:
            return NormalizedRegion(x=nx, y=ny, w=nw, h=nh)
        except Exception:
            return None
