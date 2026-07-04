#!/usr/bin/env python3
"""Forummapping hourly fact poster.

Posts the least-recently-used fact from facts.csv. Facts recycle after the
whole bank rotates (they're evergreen statistics), so the queue never dies;
the Monday content writer keeps the bank growing so repeats stay rare.
"""
import csv, datetime, os, random, sys
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(REPO, "facts.csv")
CREATE_POST = "https://api.x.com/2/tweets"


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def main():
    # runs hourly via the pulse workflow, but only posts every 2nd hour (12/day)
    hour = datetime.datetime.now(datetime.timezone.utc).hour
    if hour % 2 != 0 and "--force" not in sys.argv and "--dry-run" not in sys.argv:
        print(f"hour {hour} — not a fact hour (every 2nd), skipping")
        return
    with open(FACTS, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows:
        print("facts.csv is empty")
        return

    min_used = min(int(r["times_posted"] or 0) for r in rows)
    pool = [r for r in rows if int(r["times_posted"] or 0) == min_used]
    row = random.choice(pool)
    text = row["text"]
    if len(text) > 280:
        text = text[:277] + "…"

    if "--dry-run" in sys.argv:
        print(f"WOULD POST FACT: {text}")
        return

    resp = oauth().post(CREATE_POST, json={"text": text})
    resp.raise_for_status()
    row["times_posted"] = str(int(row["times_posted"] or 0) + 1)
    row["last_posted"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(FACTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"posted fact: {text[:70]}")


if __name__ == "__main__":
    main()
