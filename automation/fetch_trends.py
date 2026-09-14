#!/usr/bin/env python3
"""Forummapping trend scanner (GitHub Actions edition).

Every 2h: pulls X's worldwide trending list, runs the free keyword filter in
trend_keywords.py to find anything with a political/economic/finance/
geography angle, and writes ONLY that residue to trend_candidates.json.

This split matters for cost. Milan asked to minimize Claude usage as much as
possible -- the scheduled Claude task (forummapping-trend-fact-writer) reads
trend_candidates.json, not the raw trending list, so it never spends a token
filtering out sports scores and celebrity gossip. That filtering happens here,
in plain Python, for free.

A trend that was already turned into a candidate in the last 24h is not
resurfaced, even if it's still trending -- one fact per trend, not one every
2h for as long as it stays hot. Candidates older than 2 days are dropped from
the seen-list entirely (housekeeping; the fact itself expires on its own
schedule in trending_facts.csv, this is just bookkeeping so the file doesn't
grow forever).

Credentials: reuses X_API_KEY/X_API_KEY_SECRET (already GitHub secrets, no new
setup needed) -- but NOT via OAuth 1.0a like the posting scripts. A live run
proved GET /2/trends/by/woeid rejects OAuth 1.0a outright:
    "Authenticating with OAuth 1.0a User Context is forbidden for this
    endpoint. Supported authentication types are [OAuth 2.0 User Context,
    OAuth 2.0 Application-Only]."
This one endpoint needs OAuth 2.0 App-only auth specifically -- everything
else this repo calls accepts OAuth 1.0a, which is why this was missed until
the first live run. Fixed by exchanging the API key/secret for a Bearer token
via POST /oauth2/token (see get_app_bearer_token below); the trends call
itself is unchanged at $0.01/request.
"""
import csv, datetime, json, os, sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trend_keywords

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_OUT = os.path.join(REPO, "trends_raw", "latest.json")
CANDIDATES_OUT = os.path.join(REPO, "trend_candidates.json")
SEEN_PATH = os.path.join(REPO, "trend_candidates_seen.json")

BEARER_TOKEN_URL = "https://api.x.com/oauth2/token"
TRENDS_URL = "https://api.x.com/2/trends/by/woeid/1"   # 1 = worldwide
WOEID_LABEL = "worldwide"
RESURFACE_COOLDOWN_HOURS = 24     # don't re-flag the same trend within a day
SEEN_HOUSEKEEPING_DAYS = 2        # matches the 2-day rolling expiry on facts


def get_app_bearer_token():
    """Exchange X_API_KEY/X_API_KEY_SECRET for an OAuth 2.0 Application-Only
    Bearer Token (docs.x.com: POST oauth2/token, HTTP Basic auth of key:secret,
    grant_type=client_credentials). X returns the SAME existing token on
    repeat calls rather than minting a new one each time -- "repeated requests
    to this method will yield the same already-existent token until it has
    been invalidated" -- so calling this once per run (12x/day) is the
    documented pattern, not excessive: no caching needed, no extra secret to
    configure, and it isn't a separately billed resource in the pay-per-use
    pricing table (only the trends call itself is)."""
    r = requests.post(
        BEARER_TOKEN_URL,
        auth=(os.environ["X_API_KEY"], os.environ["X_API_KEY_SECRET"]),
        data={"grant_type": "client_credentials"},
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    if not r.ok:
        print(f"Could not obtain an app-only bearer token ({r.status_code}): "
              f"{(r.text or '')[:300]}")
        print("  Check console.x.com: API Key/Secret valid, app not suspended.")
        raise SystemExit(1)
    return r.json()["access_token"]


def x_get(url, token, **kw):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, **kw)
    if r.ok:
        return r
    body = (r.text or "")[:400]
    if r.status_code in (401, 403):
        print(f"X API REFUSED ({r.status_code}) on trends. Check, in order:")
        print("   1. console.x.com credit balance")
        print("   2. billing-cycle spend cap")
        print("   3. app-only bearer token obtained cleanly (see step above)")
        print(f"  X said: {body}")
        raise SystemExit(1)
    if r.status_code == 429:
        print(f"Rate limited (429) on trends. Skipping this cycle. {body}")
        raise SystemExit(0)
    print(f"X API error {r.status_code} on trends: {body}")
    raise SystemExit(1)


def load_seen():
    if os.path.exists(SEEN_PATH):
        try:
            return json.load(open(SEEN_PATH, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_seen(seen):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=1, ensure_ascii=False)


def main():
    token = get_app_bearer_token()
    resp = x_get(TRENDS_URL, token, params={"max_trends": 50})
    data = resp.json().get("data", [])
    now = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    os.makedirs(os.path.dirname(RAW_OUT), exist_ok=True)
    json.dump({
        "fetched_at": now_iso, "woeid": 1, "location": WOEID_LABEL,
        "trends": data,
    }, open(RAW_OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"trends: {len(data)} raw trends fetched ({WOEID_LABEL}) -> {RAW_OUT}")

    seen = load_seen()
    # housekeeping: drop anything older than the rolling window so this file
    # never grows without bound
    housekeeping_floor = now - datetime.timedelta(days=SEEN_HOUSEKEEPING_DAYS)
    seen = {k: v for k, v in seen.items()
            if datetime.datetime.fromisoformat(v) > housekeeping_floor}

    cooldown_floor = now - datetime.timedelta(hours=RESURFACE_COOLDOWN_HOURS)
    candidates = []
    for t in data:
        name = t.get("trend_name", "")
        matched, reason = trend_keywords.matches_niche(name)
        if not matched:
            continue
        key = trend_keywords._normalize(name)
        last_flagged = seen.get(key)
        if last_flagged and datetime.datetime.fromisoformat(last_flagged) > cooldown_floor:
            continue  # already handed to the writer within the cooldown window
        candidates.append({
            "trend_name": name,
            "tweet_count": t.get("tweet_count"),
            "reason": reason,
            "first_seen": now_iso,
        })
        seen[key] = now_iso

    save_seen(seen)
    json.dump({"fetched_at": now_iso, "candidates": candidates},
               open(CANDIDATES_OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    if candidates:
        names = ", ".join(c["trend_name"] for c in candidates)
        print(f"trends: {len(candidates)} candidate(s) worth a look -> {names}")
    else:
        print("trends: nothing matched the political/economic/finance/geography "
              "filter this cycle -- forummapping-trend-fact-writer will exit "
              "immediately and cost nothing.")


if __name__ == "__main__":
    main()
