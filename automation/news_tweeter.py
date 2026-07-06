#!/usr/bin/env python3
"""Forummapping breaking-news tweeter.

Runs inside the hourly pulse but only acts every 4th hour, and posts exactly
ONE story per run (the freshest new geopolitical/economic item from the RSS
feeds, deduped via state) — per Milan's spec: one breaking-news post every
4 hours, not a burst.

First run: seeds the dedupe state without tweeting (prevents a flood of
old items when the module goes live).
"""
import datetime, hashlib, json, os, re, sys, time
import feedparser
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(REPO, "state", "news_tweeted.json")
CREATE_POST = "https://api.x.com/2/tweets"

FEEDS = {
    "BBC": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "Guardian": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "DW": "https://rss.dw.com/rdf/rss-en-world",
    "NYT": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
}

KEYWORDS = re.compile(r"\b(" + "|".join([
    "war", "invasion", "ceasefire", "truce", "treaty", "border", "territor",
    "sanction", "tariff", "trade deal", "election", "coup", "referendum",
    "annex", "secession", "independence", "missile", "nuclear", "drone strike",
    "airstrike", "offensive", "mobiliz", "summit", "nato", "united nations",
    "eu ", "european union", "gdp", "inflation", "recession", "central bank",
    "interest rate", "currency", "devalu", "default", "imf", "world bank",
    "oil price", "opec", "gas pipeline", "energy crisis", "embargo",
    "peacekeep", "insurgen", "militia", "junta", "martial law", "parliament",
    "prime minister", "president-elect", "government collapse", "no-confidence",
]) + r")", re.I)

MAX_PER_DAY = 6   # safety ceiling; the every-4th-hour gate is the real limit
WINDOW_HOURS = 6
DAILY_STATE = os.path.join(REPO, "state", "news_daily.json")


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def hid(entry):
    return hashlib.sha1((entry.get("link") or entry.get("title", "")).encode()).hexdigest()[:16]


def collect():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=WINDOW_HOURS)
    items = []
    for outlet, url in FEEDS.items():
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"feed failed {outlet}: {e}")
            continue
        for e in feed.entries[:40]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            dt = datetime.datetime(*t[:6], tzinfo=datetime.timezone.utc) if t else None
            if dt and dt < cutoff:
                continue
            title = re.sub(r"\s+", " ", e.get("title", "")).strip()
            if not title or not KEYWORDS.search(title):
                continue
            items.append({"id": hid(e), "title": title, "outlet": outlet, "dt": dt})
    items.sort(key=lambda x: x["dt"] or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    return items


def main():
    dry = "--dry-run" in sys.argv
    # pulse runs hourly; news posts only every 4th hour (one story per run)
    hour = datetime.datetime.now(datetime.timezone.utc).hour
    if hour % 4 != 0 and not dry and "--force" not in sys.argv:
        print(f"hour {hour} — not a news hour (every 4th), skipping")
        return
    try:
        seen = json.load(open(STATE))
    except (OSError, ValueError):
        seen = None

    items = collect()

    if seen is None:
        # first run: mark everything seen, tweet nothing
        seen = [i["id"] for i in items]
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(seen, open(STATE, "w"))
        print(f"initialized dedupe state with {len(seen)} items — no tweets on first run")
        return

    today = datetime.date.today().isoformat()
    try:
        daily = json.load(open(DAILY_STATE))
    except (OSError, ValueError):
        daily = {}
    if daily.get("date") != today:
        daily = {"date": today, "count": 0}

    # newest first, exactly one story per run
    fresh = [i for i in reversed(items) if i["id"] not in seen][:1]
    if not fresh:
        print("no new matching stories this cycle")
        return

    session = None if dry else oauth()
    posted = 0
    for it in fresh:
        text = f"⚡ {it['title']} — {it['outlet']}"
        if len(text) > 280:
            text = text[:277] + "…"
        if dry:
            print(f"WOULD TWEET: {text}")
        else:
            resp = session.post(CREATE_POST, json={"text": text})
            if not resp.ok:
                print(f"tweet failed {resp.status_code}: {resp.text[:120]}")
                continue
            time.sleep(2)
        seen.append(it["id"])
        posted += 1

    if not dry:
        json.dump(seen[-3000:], open(STATE, "w"))
        daily["count"] += posted
        json.dump(daily, open(DAILY_STATE, "w"))
    print(f"done: {posted} news tweets ({daily['count'] if not dry else '?'}/{MAX_PER_DAY} today)")


if __name__ == "__main__":
    main()
