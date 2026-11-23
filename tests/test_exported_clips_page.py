"""Exported Clips page: empty state and export listing."""
from types import SimpleNamespace

import pytest

from app.ui.exported_clips_page import ExportedClipsPage


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)


def test_empty_state(qtbot, ctx):
    page = ExportedClipsPage(ctx)
    qtbot.addWidget(page)
    page.show()
    page.refresh()
    assert page.empty_label.isVisible()


def test_exports_are_listed_and_review_requested(qtbot, ctx):
    match = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    ctx.db.add_export(match_id=match.id, path="G:/out/clip.mp4", status="done",
                      export_type="compilation", duration=90.0, segment_count=6,
                      size_bytes=1024, layout="blur")
    page = ExportedClipsPage(ctx)
    qtbot.addWidget(page)
    page.show()
    page.refresh()
    assert not page.empty_label.isVisible()
    assert len(page.export_rows) == 1
    with qtbot.waitSignal(page.review_requested, timeout=2000) as sig:
        page.review_btn.click()
    assert sig.args == [match.id]
