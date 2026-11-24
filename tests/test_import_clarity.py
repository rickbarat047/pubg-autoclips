"""Import page copy clarity tests."""
from types import SimpleNamespace

import pytest

from app.ui.import_page import ImportPage


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_import_cta_relabelled_and_still_disabled(ctx, qtbot):
    page = ImportPage(ctx)
    qtbot.addWidget(page)
    assert page.import_btn.text() == "Analyse match"
    assert not page.import_btn.isEnabled()
    assert page.title.text() == "Step 1 — Add a recording"
