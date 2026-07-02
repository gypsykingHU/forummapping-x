#!/usr/bin/env python3
"""Forummapping newsletter-thread poster.

Runs ~36h after each newsletter send: finds the newest issue in
newsletter/sent/ that hasn't had its thread posted, looks up its companion
thread in newsletter_threads/queue/<same-basename>.json, and posts it.

Thread post objects support:
  "image"     — filename in Posts/ (local map)
  "image_url" — remote image URL (e.g. the newsletter's Wikimedia header)

Usage:
  python3 automation/post_newsletter_thread.py --dry-run
  python3 automation/post_newsletter_thread.py
"""
import glob, json, os, sys, time, shutil, tempfile, mimetypes
import requests
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENT_NL = os.path.join(REPO, "newsletter", "sent")
QUEUE = os.path.join(REPO, "newsletter_threads", "queue")
SENT = os.path.join(REPO, "newsletter_threads", "sent")
STATE = os.path.join(REPO, "state", "nl_threads_posted.json")
POSTS_DIR = os.path.join(REPO, "Posts")
CREATE_POST = "https://api.x.com/2/tweets"
MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
UA = {"User-Agent": "forummapping-nl-thread/1.0"}


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def upload(session, path, mime=None):
    mime = mime or mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        resp = session.post(MEDIA_UPLOAD, files={"media": (os.path.basename(path), f, mime)},
                            data={"media_category": "tweet_image"})
    resp.raise_for_status()
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


def media_id_for(session, post):
    if post.get("image"):
        return upload(session, os.path.join(POSTS_DIR, post["image"]))
    if post.get("image_url"):
        r = requests.get(post["image_url"], timeout=30, headers=UA)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(r.content)
        try:
            return upload(session, f.name, "image/jpeg")
        finally:
            os.unlink(f.name)
    return None


def main():
    try:
        posted = json.load(open(STATE))
    except (OSError, ValueError):
        posted = []

    issues = sorted(glob.glob(os.path.join(SENT_NL, "*.md")), key=os.path.getmtime, reverse=True)
    target = next((p for p in issues if os.path.basename(p) not in posted), None)
    if not target:
        print("All sent issues already threaded — nothing to do.")
        return
    base = os.path.splitext(os.path.basename(target))[0]
    tpath = os.path.join(QUEUE, base + ".json")
    if not os.path.exists(tpath):
        print(f"No companion thread for {base} — skipping (writer didn't produce one).")
        if "--dry-run" not in sys.argv:
            # mark as handled so we don't wait on it forever
            posted.append(os.path.basename(target))
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(posted, open(STATE, "w"), indent=1)
        return

    thread = json.load(open(tpath))
    if "--dry-run" in sys.argv:
        print(f"WOULD POST newsletter thread {thread['id']} ({len(thread['posts'])} posts)")
        for i, p in enumerate(thread["posts"], 1):
            tag = " +img" if p.get("image") or p.get("image_url") else ""
            print(f"  {i}. [{len(p['text'])} ch]{tag} {p['text'][:70]}")
        return

    session = oauth()
    prev_id = None
    for i, post in enumerate(thread["posts"], 1):
        payload = {"text": post["text"]}
        try:
            mid = media_id_for(session, post)
        except Exception as e:
            print(f"media failed on post {i}, continuing without: {e}")
            mid = None
        if mid:
            payload["media"] = {"media_ids": [str(mid)]}
        if prev_id:
            payload["reply"] = {"in_reply_to_tweet_id": prev_id}
        resp = session.post(CREATE_POST, json=payload)
        resp.raise_for_status()
        prev_id = resp.json()["data"]["id"]
        print(f"posted {i}/{len(thread['posts'])}: {prev_id}")
        time.sleep(3)

    posted.append(os.path.basename(target))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(posted, open(STATE, "w"), indent=1)
    os.makedirs(SENT, exist_ok=True)
    shutil.move(tpath, os.path.join(SENT, os.path.basename(tpath)))
    print(f"Newsletter thread live for {base}")


if __name__ == "__main__":
    main()
