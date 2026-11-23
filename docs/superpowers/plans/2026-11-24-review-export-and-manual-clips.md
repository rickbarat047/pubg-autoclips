# Review & Export and Manual Clips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a play button to clip preview cards and turn the post-analysis step into one simple Review & Export page where a user can drag on a full-match timeline to add missed moments, while reducing the sidebar to Dashboard / Import / Exported Clips.

**Architecture:** Reuse the existing PySide6 `CompilePage` as the Review & Export page, adding a `QMediaPlayer` dialog and drag-to-create on its existing `CompilationTimeline`. Persist manual ranges in a new additive SQLite table and merge them into the segment list before export. Keep all existing detection, scoring, and rendering code unchanged.

**Tech Stack:** Python 3.11, PySide6 (`QtMultimedia`, `QtMultimediaWidgets`), OpenCV, SQLite, pytest/pytest-qt, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-11-24-review-export-and-manual-clips-design.md`

## Global Constraints

- Windows 11, Python 3.11 64-bit, PySide6; no new heavyweight dependencies.
- Sidebar contains exactly three items: `Dashboard`, `Import`, `Exported Clips`.
- Settings and About remain reachable from Dashboard or a small top-bar control, never from the sidebar.
- Review & Export is reached by auto-navigation after analysis and by a Dashboard "Review latest match" action — never from the sidebar.
- Manual ranges must survive the `max_segments` clip limit and persist across restarts.
- `auto_export` default becomes `False`; an explicit user choice is never overwritten.
- All FFmpeg subprocess calls must keep `stdin=DEVNULL` and `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`.
- Preserve the existing stream-copy compilation + re-encode fallback and 1080×1920 verification.

## Review Focus

- Dragging a zero-length or reversed range on the timeline → no segment created (test in Task 5).
- Dragging past the end of the recording → range clamped to `video_duration` (test in Task 5).
- A manual segment overlapping a detected one → both kept, merged by existing `merge_segments` gap rules (test in Task 5).
- Exported Clips page with zero exports → clear empty state, no crash (test in Task 6).
- Player opened for a clip whose source file was moved/deleted → actionable message, no crash (test in Task 3).
- Packaging: QtMultimedia plugins missing in the frozen exe → media cannot play (smoke test in Task 8).

---

### Task 1: Persist manual segments (SQLite)

**Files:**
- Modify: `app/database/migrations.py` (add migration target 3)
- Modify: `app/database/db.py` (add 4 CRUD methods)
- Test: `tests/test_manual_segments.py` (create)

**Interfaces:**
- Produces: `DatabaseManager.add_manual_segment(match_id: int, start: float, end: float, note: str = "") -> int`; `list_manual_segments(match_id: int) -> list[dict]`; `update_manual_segment(segment_id: int, start: float, end: float) -> None`; `delete_manual_segment(segment_id: int) -> None`.

- [ ] **Step 1: Write failing test for table + CRUD**

```python
def test_manual_segment_roundtrip(db):
    mid = db.add_match(path="x.mp4", name="x", duration=600).id
    sid = db.add_manual_segment(mid, 120.5, 140.5, "missed knock")
    rows = db.list_manual_segments(mid)
    assert len(rows) == 1 and rows[0]["id"] == sid
    assert rows[0]["start"] == 120.5 and rows[0]["note"] == "missed knock"
    db.update_manual_segment(sid, 121.0, 141.0)
    assert db.list_manual_segments(mid)[0]["start"] == 121.0
    db.delete_manual_segment(sid)
    assert db.list_manual_segments(mid) == []
```

- [ ] **Step 2: Run it to verify it fails** — `pytest tests/test_manual_segments.py -v` → FAIL (no column/table).
- [ ] **Step 3: Implement** migration 3 adding `manual_segments (id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL, start REAL NOT NULL, end REAL NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)` with index on `match_id`; add the four methods using existing `transaction()`/`_connect()` patterns.
- [ ] **Step 4: Run test to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(db): persist manual clip ranges"`.

### Task 2: Change auto-export default safely

**Files:**
- Modify: `app/config.py` (`auto_export` default + version migration)
- Test: `tests/test_settings_migration.py` (create)

**Interfaces:**
- Consumes: `AppSettings.load()` existing mechanism; `version` field.
- Produces: new default `auto_export = False`; existing saved `auto_export=True` preserved.

- [ ] **Step 1: Write failing test**

```python
def test_explicit_auto_export_true_is_preserved(tmp_path):
    (tmp_path / "settings.json").write_text('{"version":5,"auto_export":true}', encoding="utf-8")
    s = AppSettings.load(path=tmp_path / "settings.json")
    assert s.auto_export is True

def test_default_auto_export_is_off():
    assert AppSettings().auto_export is False
```

- [ ] **Step 2: Run to verify it fails** — FAIL (default is True).
- [ ] **Step 3: Implement** — change default to `False`; bump version to 6; in `load()`, when upgrading from v5 only add `auto_export=False` if the key is absent. Do not touch other keys.
- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(config): default to review-before-export"`.

### Task 3: Reusable video player dialog

**Files:**
- Create: `app/ui/video_player_dialog.py`
- Test: `tests/test_video_player_dialog.py` (create)

**Interfaces:**
- Produces: `class VideoPlayerDialog(QDialog)` with `__init__(video_path: str, start: float = 0, end: float | None = None, parent=None)`; methods `play()`, `pause()`, `stop()`; signals `position_changed = Signal(float)`.

- [ ] **Step 1: Write failing test (pytest-qt)**

```python
def test_player_dialog_shows_controls(qtbot):
    dlg = VideoPlayerDialog("missing.mp4")   # must not raise
    qtbot.addWidget(dlg)
    assert dlg.play_button is not None and dlg.seek_slider is not None
```

- [ ] **Step 2: Run to verify it fails** — FAIL (module missing).
- [ ] **Step 3: Implement** — `QMediaPlayer` + `QAudioOutput` + `QVideoWidget`, play/pause button, `QSlider` scrub bound to `positionChanged`/`setPosition`, `durationChanged`, stop at `end` via `positionChanged` check, and a `QLabel` error message when the file is missing. Stop/close releases the player.
- [ ] **Step 4: Run to verify it passes** — PASS (headless Qt: no actual decode needed).
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): reusable clip player dialog"`.

### Task 4: Play button on highlight cards

**Files:**
- Modify: `app/ui/clips_page.py:22-62, 78, 143`
- Test: `tests/test_clip_card_play.py` (create)

**Interfaces:**
- Consumes: `VideoPlayerDialog` from Task 3.
- Produces: `ClipCard.play_requested = Signal(int)`; `ClipsPage.play_requested = Signal(int)`; the card button text is `▶ Play`.

- [ ] **Step 1: Write failing test**

```python
def test_play_button_emits_highlight_id(qtbot, sample_highlight):
    card = ClipCard(sample_highlight, "clip.mp4")
    qtbot.addWidget(card)
    with qtbot.waitSignal(card.play_requested, timeout=1000) as sig:
        card.play_button.click()
    assert sig.args == [sample_highlight.id]
```

- [ ] **Step 2: Run to verify it fails** — FAIL (`play_button` missing).
- [ ] **Step 3: Implement** — replace `prev = QPushButton("Preview")` with `self.play_button = QPushButton("▶ Play")`; emit `play_requested`; remove `open_editor` connection in `MainWindow`; keep `EditorPage` class on disk but unreachable from UI.
- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): play clips from highlight cards"`.

### Task 5: Review & Export page (player, timeline drag, manual segments)

**Files:**
- Modify: `app/ui/compile_page.py`
- Test: `tests/test_review_export.py` (create)

**Interfaces:**
- Consumes: `DatabaseManager` manual-segment methods (Task 1), `Segment` dataclass, `select_segments`, `VideoPlayerDialog` (Task 3).
- Produces: `CompilationTimeline.segment_drag_created = Signal(float, float)`; `CompilePage.set_match(match_id)` loads manual segments and appends them as `Segment(category="MANUAL", source_labels=["Added by you"])`; `CompilePage._on_segment_drag(start, end)` opens the player at `start` and adds the range; `CompilePage.add_current_range()` adds `player.position .. +20s` fallback.

- [ ] **Step 1: Write failing tests**

```python
def test_drag_clamps_and_rejects_tiny_ranges():
    assert CompilationTimeline.range_from_drag(590, 610, 600) == (590.0, 600.0)
    assert CompilationTimeline.range_from_drag(100, 100.2, 600) is None
    assert CompilationTimeline.range_from_drag(110, 100, 600) is None

def test_manual_segments_are_appended_and_labelled(db, sample_match):
    sid = db.add_manual_segment(sample_match.id, 300, 320, "missed")
    page = CompilePage(ctx)
    page.set_match(sample_match.id)
    manual = [s for s in page.segments if s.category == "MANUAL"]
    assert len(manual) == 1 and "Added by you" in manual[0].source_labels
```

- [ ] **Step 2: Run to verify it fails** — FAIL (static method / labels missing).
- [ ] **Step 3: Implement** — add `range_from_drag` static math helper; add `mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent` to draw a rubber-band and emit `segment_drag_created`; add player widget at top and connect marker clicks to `player.setPosition`; add `_on_segment_drag` to create a manual segment, persist via `db.add_manual_segment`, and refresh; add "Add 20s here" button; add `MANUAL` to `CATEGORY_COLORS`; ensure manual segments are added **after** `select_segments` and excluded from the max-segment cap; add Remove action that deletes from DB.
- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): review page with manual timeline selection"`.

### Task 6: Exported Clips page

**Files:**
- Create: `app/ui/exported_clips_page.py`
- Test: `tests/test_exported_clips_page.py` (create)

**Interfaces:**
- Produces: `class ExportedClipsPage(QWidget)` with `review_requested = Signal(int)` and `refresh()`; shows a list of exports with Play / Open Folder buttons and a clear empty state.

- [ ] **Step 1: Write failing test**

```python
def test_empty_state(qtbot, ctx):
    page = ExportedClipsPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    assert page.empty_label.isVisible()
```

- [ ] **Step 2: Run to verify it fails** — FAIL (module missing).
- [ ] **Step 3: Implement** — read `db.list_exports()`; rows show name, duration, category counts, file size; Play opens `VideoPlayerDialog`; Open Folder uses `QDesktopServices.openUrl`; "Review latest match" button emits `review_requested(match_id)`.
- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): exported clips page"`.

### Task 7: Rewire navigation and post-analysis flow

**Files:**
- Modify: `app/ui/main_window.py`, `app/ui/dashboard.py`
- Test: `tests/test_navigation_flow.py` (create)

**Interfaces:**
- Consumes: all pages above.
- Produces: `NAV == [("Dashboard","▦"),("Import","⬇"),("Exported Clips","▤")]`; `MainWindow.open_review(match_id)` navigates to the Review page; `MainWindow.open_player_for_highlight(hid)` opens `VideoPlayerDialog` with source path and highlight bounds.

- [ ] **Step 1: Write failing test**

```python
def test_sidebar_has_only_three_items(qtbot):
    win = MainWindow(ctx)
    qtbot.addWidget(win)
    assert [win.nav.item(i).text() for i in range(win.nav.count())] == [
        "Dashboard", "Import", "Exported Clips"]
```

- [ ] **Step 2: Run to verify it fails** — FAIL (8 items).
- [ ] **Step 3: Implement** — cut NAV to 3 items; keep Analysis/Review/Settings/About as hidden pages reached programmatically; `clips.play_requested.connect(open_player_for_highlight)`; `dashboard.review_requested.connect(open_review)`; `exported.review_requested.connect(open_review)`; `_analysis_done` always calls `open_review(match_id)` (ignore `auto_export` for the main flow but keep the advanced setting functional when explicitly enabled); add small Settings/About access on Dashboard.
- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(ui): simplify sidebar and auto-open review"`.

### Task 8: Package QtMultimedia and smoke test the exe

**Files:**
- Modify: `scripts/build_windows.ps1`
- Test: manual verification only.

- [ ] **Step 1: Add PyInstaller collection** — pass `--collect-submodules PySide6.QtMultimedia --collect-submodules PySide6.QtMultimediaWidgets` (and the matching Qt plugins directory) to the build command.
- [ ] **Step 2: Rebuild** — `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1`; confirm `dist\PUBGAutoClips\PUBGAutoClips.exe` timestamp updates.
- [ ] **Step 3: Smoke test** — launch exe, confirm responding and that the player dialog opens without a "could not load media" error; stop process.
- [ ] **Step 4: Commit** — `git commit -m "build: bundle Qt multimedia plugins"`.

### Task 9: Full verification and documentation

**Files:**
- Modify: `README.md`, `COMPLETION_REPORT.md`

- [ ] **Step 1: Run full suite** — `python -m pytest -q` → all tests pass, count reported.
- [ ] **Step 2: Real-footage check** — re-analyse one match, add one manual range through the Review page, export, and probe the MP4 for 1080×1920/30fps/H.264/AAC plus a clean full decode.
- [ ] **Step 3: Document** — update README and COMPLETION_REPORT with the new workflow, the three-item sidebar, and the manual-range persistence.
- [ ] **Step 4: Commit and push** — `git add -A && git commit -m "docs: document review and manual clip workflow" && git push origin main`.
