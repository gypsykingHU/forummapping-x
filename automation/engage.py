#!/usr/bin/env python3
"""Forummapping engagement module.

Daily, with hard caps:
  - up to MAX_COMMENTS replies under popular niche posts, each with a relevant
    map from the library (skips posts where no map genuinely matches)
  - up to MAX_FOLLOWS follows, verified accounts prioritized

State lives in state/ (committed back to the repo by the workflow).

Usage:
  python3 automation/engage.py --dry-run
  python3 automation/engage.py
"""
import csv, json, os, re, sys, time, random, mimetypes
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "content_database.csv")
POSTS_DIR = os.path.join(REPO, "Posts")
STATE_DIR = os.path.join(REPO, "state")
FOLLOWED = os.path.join(STATE_DIR, "followed.json")
ENGAGED = os.path.join(STATE_DIR, "engaged.json")
OWN_ID = os.path.join(STATE_DIR, "own_id.txt")

SEARCH = "https://api.x.com/2/tweets/search/recent"
CREATE_POST = "https://api.x.com/2/tweets"
MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
ME = "https://api.x.com/2/users/me"

MAX_COMMENTS = 5
MAX_FOLLOWS = 10
MIN_MATCH_SCORE = 2

QUERIES = [
    '(history map OR historical map OR "old map") lang:en -is:retweet -is:reply has:images',
    '(empire OR borders OR "in 1914" OR "in 1939" OR habsburg OR ottoman OR prussia) map lang:en -is:retweet -is:reply',
    '(geography OR linguistics OR dialect OR ethnic) map europe lang:en -is:retweet -is:reply',
]

REPLY_TEMPLATES = [
    "Great post — we actually made a map on exactly this:",
    "This pairs well with a map we made:",
    "Adding a map to the conversation:",
    "For anyone who wants the visual — we mapped this:",
    "Relevant map from our archive:",
]

STOPWORDS = set("the a an of in on to and or for with by at from map maps history historical this that is are was were".split())


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def load_json(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(data, open(path, "w"), indent=1)


def tokens(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOPWORDS and len(w) > 2}


def own_id(session):
    if os.path.exists(OWN_ID):
        return open(OWN_ID).read().strip()
    r = session.get(ME)
    r.raise_for_status()
    uid = r.json()["data"]["id"]
    os.makedirs(STATE_DIR, exist_ok=True)
    open(OWN_ID, "w").write(uid)
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
    followed = load_json(FOLLOWED, [])
    engaged = load_json(ENGAGED, [])
    rows = list(csv.DictReader(open(DB_PATH)))

    q = random.choice(QUERIES)
    r = session.get(SEARCH, params={
        "query": q, "max_results": 25,
        "expansions": "author_id",
        "user.fields": "verified,public_metrics,username",
        "tweet.fields": "public_metrics,author_id",
    })
    r.raise_for_status()
    data = r.json()
    posts = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    posts.sort(key=lambda t: t.get("public_metrics", {}).get("like_count", 0), reverse=True)

    # --- comments (max 5, only when a map genuinely matches) ---
    comments = 0
    for post in posts:
        if comments >= MAX_COMMENTS:
            break
        if post["id"] in engaged:
            continue
        row, score = best_map(post["text"], rows)
        if not row:
            continue
        text = f"{random.choice(REPLY_TEMPLATES)} {row['title']}"
        if dry:
            print(f"WOULD REPLY to {post['id']} (match {score}): {text} [{row['filename']}]")
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

    # --- follows (max 10, verified first) ---
    uid = None if dry else own_id(session)
    candidates = sorted(
        (u for u in users.values() if u["id"] not in followed),
        key=lambda u: (not u.get("verified", False), -u.get("public_metrics", {}).get("followers_count", 0)),
    )
    follows = 0
    for u in candidates:
        if follows >= MAX_FOLLOWS:
            break
        if dry:
            print(f"WOULD FOLLOW @{u.get('username')} (verified={u.get('verified')})")
        else:
            resp = session.post(f"https://api.x.com/2/users/{uid}/following",
                                json={"target_user_id": u["id"]})
            if not resp.ok:
                print(f"follow failed {resp.status_code}: {resp.text[:150]}")
                continue
            time.sleep(3)
        followed.append(u["id"])
        follows += 1

    if not dry:
        save_json(FOLLOWED, followed)
        save_json(ENGAGED, engaged[-2000:])
    print(f"done: {comments} comments, {follows} follows")


if __name__ == "__main__":
    main()
