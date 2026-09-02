#!/usr/bin/env python3
"""Forummapping hourly fact poster.

Posts the least-recently-used fact from facts.csv. Facts recycle after the
whole bank rotates (they're evergreen statistics), so the queue never dies;
the Monday content writer keeps the bank growing so repeats stay rare.
"""
import csv, datetime, os, random, sys, time
from requests_oauthlib import OAuth1Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTS = os.path.join(REPO, "facts.csv")
CREATE_POST = "https://api.x.com/2/tweets"
COOLDOWN_DAYS = 45        # preferred gap before a fact may reappear
SPACING_SECONDS = 90      # catch-up gap. Kept short on purpose: a long-running job holds
                          # the concurrency group and blocks the NEXT hourly trigger.
HARD_MIN_DAYS = 7         # absolute floor — never relaxed, even if it means skipping


def oauth():
    return OAuth1Session(
        os.environ["X_API_KEY"], client_secret=os.environ["X_API_KEY_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def x_post(session, url, **kw):
    """POST to X and explain failures in plain language.
    Returns the response on success; raises SystemExit with a readable message
    on the failures that actually happen in production."""
    r = session.post(url, **kw)
    if r.ok:
        return r
    body = (r.text or "")[:400]
    if r.status_code in (401, 403):
        print(f"X API REFUSED ({r.status_code}). This is almost never a code problem.")
        print("  Check, in order:")
        print("   1. console.x.com — credit balance at or below zero blocks ALL requests")
        print("   2. console.x.com — monthly spending limit reached blocks until next cycle")
        print("   3. app keys/tokens still valid and set to Read and Write")
        print(f"  X said: {body}")
        raise SystemExit(1)
    if r.status_code == 429:
        print(f"Rate limited (429). Skipping this slot rather than failing the run. {body}")
        raise SystemExit(0)          # exit clean: no failure email for a normal condition
    print(f"X API error {r.status_code}: {body}")
    raise SystemExit(1)



def slots_missed(rows, per_day=24, cap=6):
    """GitHub drops most scheduled runs (observed gaps of 2–13h on an hourly cron),
    so a run that assumes it is one-of-24 silently loses most of the day's volume.
    Work out how many posting slots have elapsed since the last post and catch up,
    capped so a very long outage doesn't dump a wall of posts at once."""
    stamps = [r["last_posted"] for r in rows if r["last_posted"]]
    if not stamps:
        return 1
    try:
        last = datetime.datetime.fromisoformat(max(stamps))
    except ValueError:
        return 1
    if last.tzinfo is None:
        last = last.replace(tzinfo=datetime.timezone.utc)
    hours = (datetime.datetime.now(datetime.timezone.utc) - last).total_seconds() / 3600
    return max(1, min(cap, int(hours / (24 / per_day))))


def main():
    # pulse runs hourly and every hour is now a fact hour (24/day)
    with open(FACTS, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not rows:
        print("facts.csv is empty")
        return

    n = 1 if "--dry-run" in sys.argv else slots_missed(rows)
    if n > 1:
        print(f"catching up: {n} fact slots elapsed since the last post")
    posted = 0
    for i in range(n):
        if i:
            time.sleep(SPACING_SECONDS)
        if not post_one(rows, fieldnames):
            break
        posted += 1
    print(f"done: {posted} fact(s) posted")


def post_one(rows, fieldnames):

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
            return False
        print(f"note: bank too small for the {COOLDOWN_DAYS}-day target — using oldest "
              f"eligible fact (still ≥{HARD_MIN_DAYS} days old). Add more facts.")

    row = min(eligible, key=last_posted)
    text = row["text"]
    if len(text) > 280:
        text = text[:277] + "…"

    if "--dry-run" in sys.argv:
        print(f"WOULD POST FACT: {text}")
        return False

    resp = x_post(oauth(), CREATE_POST, json={"text": text})
    row["times_posted"] = str(int(row["times_posted"] or 0) + 1)
    row["last_posted"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(FACTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"posted fact: {text[:70]}")
    return True


if __name__ == "__main__":
    main()
