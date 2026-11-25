"""The single-window editor shell replaces the old stacked page navigation."""
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QStackedWidget


@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None,
                           save_settings=lambda: None,
                           register_thread=lambda t: None,
                           shutdown=lambda: None)


def test_editor_shell_has_regions_and_signals(ctx, qtbot):
    from app.ui.editor.editor_window import EditorWindow

    win = EditorWindow(ctx)
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(50)

    # Old multi-page navigation must be gone.
    assert win.findChild(QStackedWidget) is None
    assert not hasattr(win, "nav_buttons")

    # Five visible shell regions.
    for name in ("topbar", "assets_panel", "preview_panel",
                 "inspector_panel", "timeline_panel"):
        region = getattr(win, name)
        assert region is not None, name
        assert region.isVisible(), name

    # Six workflow signals.
    for sig in ("import_requested", "export_requested", "settings_requested",
                "about_requested", "calibration_requested", "search_changed"):
        assert hasattr(win, sig), sig
