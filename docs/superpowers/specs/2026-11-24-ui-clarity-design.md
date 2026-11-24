# Design: UI clarity pass (Option A)

## Intent and why

The app works, but a first-time user finds it confusing: page titles and buttons use jargon ('Export', 'highlight compilation', 'Import & Analyse'), at least one instruction points to a page that no longer exists, and there is no signposting of the journey. The user asked to make the design simple and unconfusing so anyone can use it — without changing detection or export logic.

This is a **clarity pass, not a structural change**. Every page and control stays where it is, including the manual-add control.

## Goals

- **G1** Replace stale/dead text with plain action words: page titles and subtitles, button labels, status messages.
- **G2** Add a small 3-step progress indicator (`1 Import → 2 Analyse → 3 Review & Export`) at the top of the Import, Analysis, and Review pages so the journey is obvious.
- **G3** Make the primary action on each page unmistakable (one clear main button).

## Non-goals / anti-goals

- No change to detection, scoring, clip selection, rendering, or the database.
- No moving/removing pages or controls; no new sidebar entries; manual-add control stays.
- No new dependencies; no visual-companion/mockup round-trip needed (text changes are self-explanatory).

## Constraints

- Windows 11, PySide6, existing dark/lime theme (`assets/styles/theme.qss`) and existing widget helpers (`Card`, `empty_state`, `section_header`, `stat_card`).
- Existing page structure and signals must keep working; 95 tests must stay green.
- Git not on PATH (portable git at `C:\Users\rickb\AppData\Local\Temp\opencode\mingit\cmd\git.exe`).

## Concrete changes

1. **Import page** — title "Step 1 — Add a recording", subtitle "Drop a complete PUBG match recorded with OBS. We'll find the best moments for you."; keep DropZone text; primary button "Analyse match" (was "Import & Analyse").
2. **Analysis page** — title "Step 2 — Analysing your match"; keep progress/counts; fix stale `finish()` message from "Open the Highlights page…" to "Done — opening your highlights for review…"; Pause/Cancel stay.
3. **Review & Export page** — title "Step 3 — Review & export", subtitle "Watch the suggested clips, add any moment we missed, then export."; relabel mode combo to plainer "One combined video" / "Separate video clips"; keep player, timeline, segment list, '+ Add 20s here' and all buttons.
4. **Dashboard** — subtitle "Your highlights, start to finish"; Quick actions label "Continue"; keep all buttons.
5. **Step indicator** — a small reusable `StepIndicator` widget (3 labelled dots with the active one highlighted) placed at the top of Import (step 1), Analysis (step 2), Review (step 3). Styling from the existing theme; no new dependencies.

## Approaches (considered)

- **A. Clarity pass (chosen)** — text/labels + a small step indicator, no layout moves. Low risk, directly addresses the confusion, keeps manual-add.
- **B. Structural redesign** — reorganise pages, merge/split controls. Rejected: higher risk, user wants simplicity without breaking what works.
- **C. Document-only** — help text/tooltips. Rejected: doesn't fix the misleading labels users actually see.

## What's left to the builder

Exact strings, the `StepIndicator` helper signature/location, and test names are decided in the implementation plan. No ground truth from the user is needed for this task.
