# PUBG AutoClips — Single-Window Editor Redesign & Bug Audit Design

**Date:** 2026-11-25
**Status:** Awaiting approval (option B — single editor window)

## Intent and why

The user supplied a reference image (OpenReel-style video editor) and asked for the app's design and functions to match it. After being offered two interpretations, the user chose **option B: collapse the ENTIRE app into ONE editor window matching the image**, with no separate Dashboard / Import / Analysis / Highlights / Compilation / Export pages.

The application's working core — import, OCR detection, scoring, compilation, export, SQLite — stays. What is rebuilt is the **UI shell**: instead of a multi-page `QStackedWidget`, one editor workspace with left Assets panel, center video preview, right Inspector, and a bottom timeline, all in the exact dark/lime palette. The goal is a premium, single-screen content-production workspace that still performs the real highlight workflow end to end.

This decision **supersedes** earlier choices made in this session: the 7-item sidebar, "polish every page," and the separate Export vs. Compilation split. Those no longer apply because there are no separate pages.

## Honest scope boundary (important)

The reference image shows features that are **outside what this application does**. Per the standing rule "no buttons that do nothing," these will **not** be faked:

- Remove Background, Enhance Speech, Auto-Color (AI quick actions)
- "AI Vision: Tracking Active" object-tracking box
- X/Y/Z transform controls, Flip H/V, Fit
- Subtitle track and A2 audio track (no real data source)

Everything that maps to a **real** function will be wired and working: import/validate media, analyse, real video preview with play/pause/seek and timecode, detected + manual clips on a real timeline, "add clip at playhead," drag-to-add manual range, editable clip boundaries, and a lime **EXPORT** button that generates the verified vertical compilation. Status indicators ("Ready", "Analysing", job progress) reflect real state.

## Goals

- **G1 — Design system.** One Python module of design tokens (exact palette, type scale, spacing, radii, icon size) plus `theme.qss` rewritten from those values. No duplicated colour literals in UI code (including RichText inline styles and raw `QColor` literals).
- **G2 — Single editor shell.** One window: top application bar (brand, real status, search that filters Assets, lime EXPORT), left **Assets** panel (Media + Clips tabs with real thumbnails), center **preview** with real playback controls and timecode, right **Inspector** with real selected-clip properties and edit actions, bottom **timeline** with ruler, real clip track, draggable playhead, and drag-to-add manual ranges. Settings / About / kill-feed calibration open as dialogs from the top bar — not pages.
- **G3 — Every region polished** to the spec: consistent cards, buttons, states, tooltips, toasts, confirmations, empty states. (There are no separate pages; "every page" becomes "every panel and dialog.")
- **G4 — Real workflow in one window.** Import → Analyse (background worker, real progress) → highlights appear as Assets + timeline segments → add/adjust clips → EXPORT → verified result (Play / Open Folder / Return to workspace).
- **G5 — Responsive & DPI.** Reflow at 100/125/150% and smaller windows; no clipped controls; minimum 1024×640; panels use stretch/QScrollArea.
- **G6 — Bug audit and fix.** Fix all reproduced defects from the found list (below) with regression tests.
- **G7 — Verification.** Full suite green, static checks, startup, DB, media, export integrity, and an end-to-end run on real footage.
- **G8 — Documentation.** README/development notes and an eight-section final report.

## Non-goals

- No changes to detection/OCR/scoring, clip boundary math, FFmpeg commands, export pipeline, or DB schema (bug fixes to cancellation/memory/etc. are separately justified below).
- No light theme, no i18n, no new dependencies, no fake AI/video-editor features.
- No resume-after-cancel (pause/resume of a *running* analysis stays and is fixed).
- No fabricated statistics, highlights, progress, or export success.

## Constraints

- Exact palette: bg `#171A1E`, sidebar `#14171A`, card `#20252B`, elevated `#272D34`, border `#343B43`, text `#F3F4F6`, secondary `#9CA3AF`, muted `#737D88`, accent `#A3E635`, accent hover `#BEF264`, success `#22C55E`, warning `#F59E0B`, error `#EF4444`.
- Font: Inter with Segoe UI fallback (detect at runtime; do not bundle). Titles 24–28px, sections 16–18px, body 13–14px, labels 11–12px.
- Preserve all existing functionality and real features; only the shell shape changes.
- Existing core suite must stay green; PyInstaller build and frozen-exe smoke test must still work. UI tests tied to the removed multi-page shell will be rewritten for the single-window shell; detection/export/DB tests remain.

## Approaches considered

- **A — Editor-style Review page, keep 7-item sidebar (rejected by user):** lower risk, but user wants a single screen.
- **B — Collapse entire app into one editor window (chosen):** matches the reference image; reuses all working services; larger UI-shell change and requires rewriting shell-level tests.
- **C — Full rebuild including fake editor features (rejected):** would add non-functional buttons and violate the spec.

## Design decisions made here (my calls)

- **Services reused, not reimplemented:** ProjectManager, MediaValidator, AnalysisPipeline, DatabaseManager, CompilationBuilder, ExportManager, VideoPlayerDialog all stay; the new shell drives them.
- **Settings / About / Calibration** become dialogs opened from the top bar (kill-feed calibration `QDialog` import bug fixed).
- **Export** is one lime button that runs the existing compilation flow; result shown in-app with Play / Open Folder / "Back to workspace."
- **Search** filters the Assets lists (real function), not decorative.
- **Audio waveform / subtitle tracks omitted** rather than fabricated; the timeline shows one real clips track with a time ruler and playhead.
- **Thumbnails** generated by the existing background worker, not synchronously on the GUI thread.
- **Category colours** softened and routed through tokens.

## Known defects to fix (TDD, from found list)

UI / reproducible:
1. `main_window.py:204` `QDialog` not imported → calibration `NameError`.
2. `analysis_page.py:15` `pause_requested = Signal()` vs emitting bool → `TypeError`. (With the single-window shell, this becomes the shell's pause control — same bug class, wired correctly.)
3. `common.py:93–95` `ToastLabel.clear()` infinite recursion.
4. Dead `EditorPage` / `open_editor` / `export_edited` wiring — removed cleanly with the shell; clip editing lives in the Inspector.
5. Synchronous thumbnail generation on GUI thread (`clips_page.py:154`) — reuse the existing `ThumbnailWorker`.
6. Hardcoded colours and fixed sizes across ~10 files, including RichText inline styles (`dashboard.py:126`, `compile_page.py:378,384,406`), `common.py:60,63,90`, and raw `QColor` literals (`compile_page.py:77,80,86,89,94,96`) — all routed through tokens.

Core (high):
7. Unify the two `CancelledError` classes (`task_queue.py:15` vs `exceptions.py:65`) and make cancel actually stop audio analysis + FFmpeg/frame extraction, so a cancelled job never persists results or reports success.
8. Settings save `apply_preset()` overwrite of tuned values (`settings_page.py:277-283,313`); validate min>max so a bad save never resets all settings on next launch.
9. Failed/cancelled exports stuck `pending` in SQLite; job never unregistered on error/cancel.
10. Frame memory held full-res (~10 GB) and temp frames leaked on cancel — decode smaller samples and add `try/finally` cleanup.

Core (medium/low, fix where safe and testable): FFmpeg override consistency; activity-window interval on fallback; merged clip/segment max-duration cap; `manual_segments` FK/cascade; portable output-folder default; ffprobe Windows creation flags; unguarded `_compilation_done` probe; minor dead code/imports.

## What is left to the implementer

Single editor window built from tokens; every real workflow action wired; defects fixed with a failing test first; existing working logic preserved; full verification and eight-section report. No task may fabricate a feature or silently drop a real one.
