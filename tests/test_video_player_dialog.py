"""Tests for the reusable clip player dialog."""
from app.ui.video_player_dialog import VideoPlayerDialog


def test_player_dialog_shows_controls(qtbot):
    """A missing file must still produce a usable dialog with controls."""
    dlg = VideoPlayerDialog("missing.mp4")  # must not raise
    qtbot.addWidget(dlg)
    assert dlg.play_button is not None and dlg.seek_slider is not None
