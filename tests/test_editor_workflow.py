"""Top-bar EXPORT workflow and dialog smoke tests."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QDialog


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)


def test_export_uses_segments_and_shows_result(qtbot, ctx, monkeypatch, tmp_path):
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    m = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    win.current_match_id = m.id

    captured = {}
    monkeypatch.setattr(win, "start_compilation",
                        lambda req: captured.update(req))
    win.export()
    assert "segments" in captured
    assert captured["video_duration"] == 600.0

    out = tmp_path / "result.mp4"
    win.show_result(str(out), 90.0)
    assert win.result_card.isVisible()
    assert win.result_play_btn is not None
    assert win.result_folder_btn is not None
    assert win.result_back_btn is not None


def test_dialogs_are_qdialogs(qtbot, ctx, monkeypatch):
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    # Avoid a modal exec() blocking the test; the dialog object is still built.
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    win.open_settings()
    win.open_about()
    win.open_calibration()
    dialogs = getattr(win, "_dialogs", [])
    assert any(isinstance(d, QDialog) for d in dialogs)
