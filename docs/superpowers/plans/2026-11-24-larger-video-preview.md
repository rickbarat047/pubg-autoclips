# Larger Video Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make gameplay clearly visible in both video players (Review & Export inline player and standalone player) while keeping the match timeline reachable.

**Architecture:** Two small layout-only changes in existing files. Standalone `VideoPlayerDialog` gets a larger default window and video surface, which enlarges playback everywhere it opens on its own. The Review page enlarges its embedded video surface and lifts the host cap; the existing page scroll area keeps the timeline reachable at any window size.

**Tech Stack:** Python 3.11, PySide6 / QtMultimedia, pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-24-larger-video-preview-design.md`

## Global Constraints
- Layout only — detection, scoring, clip selection, rendering, export, DB untouched.
- Review page timeline MUST remain reachable via the existing scroll area (from b399603).
- No new dependencies, no new player window, no expand/collapse toggle.
- Full pytest suite (currently 101 passed) must stay green.

## Review Focus
- Timeline pushed out of reach by taller player at a small window → T2 asserts timeline is inside the scroll area after a taller embedded player.
- Embedded gameplay still too small → T2 asserts embedded `video_widget.minimumHeight() >= 240`.
- Standalone gameplay too small → T1 asserts `video_widget.minimumHeight() == 420` and window `>= 900x640`.
- Missing source file must not crash playback → T1 constructs the dialog with a non-existent path and checks it builds.
- Taller player must not break timeline drag → full suite (drag/marker tests) run in T2.

---

### Task 1: Enlarge the standalone player

**Files:**
- Modify: `app/ui/video_player_dialog.py:30-37`
- Test: `tests/test_larger_video_preview.py`

**Interfaces:**
- Consumes: `VideoPlayerDialog(video_path, start=0.0, end=None, parent=None)` from the existing UI.
- Produces: unchanged public API; only default geometry and `video_widget` minimum height change. Used by Review (embedded, overrides height), Exported Clips Play, and highlight gallery Play.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_larger_video_preview.py
def test_standalone_player_is_large_and_survives_missing_source(qtbot):
    from app.ui.video_player_dialog import VideoPlayerDialog
    dlg = VideoPlayerDialog("G:/does-not-exist.mp4")
    qtbot.addWidget(dlg)
    assert dlg.video_widget.minimumHeight() == 420
    assert dlg.width() >= 900
    assert dlg.height() >= 640
    assert dlg.error_label.isVisible(), "missing source must show a readable error"
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_larger_video_preview.py`
Expected: FAIL — `minimumHeight()` is 300, width 720, height 520.

- [ ] **Step 3: Enlarge the standalone dialog**

In `app/ui/video_player_dialog.py`: change `self.resize(720, 520)` to `self.resize(960, 680)` (line 31) and `self.video_widget.setMinimumHeight(300)` to `self.video_widget.setMinimumHeight(420)` (line 37). Leave all playback/seek logic and the missing-source error path unchanged.

- [ ] **Step 4: Run the test**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_larger_video_preview.py`
Expected: PASS.

- [ ] **Step 5: Commit**

`feat(ui): enlarge standalone video player`

---

### Task 2: Enlarge the Review & Export inline player (keep timeline reachable)

**Files:**
- Modify: `app/ui/compile_page.py:274-278` and `app/ui/compile_page.py:470-477`
- Modify: `tests/test_review_timeline_visible.py:38-39`
- Test: `tests/test_larger_video_preview.py`

**Interfaces:**
- Consumes: `CompilePage(ctx)`, `page.player_host`, `page.timeline`, `page.set_match(match_id)`; `VideoPlayerDialog` with `video_widget`.
- Produces: unchanged public API; embedded video surface ~280px, host cap ~360px.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_larger_video_preview.py`:

```python
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QScrollArea
from app.ui.compile_page import CompilePage
from app.ui.video_player_dialog import VideoPlayerDialog

@pytest.fixture
def ctx(settings, db):
    return SimpleNamespace(settings=settings, db=db, bus=None, jobs=None)

def test_embedded_player_enlarged_and_timeline_reachable(ctx, qtbot):
    m = ctx.db.add_match(path="x.mp4", name="x", duration=600.0)
    page = CompilePage(ctx)
    qtbot.addWidget(page)
    page.resize(900, 720)
    page.set_match(m.id)
    page.show()
    qtbot.wait(200)
    assert page.player_host.maximumHeight() >= 300
    dlg = page.player_host.findChild(VideoPlayerDialog)
    assert dlg is not None
    assert dlg.video_widget.minimumHeight() >= 240
    scroll = page.findChild(QScrollArea)
    assert scroll is not None
    assert page.timeline in scroll.findChildren(type(page.timeline))
```

- [ ] **Step 2: Run the test**

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_larger_video_preview.py::test_embedded_player_enlarged_and_timeline_reachable`
Expected: FAIL — host cap 240 (<300), embedded `video_widget` min height 120 (<240).

- [ ] **Step 3: Enlarge the embedded player**

In `app/ui/compile_page.py`: in `__init__` change `self.player_host.setMaximumHeight(240)` to `360` (line 275); in `_rebuild_player` change `dlg.video_widget.setMinimumHeight(120)` to `280` (line 474) and `self.player_host.setMaximumHeight(240)` to `360` (line 476). Update the two stale "must stay compact" comments to say the page scroll area keeps the timeline reachable. Leave the scroll area and all export/drag logic unchanged.

- [ ] **Step 4: Update the old assertion and run the tests**

In `tests/test_review_timeline_visible.py` change `assert host.maximumHeight() <= 260` to `assert host.maximumHeight() <= 400` (the cap is now 360; the scroll area — not a tiny player — keeps the timeline reachable).

Run: `.venv\Scripts\python.exe -m pytest -q tests/test_larger_video_preview.py tests/test_review_timeline_visible.py`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (101 + 2 new tests).

- [ ] **Step 6: Commit**

`feat(ui): enlarge review player and keep timeline reachable`

---

### Task 3: Rebuild and smoke-test the frozen app

**Files:** none (verification only).

- [ ] **Step 1: Stop any running app, then rebuild**

Run: `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`
Expected: "Build complete! results in G:\PUBG AUTOCLIPS\dist" (trailing exit 1 is the known echo behaviour).

- [ ] **Step 2: Smoke-test**

Start `dist\PUBGAutoClips\PUBGAutoClips.exe`; after ~10s confirm `Responding = True` and title `PUBG AutoClips v1.0.0`; then stop the process.
Expected: launches and stays responsive with no Qt multimedia/plugin errors in the log.
