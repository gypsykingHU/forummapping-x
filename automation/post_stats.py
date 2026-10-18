#!/usr/bin/env python3
"""Fair-distribution check: how evenly are maps, facts and threads being used?

    python3 automation/post_stats.py

The counters themselves live where the posters already write them
(content_database.csv and facts.csv: times_posted / last_posted; threads in
threads/THREAD_LOG.csv). This only reads them and prints spread + outliers.
"""
import csv, collections, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def rows(name):
    with open(os.path.join(REPO, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def spread(label, items, key):
    n = [int(r["times_posted"] or 0) for r in items]
    if not n:
        return
    hist = collections.Counter(n)
    print(f"\n{label}: {len(n)} items, {sum(n)} posts total, "
          f"min {min(n)} / max {max(n)} / avg {sum(n)/len(n):.2f}")
    print("  times_posted histogram: " + ", ".join(f"{k}x:{hist[k]}" for k in sorted(hist)))
    top = sorted(items, key=lambda r: -int(r["times_posted"] or 0))[:5]
    print("  most posted: " + "; ".join(f"{r[key]}({r['times_posted']})" for r in top))
    gap = max(n) - min(n)
    print(f"  fairness gap (max-min): {gap}" + ("  <-- uneven" if gap > 2 else "  ok"))

maps = [r for r in rows("content_database.csv") if r["status"] == "active"]
spread("MAPS (active)", maps, "map_id")
fresh = [r for r in maps if "src:claude-maps" in (r["notes"] or "")]
spread("  of which Claude Maps", fresh, "map_id")
spread("FACTS", rows("facts.csv"), "fact_id")
p = os.path.join(REPO, "threads", "THREAD_LOG.csv")
if os.path.exists(p):
    t = rows("threads/THREAD_LOG.csv")
    c = collections.Counter(r["status"] for r in t)
    print(f"\nTHREADS: {len(t)} written ({c['sent']} sent, {c['queue']} queued) -- each posts once, never repeats")
