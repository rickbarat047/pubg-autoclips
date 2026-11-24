"""Small 3-step progress indicator shown at the top of the main workflow pages."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StepIndicator(QWidget):
    """A compact '1 Import → 2 Analyse → 3 Review & Export' progress strip.

    The current step is highlighted via the ``stepActive`` object name so the
    theme can style it; the others use ``stepIdle``. Steps are 1-based.
    """

    STEPS = ["1 Import", "2 Analyse", "3 Review & Export"]

    def __init__(self, current: int = 1, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.labels: list[QLabel] = []
        for step in self.STEPS:
            label = QLabel(step)
            label.setObjectName("stepIdle")
            lay.addWidget(label)
            self.labels.append(label)
        lay.addStretch()
        self.set_current(current)

    def set_current(self, step: int) -> None:
        """Highlight step ``step`` (1-based) and dim the others."""
        for i, label in enumerate(self.labels, start=1):
            name = "stepActive" if i == step else "stepIdle"
            label.setObjectName(name)
            label.style().unpolish(label)
            label.style().polish(label)
