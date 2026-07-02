#!/usr/bin/env python3
"""Forummapping engagement module.

Method (per Milan's spec):
  FOLLOWS — look at the accounts we follow, pick the biggest ones, browse
  their follower lists, and follow up to 10 verified people per day.
  COMMENTS — browse our home feed, rank posts by engagement, and reply to
  up to 5 posts where we have a genuinely relevant map to contribute.

State lives in state/ (committed back by the workflow):
  followed.json      ids we already followed (never re-follow)
  engaged.json       post ids we already replied to
  big_accounts.json  weekly cache of our biggest followed accounts
  pagination.json    per-account cursor into their follower lists
  own_id.txt         our user id

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

MAX_COMMENTS = 5
MAX_FOLLOWS = 10
FOLLOWER_PAGE = 25      # follower profiles fetched per day ($0.01 each)
TIMELINE_PAGE = 25      # feed posts fetched per day ($0.005 each)
MIN_MATCH_SCORE = 2
BIG_CACHE_DAYS = 7

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


def big_accounts(session, uid):
    """Weekly-cached list of the biggest accounts we follow."""
    cache = load_json("big_accounts.json", {})
    today = datetime.date.today()
    if cache.get("fetched") and (today - datetime.date.fromisoformat(cache["fetched"])).days < BIG_CACHE_DAYS:
        return cache["accounts"]
    r = session.get(f"https://api.x.com/2/users/{uid}/following", params={
        "max_results": 100, "user.fields": "public_metrics,username",
    })
    r.raise_for_status()
    following = r.json().get("data", [])
    following.sort(key=lambda u: u.get("public_metrics", {}).get("followers_count", 0), reverse=True)
    accounts = [{"id": u["id"], "username": u.get("username", "")} for u in following[:5]]
    save_json("big_accounts.json", {"fetched": today.isoformat(), "accounts": accounts})
    return accounts


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
    rows = list(csv.DictReader(open(DB_PATH)))

    # ---------- COMMENTS: browse home feed, target high engagement ----------
    r = session.get(f"https://api.x.com/2/users/{uid}/timelines/reverse_chronological", params={
        "max_results": TIMELINE_PAGE,
        "tweet.fields": "public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "verified,username,public_metrics",
    })
    r.raise_for_status()
    data = r.json()
    feed = [t for t in data.get("data", []) if t.get("author_id") != uid]
    feed_users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    feed.sort(key=lambda t: t.get("public_metrics", {}).get("like_count", 0)
              + 3 * t.get("public_metrics", {}).get("reply_count", 0), reverse=True)

    comments = 0
    for post in feed:
        if comments >= MAX_COMMENTS:
            break
        if post["id"] in engaged:
            continue
        row, score = best_map(post["text"], rows)
        if not row:
            continue
        likes = post.get("public_metrics", {}).get("like_count", 0)
        text = f"{random.choice(REPLY_TEMPLATES)} {row['title']}"
        if dry:
            print(f"WOULD REPLY ({likes} likes, match {score}): {text} [{row['filename']}]")
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

    # ---------- FOLLOWS: verified followers of the big accounts we follow ----------
    follows = 0
    bigs = big_accounts(session, uid)
    if bigs:
        cursors = load_json("pagination.json", {})
        big = bigs[datetime.date.today().toordinal() % len(bigs)]  # rotate daily
        params = {"max_results": FOLLOWER_PAGE, "user.fields": "verified,username,public_metrics"}
        if cursors.get(big["id"]):
            params["pagination_token"] = cursors[big["id"]]
        r = session.get(f"https://api.x.com/2/users/{big['id']}/followers", params=params)
        if r.ok:
            payload = r.json()
            cursors[big["id"]] = payload.get("meta", {}).get("next_token")
            save_json("pagination.json", cursors)
            candidates = [u for u in payload.get("data", [])
                          if u.get("verified") and u["id"] not in followed and u["id"] != uid]
            # top up with verified authors seen in today's feed
            candidates += [u for u in feed_users.values()
                           if u.get("verified") and u["id"] not in followed and u["id"] != uid]
            for u in candidates:
                if follows >= MAX_FOLLOWS:
                    break
                if dry:
                    print(f"WOULD FOLLOW @{u.get('username')} (from @{big['username']}'s verified followers)")
                else:
                    resp = session.post(f"https://api.x.com/2/users/{uid}/following",
                                        json={"target_user_id": u["id"]})
                    if not resp.ok:
                        print(f"follow failed {resp.status_code}: {resp.text[:150]}")
                        continue
                    time.sleep(3)
                followed.append(u["id"])
                follows += 1
        else:
            print(f"follower fetch failed {r.status_code}: {r.text[:150]}")
    else:
        print("note: you don't follow anyone yet — follow a few big history/map accounts to seed the module")

    if not dry:
        save_json("followed.json", followed)
        save_json("engaged.json", engaged[-2000:])
    print(f"done: {comments} comments, {follows} follows")


if __name__ == "__main__":
    main()
