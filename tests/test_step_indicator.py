"""Step indicator widget tests."""


def test_highlights_only_current_step(qtbot):
    from app.ui.widgets.step_indicator import StepIndicator

    ind = StepIndicator(current=2)
    qtbot.addWidget(ind)
    assert [l.text() for l in ind.labels] == [
        "1 Import", "2 Analyse", "3 Review & Export",
    ]
    assert ind.labels[1].objectName() == "stepActive"
    assert ind.labels[0].objectName() == "stepIdle"
    assert ind.labels[2].objectName() == "stepIdle"
