"""Assets panel: worker-based thumbnails and search filtering."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, jobs=None)


def test_clip_thumbnails_use_worker_and_filter(ctx, qtbot, monkeypatch):
    """Thumbnails must be built on a worker, and filter() must hide non-matches."""
    from app.ui.editor.assets_panel import AssetsPanel
    import app.ui.editor.assets_panel as ap

    match = ctx.db.add_match(path="match.mp4", name="rickbarat match", duration=600.0)
    h1 = ctx.db.add_highlight(match_id=match.id, start=10, end=30,
                              duration=20.0, category="KILL", score=80.0, keep=True)
    h2 = ctx.db.add_highlight(match_id=match.id, start=40, end=60,
                              duration=20.0, category="COMBAT", score=40.0, keep=True)

    started = []

    class FakeWorker:
        def __init__(self, jobs, token=None):
            started.append(list(jobs))

        done = None

        def start(self):
            pass

    monkeypatch.setattr(ap, "ThumbnailWorker", FakeWorker)

    panel = AssetsPanel(ctx)
    qtbot.addWidget(panel)
    panel.set_matches([match])
    panel.set_highlights([h1, h2])
    panel.show()
    qtbot.wait(100)

    # Thumbnails were queued on the worker, never rendered synchronously.
    assert started, "ThumbnailWorker was never started"

    # Filtering by the match/IGN text hides the non-matching clip card.
    panel.filter("zzz-no-such-clip")
    assert panel.visible_clip_count() == 0
    panel.filter("rickbarat")
    assert panel.visible_clip_count() == 2
