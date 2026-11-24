"""Dashboard clarity tests."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_dashboard_copy(ctx, qtbot):
    from app.ui.dashboard import DashboardPage

    page = DashboardPage(ctx)
    qtbot.addWidget(page)
    subtitle = [l for l in page.findChildren(QLabel)
                if l.objectName() == "pageSubtitle"]
    assert subtitle[0].text() == "Your highlights, start to finish"
    assert page.review_btn.text() == "Continue"
