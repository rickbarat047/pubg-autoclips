"""Navigation flow: the app is a single editor window, not a stacked page set."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QStackedWidget

from app.ui.main_window import MainWindow


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)


def test_single_window_no_sidebar_navigation(qtbot, ctx):
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    # The old sidebar/navigation stack is gone. QTabWidget (used by panels)
    # creates an internal QStackedWidget, so target the old nav stack by name.
    stacks = [s for s in win.findChildren(QStackedWidget)
              if s.objectName() == "content"]
    assert stacks == []
    assert not hasattr(win, "nav_buttons")
    # The shell regions exist.
    for name in ("topbar", "assets_panel", "preview_panel",
                 "inspector_panel", "timeline_panel"):
        assert getattr(win, name) is not None
