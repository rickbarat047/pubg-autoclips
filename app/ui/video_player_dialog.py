"""Small, self-contained player for previewing a clip from the original video."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
)
from .tokens import PALETTE


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
        self.resize(960, 680)
        self.setStyleSheet(f"background: {PALETTE['dialog_bg']}; color: {PALETTE['dialog_text']};")
        self._scrubbing = False
        self._duration_ms = 0
        # Parented timers: owned by this dialog so they cannot fire into a
        # torn-down player at interpreter shutdown.
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.timeout.connect(self._commit_pending_seek)
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self._pause_safe)
        self._seek_commit_ms = 0

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(420)
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
        # QMediaPlayer ignores setPosition() until the source has finished
        # loading (durationChanged). Keep a pending seek and apply it then.
        self._pending_seek_ms: int | None = None
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        if self.start_sec > 0:
            self.seek(self.start_sec)

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

    def _player_live(self) -> bool:
        try:
            return not self.player.source().isEmpty()
        except RuntimeError:
            return False

    def _pause_safe(self) -> None:
        if self._player_live():
            self.player.pause()

    def seek(self, seconds: float) -> None:
        """Jump to an absolute position in seconds (used for marker/drag seek)."""
        if not self._player_live():
            return
        ms = int(max(0.0, float(seconds)) * 1000)
        # Before the media is ready Qt drops setPosition; remember it and
        # apply on durationChanged once the source has actually loaded.
        if self._duration_ms <= 0:
            self._pending_seek_ms = ms
            self.player.setPosition(ms)
            return
        was_playing = self.player.playbackState() == QMediaPlayer.PlayingState
        if was_playing:
            self.player.setPosition(ms)
        else:
            self.player.play()
            self._seek_commit_ms = ms
            self._commit_timer.start(150)

    def _commit_pending_seek(self) -> None:
        """Apply a deferred seek once the player has left the stopped state."""
        if not self._player_live():
            return
        self.player.setPosition(self._seek_commit_ms)
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._pause_timer.start(100)

    # -- Qt slots -----------------------------------------------------------
    def _on_duration(self, ms: int) -> None:
        self._duration_ms = ms
        if ms > 0 and getattr(self, "_pending_seek_ms", None) is not None:
            pending_ms = self._pending_seek_ms
            self._pending_seek_ms = None
            # Route through seek(): a raw setPosition() is ignored while the
            # Qt player is stopped (observed on the Windows backend).
            self.seek(pending_ms / 1000.0)

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
        self._commit_timer.stop()
        self._pause_timer.stop()
        self.stop()
        super().closeEvent(event)
