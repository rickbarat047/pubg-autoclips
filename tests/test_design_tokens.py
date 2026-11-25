"""Design token single-source-of-truth tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_palette_matches_spec_and_no_old_accent_literals():
    from app.ui import tokens

    expected = {
        "bg": "#171A1E",
        "sidebar": "#14171A",
        "card": "#20252B",
        "elevated": "#272D34",
        "border": "#343B43",
        "text": "#F3F4F6",
        "text_muted": "#9CA3AF",
        "text_dim": "#737D88",
        "accent": "#A3E635",
        "accent_light": "#BEF264",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#EF4444",
    }
    for key, value in expected.items():
        assert tokens.PALETTE[key] == value, key
    assert isinstance(tokens.font_family(), str)
    assert tokens.font_family()

    # No old lime accent literal remains in widget code.
    for py in (ROOT / "app" / "ui").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "#7CFC00" not in text, f"old accent literal in {py}"


def test_theme_contains_palette_values():
    from app.ui import tokens

    qss = (ROOT / "assets" / "styles" / "theme.qss").read_text(encoding="utf-8")
    for value in (tokens.PALETTE["bg"], tokens.PALETTE["card"],
                  tokens.PALETTE["accent"], tokens.PALETTE["danger"]):
        assert value in qss, value
