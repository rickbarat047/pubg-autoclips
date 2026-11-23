"""Dashboard page: live statistics, recent activity, quick import."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from .widgets.common import Card, empty_state, section_header, stat_card


class DashboardPage(QWidget):
    import_requested = Signal()
    review_requested = Signal(int)
    highlights_requested = Signal()
    settings_requested = Signal()
    about_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        sub = QLabel("Overview of your local highlight workspace")
        sub.setObjectName("pageSubtitle")
        lay.addWidget(title); lay.addWidget(sub)

        self.stats_row = QGridLayout()
        self.stats_row.setSpacing(14)
        lay.addLayout(self.stats_row)

        header, self.import_btn = section_header("Recent matches", "Import recording")
        self.import_btn.clicked.connect(self.import_requested.emit)
        lay.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.recent = QListWidget()
        self.recent.setMinimumHeight(220)
        body.addWidget(self.recent, 2)

        self.side = QVBoxLayout()
        info = Card()
        il = QVBoxLayout(info)
        il.setContentsMargins(18, 16, 18, 16)
        h = QLabel("Your setup")
        h.setObjectName("sectionTitle")
        il.addWidget(h)
        self.ign_lbl = QLabel()
        self.out_lbl = QLabel()
        self.out_lbl.setObjectName("muted")
        self.out_lbl.setWordWrap(True)
        il.addWidget(self.ign_lbl); il.addWidget(self.out_lbl)
        self.side.addWidget(info)

        # Quick actions — the review step and settings no longer live in the
        # sidebar, so expose them here in plain language.
        actions = Card()
        al = QVBoxLayout(actions)
        al.setContentsMargins(18, 16, 18, 16)
        al.addWidget(section_header("Quick actions")[0])
        self.review_btn = QPushButton("Review latest match")
        self.review_btn.setObjectName("primary")
        self.review_btn.setEnabled(False)
        self.review_btn.clicked.connect(self._on_review_clicked)
        al.addWidget(self.review_btn)
        self.highlights_btn = QPushButton("All highlights")
        self.highlights_btn.setObjectName("ghost")
        self.highlights_btn.setToolTip("Play every detected clip from the original recording")
        self.highlights_btn.clicked.connect(self.highlights_requested.emit)
        al.addWidget(self.highlights_btn)
        links = QHBoxLayout()
        settings_link = QPushButton("Settings")
        settings_link.setObjectName("ghost")
        settings_link.clicked.connect(self.settings_requested.emit)
        about_link = QPushButton("About")
        about_link.setObjectName("ghost")
        about_link.clicked.connect(self.about_requested.emit)
        links.addWidget(settings_link); links.addWidget(about_link)
        al.addLayout(links)
        self.side.addWidget(actions)
        self.side.addStretch()
        self._latest_match: int | None = None
        body.addLayout(self.side, 1)
        lay.addLayout(body)
        self.refresh()

    def refresh(self) -> None:
        stats = self.ctx.db.stats()
        while self.stats_row.count():
            item = self.stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (label, val) in enumerate([
            ("Matches processed", stats["matches"]),
            ("Highlights found", stats["highlights"]),
            ("Clips exported", stats["exports"]),
        ]):
            self.stats_row.addWidget(stat_card(label, str(val)), 0, i)

        self.recent.clear()
        matches = self.ctx.db.list_matches(limit=12)
        if not matches:
            empty, _ = empty_state("🎬", "No matches yet",
                                   "Import an MP4 recording to get started.")
            # Put empty state into a list item for simplicity.
            item = QListWidgetItem(self.recent)
            item.setSizeHint(empty.sizeHint())
            self.recent.setItemWidget(item, empty)
        else:
            for m in matches:
                text = (f"{m.name}   •   {m.duration/60:.1f} min   •   "
                        f"{m.width}×{m.height}   •   {m.status}")
                self.recent.addItem(QListWidgetItem(text))

        self._latest_match = matches[0].id if matches else None
        self.review_btn.setEnabled(self._latest_match is not None)

        s = self.ctx.settings
        self.ign_lbl.setText(f"In-game name: <b style='color:#7CFC00'>{s.ign or 'Not set'}</b>")
        self.ign_lbl.setTextFormat(Qt.RichText)
        self.out_lbl.setText(f"Output folder:\n{s.output_folder or 'Not configured'}")

    def _on_review_clicked(self) -> None:
        if self._latest_match is not None:
            self.review_requested.emit(self._latest_match)
