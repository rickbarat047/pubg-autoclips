"""About page: version, features and honest limitations."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import APP_NAME, __version__
from .widgets.common import Card
from .tokens import PALETTE


class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        t = QLabel("About")
        t.setObjectName("pageTitle")
        lay.addWidget(t)

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 22)
        cl.setSpacing(10)
        cl.addWidget(QLabel(f"<h2 style='color:{PALETTE['accent']};margin:0'>{APP_NAME} v{__version__}</h2>"))
        intro = QLabel(
            "A free, local-first tool that analyses complete PUBG recordings, "
            "finds highlight candidates using kill-feed OCR, audio and visual signals, "
            "and renders vertical 1080×1920 short-form MP4 clips."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        cl.addWidget(intro)
        cl.addWidget(QLabel("<b>Technology</b>"))
        cl.addWidget(QLabel(
            "PySide6 · OpenCV · RapidOCR (ONNX Runtime, CPU) · NumPy/SciPy · "
            "SoundFile · FFmpeg · SQLite · Pydantic"
        ))
        cl.addWidget(QLabel("<b>Limitations (important)</b>"))
        lim = QLabel(
            "• OCR cannot reliably distinguish kills from knocks unless the feed text "
            "itself provides evidence — uncertain events are labelled as such.\n"
            "• Clutch candidates are never asserted as verified 1v2/1v3/1v4 without "
            "player-count evidence.\n"
            "• Detection accuracy on real PUBG footage has not been validated; tune "
            "calibration and confidence settings for your HUD.\n"
            "• Everything runs locally. No data is uploaded.\n"
            "• FFmpeg is distributed under LGPL/GPL depending on build — see README.md."
        )
        lim.setWordWrap(True)
        lim.setObjectName("muted")
        cl.addWidget(lim)
        lay.addWidget(card)
        lay.addStretch()
