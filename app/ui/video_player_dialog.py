"""Small, self-contained player for previewing a clip from the original video."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
)


class VideoPlayerDialog(QDialog):
    """Play a portion of a video file without leaving the review workflow.

    The dialog never raises on a missing source — it shows a readable message
    and disables playback, so a stale highlight cannot crash the app.
    """

    position_changed = Signal(float)

    def __init__(self, video_path: str, start: float = 0.0,
                 end: float | None = None, parent=None) -> None:
        super().__init__(parent)
        self.video_path = str(video_path)
        self.start_sec = max(0.0, float(start))
        self.end_sec = max(self.start_sec, float(end)) if end is not None else None
        self.setWindowTitle("Clip Preview")
        self.setMinimumWidth(560)
        self.resize(720, 520)
        self.setStyleSheet("background: #14161a; color: #e8ecf1;")
        self._scrubbing = False
        self._duration_ms = 0

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(300)
        self.play_button = QPushButton("▶ Play", self)
        self.play_button.setObjectName("primary")
        self.play_button.setEnabled(False)
        self.time_label = QLabel("00:00 / 00:00", self)
        self.seek_slider = QSlider(Qt.Horizontal, self)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setEnabled(False)
        self.error_label = QLabel(self)
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.seek_slider, 1)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(controls)
        layout.addWidget(self.error_label)
        layout.addWidget(QLabel("Space: play/pause   •   Esc: close", self))

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.play_button.clicked.connect(self.toggle)
        self.seek_slider.sliderPressed.connect(self._on_scrub_start)
        self.seek_slider.sliderReleased.connect(self._on_scrub_end)

        if not Path(self.video_path).is_file():
            self.error_label.setText(
                f"Video file not found:\n{self.video_path}\n"
                "Check the match location in Settings."
            )
            self.error_label.show()
            return

        self.play_button.setEnabled(True)
        self.seek_slider.setEnabled(True)
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        if self.start_sec > 0:
            self.player.setPosition(int(self.start_sec * 1000))

    # -- public API used by callers -----------------------------------------
    def play(self) -> None:
        if self.player.source().isEmpty():
            return
        if self.end_sec is not None and self.player.position() >= int(self.end_sec * 1000):
            self.player.setPosition(int(self.start_sec * 1000))
        self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self.player.stop()
        self.play_button.setText("▶ Play")

    def position(self) -> float:
        """Current playback position in seconds (used by the review page)."""
        return self.player.position() / 1000.0

    # -- Qt slots -----------------------------------------------------------
    def _on_duration(self, ms: int) -> None:
        self._duration_ms = ms

    def _on_position(self, ms: int) -> None:
        if self.end_sec is not None and ms >= int(self.end_sec * 1000):
            self.stop()
            return
        if not self._scrubbing and self._duration_ms > 0:
            self.seek_slider.setValue(int(ms / self._duration_ms * 1000))
        self.time_label.setText(f"{self._fmt(ms)} / {self._fmt(self._duration_ms)}")
        self.position_changed.emit(ms / 1000.0)

    def _on_state(self, state) -> None:
        self.play_button.setText(
            "❚❚ Pause" if state == QMediaPlayer.PlayingState else "▶ Play"
        )

    def _on_scrub_start(self) -> None:
        self._scrubbing = True

    def _on_scrub_end(self) -> None:
        self._scrubbing = False
        if self._duration_ms > 0:
            self.player.setPosition(
                int(self.seek_slider.value() / 1000 * self._duration_ms)
            )

    @staticmethod
    def _fmt(ms: int) -> str:
        total = max(0, int(ms / 1000))
        return f"{total // 60:02d}:{total % 60:02d}"

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.stop()
        super().closeEvent(event)
