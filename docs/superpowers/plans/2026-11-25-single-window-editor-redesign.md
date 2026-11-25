# Single-Window Editor Redesign & Bug Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-page PySide6 app with ONE OpenReel-style editor window (top bar, left Assets, center preview, right Inspector, bottom timeline) that drives the real import→analyse→highlights→adjust→export workflow, while fixing the confirmed UI/core bugs — preserving all working detection/export logic.

**Architecture:** A new `app/ui/editor/` package holds the editor regions (assets, preview, inspector, timeline) composed by a rewritten `MainWindow` that no longer uses a QStackedWidget/sidebar. Existing services (ProjectManager, AnalysisPipeline, CompilationBuilder, DatabaseManager, VideoPlayerDialog, ThumbnailWorker) are reused, never reimplemented. A design-tokens module is the single source of palette/type values, consumed by a fully rewritten `theme.qss`; no colour literals remain in widget code. Settings/About/Calibration/onboarding become top-bar dialogs.

**Tech Stack:** Python 3.11, PySide6 (QtWidgets/QtCore/QtMultimedia), pytest + pytest-qt, SQLite, FFmpeg (bundled).

**Spec:** `docs/superpowers/specs/2026-11-25-full-ui-redesign-bug-audit-design.md` (approved; option B, only real wired features).

**Execution:** Native (user-supplied). BASE = `7cca229` (or current HEAD at execution).

---

## Global Constraints

- Exact palette: bg `#171A1E`, sidebar `#14171A`, card `#20252B`, elevated `#272D34`, border `#343B43`, text `#F3F4F6`/`#9CA3AF`/`#737D88`, accent `#A3E635`/`#BEF264`, status `#22C55E`/`#F59E0B`/`#EF4444`.
- Type: Inter with Segoe UI fallback detected at runtime, never bundled; titles 24–28px, sections 16–18px, body 13–14px, labels 11–12px.
- ONE editor window. No sidebar, no QStackedWidget page navigation, no Dashboard/Import/Analysis/Highlights/Compilation/Export/Editor page classes left in the shell.
- Every visible button does something real; do NOT fabricate Remove Background, Enhance Speech, Auto-Color, AI Vision tracking, X/Y/Z transforms, subtitle or A2 tracks.
- No changes to detection/OCR/scoring/clip math/FFmpeg/export/DB schema except the justified bug fixes in Tasks 9–10.
- Full test suite stays green; UI tests tied to removed pages are rewritten, not left broken. PyInstaller build + frozen exe must still work.
- Core workflow verifiable end-to-end with real footage; final 8-section report required.

## Review Focus

- Importing a real MP4 with the editor window open → it appears in Assets, can be analysed, and highlights populate the Clips tab (T4, T11).
- Playing a clip and moving the playhead → timecode follows position; seeking works on this Windows Qt backend (T6, T7).
- Dragging on empty timeline → a manual clip is added at the correct time and survives restart (T7).
- Pressing EXPORT with mixed detected + manual segments → one verified 1080×1920 MP4 with AAC audio and a result card (T9, T11).
- Cancelling a running analysis → audio and FFmpeg stop, no partial result is persisted, UI returns to idle (T8).
- Opening Settings, editing Detection values, pressing Save → values persist and are NOT reverted by apply_preset (T10).
- Every colour literal removed from widget code and theme.qss matches the exact palette (T1).

---

### Task 1: Design tokens + theme rewrite

**Files:**
- Create: `app/ui/tokens.py`
- Modify: `assets/styles/theme.qss`
- Test: `tests/test_design_tokens.py`

**Interfaces:**
- Produces: tokens module with `PALETTE: dict[str,str]`, `TYPE: dict[str,int]`, `font_family() -> str`, `qss() -> str` consumed by all later tasks and by `main.py`.

- [ ] **Step 1: Write failing test** — `test_palette_matches_spec_and_no_literals_elsewhere`: assert exact hex for every key in `PALETTE`; assert `font_family()` returns a string; grep `app/ui/**/*.py` for `#171A1E`/`#A3E635`/`#7CFC00` literals and assert none for the old accent; assert `theme.qss` contains `:root` or literal palette values equal to `PALETTE`.
- [ ] **Step 2: Run test** → FAIL with `ModuleNotFoundError: app.ui.tokens`.
- [ ] **Step 3: Implement `app/ui/tokens.py`** — `PALETTE` with the exact 13 spec colours, `TYPE` scale (title 26, section 17, body 14, label 11), `font_family()` returning `"Inter"` if `QFontDatabase.families()` contains it else `"Segoe UI"`, `qss()` returning the stylesheet string built from tokens.
- [ ] **Step 4: Rewrite `assets/styles/theme.qss`** — full dark theme using only the token values: QMainWindow/QWidget bg, QPushButton primary (lime) / ghost / danger, QLabel pageTitle/pageSubtitle/sectionTitle/muted, QFrame#card/#cardHover, QScrollArea, QComboBox, QLineEdit, QTabWidget, QSlider, QProgressBar, QListWidget, and the existing objectNames used by widgets. Preserve `stepActive`/`stepIdle`.
- [ ] **Step 5: Run test** → PASS.
- [ ] **Step 6: Commit** `feat(ui): add design tokens and rewrite theme`.

### Task 2: Core bug fixes — cancellation integrity

**Files:**
- Modify: `app/core/task_queue.py`, `app/core/exceptions.py`, `app/detection/audio/audio_analyzer.py`, `app/detection/pipeline.py`, `app/rendering/ffmpeg_runner.py`, `app/media/frame_extractor.py`
- Test: `tests/test_cancellation_integrity.py`

**Interfaces:**
- Produces: a single `CancelledError` re-exported from `app.core.exceptions`; `CancellationToken` cancels audio + FFmpeg processes; pipeline does not persist results for cancelled jobs.

- [ ] **Step 1: Write failing tests** — `test_single_cancelled_error_class` (the two imports are the same class), `test_cancel_terminates_ffmpeg` (a runner process launched with a token cancelled mid-run is killed), `test_cancelled_job_not_persisted` (pipeline with pre-cancelled token leaves events/analysis_jobs unchanged in the in-memory db).
- [ ] **Step 2: Run tests** → FAIL (two classes, no kill, results persisted).
- [ ] **Step 3: Implement** — make `task_queue.CancelledError = exceptions.CancelledError` (single source); in `audio_analyzer`/`ffmpeg_runner`/`frame_extractor` check token and terminate/kill the Popen on cancel, propagating the unified `CancelledError`; in `pipeline.run` wrap the body so `CancelledError` skips `_persist_events`/`_persist_highlights` and marks the job cancelled.
- [ ] **Step 4: Run tests** → PASS; run full suite → green.
- [ ] **Step 5: Commit** `fix(core): unify cancellation and stop work on cancel`.

### Task 3: Core bug fixes — settings, exports, memory, portability

**Files:**
- Modify: `app/ui/settings_page.py`, `app/config.py`, `app/core/job_manager.py`, `app/database/migrations.py`, `app/media/probe.py`, `app/detection/pipeline.py`, `app/utils/paths.py`
- Test: `tests/test_core_bugfixes.py`

**Interfaces:**
- Produces: `AppSettings.apply_preset` no longer overwrites manually-edited detection values; settings validation rejects min>max; failed/cancelled exports marked and jobs unregistered; frames released after sampling; single `ffprobe` flag helper with Windows creation flags.

- [ ] **Step 1: Write failing tests** — `test_apply_preset_preserves_manual_detection_values`, `test_settings_reject_min_gt_max`, `test_failed_export_not_pending_and_job_unregistered`, `test_frames_released_after_pipeline`, `test_ffprobe_uses_windows_creation_flags`.
- [ ] **Step 2: Run tests** → FAIL for the five defects.
- [ ] **Step 3: Implement fixes** — `apply_preset` only sets preset-name/hardware fields, not per-mode intervals/thresholds; add validated `min<=max` guard in `SettingsPage.save`/pydantic validator; update export row status and unregister job in export error/cancel paths; `del frames` + `gc` and wrap frame extraction in try/finally to remove temp frames; central `run_ffprobe` with `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP` + `stdin=DEVNULL`; replace hard-coded `G:\PUBG AUTOCLIPS\exports` default with `default_output_folder()` from `utils/paths`.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `fix(core): settings persistence, export state, memory and portability`.

### Task 4: Editor shell skeleton

**Files:**
- Create: `app/ui/editor/__init__.py`, `app/ui/editor/editor_window.py`
- Modify: `app/ui/main_window.py`, `app/main.py`
- Test: `tests/test_editor_shell.py`

**Interfaces:**
- Produces: `EditorWindow(QMainWindow)` with attributes `topbar`, `assets_panel`, `preview_panel`, `inspector_panel`, `timeline_panel`, `status_bar`; signals `import_requested`, `export_requested`, `settings_requested`, `about_requested`, `calibration_requested`; `MainWindow` becomes an alias/subclass of `EditorWindow` so `app.main` launches the editor.

- [ ] **Step 1: Write failing test** — construct `EditorWindow(ctx)` with `qtbot`; assert no `QStackedWidget` and no sidebar `nav_buttons`; assert the five region attributes exist and are visible; assert all six signals exist.
- [ ] **Step 2: Run test** → FAIL (module missing).
- [ ] **Step 3: Implement shell** — `EditorWindow` with a `QMainWindow` central widget using a layout: top `TopBar`, middle `QSplitter` (left Assets 280px, center Preview stretch, right Inspector 300px), bottom Timeline fixed 220px. Wire top-bar buttons to the six signals. `Settings/About/Calibration/onboarding` open via `QDialog` in `main_window` handlers (import QDialog — fixes UI defect #1). Remove `NAV`/`NAV_TARGETS`/stack-page wiring from `MainWindow`; keep `MainWindow = EditorWindow` compatibility import.
- [ ] **Step 4: Run test** → PASS; full suite green (rewrite any test that constructs the old nav).
- [ ] **Step 5: Commit** `feat(ui): single-window editor shell`.

### Task 5: Assets panel with thumbnails + search

**Files:**
- Create: `app/ui/editor/assets_panel.py`
- Test: `tests/test_assets_panel.py`

**Interfaces:**
- Consumes: `ThumbnailWorker`/`ThumbJob` from `app/ui/widgets/thumbnail_worker.py` (or existing thumbnail module — read it), `ProjectManager`, `db.list_highlights`.
- Produces: `AssetsPanel(QWidget)` with `clip_selected = Signal(int)`, tabs Media/Clips, `set_matches(list)`, `set_highlights(list)`, `filter(text)`.

- [ ] **Step 1: Write failing test** — `test_clip_thumbnails_use_worker_and_filter`: seed db with a match + highlight; build panel; assert a `ThumbnailWorker` is started (monkeypatch) not a synchronous `thumbnail_for_highlight` call; `filter('rickbarat')` hides non-matching cards.
- [ ] **Step 2: Run test** → FAIL.
- [ ] **Step 3: Implement** — Assets panel with `QTabWidget` Media/Clips, `QLineEdit` search, `QListWidget`/grid of `ClipCard`-like items using the reusable `ThumbnailWorker`; clicking a clip emits `clip_selected`.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `feat(ui): assets panel with worker thumbnails and search`.

### Task 6: Center preview with playback + timecode

**Files:**
- Create: `app/ui/editor/preview_panel.py`
- Test: `tests/test_preview_panel.py`

**Interfaces:**
- Consumes: `VideoPlayerDialog`/`QMediaPlayer` pattern; `Segment` boundaries.
- Produces: `PreviewPanel(QWidget)` with `set_source(path)`, `set_bounds(start,end)`, `play()/pause()/seek(float)`, `position_changed = Signal(float)`, `position() -> float`, attribute `timecode_label`.

- [ ] **Step 1: Write failing tests** — `test_timecode_updates_and_seek_works`: with synthetic video, `p.set_source(path)`, `p.seek(2.0)`, wait; assert `p.position()` ≈ 2 and `timecode_label.text()` contains `00:00:02`.
- [ ] **Step 2: Run tests** → FAIL.
- [ ] **Step 3: Implement** — embed a `QMediaPlayer`/`QVideoWidget` with play/pause/stop, a seek slider, and a `mm:ss` timecode label driven by `positionChanged`; reuse the deferred-commit seek (play then setPosition after a tick) needed on this Windows backend; respect `set_bounds` to stop at segment end.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `feat(ui): editor preview panel with playback and timecode`.

### Task 7: Inspector panel + timeline with playhead and drag-to-add

**Files:**
- Create: `app/ui/editor/inspector_panel.py`, `app/ui/editor/timeline_panel.py`
- Test: `tests/test_inspector_timeline.py`

**Interfaces:**
- Consumes: `Segment`, `select_segments`, `db.add/update/delete_manual_segment`.
- Produces: `InspectorPanel(QWidget)` with `set_segment(seg|None)`, signals `bounds_changed(int,float,float)`, `add_at_playhead`, `split_requested`, `remove_requested`; `TimelinePanel(QWidget)` with `set_segments(list,duration)`, `playhead_changed = Signal(float)`, `range_added = Signal(float,float)`, `set_playhead(float)`, `add_at_playhead() -> tuple[float,float]`.

- [ ] **Step 1: Write failing tests** — `test_timeline_drag_maps_pixels_to_seconds` (1000px, 600s, drag x=500→598 → ~295–305 / 355–365), `test_playhead_follows_click`, `test_inspector_edits_emit_bounds`, `test_add_at_playhead_returns_20s_range`.
- [ ] **Step 2: Run tests** → FAIL.
- [ ] **Step 3: Implement** — timeline paints a time ruler, lime playhead and real clip track; mousePress on track sets playhead (emit), drag on empty → `_x_to_time` conversion (reuse the tested mapping) → `range_added`; Inspector shows category/score/confidence labels + editable start/end spinboxes + Add/Split/Remove buttons emitting their signals. Wire Preview's `position_changed` to `timeline.set_playhead`.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `feat(ui): inspector and timeline with manual clip add`.

### Task 8: Top-bar EXPORT workflow + verified result + dialogs

**Files:**
- Modify: `app/ui/editor/editor_window.py`, `app/ui/main_window.py`
- Test: `tests/test_editor_workflow.py`

**Interfaces:**
- Consumes: signals from T4–T7, `CompilationBuilder`, `_compilation_request` pattern.
- Produces: `EditorWindow.export()`, `EditorWindow.show_result(path,duration)`, and working Settings/About/Calibration dialog handlers.

- [ ] **Step 1: Write failing tests** — `test_export_uses_segments_and_shows_result` (monkeypatch compilation worker; assert a compilation request dict emitted with current segments and a result card shown with Play/Open Folder/Back), `test_dialogs_are_qdialogs` (settings/about/calibration handlers construct `QDialog` without NameError).
- [ ] **Step 2: Run tests** → FAIL.
- [ ] **Step 3: Implement** — top-bar EXPORT gathers timeline segments and starts compilation via the existing worker path (keep persistent worker refs); on success show a result card with Play Video / Open Folder / Back to workspace; wire Assets `clip_selected`→preview+inspector, timeline `range_added`→`db.add_manual_segment`+reload, Inspector signals→persist edits; implement dialog handlers using imported `QDialog`.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `feat(ui): wire editor export workflow and dialogs`.

### Task 9: Shared-widget bug fixes + colour sweep

**Files:**
- Modify: `app/ui/widgets/common.py`, `app/ui/widgets/step_indicator.py`
- Test: `tests/test_shared_widget_bugfixes.py`

**Interfaces:**
- Consumes: tokens from T1.
- Produces: `ToastLabel.clear()` non-recursive; no colour literals in `app/ui/**/*.py`.

- [ ] **Step 1: Write failing tests** — `test_toast_clear_empties_text` (clear() sets empty text and does not call itself), `test_no_ui_colour_literals` (grep app/ui/**/*.py for `#` hex colours and `QColor(` literals → none).
- [ ] **Step 2: Run tests** → FAIL.
- [ ] **Step 3: Implement** — `ToastLabel.clear()` calls `setText("")` (superclass), not `self.clear`; replace all inline `setStyleSheet` colour values and `QColor` literals with token-derived values or theme objectNames; delete dead `EditorPage`/`open_editor`/`export_edited` wiring if still present.
- [ ] **Step 4: Run tests** → PASS; full suite green.
- [ ] **Step 5: Commit** `fix(ui): toast recursion, colour sweep, dead editor removal`.

### Task 10: Remove obsolete pages/tests + full suite green

**Files:**
- Delete: `app/ui/dashboard.py`, `import_page.py`, `analysis_page.py`, `clips_page.py`, `compile_page.py`, `exported_clips_page.py`, `editor_page.py` (only after their functions are absorbed by T4–T8)
- Modify/delete: UI tests referencing those pages
- Test: full suite

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a coherent codebase where `pytest -q` is fully green and no module imports a deleted page.

- [ ] **Step 1: Run full suite** — identify every test importing removed pages.
- [ ] **Step 2: Rewrite or delete those tests** so they test equivalent behaviour through `EditorWindow` regions (T4–T8), keeping coverage of import/analyse/highlights/export.
- [ ] **Step 3: Delete obsolete page modules and dead imports**; fix any lingering imports.
- [ ] **Step 4: Run full suite** → green (target ≥ 103 passing).
- [ ] **Step 5: Commit** `refactor(ui): remove obsolete page modules and tests`.

### Task 11: Real-footage E2E + docs + report + rebuild

**Files:** Modify `README.md`, `COMPLETION_REPORT.md`; rebuild exe.

- [ ] **Step 1: Run the real workflow** on match 7 (`G:\GAMEPLAY\2026-11-18 21-23-06.mp4`): import, analyse via the editor, confirm highlights populate, add a manual 700–720s range, export, probe the MP4 (1080×1920, 30fps, h264, AAC), full-decode check, clean up temp artifacts.
- [ ] **Step 2: Verify at 100%/125%/150% DPI** if possible; report unverified if not.
- [ ] **Step 3: Update README + COMPLETION_REPORT** with the single-editor workflow and the 8-section report (features implemented / not / deps / tests / performance / known bugs / launch command / build command / export location).
- [ ] **Step 4: Rebuild exe** via `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1` and smoke-launch; confirm title and no plugin errors.
- [ ] **Step 5: Commit + push** `docs: single-window editor redesign, bug audit and verification`.

---

## Self-Review

- **Spec coverage:** G1→T1, G2→T4–T8, G3→T4–T9, G4→T4/T8/T11, G5→T4/T11, G6→T2/T3/T9, G7→T11, G8→T11. All covered.
- **Step scan:** each step is one action with a checkable result.
- **Type consistency:** signal/slot names consistent across T4–T8 (`clip_selected`, `position_changed`, `range_added`, `bounds_changed`).
- **Review Focus:** each line has a test in the owning task (T1/T2/T4/T6/T7/T8/T11).
- **Proportion:** plan is longer than the code it describes only in task scaffolding; bodies are signatures + test names, not transcripts.
