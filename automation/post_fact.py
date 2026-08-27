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
COOLDOWN_DAYS = 45        # preferred gap before a fact may reappear
HARD_MIN_DAYS = 7         # absolute floor — never relaxed, even if it means skipping


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def main():
    # pulse runs hourly and every hour is now a fact hour (24/day)
    with open(FACTS, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows:
        print("facts.csv is empty")
        return

    # Spacing policy: always prefer the least-posted facts, and within that tier
    # take the one that has been off the timeline longest. Random choice inside the
    # tier is what let facts reappear days apart once the bank completed a cycle.
    def last_posted(r):
        return r["last_posted"] or ""          # never-posted sorts first (empty string)

    min_used = min(int(r["times_posted"] or 0) for r in rows)
    pool = [r for r in rows if int(r["times_posted"] or 0) == min_used]

    # Hard cooldown: never repeat anything seen in the last COOLDOWN_DAYS, even if
    # it is technically "least posted". Only relaxed if the whole bank is too small.
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=COOLDOWN_DAYS)).isoformat()
    eligible = [r for r in pool if last_posted(r) < cutoff or not r["last_posted"]]
    if not eligible:
        # Relax toward the hard floor, but never past it: repeating a fact within a
        # week is worse than posting nothing, because followers notice repetition.
        floor = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=HARD_MIN_DAYS)).isoformat()
        eligible = [r for r in rows if last_posted(r) < floor or not r["last_posted"]]
        if not eligible:
            print(f"SKIPPING: every fact in the bank of {len(rows)} was posted within the "
                  f"last {HARD_MIN_DAYS} days. Grow facts.csv rather than repeat.")
            return
        print(f"note: bank too small for the {COOLDOWN_DAYS}-day target — using oldest "
              f"eligible fact (still ≥{HARD_MIN_DAYS} days old). Add more facts.")

    row = min(eligible, key=last_posted)
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
