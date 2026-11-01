# cron-job.org setup (replaces GitHub's unreliable scheduler)

Why: GitHub drops many scheduled runs (about 4 of 12 map slots/day got through). cron-job.org calls
GitHub's API at the exact time and starts the same workflows on demand. Cost: $0.

## Step 1: GitHub token (you create it, ~2 min)
GitHub > Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token
- Name: cron-job-forummapping
- Expiration: 1 year (set a calendar reminder to renew)
- Repository access: Only select repositories > gypsykingHU/forummapping-x
- Permissions > Repository permissions > **Actions: Read and write** (nothing else needed)
- Copy the token (shown once). Never paste it in chat or commit it.

## Step 2: cron-job.org account (you create it)
https://console.cron-job.org/signup, then Settings > set **Timezone = UTC** so the times below match.

## Step 3: create 4 jobs (same settings except URL and schedule)
Common to all jobs (Advanced tab):
- Request method: **POST**
- Request body: `{"ref":"main"}`
- Headers:
  - `Authorization: Bearer <YOUR TOKEN>`
  - `Accept: application/vnd.github+json`
  - `X-GitHub-Api-Version: 2022-11-28`
  - `Content-Type: application/json`
- Expected success: HTTP **204**
- Enable "notify me on failure"

| Job title | URL (POST) | Schedule (UTC) |
|---|---|---|
| Maps | https://api.github.com/repos/gypsykingHU/forummapping-x/actions/workflows/feed-poster.yml/dispatches | Custom: minute 7, hours 0,2,4,6,8,10,12,14,16,18,20,22, every day |
| Facts | https://api.github.com/repos/gypsykingHU/forummapping-x/actions/workflows/hourly-pulse.yml/dispatches | Custom: minute 7, hours 1,3,5,7,9,11,13,15,17,19,21,23, every day |
| Threads | https://api.github.com/repos/gypsykingHU/forummapping-x/actions/workflows/thread-poster.yml/dispatches | Custom: minute 30, hours 7 and 18, every day (08:30 / 19:30 CET) |

That is 3 jobs (threads is one job with two hours). Use "Test run" on each once; expect 204, then check the Actions tab.
Because cron-job.org has a timezone option, you can instead set the account timezone to Europe/Budapest and enter threads as 08:30 and 19:30 so daylight saving is followed automatically (shift the other hours accordingly).

## Step 4: after the first on-time runs succeed, tell Claude
Claude then removes the `schedule:` lines from the three workflows. Leaving both on would double-post at random extra times
(the repeat-protection stops the same map twice in a row, but not extra posts), so GitHub's own cron should not run in parallel.

---
## Status (2026-11-01): jobs created in cron-job.org by Claude
Three jobs exist, timezone **Europe/Brussels** (follows CET/CEST automatically):
- Maps: `7 */2 * * *` (even Brussels hours) -> feed-poster.yml
- Facts: `7 1,3,5,...,23 * * *` (odd Brussels hours) -> hourly-pulse.yml
- Threads: `30 8,19 * * *` (08:30 and 19:30 Brussels) -> thread-poster.yml

Remaining manual step: in each of the 3 jobs, Advanced tab > Headers > Authorization, replace
`Bearer PASTE_YOUR_GITHUB_TOKEN_HERE` with `Bearer <your token>`, Save, then Test run (expect HTTP 204).
