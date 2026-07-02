#!/usr/bin/env python3
"""Forummapping X article poster.

Runs ~1.5 days after each newsletter send: takes the most recent issue from
newsletter/sent/ that hasn't been posted as an X article yet, formats it as a
long-form X post (Premium allows up to 25k chars), attaches the same header
image the newsletter used, and posts it.

Usage:
  python3 automation/post_article.py --dry-run
  python3 automation/post_article.py
"""
import glob, json, os, re, sys, tempfile
import requests
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENT = os.path.join(REPO, "newsletter", "sent")
STATE = os.path.join(REPO, "state", "articles_posted.json")
CREATE_POST = "https://api.x.com/2/tweets"
MEDIA_UPLOAD = "https://api.x.com/2/media/upload"
UA = {"User-Agent": "forummapping-articles/1.0"}

SUBSCRIBE = ("\n\n📬 This article first appeared in Lines & Legends, our free "
             "newsletter — the news that changes maps, every 3 days. "
             "Subscribe: https://buttondown.com/forummapping")


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def parse(path):
    raw = open(path, encoding="utf-8").read()
    _, header, body = raw.split("---", 2)
    meta = {}
    for line in header.strip().splitlines():
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, body.strip()


def image_ok(url):
    try:
        r = requests.head(url, timeout=15, allow_redirects=True, headers=UA)
        return r.ok and "image" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def commons_search(query):
    import urllib.parse
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": query,
            "srnamespace": 6, "srlimit": 5, "format": "json",
        }, headers=UA, timeout=20)
        for hit in r.json().get("query", {}).get("search", []):
            name = hit["title"].split(":", 1)[-1]
            url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                   + urllib.parse.quote(name) + "?width=1200")
            if image_ok(url):
                return url
    except (requests.RequestException, ValueError):
        pass
    return None


def to_plain(md):
    """Markdown -> plain text suitable for a long X post."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)              # images out
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)        # links -> text
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)              # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)                  # italics
    text = re.sub(r"^#+\s*", "", text, flags=re.M)              # headings
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def upload_image_from_url(session, url):
    r = requests.get(url, timeout=30, headers=UA)
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        f.write(r.content)
        f.flush()
        f.seek(0)
        resp = session.post(MEDIA_UPLOAD,
                            files={"media": ("header.jpg", open(f.name, "rb"), "image/jpeg")},
                            data={"media_category": "tweet_image"})
    resp.raise_for_status()
    d = resp.json()
    return d.get("data", d).get("id") or d.get("media_id_string")


def main():
    try:
        posted = json.load(open(STATE))
    except (OSError, ValueError):
        posted = []

    issues = sorted(glob.glob(os.path.join(SENT, "*.md")), key=os.path.getmtime, reverse=True)
    target = next((p for p in issues if os.path.basename(p) not in posted), None)
    if not target:
        print("No unposted newsletter issues — nothing to do.")
        return

    meta, body = parse(target)
    text = f"{meta['subject'].upper()}\n\n{to_plain(body)}{SUBSCRIBE}"
    if len(text) > 24000:
        text = text[:24000] + "…"

    img = meta.get("header_image")
    if img and not image_ok(img):
        img = None
    if not img and meta.get("header_image_search"):
        img = commons_search(meta["header_image_search"])

    if "--dry-run" in sys.argv:
        print(f"WOULD POST article from {os.path.basename(target)} "
              f"({len(text)} chars, image={'yes' if img else 'no'})")
        print(text[:400], "...")
        return

    session = oauth()
    payload = {"text": text}
    if img:
        try:
            payload["media"] = {"media_ids": [str(upload_image_from_url(session, img))]}
        except Exception as e:
            print(f"image upload failed, posting without: {e}")
    resp = session.post(CREATE_POST, json=payload)
    resp.raise_for_status()
    post_id = resp.json()["data"]["id"]

    posted.append(os.path.basename(target))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(posted, open(STATE, "w"), indent=1)
    print(f"Posted article: https://x.com/forummapping/status/{post_id}")


if __name__ == "__main__":
    main()
