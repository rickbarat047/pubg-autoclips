# Debug findings — missing knock/kill moments (2026-11-23)

## Environment blocker (must fix before ANY verification)
Windows Smart App Control flipped from evaluation (2) to enforced (1) on 2026-11-23.
Code Integrity log shows event 3033/3077 blocking `_pydantic_core.cp311-win_amd64.pyd`
and numpy's `_multiarray_umath.pyd` ("did not meet the Enterprise signing level").
No Python command that imports pydantic/numpy/cv2 can run. PyInstaller exe is also
unsigned and will be blocked. Requires user action: disable Smart App Control
(Windows Security → App & browser control → Smart App Control → Off). This is a
one-way switch. Session is not admin, so it cannot be automated.

## Evidence from real DB (match 7, 1598.5 s, 1920x1080)
- 33 events: 13 OCR feed events + 20 audio-only COMBAT.
- Recognised OCR text is a *blob* of several feed rows + HUD, e.g.
  `'2KILLED 2ASSISTED 33 ALIVE 285 3[NTRS]rickbarat X[426]uznaev'`.
- All OCR events have ocr_confidence 0.85–1.00 because `OcrEngine.recognize`
  reports the **max confidence of any line**, not the confidence of the line
  that matched the IGN.
- Pairs of feed rows 2–4 s apart (948/950/954, 1296/1300, 1322/1324, 1550/1558).
- 12 highlights created (max_clips_per_match=12); audio-only COMBAT events
  consumed 8 of those slots while several real kills were merged/dropped.

## Root causes (code review)
1. **Blob OCR**: whole calibrated region treated as one feed line. HUD + multiple
   rows mixed. Victim token extracted from wrong row → wrong signature.
2. **`recognize_rows` returns ONE band** (highest confidence) and is only called
   when the crop *changed* and whole-region score < 0.55. Dim/knock rows that
   persist across frames are never retried with the better per-row OCR.
3. **Global `__any__` 1.5 s cooldown** in `feed_detector._process` drops any
   second event, regardless of signature/category (breaks "accurate" preset).
4. **Fuzzy victim dedup collapses knock candidates**: when the IGN token is
   garbled, `feed_entry_signature` returns bare IGN, so `victim == prev_victim`
   ('rickbarat') for every such row → all suppressed within 45 s. Similar enemy
   names (>=0.68 ratio) also collapse.
5. **`cfg.confidence_threshold` is never used**; `ocr_conf` is not tied to the
   matching line, so garbage reads score 1.00.
6. **`rank_events` dedups by time only** (0.8 s), ignoring category — a COMBAT
   event can evict a real KILL.
7. **Adaptive interval `max(configured, duration/900)`** forces 2.67 s sampling
   on 40-min matches and ignores the "accurate" preset's 1 s request.
8. **`merge_segments` (gap 6 s)** merges distinct encounters into very long
   segments without enforcing max_segment_sec.

## Planned fixes
- A: OcrResult carries per-line scores; `recognize_rows` returns ALL bands.
- B: `feed_entry_signature` uses the best-matching individual line and robust
  victim extraction; add `matched_line_confidence` helper.
- C: `feed_detector._process`: per-signature dedup only, strict fuzzy victim
  check (len>=4, ratio>=0.85), remove global cooldown, honour confidence
  threshold, prefer confirmed over possible, always try row OCR when weak.
- D: `rank_events`: category-aware priority and dedup.
- E: pipeline sampling uses finer of OCR/visual intervals, cap 1800 samples.
- F: tests for A–E.
