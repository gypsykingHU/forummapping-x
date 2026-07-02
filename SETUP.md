# Forummapping X Automation — Setup (one time, ~15 minutes)

## 1. Create a GitHub account and repo
1. Sign up at https://github.com (free) if you don't have an account.
2. Click **New repository** → name it `forummapping-x` → set it to **Private** → Create.

## 2. Push this folder to the repo
Open Terminal, then run (replace YOURUSERNAME):

```bash
cd "/Users/milanfabian/Projects/Forummapping/x-automation"
git init -b main
git add .
git commit -m "initial: feed poster + content database"
git remote add origin https://github.com/YOURUSERNAME/forummapping-x.git
git push -u origin main
```

GitHub will ask you to sign in the first time (it opens a browser window).
The push uploads ~400 images, so it may take a few minutes.

## 3. Add your X API keys as secrets
In the repo on github.com: **Settings → Secrets and variables → Actions → New repository secret**.

Yes — each one is added individually: click **New repository secret**, enter the name exactly as shown below, paste the matching value, click **Add secret**, then repeat until all four are in (values are in `x_api_credentials.env` in your Forummapping folder):

| Secret name | Value from env file |
|---|---|
| `X_API_KEY` | X_API_KEY |
| `X_API_KEY_SECRET` | X_API_KEY_SECRET |
| `X_ACCESS_TOKEN` | X_ACCESS_TOKEN |
| `X_ACCESS_TOKEN_SECRET` | X_ACCESS_TOKEN_SECRET |

## 4. Test it
1. Repo → **Actions** tab → enable workflows if prompted.
2. Click **Feed poster** → **Run workflow** → tick **Dry run** → Run.
   Green check = credentials and setup work (nothing is posted).
3. Run it again *without* dry run → it posts one real map to @forummapping.

## 5. Done
The schedule takes over automatically: 4 posts/day at ~8am, 12pm, 5pm, 8:30pm US Eastern.
Every post is logged back into `content_database.csv` in the repo.

To pause everything: Actions tab → Feed poster → "…" menu → Disable workflow.
