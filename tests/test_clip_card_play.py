"""Highlight cards must offer a direct play action."""
from types import SimpleNamespace

from app.ui.clips_page import ClipCard


def _highlight() -> SimpleNamespace:
    return SimpleNamespace(
        id=42, category="KILL", start=100.0, end=120.0, duration=20.0,
        score=80.0, confidence=0.9, keep=True,
    )


def test_clip_card_has_play_button_and_emits_highlight_id(qtbot):
    card = ClipCard(_highlight(), "missing.mp4")
    qtbot.addWidget(card)

    assert card.play_button.text() == "▶ Play"
    with qtbot.waitSignal(card.play_requested, timeout=1000) as signal:
        card.play_button.click()
    assert signal.args == [42]
