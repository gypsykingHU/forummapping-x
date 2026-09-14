#!/usr/bin/env python3
"""Forummapping feed poster (GitHub Actions edition).

Picks the least-recently-posted active map from content_database.csv,
posts it to X with its caption, and updates the database.

Credentials come from environment variables (GitHub Actions secrets):
  X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

Usage:
  python3 automation/post_to_x.py --check     # verify credentials only
  python3 automation/post_to_x.py --dry-run   # show what would be posted
  python3 automation/post_to_x.py             # post for real
"""
import csv, os, random, sys, time, datetime, mimetypes
from requests_oauthlib import OAuth1Session

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state_store

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "content_database.csv")
POSTS_DIR = os.path.join(REPO, "Posts")

MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
CREATE_POST = "https://api.x.com/2/tweets"
ME = "https://api.x.com/2/users/me"
MAX_CHARS = 280


def x_call(r, what="request"):
    """Turn an X API failure into a readable log line instead of a traceback.
    429 exits clean (normal condition, no failure email); auth/credit problems
    exit 1 with a checklist; anything else prints the status and body."""
    if r.ok:
        return r
    body = (r.text or "")[:400]
    if r.status_code == 429:
        print(f"Rate limited (429) on {what}. Skipping this slot rather than failing.")
        raise SystemExit(0)
    if r.status_code in (401, 403):
        print(f"X API REFUSED ({r.status_code}) on {what}. Check, in order:")
        print("   1. console.x.com credit balance (zero blocks everything)")
        print("   2. console.x.com billing-cycle spend cap")
        print("   3. tokens valid and set to Read and Write")
        print(f"  X said: {body}")
        raise SystemExit(1)
    if 500 <= r.status_code < 600:
        print(f"X server error {r.status_code} on {what} — transient, skipping. {body}")
        raise SystemExit(0)
    print(f"X API error {r.status_code} on {what}: {body}")
    raise SystemExit(1)



def oauth():
    missing = [k for k in ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
               if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing environment variables: {missing}")
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


class DuplicatePost(Exception):
    """X refused this exact caption as a repeat post. Distinct from an auth/credit
    403: nothing is misconfigured, this one map just can't go out. Most likely
    explanation: it actually posted during the Aug 27 - Sep 2 outage, when the old
    "Save state" step could fail silently and never record it (fixed in 15e91c5 /
    ee58f50). The caller should move to the next slot, not abort the run."""


def x_post(session, url, **kw):
    """POST to X and explain failures in plain language.
    Returns the response on success; raises SystemExit with a readable message
    on genuine auth/credit failures, or DuplicatePost when X's own duplicate-
    content filter is the reason (see DuplicatePost docstring)."""
    r = session.post(url, **kw)
    if r.ok:
        return r
    body = (r.text or "")[:400]
    if r.status_code == 403 and "duplicate content" in body.lower():
        print(f"X REFUSED this post as a duplicate of something already on the "
              f"timeline. The claim is already saved, so this row won't be picked "
              f"again — moving to the next slot rather than failing the run.")
        print(f"  X said: {body}")
        raise DuplicatePost(body)
    if r.status_code in (401, 403):
        print(f"X API REFUSED ({r.status_code}). This is almost never a code problem.")
        print("  Check, in order:")
        print("   1. console.x.com — credit balance at or below zero blocks ALL requests")
        print("   2. console.x.com — monthly spending limit reached blocks until next cycle")
        print("   3. app keys/tokens still valid and set to Read and Write")
        print(f"  X said: {body}")
        raise SystemExit(1)
    if r.status_code == 429:
        print(f"Rate limited (429). Skipping this slot rather than failing the run. {body}")
        raise SystemExit(0)          # exit clean: no failure email for a normal condition
    print(f"X API error {r.status_code}: {body}")
    raise SystemExit(1)



SPACING_SECONDS = 120     # catch-up gap — short, to keep total job time low
COOLDOWN_DAYS = 60        # preferred gap before a map may reappear
HARD_MIN_DAYS = 7         # absolute floor — never relaxed, even if it means skipping





def slots_missed(rows, per_day=6, cap=2):
    """GitHub drops most scheduled runs, so treat each run as responsible for every
    slot since the last successful post rather than exactly one."""
    stamps = [r["last_posted"] for r in rows if r["last_posted"]]
    if not stamps:
        return 1
    try:
        last = datetime.datetime.fromisoformat(max(stamps))
    except ValueError:
        return 1
    if last.tzinfo is None:
        last = last.replace(tzinfo=datetime.timezone.utc)
    hours = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds() / 3600
    return max(1, min(cap, int(hours / (24 / per_day))))


def is_owid(r):
    return r["filename"].startswith("owid-") or "OWID" in (r["notes"] or "")


def _pick_within_group(pool_rows):
    """The original whole-library algorithm, scoped to one group (original or
    OWID). Least-posted first within the group; within that tier, whatever has
    been off the feed longest. This is what makes rotation continuous: once
    every map in a group has been posted the same number of times, the next
    pick is just the oldest last_posted in the group -- it keeps cycling
    forever rather than ever treating "already posted" as disqualifying."""
    def last_posted(r):
        return r["last_posted"] or ""          # never-posted sorts first

    min_posted = min(int(r["times_posted"] or 0) for r in pool_rows)
    tier = [r for r in pool_rows if int(r["times_posted"] or 0) == min_posted]

    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=COOLDOWN_DAYS)).isoformat()
    eligible = [r for r in tier if last_posted(r) < cutoff or not r["last_posted"]]
    if not eligible:
        floor = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=HARD_MIN_DAYS)).isoformat()
        eligible = [r for r in pool_rows if last_posted(r) < floor or not r["last_posted"]]
        if not eligible:
            return None
        print(f"note: group too small for the {COOLDOWN_DAYS}-day target — using "
              f"oldest eligible map (still >={HARD_MIN_DAYS} days old)")

    today = datetime.date.today().isoformat()
    todays_cats = {r["category"] for r in pool_rows if (r["last_posted"] or "")[:10] == today}
    varied = [r for r in eligible if r["category"] not in todays_cats]
    return min(varied or eligible, key=last_posted)


def pick_row(rows):
    """Choose a map so that, over time, the split between original/historical
    maps and Our World in Data maps tracks their share of the active library
    -- Milan's call, after 138 freshly-imported OWID maps (all starting at
    times_posted=0) monopolized the old whole-library least-posted tier and
    crowded out originals for days. That old logic wasn't wrong exactly, but
    ANY future bulk import of one type reproduces the same imbalance, because
    a single times_posted tier spanning both groups always drains the newer
    group completely before the older group gets a look.

    Fix: track originals and OWID as two independent rotations (each using
    the old least-posted-then-oldest logic, so each keeps cycling
    indefinitely -- posted before is never a disqualifier). Which group gets
    THIS slot is decided by comparing each group's actual share of posts so
    far to its share of the active library, recomputed fresh every run so it
    self-adjusts to future imports without needing a hardcoded ratio: whichever
    group is furthest below its target share gets the slot. This is a
    deficit/weighted-fair-queueing scheduler, the same idea network switches
    use to split bandwidth proportionally between competing streams."""
    active = [r for r in rows if r["status"] == "active" and r["caption"].strip()]
    if not active:
        sys.exit("No active rows in database.")

    owid_pool = [r for r in active if is_owid(r)]
    orig_pool = [r for r in active if not is_owid(r)]

    def group_choice():
        if not owid_pool:
            return "original"
        if not orig_pool:
            return "owid"
        target_owid_share = len(owid_pool) / len(active)
        owid_posts = sum(int(r["times_posted"] or 0) for r in owid_pool)
        orig_posts = sum(int(r["times_posted"] or 0) for r in orig_pool)
        total_posts = owid_posts + orig_posts
        if total_posts == 0:
            # bootstrap: nothing posted yet, go with whichever group is larger
            return "owid" if target_owid_share >= 0.5 else "original"
        current_owid_share = owid_posts / total_posts
        # whichever group is furthest under its target share of the library
        # gets this slot -- pulls the mix back toward proportional over time
        # regardless of what caused the current skew.
        return "owid" if current_owid_share < target_owid_share else "original"

    choice = group_choice()
    row = _pick_within_group(owid_pool if choice == "owid" else orig_pool)
    if row is None:
        # that group is genuinely exhausted (cooldown-locked) -- fall back to
        # the other rather than skip a slot outright.
        other = orig_pool if choice == "owid" else owid_pool
        row = _pick_within_group(other) if other else None
    return row


def trim(text):
    if len(text) <= MAX_CHARS:
        return text
    cut = text[:MAX_CHARS - 1]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut + "…"


def upload_media(session, path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        resp = session.post(MEDIA_UPLOAD, files={"media": (os.path.basename(path), f, mime)},
                            data={"media_category": "tweet_image"})
    x_call(resp, "media upload")
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


def post_one(session, rows, fieldnames):
    """Reserve the map's ID first, then post.

    Order matters. The old order was post -> record, with the record pushed by
    git at the end of the whole job; when that push failed, the post had
    happened but nothing remembered it, and the map came back around inside the
    week. Reserving first inverts the risk: the worst case is a map that gets
    marked as used without going out (one map lost from a library of ~485),
    instead of a map going out twice in front of the audience.
    """
    row = pick_row(rows)
    if row is None:
        print(f"SKIPPING: every active map was posted within the last {HARD_MIN_DAYS} days. "
              f"Add maps rather than repeat.")
        return False
    img = os.path.join(POSTS_DIR, row["filename"])
    text = trim(row["caption"])
    mid = row.get("map_id") or row["filename"]

    if "--dry-run" in sys.argv:
        print(f"WOULD POST: [{mid}] {row['filename']}\nCaption: {text}")
        return False

    # --- 1. claim the ID, durably, before anything goes out -----------------
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    claim = {
        "last_posted": stamp,
        "times_posted": str(int(row["times_posted"] or 0) + 1),
    }
    if not state_store.update_csv_row(
            "content_database.csv", "map_id", mid, claim,
            f"claim: map {datetime.date.today().isoformat()}"):
        print(f"SKIPPING this slot: could not record the claim on {mid}, so posting it "
              f"would risk a repeat. Nothing was posted.")
        return False
    row.update(claim)          # keep the in-memory copy consistent for this run

    # --- 2. now post; the claim already stands ------------------------------
    media_id = upload_media(session, img)
    resp = x_post(session, CREATE_POST, json={"text": text, "media": {"media_ids": [str(media_id)]}})
    post_id = resp.json()["data"]["id"]

    # --- 3. annotate with the live post id (best effort; the lock is already safe)
    note = f"posted {datetime.date.today().isoformat()} id {post_id}"
    row["notes"] = f"{row['notes']}; {note}" if row["notes"] else note
    state_store.update_csv_row(
        "content_database.csv", "map_id", mid, {"notes": row["notes"]},
        f"log: map {datetime.date.today().isoformat()}")

    print(f"Posted [{mid}] {row['filename']} -> https://x.com/forummapping/status/{post_id}")
    return True


def load_database():
    """Prefer the remote copy of the database; fall back to the checkout."""
    if state_store.available():
        remote = state_store.read_csv("content_database.csv")
        if remote:
            rows, fields = remote
            print(f"database: read {len(rows)} rows from origin/main (authoritative)")
            return rows, fields
        print("database: could not read origin/main — using the checkout")
    with open(DB_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def main():
    session = oauth()

    if "--check" in sys.argv:
        r = session.get(ME)
        print(r.status_code, r.text[:300])
        sys.exit(0 if r.ok else 1)

    # Read the database from the remote branch when we can. The runner's
    # checkout is a snapshot from job-start and may already be behind another
    # run's stamps; trusting it is how a "posted" map looks unposted.
    rows, fieldnames = load_database()

    # Spacing is handled by the workflow cron (every 4h), not here. The 7-day
    # no-repeat rule in pick_row() still applies and is unrelated to spacing.
    n = 1 if "--dry-run" in sys.argv else slots_missed(rows)
    if n > 1:
        print(f"catching up: {n} map slots elapsed since the last post")
    posted = skipped_dupes = 0
    for i in range(n):
        if i:
            time.sleep(SPACING_SECONDS)
        try:
            if not post_one(session, rows, fieldnames):
                break
        except DuplicatePost:
            # The claim for that map is already saved (it happened before the X
            # call), so it won't be picked again. Move on to the next slot instead
            # of losing the rest of this catch-up batch to one already-posted map.
            skipped_dupes += 1
            continue
        posted += 1
    extra = f", {skipped_dupes} skipped as duplicates" if skipped_dupes else ""
    print(f"done: {posted} map(s) posted{extra}")


if __name__ == "__main__":
    main()
