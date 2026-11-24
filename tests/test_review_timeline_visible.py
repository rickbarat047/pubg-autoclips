"""The match timeline must be reachable on the Review & Export page."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QScrollArea

from app.ui.compile_page import CompilePage


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_timeline_is_reachable_in_a_scrolling_page(ctx, qtbot):
    """Regression: the timeline was pushed below the viewport with no way to scroll.

    The Review page used to add every widget to a plain QVBoxLayout. The
    embedded 372px player pushed the timeline to y~708, past the bottom of a
    normal window, so users could not see or drag it to add a missed moment.
    """
    page = CompilePage(ctx)
    qtbot.addWidget(page)
    page.resize(900, 600)
    page.show()
    qtbot.wait(200)

    # The page must expose a scroll area that contains the timeline.
    scroll = page.findChild(QScrollArea)
    assert scroll is not None, "Review page needs a scroll area so all content is reachable"
    assert page.timeline in scroll.findChildren(type(page.timeline))

    # The embedded player height is capped; the page scroll area keeps the
    # timeline reachable even when the player is enlarged.
    host = page.player_host
    assert host.maximumHeight() > 0, "Embedded player height must be capped"
    assert host.maximumHeight() <= 400
