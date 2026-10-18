#!/usr/bin/env python3
"""Thread log -- one row per thread ever written, so the writer can see what has
been covered (topics AND source maps) and never repeat itself.

    threads/THREAD_LOG.csv
    thread_id, status, posted_date, topic, map_ids, images, data_sources, opener

`sync` rebuilds the log from threads/sent/ and threads/queue/ (the folders stay
the source of truth; the log is a readable index over them). Rows already in the
log keep their posted_date. post_thread.py calls sync() right after a thread
goes out, so the date is exact; older threads are back-filled from git history.

    python3 automation/thread_log.py sync          # rebuild/refresh the log
    python3 automation/thread_log.py covered       # topics + map_ids already used (for the writer)
    python3 automation/thread_log.py unused-maps   # active maps not yet used in any thread, newest first
"""
import csv, datetime, glob, json, os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREADS = os.path.join(REPO, "threads")
LOG = os.path.join(THREADS, "THREAD_LOG.csv")
DB = os.path.join(REPO, "content_database.csv")
FIELDS = ["thread_id", "status", "posted_date", "topic", "map_ids", "images", "data_sources", "opener"]


def _db_by_filename():
    if not os.path.exists(DB):
        return {}
    with open(DB, newline="", encoding="utf-8") as f:
        return {r["filename"]: r["map_id"] for r in csv.DictReader(f)}


_GIT_DATES = None


def _git_date(relpath):
    """Date a file first appeared under threads/sent/ (back-fill only; one git
    call for all files; shallow clones return '')."""
    global _GIT_DATES
    if _GIT_DATES is None:
        _GIT_DATES = {}
        try:
            out = subprocess.run(["git", "log", "--diff-filter=A", "--name-only", "--format=@%as",
                                  "--", "threads/sent"], cwd=REPO, capture_output=True,
                                 text=True, timeout=60).stdout
            date = ""
            for line in out.splitlines():
                if line.startswith("@"):
                    date = line[1:]
                elif line.strip():
                    _GIT_DATES[line.strip()] = date      # oldest add wins (log is newest-first)
        except Exception:
            pass
    return _GIT_DATES.get(relpath, "")


def _topic(thread_id):
    return re.sub(r"^\d+-", "", thread_id).replace("-", " ")


def _sources(text):
    s = []
    if "Our World in Data" in text: s.append("OWID")
    if re.search(r"World Bank", text): s.append("World Bank")
    if re.search(r"Nobel", text): s.append("NobelPrize.org")
    return "; ".join(s)


def sync(posted_today_id=None):
    existing = {}
    if os.path.exists(LOG):
        with open(LOG, newline="", encoding="utf-8") as f:
            existing = {r["thread_id"]: r for r in csv.DictReader(f)}
    by_fn = _db_by_filename()
    today = datetime.date.today().isoformat()
    out = []
    for status in ("sent", "queue"):
        for path in sorted(glob.glob(os.path.join(THREADS, status, "*.json"))):
            try:
                t = json.load(open(path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            tid = t.get("id") or os.path.splitext(os.path.basename(path))[0]
            posts = t.get("posts", [])
            imgs = []
            for p in posts:
                if p.get("image") and p["image"] not in imgs:
                    imgs.append(p["image"])
            text = " ".join(p.get("text", "") for p in posts)
            posted = ""
            if status == "sent":
                posted = (existing.get(tid) or {}).get("posted_date") or ""
                if not posted:
                    posted = today if tid == posted_today_id else _git_date(f"threads/sent/{os.path.basename(path)}")
            out.append({
                "thread_id": tid, "status": status, "posted_date": posted,
                "topic": _topic(tid),
                "map_ids": "; ".join(by_fn[i] for i in imgs if i in by_fn),
                "images": "; ".join(imgs), "data_sources": _sources(text),
                "opener": (posts[0]["text"].split("\n")[0][:140] if posts else ""),
            })
    out.sort(key=lambda r: r["thread_id"])
    os.makedirs(THREADS, exist_ok=True)
    with open(LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def _read():
    if not os.path.exists(LOG):
        return sync()
    with open(LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd == "sync":
        rows = sync()
        sent = sum(1 for r in rows if r["status"] == "sent")
        print(f"thread log: {len(rows)} threads ({sent} sent, {len(rows) - sent} queued) -> {LOG}")
    elif cmd == "covered":
        for r in _read():
            print(f"{r['thread_id']}\t{r['status']}\t{r['posted_date']}\t{r['map_ids']}")
    elif cmd == "unused-maps":
        used = {m for r in _read() for m in r["map_ids"].split("; ") if m}
        with open(DB, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["status"] == "active" and r["map_id"] not in used]
        rows.sort(key=lambda r: (FRESH not in (r["notes"] or ""), -int(r["map_id"][3:])))
        for r in rows[:40]:
            print(f"{r['map_id']}\t{r['filename']}\t{r['title']}\t{'NEW' if FRESH in (r['notes'] or '') else ''}")
        print(f"{len(rows)} active maps not yet used in a thread (NEW = from Approved Maps, listed first)")
    else:
        sys.exit(__doc__)


FRESH = "src:claude-maps"

if __name__ == "__main__":
    main()
