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
import csv, os, random, sys, datetime, mimetypes
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "content_database.csv")
POSTS_DIR = os.path.join(REPO, "Posts")

MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
CREATE_POST = "https://api.x.com/2/tweets"
ME = "https://api.x.com/2/users/me"
MAX_CHARS = 280


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


def pick_row(rows):
    active = [r for r in rows if r["status"] == "active" and r["caption"].strip()]
    if not active:
        sys.exit("No active rows in database.")
    min_posted = min(int(r["times_posted"] or 0) for r in active)
    pool = [r for r in active if int(r["times_posted"] or 0) == min_posted]
    today = datetime.date.today().isoformat()
    todays_cats = {r["category"] for r in active if (r["last_posted"] or "")[:10] == today}
    varied = [r for r in pool if r["category"] not in todays_cats]
    return random.choice(varied or pool)


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
    resp.raise_for_status()
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


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

    row = pick_row(rows)
    img = os.path.join(POSTS_DIR, row["filename"])
    text = trim(row["caption"])

    if "--dry-run" in sys.argv:
        print(f"WOULD POST: {row['filename']}\nCaption: {text}")
        return

    media_id = upload_media(session, img)
    resp = session.post(CREATE_POST, json={"text": text, "media": {"media_ids": [str(media_id)]}})
    resp.raise_for_status()
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


if __name__ == "__main__":
    main()
