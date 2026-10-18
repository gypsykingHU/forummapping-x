#!/usr/bin/env python3
"""Approved Maps intake -- the second map pipeline.

Milan's "Claude Maps" generators drop finished, approved maps into
    Forummapping/Claude Maps/Approved Maps/
This script moves them into the live library (x-automation/Posts/) and adds a
row for each to content_database.csv, so they enter the normal posting, thread
and newsletter pipelines. post_to_x.pick_row() gives never-posted rows tagged
src:claude-maps first claim on map slots (see FRESH_* there), so new maps go
out before the old library gets its turn again.

Two steps, because a post needs a caption and a caption needs eyes on the map:

  python3 automation/ingest_approved.py              # 1. move + add rows (status pending-caption)
  python3 automation/ingest_approved.py --pending    #    list rows still waiting for a caption
  python3 automation/ingest_approved.py --captions captions.json
                                                     # 2. fill captions, rows become 'active'

captions.json: {"<map_id or filename>": {"title": "...", "caption": "<=280 chars",
                "category": "...", "era": "...", "region": "..."}, ...}
(title/caption required; category/era/region optional, defaults Economy & society/Modern/Europe.)

A row stays out of rotation until it has a caption and status 'active' --
pick_row() ignores anything else -- so a half-finished intake can never post.

Safe to re-run: files are matched by SHA-256, so a map already in Posts/ is
never imported twice (the stray copy in Approved Maps is just removed).
Every move is appended to state/approved_ingest_log.csv.

Flags: --dry-run (show only), --src DIR (override the Approved Maps folder).
"""
import csv, datetime, hashlib, json, os, re, shutil, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "content_database.csv")
POSTS = os.path.join(REPO, "Posts")
LOG = os.path.join(REPO, "state", "approved_ingest_log.csv")
DEFAULT_SRC = os.path.join(os.path.dirname(REPO), "Claude Maps", "Approved Maps")
SRC_TAG = "src:claude-maps"          # pick_row() keys the priority lane off this
PREFIX = "cm-"                       # filename prefix for imported maps
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
FIELDS = ["map_id", "filename", "title", "caption", "category", "era", "region",
          "status", "last_posted", "times_posted", "notes"]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_db():
    with open(DB, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), (reader.fieldnames or FIELDS)


def save_db(rows, fields):
    tmp = DB + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, DB)


def humanize(stem):
    s = re.sub(r"^\d+[_-]", "", stem).replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:]


def next_id(rows):
    return max((int(r["map_id"][3:]) for r in rows if re.fullmatch(r"FM-\d+", r["map_id"])), default=0) + 1


def log_rows(entries):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["date", "map_id", "filename", "source_name", "sha256"])
        w.writerows(entries)


def ingest(src, dry):
    if not os.path.isdir(src):
        print(f"Approved Maps folder not found: {src}")
        return
    files = sorted(f for f in os.listdir(src) if f.lower().endswith(IMG_EXT) and not f.startswith("."))
    if not files:
        print("Approved Maps is empty -- nothing to ingest.")
        return
    rows, fields = load_db()
    known = {}
    for fn in os.listdir(POSTS):
        p = os.path.join(POSTS, fn)
        if os.path.isfile(p) and fn.lower().endswith(IMG_EXT):
            known[sha(p)] = fn
    today = datetime.date.today().isoformat()
    n = next_id(rows)
    entries, added = [], 0
    for name in files:
        path = os.path.join(src, name)
        digest = sha(path)
        if digest in known:
            print(f"already in library as {known[digest]} -- {'would remove' if dry else 'removing'} the copy: {name}")
            if not dry:
                os.remove(path)
            continue
        dest_name = PREFIX + name
        base, ext = os.path.splitext(dest_name)
        k = 2
        while os.path.exists(os.path.join(POSTS, dest_name)):
            dest_name = f"{base}-{k}{ext}"; k += 1
        mid = f"FM-{n:04d}"
        if dry:
            print(f"WOULD INGEST {name} -> Posts/{dest_name} as {mid}")
            n += 1
            continue
        shutil.copy2(path, os.path.join(POSTS, dest_name))
        if sha(os.path.join(POSTS, dest_name)) != digest:
            os.remove(os.path.join(POSTS, dest_name))
            print(f"copy verification failed for {name}; left it in Approved Maps")
            continue
        os.remove(path)                      # only after the verified copy exists
        rows.append({
            "map_id": mid, "filename": dest_name, "title": humanize(os.path.splitext(name)[0]),
            "caption": "", "category": "", "era": "", "region": "Europe",
            "status": "pending-caption", "last_posted": "", "times_posted": "0",
            "notes": f"{SRC_TAG}; ingested {today}",
        })
        entries.append([today, mid, dest_name, name, digest])
        known[digest] = dest_name
        print(f"ingested {name} -> Posts/{dest_name} as {mid} (pending-caption)")
        n += 1
        added += 1
    if added:
        save_db(rows, fields)
        log_rows(entries)
    print(f"done: {added} map(s) ingested. Next: write captions, then --captions FILE.json")


def pending():
    rows, _ = load_db()
    p = [r for r in rows if r["status"] == "pending-caption"]
    for r in p:
        print(f"{r['map_id']}\t{r['filename']}\t{r['title']}")
    print(f"{len(p)} map(s) waiting for a caption.")


def apply_captions(path, dry):
    data = json.load(open(path, encoding="utf-8"))
    rows, fields = load_db()
    by_key = {}
    for r in rows:
        by_key[r["map_id"]] = r
        by_key[r["filename"]] = r
    bad = []
    for key, c in data.items():
        r = by_key.get(key)
        if r is None:
            bad.append(f"{key}: no such map"); continue
        cap = (c.get("caption") or "").strip()
        if not cap or len(cap) > 280:
            bad.append(f"{key}: caption missing or {len(cap)} chars (max 280)"); continue
        if not (c.get("title") or "").strip():
            bad.append(f"{key}: title missing"); continue
        if not os.path.exists(os.path.join(POSTS, r["filename"])):
            bad.append(f"{key}: image {r['filename']} missing from Posts/"); continue
    if bad:
        print("NOT APPLIED -- fix these first:\n  " + "\n  ".join(bad))
        sys.exit(1)
    for key, c in data.items():
        r = by_key[key]
        r["title"] = c["title"].strip()
        r["caption"] = c["caption"].strip()
        r["category"] = c.get("category") or r["category"] or "Economy & society"
        r["era"] = c.get("era") or r["era"] or "Modern"
        r["region"] = c.get("region") or r["region"] or "Europe"
        r["status"] = "active"
        print(f"{'would activate' if dry else 'activated'} {r['map_id']} {r['filename']}")
    if not dry:
        save_db(rows, fields)


def main():
    dry = "--dry-run" in sys.argv
    src = DEFAULT_SRC
    if "--src" in sys.argv:
        src = sys.argv[sys.argv.index("--src") + 1]
    if "--pending" in sys.argv:
        return pending()
    if "--captions" in sys.argv:
        return apply_captions(sys.argv[sys.argv.index("--captions") + 1], dry)
    ingest(src, dry)


if __name__ == "__main__":
    main()
