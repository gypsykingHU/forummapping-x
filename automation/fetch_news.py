#!/usr/bin/env python3
"""Fetch world-news RSS feeds from reputable outlets and store the raw items
in news_raw/latest.json, for the newsletter digest writer to read locally."""
import datetime, json, os, re
import feedparser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "news_raw", "latest.json")

FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "Deutsche Welle": "https://rss.dw.com/rdf/rss-en-world",
    "NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
}

WINDOW_DAYS = 4


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()[:500]


def main():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=WINDOW_DAYS)
    items = []
    for outlet, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"feed failed {outlet}: {e}")
            continue
        count = 0
        for e in feed.entries[:60]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            dt = datetime.datetime(*t[:6], tzinfo=datetime.timezone.utc) if t else None
            if dt and dt < cutoff:
                continue
            items.append({
                "outlet": outlet,
                "title": clean(e.get("title", "")),
                "summary": clean(e.get("summary", e.get("description", ""))),
                "link": e.get("link", ""),
                "published": dt.isoformat(timespec="seconds") if dt else None,
            })
            count += 1
        print(f"{outlet}: {count} items")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "items": items,
    }, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {len(items)} items -> {OUT}")


if __name__ == "__main__":
    main()
