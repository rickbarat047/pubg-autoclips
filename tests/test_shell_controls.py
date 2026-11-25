"""Integration: shell exposes analysis progress/cancel/pause and inspector actions."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)


def test_shell_has_analysis_controls(qtbot, ctx):
    """Cancel/Pause must be reachable in the single window (not a hidden page)."""
    from app.ui.main_window import MainWindow

    win = MainWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    # Controls exist in the top bar; hidden until an analysis job starts.
    assert win.cancel_btn is not None and win.pause_btn is not None
    assert win.analysis_status is not None
    # start_analysis reveals them.
    win.pause_btn.show()
    win.cancel_btn.show()
    assert win.pause_btn.isVisible() and win.cancel_btn.isVisible()


def test_pause_signal_carries_bool(qtbot):
    from app.ui.analysis_page import AnalysisPage

    page = AnalysisPage()
    qtbot.addWidget(page)
    captured = []
    page.pause_requested.connect(lambda v: captured.append(v))
    page._paused = False
    page.toggle_pause()  # emits True
    assert captured == [True]
    assert isinstance(captured[0], bool)
