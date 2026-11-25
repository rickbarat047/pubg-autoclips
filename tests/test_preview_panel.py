"""Tests for the editor centre preview panel."""
from PySide6.QtWidgets import QApplication


def test_timecode_updates_and_seek_works(synthetic_video, qtbot):
    """A seek must move playback and the timecode label must show mm:ss."""
    from app.ui.editor.preview_panel import PreviewPanel

    panel = PreviewPanel()
    qtbot.addWidget(panel)
    panel.set_source(str(synthetic_video))
    qtbot.wait(300)  # let durationChanged fire and load the source

    panel.seek(2.0)
    qtbot.wait(600)  # deferred commit needs a play->pause tick

    assert abs(panel.position() - 2.0) < 0.5
    assert "00:00:02" in panel.timecode_label.text()
