"""Shared-widget bug fixes and colour-sweep regression tests."""
import re
from pathlib import Path

import pytest


def test_toast_clear_empties_text(qtbot):
    """ToastLabel.clear() must clear text (not recurse into itself)."""
    from app.ui.widgets.common import ToastLabel

    toast = ToastLabel()
    qtbot.addWidget(toast)
    toast.show_message("hello")
    assert toast.text() == "hello"
    toast.clear()
    assert toast.text() == ""


def test_no_ui_colour_literals():
    """No UI module may hardcode hex colours or string QColor literals."""
    ui_dir = Path(__file__).resolve().parents[1] / "app" / "ui"
    hex_re = re.compile(r"#[0-9A-Fa-f]{6}\b")
    qcolor_re = re.compile(r"QColor\(\s*['\"]#")
    offenders = []
    for path in ui_dir.rglob("*.py"):
        if path.name == "tokens.py":  # the single source of truth
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if hex_re.search(line) or qcolor_re.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, "Hardcoded UI colours:\n" + "\n".join(offenders)
