#!/usr/bin/env python3
"""Forummapping weekly analytics report.

Pulls the account's recent posts and their metrics (cheap owned reads),
writes reports/report-YYYY-MM-DD.md, and appends performance notes to
top/bottom performers in content_database.csv.
"""
import csv, datetime, os, re
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO, "content_database.csv")
REPORTS = os.path.join(REPO, "reports")
ME = "https://api.x.com/2/users/me"


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def main():
    session = oauth()
    me = session.get(ME, params={"user.fields": "public_metrics"})
    me.raise_for_status()
    user = me.json()["data"]
    uid = user["id"]
    followers = user.get("public_metrics", {}).get("followers_count", "?")

    week_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat(timespec="seconds")
    r = session.get(f"https://api.x.com/2/users/{uid}/tweets", params={
        "max_results": 100, "start_time": week_ago,
        "tweet.fields": "public_metrics,created_at",
        "exclude": "replies",
    })
    r.raise_for_status()
    posts = r.json().get("data", [])

    def imp(t): return t.get("public_metrics", {}).get("impression_count", 0)
    posts.sort(key=imp, reverse=True)
    total_imp = sum(imp(t) for t in posts)
    total_likes = sum(t.get("public_metrics", {}).get("like_count", 0) for t in posts)

    today = datetime.date.today().isoformat()
    lines = [
        f"# Weekly report — {today}",
        "",
        f"- Followers: {followers}",
        f"- Posts (7 days, excl. replies): {len(posts)}",
        f"- Impressions: {total_imp:,}",
        f"- Likes: {total_likes:,}",
        f"- Pace toward 5M/3mo monetization threshold: {total_imp*13:,} per quarter at this rate",
        "",
        "## Top 5 posts",
    ]
    for t in posts[:5]:
        pm = t.get("public_metrics", {})
        lines.append(f"- {imp(t):,} imp, {pm.get('like_count',0)} likes — {t['text'][:80]!r} (id {t['id']})")
    lines.append("")
    lines.append("## Bottom 5 posts")
    for t in posts[-5:]:
        lines.append(f"- {imp(t):,} imp — {t['text'][:80]!r} (id {t['id']})")

    os.makedirs(REPORTS, exist_ok=True)
    open(os.path.join(REPORTS, f"report-{today}.md"), "w").write("\n".join(lines) + "\n")

    # annotate database rows via the post ids logged in notes
    rows = list(csv.DictReader(open(DB_PATH)))
    fieldnames = rows[0].keys()
    by_id = {}
    for row in rows:
        for pid in re.findall(r"id (\d+)", row["notes"]):
            by_id[pid] = row
    for label, group in (("top performer", posts[:5]), ("weak performer", posts[-5:])):
        for t in group:
            row = by_id.get(t["id"])
            if row and total_imp:
                note = f"{label} wk {today} ({imp(t):,} imp)"
                row["notes"] = f"{row['notes']}; {note}"
    with open(DB_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"report written: {len(posts)} posts, {total_imp:,} impressions, {followers} followers")


if __name__ == "__main__":
    main()
