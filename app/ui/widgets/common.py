"""Reusable styled widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)


class Card(QFrame):
    def __init__(self, parent=None, hover: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("cardHover" if hover else "card")
        self.setFrameShape(QFrame.NoFrame)


def stat_card(title: str, value: str = "0", accent: bool = True) -> Card:
    card = Card()
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 18, 20, 18)
    v = QLabel(value)
    v.setObjectName("statValue" if accent else "pageTitle")
    l = QLabel(title)
    l.setObjectName("statLabel")
    lay.addWidget(v)
    lay.addWidget(l)
    return card


def section_header(title: str, action_text: str | None = None):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    t = QLabel(title)
    t.setObjectName("sectionTitle")
    lay.addWidget(t)
    lay.addStretch()
    btn = None
    if action_text:
        btn = QPushButton(action_text)
        btn.setObjectName("ghost")
        lay.addWidget(btn)
    return w, btn


def empty_state(icon: str, title: str, message: str, action_text: str | None = None):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setAlignment(Qt.AlignCenter)
    lay.setSpacing(8)
    ic = QLabel(icon)
    ic.setAlignment(Qt.AlignCenter)
    ic.setStyleSheet("font-size: 48px;")
    ttl = QLabel(title)
    ttl.setAlignment(Qt.AlignCenter)
    ttl.setStyleSheet("font-size: 17px; font-weight: 700; color: #E8ECEF;")
    msg = QLabel(message)
    msg.setAlignment(Qt.AlignCenter)
    msg.setObjectName("muted")
    msg.setWordWrap(True)
    lay.addStretch(); lay.addWidget(ic); lay.addWidget(ttl); lay.addWidget(msg)
    btn = None
    if action_text:
        btn = QPushButton(action_text)
        btn.setObjectName("primary")
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lay.addWidget(btn)
    lay.addStretch()
    return w, btn


class ToastLabel(QLabel):
    """A transient status message row."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("muted")
        self.setWordWrap(True)
        self.hide()

    def show_message(self, text: str, error: bool = False) -> None:
        self.setText(text)
        self.setStyleSheet("color: #FF8A8A;" if error else "color: #7CFC00;")
        self.show()

    def clear(self) -> None:
        self.clear()
        self.hide()
