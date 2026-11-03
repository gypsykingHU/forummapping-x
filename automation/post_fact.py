#!/usr/bin/env python3
"""Forummapping fact poster (2 facts per run, 5 runs/day).

Posts the least-recently-used fact from facts.csv. Facts recycle after the
whole bank rotates (they're evergreen statistics), so the queue never dies;
the Monday content writer keeps the bank growing so repeats stay rare.
"""
import csv, datetime, os, sys, time
from requests_oauthlib import OAuth1Session

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state_store

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


class DuplicatePost(Exception):
    """X refused this exact text as a repeat post. Distinct from an auth/credit 403:
    nothing is misconfigured, this one fact just can't go out. The caller should
    move on to the next slot, not abort the run."""


def x_post(session, url, **kw):
    """POST to X and explain failures in plain language.
    Returns the response on success; raises SystemExit with a readable message
    on genuine auth/credit failures, or DuplicatePost when X's own duplicate-
    content filter is the reason (see DuplicatePost docstring)."""
    r = session.post(url, **kw)
    if r.ok:
        return r
    body = (r.text or "")[:400]
    if r.status_code == 403 and "duplicate content" in body.lower():
        # Most likely explanation: this exact text already went out for real during
        # the Aug 27 - Sep 2 window, when the old "Save state" step could fail
        # silently and leave facts.csv believing nothing was posted (fixed in
        # 15e91c5 / ee58f50). The claim for this row is already recorded by the
        # time we get here, so the record is correct going forward either way.
        print(f"X REFUSED this post as a duplicate of something already on the "
              f"timeline. The claim is already saved, so this row won't be picked "
              f"again — moving to the next slot rather than failing the run.")
        print(f"  X said: {body}")
        raise DuplicatePost(body)
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
    if 500 <= r.status_code < 600:
        # X's own infrastructure, not us -- matches post_to_x.py's x_call().
        # Run #856 failed the whole job on a bare 503 mid-run; the claim for
        # that fact had already been recorded (reserve-before-post), so the
        # fact was marked used without ever going out. Exiting clean here
        # means a future transient 5xx costs one fact's turn, not a red job.
        print(f"X server error {r.status_code} — transient, skipping. {body}")
        raise SystemExit(0)
    print(f"X API error {r.status_code}: {body}")
    raise SystemExit(1)



def load_facts():
    """Prefer the remote bank; the checkout can be behind another run's stamps."""
    if state_store.available():
        remote = state_store.read_csv("facts.csv")
        if remote:
            rows, fields = remote
            print(f"facts: read {len(rows)} rows from origin/main (authoritative)")
            return rows, fields
        print("facts: could not read origin/main — using the checkout")
    with open(FACTS, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


FACTS_PER_RUN = 1          # cron-job.org fires on odd hours (every 2h): 12 facts/day
SPACING_SECONDS = 20       # only matters if FACTS_PER_RUN is raised again

# NEW-FACT LANE (Milan, 2026-11-03): facts that have never been posted go out first
# (lowest fact_id first), but never more than FRESH_MAX_IN_WINDOW of the last
# FRESH_WINDOW fact posts -- the rest of the time the normal rotation (least-posted,
# longest-rested) continues, so old facts keep circulating.
FRESH_WINDOW = 4
FRESH_MAX_IN_WINDOW = 3
LOW_STOCK_USED_PCT = 90    # at/above this share of the bank used at least once, more facts must be written


def bank_status(rows):
    n = len(rows)
    used = sum(1 for r in rows if int(r["times_posted"] or 0) > 0)
    pct = 100.0 * used / n if n else 100.0
    return n, used, pct


def _fresh_pick(rows):
    """Return the next never-posted fact if the new-fact lane has room, else None."""
    fresh = [r for r in rows if int(r["times_posted"] or 0) == 0]
    if not fresh:
        return None
    recent = sorted((r for r in rows if r["last_posted"]), key=lambda r: r["last_posted"],
                    reverse=True)[:FRESH_WINDOW]
    # a fact whose times_posted is exactly 1 and was posted recently went out as its
    # first-ever post, i.e. through this lane
    used = sum(1 for r in recent if int(r["times_posted"] or 0) == 1)
    if used >= FRESH_MAX_IN_WINDOW and len(fresh) < len(rows):
        return None
    return min(fresh, key=lambda r: r.get("fact_id") or "")


def main():
    # Exactly FACTS_PER_RUN facts per run, no catch-up: a missed cron means
    # fewer facts that day, never a burst later. The workflow cron (5x/day) is
    # the only cadence control. post_one() always takes the least-posted,
    # longest-rested fact, so the bank is used evenly.
    rows, fieldnames = load_facts()
    if not rows:
        print("facts.csv is empty")
        return

    if "--status" in sys.argv:                 # used by the content tasks: no posting
        n, used, pct = bank_status(rows)
        print(f"fact bank: {used}/{n} used at least once ({pct:.1f}%), {n - used} never posted; "
              f"{'LOW STOCK -- write new facts' if pct >= LOW_STOCK_USED_PCT else 'ok'}")
        return

    n, used, pct = bank_status(rows)
    print(f"fact bank: {used}/{n} used at least once ({pct:.1f}%), {n - used} never posted")
    if pct >= LOW_STOCK_USED_PCT:
        print(f"LOW STOCK: {pct:.0f}% of the bank has been used (threshold {LOW_STOCK_USED_PCT}%) "
              f"-- the daily intake/content-writer task should write new facts.")

    posted = 0
    for i in range(FACTS_PER_RUN):
        if i and "--dry-run" not in sys.argv:
            time.sleep(SPACING_SECONDS)
        try:
            if post_one(rows, fieldnames):
                posted += 1
            elif "--dry-run" not in sys.argv:
                break                      # nothing eligible / claim failed: stop, don't retry
        except DuplicatePost:
            # claim already saved, so that row won't be picked again; try the next slot
            print("duplicate refused by X (claim recorded) -- moving on")
    print(f"done: {posted} fact(s) posted")


def post_one(rows, fieldnames):

    # Spacing policy: always prefer the least-posted facts, and within that tier
    # take the one that has been off the timeline longest. Random choice inside the
    # tier is what let facts reappear days apart once the bank completed a cycle.
    def last_posted(r):
        return r["last_posted"] or ""          # never-posted sorts first (empty string)

    fresh_row = _fresh_pick(rows)
    if fresh_row is not None:
        pool = [fresh_row]
    else:
        # new-fact lane full (or empty): normal rotation, newest facts excluded so the
        # lane's own ordering is not undone
        base = [r for r in rows if int(r["times_posted"] or 0) > 0] or rows
        min_used = min(int(r["times_posted"] or 0) for r in base)
        pool = [r for r in base if int(r["times_posted"] or 0) == min_used]

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
    fid = row.get("fact_id") or text[:40]

    if "--dry-run" in sys.argv:
        print(f"WOULD POST FACT: [{fid}] {text}")
        return False

    # Claim the ID before posting, not after. See post_to_x.post_one() for why:
    # a post whose record is lost is a post that goes out again inside the week.
    claim = {
        "times_posted": str(int(row["times_posted"] or 0) + 1),
        "last_posted": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    if not state_store.update_csv_row(
            "facts.csv", "fact_id", fid, claim,
            f"claim: fact {datetime.date.today().isoformat()}"):
        print(f"SKIPPING this slot: could not record the claim on {fid}, so posting it "
              f"would risk a repeat. Nothing was posted.")
        return False
    row.update(claim)

    x_post(oauth(), CREATE_POST, json={"text": text})
    print(f"posted fact [{fid}]: {text[:70]}")
    return True


if __name__ == "__main__":
    main()
