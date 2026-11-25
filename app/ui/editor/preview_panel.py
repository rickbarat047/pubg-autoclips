"""Centre preview panel: real video playback with timecode and seek.

Mirrors the proven seek behaviour of VideoPlayerDialog (the Windows Qt
backend ignores setPosition() while stopped, so seeks are committed after a
short play->pause tick).  Kept as a standalone widget so the editor shell can
host it in its centre region.

The QMediaPlayer/QAudioOutput are created lazily on the first ``set_source``.
Constructing a media backend that is never used is the main cause of the
Windows Qt-multimedia teardown crash, so widgets that only build the editor
shell (tests, navigation) never instantiate one.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)


def _fmt(ms: int) -> str:
    """Format milliseconds as HH:MM:SS."""
    seconds = max(0, int(ms) // 1000)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class PreviewPanel(QWidget):
    """Video preview with play/pause, a scrub slider and a timecode label."""

    position_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._duration_ms = 0
        self._pending_seek_ms: int | None = None
        self._start = 0.0
        self._end: float | None = None
        self._scrubbing = False
        self.player: QMediaPlayer | None = None
        self.audio: QAudioOutput | None = None
        # Parented, single-shot timers: unlike QTimer.singleShot these are owned
        # by this widget, so they cannot fire into a torn-down C++ player.
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.timeout.connect(self._commit_pending_seek)
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self.player_pause_safe)
        self._seek_commit_ms = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(240)
        lay.addWidget(self.video_widget, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("▶ Play")
        self.play_button.setObjectName("primary")
        self.play_button.clicked.connect(self.toggle)
        controls.addWidget(self.play_button)

        self.seek_slider = QSlider()
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderPressed.connect(self._scrub_start)
        self.seek_slider.sliderReleased.connect(self._scrub_end)
        controls.addWidget(self.seek_slider, 1)

        self.timecode_label = QLabel("00:00:00 / 00:00:00")
        self.timecode_label.setObjectName("muted")
        controls.addWidget(self.timecode_label)
        lay.addLayout(controls)

    def _ensure_player(self) -> bool:
        """Create the media backend on first use; return True when available."""
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video_widget)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
        return self.player is not None

    # -- public API ----------------------------------------------------------
    def set_source(self, path: str) -> None:
        """Load a video file for playback (lazily creates the backend)."""
        self.source_path = path
        if not path and self.player is None:
            return
        self._ensure_player()
        self.player.setSource(QUrl.fromLocalFile(path) if path else QUrl())

    def set_bounds(self, start: float, end: float | None = None) -> None:
        """Restrict playback to [start, end]; used to preview a single clip."""
        self._start = max(0.0, float(start))
        self._end = float(end) if end is not None else None

    def play(self) -> None:
        if not self._player_live():
            return
        if self._end is not None and self.position() >= self._end:
            self.seek(self._start)
        self.player.play()
        self.play_button.setText("❚❚ Pause")

    def pause(self) -> None:
        if self.player is not None:
            self.player.pause()
        self.play_button.setText("▶ Play")

    def toggle(self) -> None:
        if self.player is not None and \
                self.player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self.player is not None:
            self.player.stop()
        self.play_button.setText("▶ Play")

    def position(self) -> float:
        return self.player.position() / 1000.0 if self.player is not None else 0.0

    def _player_live(self) -> bool:
        """Guard against callbacks arriving after Qt has torn the player down."""
        if self.player is None:
            return False
        try:
            return not self.player.source().isEmpty()
        except RuntimeError:
            return False

    def player_pause_safe(self) -> None:
        if self._player_live():
            self.player.pause()

    def seek(self, seconds: float) -> None:
        if not self._player_live():
            return
        ms = int(max(0.0, float(seconds)) * 1000)
        if self._duration_ms <= 0:
            self._pending_seek_ms = ms
            self.player.setPosition(ms)
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.setPosition(ms)
        else:
            self.player.play()
            self._seek_commit_ms = ms
            self._commit_timer.start(150)

    def _commit_pending_seek(self) -> None:
        if not self._player_live():
            return
        ms = self._seek_commit_ms
        self.player.setPosition(ms)
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self._pause_timer.start(100)

    # -- Qt slots ------------------------------------------------------------
    def _on_duration(self, ms: int) -> None:
        self._duration_ms = ms
        if ms > 0 and self._pending_seek_ms is not None:
            pending = self._pending_seek_ms
            self._pending_seek_ms = None
            self.seek(pending / 1000.0)

    def _on_position(self, ms: int) -> None:
        if self._end is not None and ms >= self._end * 1000:
            self.player.pause()
            self.player.setPosition(int(self._end * 1000))
            self.play_button.setText("▶ Play")
        self.timecode_label.setText(f"{_fmt(ms)} / {_fmt(self._duration_ms)}")
        if not self._scrubbing and self._duration_ms > 0:
            self.seek_slider.setValue(int(ms / self._duration_ms * 1000))
        self.position_changed.emit(ms / 1000.0)

    def _scrub_start(self) -> None:
        self._scrubbing = True

    def _scrub_end(self) -> None:
        self._scrubbing = False
        if self._duration_ms > 0:
            # Slider is a 0-1000 fraction; _duration_ms is milliseconds;
            # seek() expects SECONDS — divide by 1000 here.
            self.seek(self.seek_slider.value() / 1000.0 * self._duration_ms / 1000.0)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Stop timers and the media pipeline before teardown to avoid races."""
        self._commit_timer.stop()
        self._pause_timer.stop()
        if self.player is not None:
            try:
                self.player.stop()
            except Exception:  # noqa: BLE001 - best effort during teardown
                pass
        super().closeEvent(event)
