#!/usr/bin/env python3
"""Forummapping engagement module.

FOLLOWS — every run: browse the verified-follower list of the seed account
(Amazing Maps), follow up to FOLLOWS_PER_RUN new people. Runs once daily,
so up to 10 follows/day.
COMMENTS — max MAX_COMMENTS_PER_DAY across all runs: browse the home feed,
rank by engagement, reply where a genuinely relevant map exists.

To change intensity, edit FOLLOWS_PER_RUN / MAX_COMMENTS_PER_DAY below and
the cron schedule in .github/workflows/engagement.yml.

Usage:
  python3 automation/engage.py --dry-run
  python3 automation/engage.py
"""
import csv, json, os, re, sys, time, random, mimetypes, datetime
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "content_database.csv")
POSTS_DIR = os.path.join(REPO, "Posts")
STATE_DIR = os.path.join(REPO, "state")

CREATE_POST = "https://api.x.com/2/tweets"
MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
ME = "https://api.x.com/2/users/me"

SEED_HANDLES = ["Amazing_Maps"]   # source accounts for follower browsing
FOLLOWS_PER_RUN = 10              # one run per day = 10 follows/day
MAX_COMMENTS_PER_DAY = 5
FOLLOWER_PAGE = 10                # follower profiles fetched per run (billed per profile)
TIMELINE_PAGE = 25                # feed posts fetched per run
MIN_MATCH_SCORE = 2

REPLY_TEMPLATES = [
    "Great post — we actually made a map on exactly this:",
    "This pairs well with a map we made:",
    "Adding a map to the conversation:",
    "For anyone who wants the visual — we mapped this:",
    "Relevant map from our archive:",
]

STOPWORDS = set("the a an of in on to and or for with by at from map maps history historical this that is are was were have has had its it's".split())


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def load_json(name, default):
    try:
        return json.load(open(os.path.join(STATE_DIR, name)))
    except (OSError, ValueError):
        return default


def save_json(name, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump(data, open(os.path.join(STATE_DIR, name), "w"), indent=1)


def tokens(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def own_id(session):
    p = os.path.join(STATE_DIR, "own_id.txt")
    if os.path.exists(p):
        return open(p).read().strip()
    r = session.get(ME)
    r.raise_for_status()
    uid = r.json()["data"]["id"]
    os.makedirs(STATE_DIR, exist_ok=True)
    open(p, "w").write(uid)
    return uid


def seed_ids(session):
    """Resolve seed handles to ids once, then cache."""
    cache = load_json("seeds.json", {})
    changed = False
    for h in SEED_HANDLES:
        if h not in cache:
            r = session.get(f"https://api.x.com/2/users/by/username/{h}")
            if r.ok:
                cache[h] = r.json()["data"]["id"]
                changed = True
            else:
                print(f"seed lookup failed for @{h}: {r.status_code}")
    if changed:
        save_json("seeds.json", cache)
    return [{"username": h, "id": i} for h, i in cache.items()]


def upload_media(session, path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        resp = session.post(MEDIA_UPLOAD, files={"media": (os.path.basename(path), f, mime)},
                            data={"media_category": "tweet_image"})
    resp.raise_for_status()
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


def best_map(post_text, rows):
    ptoks = tokens(post_text)
    best, score = None, 0
    for r in rows:
        if r["status"] != "active":
            continue
        s = len(ptoks & tokens(r["title"] + " " + r["region"] + " " + r["era"]))
        if s > score:
            best, score = r, s
    return (best, score) if score >= MIN_MATCH_SCORE else (None, 0)


def main():
    dry = "--dry-run" in sys.argv
    session = oauth()
    uid = own_id(session)
    followed = load_json("followed.json", [])
    engaged = load_json("engaged.json", [])
    today = datetime.date.today().isoformat()
    daily = load_json("daily.json", {})
    if daily.get("date") != today:
        daily = {"date": today, "comments": 0}
    rows = list(csv.DictReader(open(DB_PATH)))

    # ---------- COMMENTS (daily cap shared across runs) ----------
    comments = 0
    if daily["comments"] < MAX_COMMENTS_PER_DAY:
        r = session.get(f"https://api.x.com/2/users/{uid}/timelines/reverse_chronological", params={
            "max_results": TIMELINE_PAGE,
            "tweet.fields": "public_metrics,author_id",
        })
        if r.ok:
            feed = [t for t in r.json().get("data", []) if t.get("author_id") != uid]
            feed.sort(key=lambda t: t.get("public_metrics", {}).get("like_count", 0)
                      + 3 * t.get("public_metrics", {}).get("reply_count", 0), reverse=True)
            for post in feed:
                if daily["comments"] + comments >= MAX_COMMENTS_PER_DAY:
                    break
                if post["id"] in engaged:
                    continue
                row, score = best_map(post["text"], rows)
                if not row:
                    continue
                text = f"{random.choice(REPLY_TEMPLATES)} {row['title']}"
                if dry:
                    print(f"WOULD REPLY (match {score}): {text} [{row['filename']}]")
                else:
                    media_id = upload_media(session, os.path.join(POSTS_DIR, row["filename"]))
                    resp = session.post(CREATE_POST, json={
                        "text": text,
                        "media": {"media_ids": [str(media_id)]},
                        "reply": {"in_reply_to_tweet_id": post["id"]},
                    })
                    if not resp.ok:
                        print(f"reply failed {resp.status_code}: {resp.text[:150]}")
                        continue
                    time.sleep(5)
                engaged.append(post["id"])
                comments += 1
        else:
            print(f"feed fetch failed {r.status_code}: {r.text[:150]}")

    # ---------- FOLLOWS: verified followers of the seed account ----------
    follows = 0
    seeds = seed_ids(session)
    if seeds:
        cursors = load_json("pagination.json", {})
        seed = seeds[datetime.datetime.now().hour // 4 % len(seeds)]
        params = {"max_results": FOLLOWER_PAGE, "user.fields": "verified,username,public_metrics"}
        if cursors.get(seed["id"]):
            params["pagination_token"] = cursors[seed["id"]]
        r = session.get(f"https://api.x.com/2/users/{seed['id']}/followers", params=params)
        if r.ok:
            payload = r.json()
            nxt = payload.get("meta", {}).get("next_token")
            cursors[seed["id"]] = nxt
            if not dry:
                save_json("pagination.json", cursors)
            candidates = [u for u in payload.get("data", [])
                          if u["id"] not in followed and u["id"] != uid]
            candidates.sort(key=lambda u: not u.get("verified", False))  # verified first
            for u in candidates:
                if follows >= FOLLOWS_PER_RUN:
                    break
                if dry:
                    print(f"WOULD FOLLOW @{u.get('username')} (verified follower of @{seed['username']})")
                else:
                    resp = session.post(f"https://api.x.com/2/users/{uid}/following",
                                        json={"target_user_id": u["id"]})
                    if not resp.ok:
                        print(f"follow failed {resp.status_code}: {resp.text[:150]}")
                        continue
                    time.sleep(3)
                followed.append(u["id"])
                follows += 1
            if follows < FOLLOWS_PER_RUN:
                print(f"note: {follows} new accounts on this page of "
                      f"@{seed['username']}'s followers — next run continues from the next page")
        else:
            print(f"follower fetch failed {r.status_code}: {r.text[:150]}")

    if not dry:
        daily["comments"] += comments
        save_json("daily.json", daily)
        save_json("followed.json", followed)
        save_json("engaged.json", engaged[-2000:])
    print(f"done: {comments} comments, {follows} follows")


if __name__ == "__main__":
    main()
