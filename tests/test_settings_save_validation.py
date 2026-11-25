"""Settings save must reject min>max instead of persisting an invalid file."""
from types import SimpleNamespace


def test_save_rejects_min_gt_max(qtbot, settings, db, monkeypatch):
    from app.ui.settings_page import SettingsPage

    saved = []
    ctx = SimpleNamespace(settings=settings, db=db,
                          save_settings=lambda: saved.append(True))
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    page.min_dur.setValue(60.0)
    page.max_dur.setValue(10.0)
    page.save()
    assert saved == []  # must NOT persist
