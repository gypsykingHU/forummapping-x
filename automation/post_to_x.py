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


def x_post(session, url, **kw):
    """POST to X and explain failures in plain language.
    Returns the response on success; raises SystemExit with a readable message
    on the failures that actually happen in production."""
    r = session.post(url, **kw)
    if r.ok:
        return r
    body = (r.text or "")[:400]
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


def pick_row(rows):
    """Least-posted first; within that tier, whatever has been off the feed longest.
    Random selection inside the tier is what causes maps to resurface days apart
    once the library completes a rotation, so ordering by age is deliberate."""
    active = [r for r in rows if r["status"] == "active" and r["caption"].strip()]
    if not active:
        sys.exit("No active rows in database.")

    def last_posted(r):
        return r["last_posted"] or ""          # never-posted sorts first

    min_posted = min(int(r["times_posted"] or 0) for r in active)
    pool = [r for r in active if int(r["times_posted"] or 0) == min_posted]

    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=COOLDOWN_DAYS)).isoformat()
    eligible = [r for r in pool if last_posted(r) < cutoff or not r["last_posted"]]
    if not eligible:
        # Relax toward the hard floor, never past it. A map reappearing inside a week
        # is the single most visible failure mode for this account.
        floor = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=HARD_MIN_DAYS)).isoformat()
        eligible = [r for r in active if last_posted(r) < floor or not r["last_posted"]]
        if not eligible:
            return None    # caller skips this cycle rather than repeat
        print(f"note: library small for the {COOLDOWN_DAYS}-day target — using oldest "
              f"eligible map (still ≥{HARD_MIN_DAYS} days old)")

    # keep same-day variety: avoid a category already used today when possible
    today = datetime.date.today().isoformat()
    todays_cats = {r["category"] for r in active if (r["last_posted"] or "")[:10] == today}
    varied = [r for r in eligible if r["category"] not in todays_cats]

    return min(varied or eligible, key=last_posted)


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
    row = pick_row(rows)
    if row is None:
        print(f"SKIPPING: every active map was posted within the last {HARD_MIN_DAYS} days. "
              f"Add maps rather than repeat.")
        return False
    img = os.path.join(POSTS_DIR, row["filename"])
    text = trim(row["caption"])

    if "--dry-run" in sys.argv:
        print(f"WOULD POST: {row['filename']}\nCaption: {text}")
        return False

    media_id = upload_media(session, img)
    resp = x_post(session, CREATE_POST, json={"text": text, "media": {"media_ids": [str(media_id)]}})
    post_id = resp.json()["data"]["id"]

    row["last_posted"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    row["times_posted"] = str(int(row["times_posted"] or 0) + 1)
    note = f"posted {datetime.date.today().isoformat()} id {post_id}"
    row["notes"] = f"{row['notes']}; {note}" if row["notes"] else note

    with open(DB_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Posted {row['filename']} -> https://x.com/forummapping/status/{post_id}")
    return True


def main():
    session = oauth()

    if "--check" in sys.argv:
        r = session.get(ME)
        print(r.status_code, r.text[:300])
        sys.exit(0 if r.ok else 1)

    with open(DB_PATH, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Spacing is handled by the workflow cron (every 4h), not here. The 7-day
    # no-repeat rule in pick_row() still applies and is unrelated to spacing.
    n = 1 if "--dry-run" in sys.argv else slots_missed(rows)
    if n > 1:
        print(f"catching up: {n} map slots elapsed since the last post")
    posted = 0
    for i in range(n):
        if i:
            time.sleep(SPACING_SECONDS)
        if not post_one(session, rows, fieldnames):
            break
        posted += 1
    print(f"done: {posted} map(s) posted")


if __name__ == "__main__":
    main()
