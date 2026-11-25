"""Right-hand Inspector for the selected clip: properties + real edit actions."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..tokens import PALETTE


class InspectorPanel(QWidget):
    bounds_changed = Signal(int, float, float)  # manual_id, start, end
    add_at_playhead = Signal()
    split_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segment = None
        self._manual_id: int | None = None
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel("Inspector")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        self.info = QLabel("Select a clip on the timeline to edit it.")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        form = QFormLayout()
        self.start_sb = QDoubleSpinBox()
        self.end_sb = QDoubleSpinBox()
        for sb in (self.start_sb, self.end_sb):
            sb.setRange(0.0, 100000.0)
            sb.setDecimals(1)
            sb.setSuffix(" s")
        form.addRow(QLabel("Start"), self.start_sb)
        form.addRow(QLabel("End"), self.end_sb)
        root.addLayout(form)

        actions = QHBoxLayout()
        self.add_btn = QPushButton("Add 20s")
        self.add_btn.setObjectName("ghost")
        self.add_btn.setToolTip("Add a 20-second clip at the playhead")
        self.split_btn = QPushButton("Split")
        self.split_btn.setObjectName("ghost")
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("danger")
        actions.addWidget(self.add_btn)
        actions.addWidget(self.split_btn)
        actions.addWidget(self.remove_btn)
        root.addLayout(actions)
        root.addStretch()

        self.start_sb.valueChanged.connect(self._on_bounds)
        self.end_sb.valueChanged.connect(self._on_bounds)
        self.add_btn.clicked.connect(self.add_at_playhead.emit)
        self.split_btn.clicked.connect(self.split_requested.emit)
        self.remove_btn.clicked.connect(self.remove_requested.emit)

    # ---- data -----------------------------------------------------------
    def set_segment(self, segment) -> None:
        self._segment = segment
        self._manual_id = None
        if segment is None:
            self.info.setText("Select a clip on the timeline to edit it.")
            self.start_sb.setValue(0.0)
            self.end_sb.setValue(0.0)
            return
        evidence = getattr(segment, "evidence", None) or {}
        self._manual_id = evidence.get("manual_id")
        cat = getattr(segment, "category", "CLIP")
        score = getattr(segment, "score", 0.0)
        conf = getattr(segment, "confidence", 0.0)
        self.info.setText(
            f"<b style='color:{PALETTE['accent']}'>{cat}</b><br>"
            f"Score {score:.0f} &nbsp; Confidence {conf:.0%}"
        )
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self._updating = True
        self.start_sb.setValue(float(segment.start))
        self.end_sb.setValue(float(segment.end))
        self._updating = False

    def _on_bounds(self, _value: float) -> None:
        if self._updating or self._manual_id is None:
            return
        start = self.start_sb.value()
        end = self.end_sb.value()
        if end - start < 0.5:
            return
        self.bounds_changed.emit(int(self._manual_id), start, end)
