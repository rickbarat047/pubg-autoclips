"""Assets panel for the single-window editor.

Left column: a Media tab (imported matches) and a Clips tab (detected
highlights). Clip thumbnails are produced by ThumbnailWorker on a background
thread so the UI never blocks.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from ...utils.paths import thumbnails_dir
from ...workers.thumbnail_worker import ThumbJob, ThumbnailWorker
from ..widgets.common import section


class AssetsPanel(QWidget):
    """Media/Clips browser with worker-generated thumbnails and text filter."""

    clip_selected = Signal(int)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._matches: list = []
        self._highlights: list = []
        self._filter_text = ""
        self._workers: list[ThumbnailWorker] = []
        self._clip_cards: dict[int, QWidget] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.tabs = QTabWidget()
        self.media_list = QListWidget()
        self.clip_list = QListWidget()
        self.clip_list.itemClicked.connect(self._on_clip_clicked)
        self.tabs.addTab(self.media_list, "Media")
        self.tabs.addTab(self.clip_list, "Clips")
        lay.addWidget(section("Assets"))
        lay.addWidget(self.tabs)

    # ---- population ----------------------------------------------------
    def set_matches(self, matches: list) -> None:
        self._matches = list(matches)
        self.media_list.clear()
        for m in self._matches:
            item = QListWidgetItem(getattr(m, "name", str(m)))
            self.media_list.addItem(item)

    def set_highlights(self, highlights: list) -> None:
        self._highlights = list(highlights)
        self.clip_list.clear()
        self._clip_cards.clear()
        jobs: list[ThumbJob] = []
        for h in self._highlights:
            label = self._clip_label(h)
            item = QListWidgetItem(label)
            item.setData(0x0100, h.id)  # Qt.UserRole
            item.setHidden(not self._matches_filter(label))
            self.clip_list.addItem(item)
            self._clip_cards[h.id] = item
            # Match metadata for the thumbnail path.
            match = next((m for m in self._matches
                          if getattr(m, "id", None) == getattr(h, "match_id", None)), None)
            if match is not None:
                out = thumbnails_dir() / f"m{getattr(match, 'id', 0)}_h{h.id}.jpg"
                jobs.append(ThumbJob(
                    video_path=getattr(match, "path", ""),
                    timestamp=float(getattr(h, "start", 0.0)),
                    out_path=str(out),
                    key=str(h.id),
                ))
        if jobs:
            worker = ThumbnailWorker(jobs)
            if getattr(worker, "done", None) is not None:
                worker.done.connect(self._on_thumb)
            self._workers.append(worker)
            if hasattr(worker, "start"):
                worker.start()
            else:  # plain QObject worker (e.g. test fake) — run synchronously
                worker.run()

    def _clip_label(self, h) -> str:
        cat = str(getattr(h, "category", "CLIP"))
        start = float(getattr(h, "start", 0.0))
        return f"{cat}  ·  {start:.0f}s"

    # ---- filtering ------------------------------------------------------
    def filter(self, text: str) -> None:
        self._filter_text = (text or "").strip().lower()
        for h in self._highlights:
            item = self._clip_cards.get(h.id)
            if item is not None:
                item.setHidden(not self._matches_filter(self._clip_label(h)))

    def _matches_filter(self, label: str) -> bool:
        if not self._filter_text:
            return True
        haystack = label.lower()
        # Include the match name so searching an IGN that appears in the
        # recording filename finds its clips.
        for m in self._matches:
            if getattr(m, "id", None) is not None:
                haystack += " " + str(getattr(m, "name", "")).lower()
        return self._filter_text in haystack

    def visible_clip_count(self) -> int:
        return sum(1 for i in range(self.clip_list.count())
                   if not self.clip_list.item(i).isHidden())

    # ---- signals --------------------------------------------------------
    def _on_clip_clicked(self, item: QListWidgetItem) -> None:
        hid = item.data(0x0100)
        if hid is not None:
            self.clip_selected.emit(int(hid))

    def _on_thumb(self, key: str, path: str) -> None:
        # Thumbnail ready — attach to the matching item if it still exists.
        try:
            hid = int(key)
        except (TypeError, ValueError):
            return
        item = self._clip_cards.get(hid)
        if item is not None and path:
            item.setToolTip(path)
            pix = QPixmap(path)
            if not pix.isNull():
                item.setIcon(QIcon(pix.scaled(80, 50, Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)))
