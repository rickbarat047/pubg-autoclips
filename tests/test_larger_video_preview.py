"""Larger video preview tests — standalone and embedded player sizing."""
from types import SimpleNamespace

from PySide6.QtWidgets import QScrollArea

from app.ui.video_player_dialog import VideoPlayerDialog


def test_standalone_player_is_large_and_survives_missing_source(qtbot):
    dlg = VideoPlayerDialog("G:/does-not-exist.mp4")
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.wait(100)
    assert dlg.video_widget.minimumHeight() == 420
    assert dlg.width() >= 900
    assert dlg.height() >= 640
    assert dlg.error_label.isVisible()


def test_embedded_player_enlarged_and_timeline_reachable(db, settings, qtbot):
    from app.ui.compile_page import CompilePage

    ctx = SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)
    match = db.add_match(path="x.mp4", name="x", duration=600.0)
    page = CompilePage(ctx)
    qtbot.addWidget(page)
    page.resize(900, 720)
    page.set_match(match.id)
    page.show()
    qtbot.wait(200)

    assert page.player_host.maximumHeight() >= 300
    dlg = page.player_host.findChild(VideoPlayerDialog)
    assert dlg is not None
    assert dlg.video_widget.minimumHeight() >= 240
    scroll = page.findChild(QScrollArea)
    assert scroll is not None
    assert page.timeline in scroll.findChildren(type(page.timeline))
