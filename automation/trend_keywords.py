#!/usr/bin/env python3
"""Cheap, Claude-free relevance filter for X's trending topics list.

Milan's instruction: poll trends every 2h, target political/economic/finance/
geography niches, and minimize Claude usage as much as possible. The way to do
that is to never spend a token on the ~80%+ of trending topics that are sports
scores, celebrity news, and memes -- filter those out in plain Python first,
and only hand the scheduled Claude task the small residue that's actually
worth its judgment.

This is a keyword/gazetteer match, not semantic understanding, so it is
deliberately generous (prefers false positives over false negatives -- a
missed trend costs nothing, a filtered-out real one costs an opportunity).
The Claude task downstream still has to decide whether a match is actually
worth a fact and isn't a tragedy/celebrity trend that just happens to contain
a country name.
"""
import re

try:
    import pycountry
    COUNTRIES = {c.name for c in pycountry.countries}
    # common short/alternate forms pycountry doesn't carry
    COUNTRIES |= {
        "USA", "US", "U.S.", "U.S.A.", "America", "UK", "U.K.", "Britain",
        "South Korea", "North Korea", "Russia", "Iran", "Syria", "Palestine",
        "Ivory Coast", "Vatican", "Czech Republic", "Congo", "DR Congo",
        "Taiwan", "Vietnam", "Laos", "Burma", "Macau", "Hong Kong",
    }
except ImportError:
    # requirements.txt pins pycountry, but degrade instead of hard-failing if
    # the runner's pip cache is ever stale -- a shorter list beats a dead job.
    COUNTRIES = {
        "United States", "USA", "US", "China", "Russia", "India", "Ukraine",
        "France", "Germany", "United Kingdom", "UK", "Britain", "Japan",
        "Brazil", "Mexico", "Canada", "Italy", "Spain", "Israel", "Palestine",
        "Iran", "Iraq", "Syria", "Turkey", "Egypt", "Saudi Arabia", "Poland",
        "South Korea", "North Korea", "Taiwan", "Australia", "Nigeria",
        "South Africa", "Argentina", "Venezuela", "Pakistan", "Indonesia",
    }

# Demonyms for the countries that actually show up in political/economic news
# regularly. Not exhaustive by design -- the long tail is covered by the
# country names themselves, which is the stronger signal anyway.
DEMONYMS = {
    "american", "chinese", "russian", "ukrainian", "indian", "french",
    "german", "british", "japanese", "brazilian", "mexican", "canadian",
    "italian", "spanish", "israeli", "palestinian", "iranian", "iraqi",
    "syrian", "turkish", "egyptian", "saudi", "polish", "korean", "taiwanese",
    "australian", "nigerian", "argentine", "venezuelan", "pakistani",
    "indonesian", "greek", "portuguese", "dutch", "swedish", "finnish",
    "norwegian", "danish", "swiss", "austrian", "belgian", "irish", "scottish",
    "welsh", "vietnamese", "thai", "filipino", "malaysian", "singaporean",
    "kenyan", "ethiopian", "moroccan", "algerian", "colombian", "chilean",
    "peruvian", "cuban", "haitian", "afghan", "yemeni", "lebanese", "jordanian",
    "kurdish", "armenian", "georgian", "kazakh", "azerbaijani",
}

CAPITALS_AND_MAJOR_CITIES = {
    "washington", "beijing", "moscow", "kyiv", "kiev", "new delhi", "paris",
    "berlin", "london", "tokyo", "brasilia", "mexico city", "ottawa", "rome",
    "madrid", "jerusalem", "tel aviv", "gaza", "tehran", "baghdad",
    "damascus", "ankara", "istanbul", "cairo", "riyadh", "warsaw", "seoul",
    "pyongyang", "taipei", "canberra", "abuja", "lagos", "pretoria",
    "buenos aires", "caracas", "islamabad", "jakarta", "athens", "lisbon",
    "amsterdam", "stockholm", "helsinki", "oslo", "copenhagen", "bern",
    "vienna", "brussels", "dublin", "hanoi", "bangkok", "manila",
    "kuala lumpur", "singapore", "nairobi", "addis ababa", "rabat",
    "algiers", "bogota", "santiago", "lima", "havana", "kabul", "sanaa",
    "beirut", "amman", "yerevan", "tbilisi", "astana", "baku", "brussels",
    "geneva", "the hague", "strasbourg",
}

POLITICAL_ECON_FINANCE_TERMS = {
    # governance / conflict
    "election", "elections", "referendum", "parliament", "congress", "senate",
    "president", "prime minister", "coup", "impeachment", "sanctions",
    "ceasefire", "treaty", "summit", "coalition", "cabinet", "constitution",
    "protest", "protests", "uprising", "annexation", "border", "borders",
    "territory", "territorial", "sovereignty", "independence", "secession",
    "nato", "un", "united nations", "eu", "european union", "g7", "g20",
    "brics", "who", "imf", "world bank", "wto", "opec",
    # economics / finance
    "inflation", "recession", "gdp", "interest rate", "interest rates",
    "federal reserve", "central bank", "tariff", "tariffs", "trade war",
    "stock market", "stocks", "bond market", "currency", "devaluation",
    "debt ceiling", "budget", "deficit", "unemployment", "jobs report",
    "crypto", "bitcoin", "oil prices", "opec+", "supply chain", "exports",
    "imports", "embargo",
    # geography / territory framing
    "earthquake", "wildfire", "flood", "drought", "map", "maps", "atlas",
    "border wall", "migration", "refugees", "immigration",
}


def _normalize(trend_name):
    t = trend_name.lstrip("#").strip().lower()
    return re.sub(r"\s+", " ", t)


def matches_niche(trend_name):
    """Return (bool matched, str reason) for whether a trend is worth Claude's
    time.

    Multi-word gazetteer entries ("United States", "South Korea", "the hague")
    are matched as substrings of the normalized trend text -- safe, because a
    multi-word phrase colliding by accident inside another word is
    vanishingly rare. Single-word entries are matched ONLY against whole,
    tokenized words, never raw substrings -- short country codes like "UK" or
    "US" would otherwise match inside unrelated words ("UK" is literally the
    first two letters of "Ukraine", which is exactly the false-positive this
    caught in testing: it flagged "#Ukraine" as a UK match instead of a
    Ukraine match. Right call, wrong reason, and the same bug would wrongly
    match plenty of things that AREN'T political at all)."""
    norm = _normalize(trend_name)
    if not norm:
        return False, ""
    words = set(re.findall(r"[a-z']+", norm))

    def check(entries, label):
        for entry in entries:
            e = entry.lower()
            if " " in e:
                if e in norm:
                    return True, f"{label}:{entry}"
            elif e in words:
                return True, f"{label}:{entry}"
        return None

    for group, label in (
        (COUNTRIES, "country"),
        (DEMONYMS, "demonym"),
        (CAPITALS_AND_MAJOR_CITIES, "city"),
        (POLITICAL_ECON_FINANCE_TERMS, "term"),
    ):
        hit = check(group, label)
        if hit:
            return hit
    return False, ""


if __name__ == "__main__":
    # quick self-test when run directly
    tests = [
        ("#Ukraine", True), ("Taylor Swift", False), ("NBA Finals", False),
        ("Tariffs", True), ("Ceasefire talks", True), ("#WorldCup", False),
        ("Bitcoin", True), ("Kyiv strikes", True), ("Fortnite update", False),
    ]
    for name, expected in tests:
        got, reason = matches_niche(name)
        mark = "ok" if got == expected else "MISMATCH"
        print(f"  [{mark}] {name!r:22s} -> {got} ({reason})")
