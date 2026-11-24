"""Review & Export page copy tests."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_review_copy_and_manual_add_survive(ctx, qtbot):
    from app.ui.compile_page import CompilePage

    page = CompilePage(ctx)
    qtbot.addWidget(page)
    assert page.title.text() == "Step 3 — Review & export"
    assert page.mode.itemText(0) == "One combined video"
    assert page.mode.itemText(1) == "Separate video clips"
    assert page.add_range_btn.text() == "+ Add 20s here"
