# UI Clarity Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app self-explanatory for first-time users by replacing stale/jargon copy with plain step-based action words and adding a 3-step progress indicator — with no structural, detection, export, or database changes.

**Architecture:** A new reusable `StepIndicator` QWidget (in `app/ui/widgets/`) is inserted at the top of the Import, Analysis, and Review pages. Copy on those pages plus the Dashboard is rewritten to plain action words. Styled via object names in the existing `theme.qss`. All pages, controls, and the manual-add feature stay exactly where they are.

**Tech Stack:** Python 3.11, PySide6, pytest + pytest-qt, existing theme.qss.

**Spec:** `docs/superpowers/specs/2026-11-24-ui-clarity-design.md`

## Global Constraints

- Clarity pass ONLY: no change to detection, export pipeline, database, or navigation structure.
- Every page and every control stays, INCLUDING the manual-add control (`+ Add 20s here`) and all signals.
- Copy values are exact from the spec: Import title `Step 1 — Add a recording`, CTA `Analyse match`; Analysis title `Step 2 — Analysing your match`; Review title `Step 3 — Review & export`; combo `One combined video` / `Separate video clips`; Dashboard subtitle `Your highlights, start to finish`; Quick actions `Continue`.
- StepIndicator steps exact: `1 Import`, `2 Analyse`, `3 Review & Export`; current step highlighted.
- Styled via object names in `assets/styles/theme.qss` (do not hardcode colors in widgets where theme exists).
- Full suite currently 95 passing; must stay green.

## Review Focus

- **Stale "Open the Highlights page" instruction** (Analysis `finish()`) — user must be told to review/export instead. Test pinned in Task 2.
- **Step indicator current-step highlight correctness** — a user on Import must see step 1 highlighted, not step 3. Test pinned in Task 1.
- **Primary CTA remains enabled/disabled correctly** — relabeling the Import CTA must not break its disabled-until-valid behavior. Test pinned in Task 3.
- **Manual-add control survives** — the `+ Add 20s here` control on Review must remain present. Test pinned in Task 4.
- **Combo labels still map to the same export modes** — relabeling must not change `export_mode` values. Test pinned in Task 4.

---

### Task 1: StepIndicator widget

**Files:**
- Create: `app/ui/widgets/step_indicator.py`
- Modify: `assets/styles/theme.qss`
- Test: `tests/test_step_indicator.py`

**Interfaces:**
- Consumes: nothing new (Qt only).
- Produces: `StepIndicator(QWidget)` with `__init__(current: int, parent=None)`; steps hardcoded to `["1 Import", "2 Analyse", "3 Review & Export"]`; attribute `labels: list[QLabel]`; `set_current(step: int) -> None` highlights current label via object name `stepActive` vs `stepIdle`. Steps are 1-based (current ∈ {1,2,3}).

- [ ] **Step 1: Write the failing test**

```python
def test_highlights_only_current_step(qtbot):
    from app.ui.widgets.step_indicator import StepIndicator
    ind = StepIndicator(current=2)
    qtbot.addWidget(ind)
    assert [l.text() for l in ind.labels] == ["1 Import", "2 Analyse", "3 Review & Export"]
    assert ind.labels[1].objectName() == "stepActive"
    assert ind.labels[0].objectName() == "stepIdle"
    assert ind.labels[2].objectName() == "stepIdle"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_step_indicator.py`
Expected: FAIL with ModuleNotFoundError for `app.ui.widgets.step_indicator`

- [ ] **Step 3: Implement StepIndicator**

Create `app/ui/widgets/step_indicator.py`: QWidget with QHBoxLayout, three QLabel children (text from spec), `set_current()` sets objectName to `stepActive` for `current-1` and `stepIdle` for others (call `.setObjectName()` + `.style().unpolish()/polish()` to refresh). Add `.stepActive` and `.stepIdle` color styles to `assets/styles/theme.qss` following existing selector style (accent color for active, muted for idle).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_step_indicator.py`
Expected: PASS

- [ ] **Step 5: Commit**

`git add app/ui/widgets/step_indicator.py assets/styles/theme.qss tests/test_step_indicator.py` → commit `feat(ui): add reusable step indicator`

---

### Task 2: Fix stale Analysis copy + add step indicator

**Files:**
- Modify: `app/ui/analysis_page.py`
- Test: `tests/test_analysis_clarity.py`

**Interfaces:**
- Consumes: `StepIndicator(current=2)` from Task 1.
- Produces: `AnalysisPage.step_indicator` attribute; `finish()` message no longer mentions "Highlights".

- [ ] **Step 1: Write failing test**

```python
def test_finish_does_not_point_to_highlights(ctx, qtbot):
    from app.ui.analysis_page import AnalysisPage
    page = AnalysisPage()
    qtbot.addWidget(page)
    page.finish()
    assert "Highlights" not in page.msg_lbl.text()
    assert "review" in page.msg_lbl.text().lower()
```

- [ ] **Step 2: Run to verify fail**
Run: `.venv\Scripts\python.exe -m pytest -q tests/test_analysis_clarity.py`
Expected: FAIL — msg still says "Open the Highlights page to review results."

- [ ] **Step 3: Implement**
In `app/ui/analysis_page.py`: change title text to `Step 2 — Analysing your match`. Insert `self.step_indicator = StepIndicator(current=2)` into the layout right after the sub label. Change `finish()` msg to `Analysis complete — review and export your clips on the next screen.` Keep Pause/Cancel and all signals unchanged.

- [ ] **Step 4: Run to verify pass**
Run: `.venv\Scripts\python.exe -m pytest -q tests/test_analysis_clarity.py`
Expected: PASS

- [ ] **Step 5: Commit** → `feat(ui): clarify analysis page and fix stale instruction`

---

### Task 3: Import page copy + step indicator

**Files:**
- Modify: `app/ui/import_page.py`
- Test: `tests/test_import_clarity.py`

**Interfaces:**
- Consumes: `StepIndicator(current=1)` from Task 1.
- Produces: `ImportPage.step_indicator` attribute. `import_btn` text = `Analyse match`, still disabled until valid file.

- [ ] **Step 1: Write failing test**

```python
def test_import_cta_relabelled_and_still_disabled(ctx, qtbot):
    from app.ui.import_page import ImportPage
    page = ImportPage(ctx)
    qtbot.addWidget(page)
    assert page.import_btn.text() == "Analyse match"
    assert not page.import_btn.isEnabled()
    assert page.title.text() == "Step 1 — Add a recording"
```

- [ ] **Step 2: Run to verify fail**
Run: `.venv\Scripts\python.exe -m pytest -q tests/test_import_clarity.py`
Expected: FAIL — text mismatch.

- [ ] **Step 3: Implement**
In `app/ui/import_page.py`: set title to `Step 1 — Add a recording`; insert `self.step_indicator = StepIndicator(current=1)` after sub label (store title as `self.title` if not already). Relabel CTA to `Analyse match`. Keep disabled-until-valid logic and `match_ready` signal unchanged.

- [ ] **Step 4: Run to verify pass**
Expected: PASS.

- [ ] **Step 5: Commit** → `feat(ui): clarify import page copy`

---

### Task 4: Review & Export copy + step indicator (preserve manual-add)

**Files:**
- Modify: `app/ui/compile_page.py`
- Test: `tests/test_review_clarity.py`

**Interfaces:**
- Consumes: `StepIndicator(current=3)` from Task 1.
- Produces: `CompilePage.step_indicator` attribute; mode combo items changed labels only (`export_mode` stored values unchanged: `"compilation"`/`"separate"`).

- [ ] **Step 1: Write failing test**

```python
def test_review_copy_and_manual_add_survive(ctx, qtbot):
    from app.ui.compile_page import CompilePage
    page = CompilePage(ctx)
    qtbot.addWidget(page)
    assert page.title.text() == "Step 3 — Review & export"
    assert page.mode.itemText(0) == "One combined video"
    assert page.mode.itemText(1) == "Separate video clips"
    assert page.add_range_btn.text() == "+ Add 20s here"
```

- [ ] **Step 2: Run to verify fail**
Run: `.venv\Scripts\python.exe -m pytest -q tests/test_review_clarity.py`
Expected: FAIL — title/combo text mismatch.

- [ ] **Step 3: Implement**
In `app/ui/compile_page.py`: title → `Step 3 — Review & export`; sub → `Check your clips, add anything missed, then export`. Insert `self.step_indicator = StepIndicator(current=3)` after sub. Change combo labels to `One combined video` / `Separate video clips` while keeping the stored `export_mode` values intact (use itemData or map by index). Leave all controls including `add_range_btn` unchanged. Store title as `self.title`.

- [ ] **Step 4: Run to verify pass**
Expected: PASS.

- [ ] **Step 5: Commit** → `feat(ui): clarify review and export page`

---

### Task 5: Dashboard copy + full verification

**Files:**
- Modify: `app/ui/dashboard.py`
- Test: `tests/test_dashboard_clarity.py`

**Interfaces:**
- Consumes: nothing.
- Produces: dashboard subtitle and review button label updated; signals unchanged.

- [ ] **Step 1: Write failing test**

```python
def test_dashboard_copy(ctx, qtbot):
    from app.ui.dashboard import DashboardPage
    page = DashboardPage(ctx)
    qtbot.addWidget(page)
    assert page.sub.text() == "Your highlights, start to finish"
    assert page.review_btn.text() == "Continue"
```

- [ ] **Step 2: Run to verify fail**
Expected: FAIL — label mismatch.

- [ ] **Step 3: Implement**
In `app/ui/dashboard.py`: subtitle → `Your highlights, start to finish`; review button → `Continue`. Store subtitle as `self.sub`. Keep all signals and the 'All highlights'/Settings/About controls unchanged.

- [ ] **Step 4: Run targeted + full suite**
Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (95 + new tests).

- [ ] **Step 5: Commit** → `feat(ui): clarify dashboard copy`

---

## Final Handoff

- Rebuild the frozen exe (`powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`) and smoke-launch to confirm theme changes render.
- No change to detection/export/DB.
