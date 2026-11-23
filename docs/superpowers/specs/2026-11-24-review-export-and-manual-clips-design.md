# Design: Clip Playback, Review & Export Timeline, and Simple Navigation

## Intent / why

The user confirmed the detection fixes work well, but two gaps remain:

1. Users cannot play a detected clip before exporting it — they only see a still
   thumbnail. They want a play button on the highlight card.
2. Roughly 1 in 5 recordings still misses a knock. The user wants a way to add
   that missed moment by hand, but the interface must stay simple enough for
   people who are not comfortable with video editing.

Both changes serve one goal: make the **end of the workflow** a single, calm
review step where the user watches, adjusts, adds anything missing, and exports
— without needing to understand the app's internal pages.

## Goals

- **G1 — Play before export.** Each highlight card gets a single `▶ Play`
  button that opens a small player window on the original footage for just that
  clip: play/pause, scrub bar, stop at end. No second editor page.
- **G2 — Review & Export as the final step.** After analysis completes, the app
  navigates automatically to a single Review & Export page (the existing
  Export/Compile page, extended). It contains:
  - a video player at the top (play/pause, current time),
  - a **match timeline** for the whole recording, with colored markers for the
    detected segments,
  - **drag on empty timeline space** to add a missed moment; the player seeks
    while dragging; a simple numeric fallback (`Add 20s here`) is also present,
  - clicking a marker seeks the player to that segment,
  - a segment list with editable start/end boxes, `Remove`, and a clear
    `Added by you` label on manual rows,
  - one primary `Export compilation` button plus the existing separate-MP4
    mode switch, output folder control, and result card (Open Folder / Play Video).
- **G3 — Three-item sidebar.** The left navigation contains **only**:
  `Dashboard`, `Import`, and a new `Exported Clips` page that lists videos that
  were already exported. `Highlights`, `Editor`, and `Export` are removed from
  the sidebar. Review & Export is reached by auto-navigation after analysis,
  plus a `Review latest match` entry point from the Dashboard.
- **G4 — Review before saving.** `auto_export` defaults to **off** (the setting
  and behavior remain available for advanced users). Manually added ranges are
  stored in SQLite, are never dropped by the clip-count limit, and survive a
  re-open of the page / app restart.

## Non-goals

- No full professional video editor (no multi-track, no effects, no keyframes).
- No new detection algorithms and no changes to OCR/scoring logic.
- No removal of the existing export pipeline, layouts, or verification.
- No new sidebar entries beyond the three named above.

## Constraints

- Windows 11, Python 3.11, PySide6. QtMultimedia imports successfully in the
  venv; the packaged `.exe` must be smoke-tested with the media plugins present
  (PyInstaller may need `collect QtMultimedia plugins` / hiddenimports).
- Offline, local-first. No paid APIs.
- Keep changes small and consistent with the existing page/widget patterns.
- SQLite migration must be additive and backward compatible.

## Approaches considered

- **Playback: separate lightweight dialog vs. inline player in the card.**
  Chose the separate dialog — one reusable window, no layout churn in the
  responsive card grid, and it can play original (horizontal) footage without
  distorting the card. The Editor page's still-frame preview stays available
  but is no longer in the sidebar.
- **Manual selection: drag on timeline vs. start/end number boxes only.** The
  user explicitly chose **drag**; number boxes remain as a precise fallback and
  for editing the bounds after dragging, since they are familiar and exact.
- **Navigation: keep all pages vs. three-item sidebar.** The user explicitly
  chose the three-item sidebar (`Dashboard`, `Import`, `Exported Clips`) to
  avoid confusing non-technical users.

## Builder calls (my decisions, not user requests)

- The player will use `QMediaPlayer` + `QAudioOutput` + `QVideoWidget` from
  QtMultimedia, instantiated once per dialog and reused.
- The manual-range DB table is additive: `manual_segments(id, match_id, start,
  end, note, created_at)` with a migration that creates it if absent.
- `auto_export` default flips to `False` via a config migration that preserves
  any explicit user choice already on disk.
- The Review & Export page is the existing `CompilePage`, extended — not a new
  page class. This keeps the export code path single-sourced.

## What's left to the builder

Implement the plan produced by the next step: wire the card play button, build
the player dialog, extend the compile page with the timeline/drag/segments UI,
add the manual-range persistence, reduce the sidebar to three items with an
Exported Clips page and Dashboard review entry, flip the auto-export default,
add tests, rebuild, and smoke-test the packaged `.exe`.
