"""Design tokens — single source of truth for colour and type.

Every UI colour and the font family derive from here so the theme has no
scattered literals. ``font_family()`` prefers Inter when installed and falls
back to Segoe UI (Windows default); Inter is detected at runtime, never
bundled.
"""
from __future__ import annotations

PALETTE: dict[str, str] = {
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
    # Supporting tones used by specific widgets (all still tokenised).
    "soft_red": "#FF8A8A",
    "soft_yellow": "#E8C56A",
    "heading": "#E8ECEF",
    "dim_alt": "#9AA5AD",
    "dim_alt2": "#7E8A92",
    "viewport": "#0C0E10",
    "thumb": "#0F1214",
    "track": "#161B1E",
    "track_alt": "#22282D",
    "on_accent": "#10150A",
    "white": "#FFFFFF",
    "dialog_bg": "#14161A",
    "dialog_text": "#E8ECF1",
    # Category colours (softened accent-family tokens).
    "kill": "#A3E635",
    "multi_kill": "#B6FF3D",
    "clutch": "#FFC542",
    "knock": "#FF8A5B",
    "knock_candidate": "#FFAB8A",
    "combat": "#42C6FF",
    "manual": "#FF5EDB",
}

TYPE: dict[str, int] = {
    "title": 26,
    "section": 17,
    "body": 14,
    "label": 11,
}


def font_family() -> str:
    """Return the UI font family: Inter if present, else Segoe UI."""
    try:
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication
        # QFontDatabase.families() crashes natively when no QApplication
        # exists (e.g. theme loaded before the app, or in headless tests).
        if QApplication.instance() is None:
            return "Segoe UI"
        families = {f.lower() for f in QFontDatabase.families()}
        if "inter" in families:
            return "Inter"
    except Exception:
        pass
    return "Segoe UI"


def qss() -> str:
    """Build the application stylesheet from tokens."""
    p = PALETTE
    t = TYPE
    font = font_family()
    return f"""
QWidget {{
    background: {p['bg']}; color: {p['text']};
    font-family: "{font}", "Segoe UI", sans-serif;
    font-size: {t['body']}px;
}}
QMainWindow, QDialog {{ background: {p['bg']}; }}
#sidebar {{ background: {p['sidebar']}; border-right: 1px solid {p['border']}; }}
#brand {{ font-size: {t['section']}px; font-weight: 700; color: {p['text']}; }}
#brandSub {{ font-size: {t['label']}px; color: {p['accent']}; letter-spacing: 2px; }}
QPushButton#navBtn {{
    background: transparent; color: {p['text_muted']}; border: none;
    text-align: left; padding: 12px 16px; border-radius: 8px;
    font-size: {t['body']}px; font-weight: 600;
}}
QPushButton#navBtn:hover {{ background: {p['elevated']}; color: {p['text']}; }}
QPushButton#navBtn:checked {{
    background: {p['card']}; color: {p['accent']};
    border-left: 3px solid {p['accent']};
}}
#content {{ background: {p['bg']}; }}
QLabel#pageTitle {{ font-size: {t['title']}px; font-weight: 700; color: {p['text']}; }}
QLabel#pageSubtitle {{ font-size: {t['body']}px; color: {p['text_muted']}; }}
QLabel#sectionTitle {{ font-size: {t['section']}px; font-weight: 700; color: {p['text']}; }}
QLabel#muted {{ color: {p['text_dim']}; }}
QLabel#accent {{ color: {p['accent']}; font-weight: 600; }}
QLabel#stepIdle {{ color: {p['text_dim']}; font-size: {t['label'] + 1}px; font-weight: 600; }}
QLabel#stepActive {{
    color: {p['bg']}; font-size: {t['label'] + 1}px; font-weight: 700;
    background: {p['accent']}; border-radius: 12px; padding: 4px 10px;
}}
QFrame#card {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 12px; }}
QFrame#cardHover:hover {{ border: 1px solid {p['accent']}; background: {p['elevated']}; }}
QLabel#statValue {{ font-size: {t['title'] + 2}px; font-weight: 700; color: {p['accent']}; }}
QLabel#statLabel {{ font-size: {t['label'] + 1}px; color: {p['text_muted']}; }}
QPushButton {{
    background: {p['elevated']}; color: {p['text']}; border: 1px solid {p['border']};
    border-radius: 8px; padding: 9px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {p['border']}; }}
QPushButton:disabled {{ background: {p['card']}; color: {p['text_dim']}; }}
QPushButton#primary {{ background: {p['accent']}; color: {p['bg']}; border: 1px solid {p['accent_light']}; }}
QPushButton#primary:hover {{ background: {p['accent_light']}; }}
QPushButton#primary:disabled {{ background: {p['border']}; color: {p['text_dim']}; }}
QPushButton#danger {{ background: {p['elevated']}; color: {p['danger']}; border: 1px solid {p['danger']}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid {p['border']}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
    background: {p['sidebar']}; border: 1px solid {p['border']}; border-radius: 7px;
    padding: 8px 10px; color: {p['text']}; selection-background-color: {p['accent']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['border']}; }}
QCheckBox::indicator {{ border: 1px solid {p['border']}; background: {p['sidebar']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
QListWidget, QTableWidget, QTreeWidget {{
    background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 10px;
}}
QListWidget::item:selected {{ background: {p['card']}; color: {p['accent']}; }}
QProgressBar {{ background: {p['elevated']}; border: none; border-radius: 6px; height: 8px; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 6px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 30px; }}
#dropZone {{ border: 2px dashed {p['border']}; border-radius: 12px; background: {p['card']}; }}
#dropZoneActive {{ border: 2px dashed {p['accent']}; background: {p['card']}; }}
QToolTip {{ background: {p['elevated']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 5px; }}
"""
