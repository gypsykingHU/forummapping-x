#!/usr/bin/env python3
"""Forummapping newsletter engine.

Sends the next article from newsletter/queue/ via the Buttondown API,
then moves it to newsletter/sent/.

Article file format (markdown with a simple header block):
---
subject: The subject line
header_image: https://commons.wikimedia.org/wiki/Special:FilePath/Example.jpg?width=800
header_caption: Caption shown under the image
---
Body markdown...

Usage:
  python3 automation/send_newsletter.py --dry-run
  python3 automation/send_newsletter.py
"""
import os, sys, glob, shutil, requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(REPO, "newsletter", "queue")
SENT = os.path.join(REPO, "newsletter", "sent")
API = "https://api.buttondown.com/v1/emails"

FOOTER = (
    "\n\n---\n\n*Enjoyed this? It came from a map. Follow "
    "[@forummapping on X](https://x.com/forummapping) for daily history maps, "
    "and forward this email to a friend who loves history.*"
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
        r = requests.head(url, timeout=15, allow_redirects=True,
                          headers={"User-Agent": "forummapping-newsletter/1.0"})
        return r.ok and "image" in r.headers.get("content-type", "")
    except requests.RequestException:
        return False


def commons_search(query):
    """Find a real image on Wikimedia Commons matching the query."""
    import urllib.parse
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": query,
            "srnamespace": 6, "srlimit": 5, "format": "json",
        }, headers={"User-Agent": "forummapping-newsletter/1.0"}, timeout=20)
        for hit in r.json().get("query", {}).get("search", []):
            name = hit["title"].split(":", 1)[-1]
            url = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
                   + urllib.parse.quote(name) + "?width=800")
            if image_ok(url):
                return url
    except (requests.RequestException, ValueError):
        pass
    return None


def main():
    key = os.environ.get("BUTTONDOWN_API_KEY")
    if not key:
        sys.exit("Missing BUTTONDOWN_API_KEY")

    files = sorted(glob.glob(os.path.join(QUEUE, "*.md")))
    if not files:
        print("Newsletter queue is empty — add more articles to newsletter/queue/.")
        return
    path = files[0]
    meta, body = parse(path)

    parts = []
    img = meta.get("header_image")
    if img and not image_ok(img):
        print(f"note: header image unavailable: {img}")
        img = None
    if not img and meta.get("header_image_search"):
        img = commons_search(meta["header_image_search"])
        print(f"note: resolved via Commons search: {img}")
    if img:
        parts.append(f"![{meta.get('header_caption','')}]({img})")
        if meta.get("header_caption"):
            parts.append(f"*{meta['header_caption']}*")
    parts.append(body)
    full_body = "\n\n".join(parts) + FOOTER

    if "--dry-run" in sys.argv:
        print(f"WOULD SEND: {meta['subject']}\n{full_body[:500]}...")
        return

    resp = requests.post(
        API,
        headers={"Authorization": f"Token {key}", "X-Buttondown-Live-Dangerously": "true"},
        json={"subject": meta["subject"], "body": full_body, "status": "about_to_send"},
        timeout=30,
    )
    if not resp.ok:
        sys.exit(f"Buttondown error {resp.status_code}: {resp.text[:300]}")

    os.makedirs(SENT, exist_ok=True)
    shutil.move(path, os.path.join(SENT, os.path.basename(path)))
    print(f"Sent: {meta['subject']}")


if __name__ == "__main__":
    main()
