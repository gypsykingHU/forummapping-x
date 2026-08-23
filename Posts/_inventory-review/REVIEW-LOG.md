# Post Inventory Review — Log

**Opened:** 2026-08-23 · **Instructed by:** Milan · **Status:** open, awaiting clearance

Nothing has been deleted. All 49 flagged items were moved out of `Posts/` into `Posts/_inventory-review/` and their `content_database.csv` status was changed away from `active`, so `automation/post_to_x.py` (which selects only `status == "active"`) can no longer pick them up. They will not be used in posts, threads or newsletters until you clear them.

## How to clear an item

Move the file back to `Posts/` and set its `content_database.csv` status back to `active` (and trim the review tag from `notes`). Tell me and I'll do it.

## Summary

| Disposition | Folder | Count |
|---|---|---|
| review | `Posts/_inventory-review/01-review/` | 11 |
| update | `Posts/_inventory-review/02-update/` | 7 |
| pending-delete | `Posts/_inventory-review/03-pending-delete/` | 18 |
| pending-delete-remake | `Posts/_inventory-review/04-pending-delete-remake/` | 13 |
| **total flagged** | | **49** |

## ⚠ Needs your decision

`threads/queue/054-languages-of-france.json` — a queued 9-post thread built entirely around **Languages/Dialects of France** (`2_15_23 PM.png`), which you marked *delete*. I moved the whole thread to `Posts/_inventory-review/_blocked-threads/` so it cannot post a map you've flagged. It needs either a replacement map or to be dropped.

Four other flagged maps are referenced by threads in `threads/sent/` (already published, left untouched): `2_55_52 PM` in 036-oldest-university…, `2_17_24 PM` in 041-richest-leaders…, `2_17_45 PM` in 042-most-corrupt-leaders…, `2_14_40 PM` in 031-languages-of-italy.

## Review — keep in library, fact-check before any reuse

Folder: `Posts/_inventory-review/01-review/`

| # | Title | Your instruction | File |
|---|---|---|---|
| 1 | Most Valuable Banknote in Every European Country | review banknotes | `(1) Instagram - Google Chrome 9_26_2025 7_09_20 PM.png` |
| 2 | Year and Method of Last Execution in Europe | review exact dates & methods | `(3) Instagram - Google Chrome 10_10_2025 10_54_10 AM.png` |
| 3 | Europe During WW1 (1918) | review — needs details | `(3) Instagram - Google Chrome 10_19_2025 2_20_50 PM.png` |
| 4 | Religion of Europe in 1600 | review religious territories | `(3) Instagram - Google Chrome 10_19_2025 2_21_36 PM.png` |
| 5 | Religions in Europe, 900 AD | review according to historical facts | `(3) Instagram - Google Chrome 10_19_2025 2_35_29 PM.png` |
| 6 | Legality of Holocaust Denial | check validity | `(3) Instagram - Google Chrome 10_19_2025 2_38_30 PM.png` |
| 7 | Currencies in Europe, 1914 | check validity & make new versions | `(3) Instagram - Google Chrome 10_19_2025 2_40_38 PM.png` |
| 8 | Recognition of Crimea as part of Ukraine or Russia | check validity | `(3) Instagram - Google Chrome 10_19_2025 2_41_22 PM.png` |
| 9 | The Oldest University in Each European Country | review | `(3) Instagram - Google Chrome 10_19_2025 2_55_52 PM.png` |
| 10 | Countries Which Can Enter the US Without a Visa | review | `(3) Instagram - Google Chrome 10_19_2025 2_57_57 PM.png` |
| 11 | Percentage of Population Not Having an Indoor Flushing Toilet | review & delete — review first, then delete | `(3) Instagram - Google Chrome 10_19_2025 2_58_59 PM.png` |

## Update — keep in library, data/labels need refreshing

Folder: `Posts/_inventory-review/02-update/`

| # | Title | Your instruction | File |
|---|---|---|---|
| 1 | GDP (PPP) per Capita in Europe, 1938 | update with 2026 dollars | `(3) Instagram - Google Chrome 10_19_2025 2_35_42 PM.png` |
| 2 | Recognition of Israel and Palestine | needs updated version | `(3) Instagram - Google Chrome 10_19_2025 2_45_00 PM.png` |
| 3 | GDP of European Countries in 1938 (Excluding Colonies) | update with current dollar values | `(5) Instagram - Google Chrome 8_4_2025 12_39_35 PM.png` |
| 4 | Tourism as a % of GDP | update with year | `(5) Instagram - Google Chrome 8_11_2025 10_27_05 AM.png` |
| 5 | Countries That Are More Developed Than the USA | review & update with HDI | `(5) Instagram - Google Chrome 8_15_2025 10_33_56 PM.png` |
| 6 | Leading Import Partners of African Countries | update with year & make current version | `(3) Instagram - Google Chrome 10_19_2025 2_37_37 PM.png` |
| 7 | The European Union | needs update | `(3) Instagram - Google Chrome 10_19_2025 2_54_09 PM.png` |

## Pending delete — staged, NOT deleted

Folder: `Posts/_inventory-review/03-pending-delete/`

| # | Title | Your instruction | File |
|---|---|---|---|
| 1 | Languages/Dialects of Italy | bad map, delete from library | `(3) Instagram - Google Chrome 10_19_2025 2_14_40 PM.png` |
| 2 | Map of Germanic Y-DNA in Europe | delete | `(3) Instagram - Google Chrome 10_19_2025 2_14_42 PM.png` |
| 3 | Map of Slavic Y-DNA in Europe | delete | `(3) Instagram - Google Chrome 10_19_2025 2_14_54 PM.png` |
| 4 | Languages/Dialects of France | delete | `(3) Instagram - Google Chrome 10_19_2025 2_15_23 PM.png` |
| 5 | Distribution of Haplogroup I2a2 (Y-DNA) in Europe (pre-Celto-Germanic) | delete | `(3) Instagram - Google Chrome 10_19_2025 2_15_38 PM.png` |
| 6 | Top Leaders with the Most Killed People | delete | `(3) Instagram - Google Chrome 10_19_2025 2_17_16 PM.png` |
| 7 | Richest Leaders in the World | delete | `(3) Instagram - Google Chrome 10_19_2025 2_17_24 PM.png` |
| 8 | Longest Serving Leaders | delete | `(3) Instagram - Google Chrome 10_19_2025 2_17_30 PM.png` |
| 9 | Top Leaders With Most Assassination Attempts Part 2 | delete | `(3) Instagram - Google Chrome 10_19_2025 2_17_37 PM.png` |
| 10 | Most Corrupt Leaders by Amount Embezzled | delete | `(3) Instagram - Google Chrome 10_19_2025 2_17_45 PM.png` |
| 11 | Axis Occupation of Yugoslavia (1941-1945) | delete | `(3) Instagram - Google Chrome 10_19_2025 2_19_52 PM.png` |
| 12 | Dialects of Italy | delete | `(3) Instagram - Google Chrome 10_19_2025 2_20_10 PM.png` |
| 13 | Palestinian Land Loss | delete | `(3) Instagram - Google Chrome 10_19_2025 2_22_23 PM.png` |
| 14 | Religions of Europe and around | delete | `(3) Instagram - Google Chrome 10_19_2025 2_22_28 PM.png` |
| 15 | Countries that Have Been Colonized by Europe | delete | `(3) Instagram - Google Chrome 10_19_2025 2_29_55 PM.png` |
| 16 | Number of Official Languages by Country | delete | `(3) Instagram - Google Chrome 10_19_2025 2_36_09 PM.png` |
| 17 | Second Most Spoken Languages in Poland Before WW2 by County | delete | `(3) Instagram - Google Chrome 10_19_2025 2_38_09 PM.png` |
| 18 | European Countries' Previous Flag | delete | `(3) Instagram - Google Chrome 10_19_2025 2_56_56 PM.png` |

## Pending delete + remake — staged, replacement to be produced

Folder: `Posts/_inventory-review/04-pending-delete-remake/`

| # | Title | Your instruction | File |
|---|---|---|---|
| 1 | Most Popular Male Newborn Names in Europe | delete & make a new one | `(5) Instagram - Google Chrome 8_16_2025 11_46_59 AM.png` |
| 2 | AI Created Alternative Names for European Countries | delete (maybe make a new one) | `1000004234.jpg` |
| 3 | Recognition of Crimea as part of Ukraine or Russia | delete & make a note for updated version | `(3) Instagram - Google Chrome 10_19_2025 2_29_18 PM.png` |
| 4 | GDP (PPP) per Capita in Europe: 1913 Vs. 1938 | delete & make a new version with current dollars | `(3) Instagram - Google Chrome 10_19_2025 2_29_38 PM.png` |
| 5 | GDP per Capita in Europe: 1913 vs 1938 | delete & make new version with current dollars | `(3) Instagram - Google Chrome 10_19_2025 2_29_44 PM.png` |
| 6 | Cold War Alliances in 1980 | delete & make reviewed version | `(3) Instagram - Google Chrome 10_19_2025 2_35_33 PM.png` |
| 7 | Countries the US is Obliged to go to War for | delete & make current version | `(3) Instagram - Google Chrome 10_19_2025 2_37_59 PM.png` |
| 8 | Largest Trading Partners of European Countries | delete & make new version | `(3) Instagram - Google Chrome 10_19_2025 2_41_14 PM.png` |
| 9 | Countries with Bigger Economy than California | delete & update | `(3) Instagram - Google Chrome 10_19_2025 2_41_26 PM.png` |
| 10 | World Divided Equally by GDP | delete & make new version | `(3) Instagram - Google Chrome 10_19_2025 2_41_37 PM.png` |
| 11 | Countries with lower GDP than Elon Musk's Net Worth | delete & make new version | `(3) Instagram - Google Chrome 10_19_2025 2_42_36 PM.png` |
| 12 | Inflation Rate in European Countries | delete & make new version | `(3) Instagram - Google Chrome 10_19_2025 2_57_16 PM.png` |
| 13 | Number of Nobel Prize Laureates by European Country | delete & make new version | `(3) Instagram - Google Chrome 10_19_2025 2_57_39 PM.png` |

## Change log

- **2026-08-23** — Inventory review opened by Milan. 49 items flagged, sorted into four folders, statuses set to `review` / `update` / `pending-delete` / `pending-delete-remake`. No files deleted. Queued thread 054 held. Active rotation went from 534 to 485 maps.
