#!/usr/bin/env python3
"""Forummapping thread engine.

Posts the next pre-written thread from threads/queue/ as a reply chain,
then moves it to threads/sent/.

Thread file format (JSON):
{
  "id": "001-slug",
  "posts": [
    {"text": "post text", "image": "optional filename in Posts/"},
    ...
  ]
}

Usage:
  python3 automation/post_thread.py --dry-run
  python3 automation/post_thread.py
"""
import json, os, sys, glob, shutil, time, mimetypes
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(REPO, "threads", "queue")
SENT = os.path.join(REPO, "threads", "sent")
POSTS_DIR = os.path.join(REPO, "Posts")
MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
CREATE_POST = "https://api.x.com/2/tweets"


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def upload_media(session, path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        resp = session.post(MEDIA_UPLOAD, files={"media": (os.path.basename(path), f, mime)},
                            data={"media_category": "tweet_image"})
    resp.raise_for_status()
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


def main():
    files = sorted(glob.glob(os.path.join(QUEUE, "*.json")))
    if not files:
        print("Thread queue is empty — nothing to post. Add more threads to threads/queue/.")
        return
    path = files[0]
    thread = json.load(open(path))

    if "--dry-run" in sys.argv:
        print(f"WOULD POST thread {thread['id']} ({len(thread['posts'])} posts)")
        for i, p in enumerate(thread["posts"], 1):
            print(f"  {i}. [{len(p['text'])} ch]{' +img' if p.get('image') else ''} {p['text'][:70]}")
        return

    session = oauth()
    prev_id = None
    for i, post in enumerate(thread["posts"], 1):
        payload = {"text": post["text"]}
        if post.get("image"):
            media_id = upload_media(session, os.path.join(POSTS_DIR, post["image"]))
            payload["media"] = {"media_ids": [str(media_id)]}
        if prev_id:
            payload["reply"] = {"in_reply_to_tweet_id": prev_id}
        resp = session.post(CREATE_POST, json=payload)
        resp.raise_for_status()
        prev_id = resp.json()["data"]["id"]
        print(f"posted {i}/{len(thread['posts'])}: {prev_id}")
        time.sleep(3)

    os.makedirs(SENT, exist_ok=True)
    shutil.move(path, os.path.join(SENT, os.path.basename(path)))
    print(f"Thread {thread['id']} complete: https://x.com/forummapping")


if __name__ == "__main__":
    main()
