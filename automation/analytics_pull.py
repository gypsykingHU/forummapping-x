#!/usr/bin/env python3
"""One-off analytics pull: every @forummapping post since START with its public metrics.

    python automation/analytics_pull.py [--start 2026-10-01]

Writes reports/posts-YYYY-MM-DD.csv. Cost: X API owned reads, about $0.001 per post
returned (about $1 for ~1,000 posts). Run from the 'Analytics pull' workflow, which has the
API secrets; nothing here is scheduled.
"""
import csv, datetime, os, sys, time
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = "2026-10-01"
if "--start" in sys.argv:
    START = sys.argv[sys.argv.index("--start") + 1]


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"])


def main():
    s = oauth()
    me = s.get("https://api.x.com/2/users/me")
    if not me.ok:
        sys.exit(f"auth failed {me.status_code}: {me.text[:200]}")
    uid = me.json()["data"]["id"]
    rows, token, pages = [], None, 0
    while True:
        params = {"max_results": 100, "start_time": START + "T00:00:00Z",
                  "tweet.fields": "created_at,public_metrics,referenced_tweets,attachments,in_reply_to_user_id"}
        if token:
            params["pagination_token"] = token
        r = s.get(f"https://api.x.com/2/users/{uid}/tweets", params=params)
        if r.status_code == 429:
            time.sleep(30); continue
        if not r.ok:
            sys.exit(f"timeline failed {r.status_code}: {r.text[:300]}")
        d = r.json()
        for t in d.get("data", []):
            m = t.get("public_metrics", {})
            refs = [x["type"] for x in t.get("referenced_tweets", [])]
            rows.append({
                "id": t["id"], "created_at": t["created_at"], "text": t["text"].replace("\n", " "),
                "impressions": m.get("impression_count", ""), "likes": m.get("like_count", ""),
                "replies": m.get("reply_count", ""), "reposts": m.get("retweet_count", ""),
                "quotes": m.get("quote_count", ""), "bookmarks": m.get("bookmark_count", ""),
                "is_reply": int("replied_to" in refs), "has_media": int(bool(t.get("attachments", {}).get("media_keys"))),
            })
        pages += 1
        token = d.get("meta", {}).get("next_token")
        if not token or pages > 40:
            break
    os.makedirs(os.path.join(REPO, "reports"), exist_ok=True)
    out = os.path.join(REPO, "reports", f"posts-{datetime.date.today().isoformat()}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"], lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} posts since {START} -> {out} (approx cost ${0.001 * len(rows) + 0.01:.2f})")


if __name__ == "__main__":
    main()
