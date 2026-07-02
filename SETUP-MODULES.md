# New Modules — Setup (~10 minutes)

You now have 5 automations. The feed poster is already live; here's how to switch on the rest.

| Module | Schedule | Needs |
|---|---|---|
| Feed poster | 4×/day | ✅ already running |
| Thread poster | Tue + Fri 1pm ET | nothing new |
| Newsletter | every 3 days | Buttondown API key |
| Engagement (5 comments / 10 follows) | daily ~10am ET | nothing new |
| Weekly report | Sunday | nothing new |

## 1. Push the new files
Open **GitHub Desktop** — it will show all the new files (scripts, workflows, threads, articles).
Type a summary like "add all modules" → **Commit to main** → **Push origin**.

## 2. Create the newsletter account (5 min)
1. Sign up free at https://buttondown.com — pick the username **forummapping**
   (your newsletter address becomes forummapping@buttondown.email).
2. In Buttondown: **Settings → API** → copy your API key.
3. In your GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `BUTTONDOWN_API_KEY`
   - Value: the key you copied
4. Put the newsletter signup link (https://buttondown.com/forummapping) in your X bio.

## 3. Test each module (dry runs — nothing is posted)
Repo → **Actions** tab, then for each of **Thread poster**, **Newsletter**, **Engagement**:
**Run workflow** → tick **Dry run** → Run → wait for the green check and read the log to see what it *would* do.

The **Weekly report** has no dry run (it only reads data) — just run it once to get your first report in the `reports/` folder.

## 4. Go live
Nothing else to do — the schedules take over. First real thread goes out next Tuesday or Friday, first newsletter on the next day-of-month divisible by 3, engagement starts tomorrow morning.

## Content queues — important
Threads and newsletter articles are **pre-written and stored in the repo**:
- `threads/queue/` — 4 threads loaded (2 weeks of Tue/Fri)
- `newsletter/queue/` — 3 articles loaded (9 days)

When a queue runs empty the workflow just logs "queue empty" and skips — nothing breaks.
Ask Claude to write the next batch anytime; review the files before pushing if you want editorial control.

## Safety valves
- Pause any module: Actions → workflow name → "…" menu → **Disable workflow**
- Engagement caps are hard-coded: 5 comments, 10 follows max per day, verified accounts prioritized, and comments only happen when a genuinely relevant map matches the conversation — some days it will do fewer, which is good.
- If X ever sends an automation warning: disable Engagement immediately and tell Claude — the module can be switched to draft-and-approve mode.
