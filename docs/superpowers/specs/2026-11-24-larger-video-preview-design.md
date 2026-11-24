# Larger video preview — design (approved)

## Intent
The user reported that video playback on the Exported Clips page works well but
the gameplay is too small to see, and on the Review & Export page the gameplay
is too small to judge when adding manual clips. They chose **Option A (bigger
inline player)** and explicitly asked to **enlarge both players**.

## Scope
Layout only. Detection, scoring, clip selection, rendering, export and database
logic stay untouched. Only the video-display sizes change.

## Goals
- G1: Review & Export inline player shows gameplay large enough to judge a
  manual clip boundary (target video surface ~280px tall).
- G2: The standalone player opened from Exported Clips (and the highlight
  gallery / Exported Clips "Play") shows gameplay clearly (larger window and
  video surface than today's 720x520 / 300px).
- G3: The match timeline stays reachable at any window size. The whole Review
  page is already wrapped in a scroll area, so a taller player does not make
  the timeline unreachable; it may require a short scroll.

## Non-goals
- No new full-screen mode or expand/collapse toggle (approach B) and no second
  separate player window (approach C) — user chose A.
- No change to playback controls, seeking, or export behaviour.

## Approach chosen — A (bigger player)
- `VideoPlayerDialog` standalone geometry: enlarge default from 720x520 to
  roughly 960x680, and raise `video_widget.setMinimumHeight` from 300 to ~420.
  This enlarges playback everywhere the dialog is shown on its own (Exported
  Clips Play, highlight gallery Play).
- Review & Export embedded player: override the embedded video surface to a
  larger ~280px (was 120px) and raise the host cap from 240 to ~360, so the
  gameplay is readable while adding manual clips.
- Keep the Review page scroll area (from commit b399603) so the timeline cannot
  be pushed out of reach again.

## Constraints
- PySide6 / QtMultimedia, Windows 11, Python 3.11 — no new dependencies.
- Timeline must remain reachable (scroll area stays).
- Full pytest suite must stay green; existing vision/export tests untouched.

## Decision
User directive verbatim: "enlarge both please..and go with option a". Approval
covers the approach and this design.
