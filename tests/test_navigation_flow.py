"""Navigation flow: only three sidebar items, review reachable after analysis."""
from types import SimpleNamespace

import pytest

from app.ui.main_window import MainWindow


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           shutdown=lambda: None)


def test_sidebar_has_only_three_items(qtbot, ctx):
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    labels = [" ".join(b.text().split()[1:]) for b in win.nav_buttons]
    assert labels == ["Dashboard", "Import", "Exported Clips"]
