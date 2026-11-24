"""Analysis page clarity tests."""


def test_finish_does_not_point_to_highlights(qtbot):
    from app.ui.analysis_page import AnalysisPage

    page = AnalysisPage()
    qtbot.addWidget(page)
    page.finish()
    assert "Highlights" not in page.msg_lbl.text()
    assert "review" in page.msg_lbl.text().lower()
