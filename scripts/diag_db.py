"""Diagnostic: dump DB events/highlights and recent OCR log lines."""
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["LOCALAPPDATA"]) / "PUBG AutoClips" / "PUBG AutoClips"
db = root / "pubg_autoclips.sqlite3"
c = sqlite3.connect(str(db))
c.row_factory = sqlite3.Row
print("TABLES:", [r[0] for r in c.execute("select name from sqlite_master where type='table'")])
for t in ("matches", "analysis_jobs", "events", "highlights", "exports"):
    try:
        print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
    except Exception as e:
        print(t, "ERR", e)
for t in ("matches", "events", "highlights"):
    print(f"--- {t} cols:", [r[1] for r in c.execute(f"pragma table_info({t})")])
print("--- matches ---")
for r in c.execute("select * from matches order by id"):
    print(dict(r))
print("--- EVENTS ---")
for r in c.execute(
    "select id,match_id,timestamp,category,score,confidence,source,"
    "recognised_text,ocr_confidence from events order by match_id,timestamp"
):
    d = dict(r)
    print(
        f"m{d['match_id']} e{d['id']} t={d['timestamp']:.1f} "
        f"{d['category']:<16} score={d['score']:.1f} conf={d['confidence']:.2f} "
        f"ocr={d['ocr_confidence']:.2f} {d['source']:<16} {d['recognised_text'][:60]!r}"
    )
print("--- HIGHLIGHTS ---")
for r in c.execute(
    "select id,match_id,event_id,start,end,score,category from highlights order by match_id,start"
):
    d = dict(r)
    print(
        f"m{d['match_id']} h{d['id']} eid={d['event_id']} "
        f"{d['start']:.1f}-{d['end']:.1f} {d['category']:<16} {d['score']:.1f}"
    )
print("--- LOG OCR/analysis lines (last 120 matching) ---")
log = root / "Logs" / "pubg_autoclips.log"
if log.exists():
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    import re
    for ln in lines:
        if re.search(r"OCR|event|interval|extract|sample|Knock|knock|feed|analysis", ln, re.I):
            print(ln[:240])
