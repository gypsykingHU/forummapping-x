#!/usr/bin/env python3
"""Forummapping engagement module.

COMMENTS — max MAX_COMMENTS_PER_DAY: search X for popular niche posts
(history/geography/geopolitics), rank by engagement, reply where a genuinely
relevant map exists. Search-based, so it works without following anyone.

To change intensity, edit MAX_COMMENTS_PER_DAY below and
the cron schedule in .github/workflows/engagement.yml.
(Following was removed per Milan's instruction, July 2026.)

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

MAX_COMMENTS_PER_DAY = 5
SEARCH_PAGE = 25                  # posts fetched per run ($0.005 each)
MIN_MATCH_SCORE = 2
MIN_LIKES = 20                    # only engage posts that already have traction

QUERIES = [
    '(history OR empire OR "old map" OR cartography) map lang:en -is:retweet -is:reply',
    '("in 1914" OR "in 1939" OR habsburg OR ottoman OR prussia OR byzantine) lang:en -is:retweet -is:reply',
    '(border OR borders OR territory) (dispute OR history OR changed) lang:en -is:retweet -is:reply',
    '(geography OR linguistics OR dialects OR ethnic groups) europe lang:en -is:retweet -is:reply',
]

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
    engaged = load_json("engaged.json", [])
    today = datetime.date.today().isoformat()
    daily = load_json("daily.json", {})
    if daily.get("date") != today:
        daily = {"date": today, "comments": 0}
    rows = list(csv.DictReader(open(DB_PATH)))

    # ---------- COMMENTS (daily cap, search-based) ----------
    comments = 0
    if daily["comments"] < MAX_COMMENTS_PER_DAY:
        query = QUERIES[datetime.date.today().toordinal() % len(QUERIES)]
        r = session.get("https://api.x.com/2/tweets/search/recent", params={
            "query": query,
            "max_results": SEARCH_PAGE,
            "tweet.fields": "public_metrics,author_id",
        })
        if r.ok:
            feed = [t for t in r.json().get("data", []) if t.get("author_id") != uid
                    and t.get("public_metrics", {}).get("like_count", 0) >= MIN_LIKES]
            feed.sort(key=lambda t: t.get("public_metrics", {}).get("like_count", 0)
                      + 3 * t.get("public_metrics", {}).get("reply_count", 0), reverse=True)
            if not feed:
                print(f"note: search returned no posts with ≥{MIN_LIKES} likes for today's query")
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

    if not dry:
        daily["comments"] += comments
        save_json("daily.json", daily)
        save_json("engaged.json", engaged[-2000:])
    print(f"done: {comments} comments")


if __name__ == "__main__":
    main()
