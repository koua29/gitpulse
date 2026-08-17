# 📊 GitPulse

Self-hosted GitHub stats for **@koua29** — because GitHub only keeps traffic for **14 days** and has no account-wide dashboard.

A GitHub Action runs once a day, pulls views / unique visitors / clones / referrers / stars / forks / followers for **every repo you own** (public *and* private), and **merges them into history files committed back to this repo** — so the data outlives the 14-day window. A static **GitHub Pages** dashboard charts it all.

**Zero servers, zero cost, runs even when your Mac is off.**

## What you get

- 📈 Unlimited history of views / unique visitors / clones — per repo and aggregated
- ⭐ Stars, forks, followers over time
- 🌍 Top referring sites, popular content
- 🏆 Repos ranked by traffic
- 🖥️ A graphical dashboard on GitHub Pages
- 🔖 A ready-made Markdown badge for your profile README

## How it works

```
cron 06:17 UTC → Action → collect.py → merge into data/ → git commit → Pages refreshes
```

- `collect.py` — the collector (Python **standard library only**, no dependencies)
- `.github/workflows/collect.yml` — the daily schedule + auto-commit
- `data/` — the accumulated history (JSON, versioned by git)
- `docs/` — the GitHub Pages dashboard (static HTML + Chart.js)

## Setup

1. **Create a token** — GitHub → *Settings → Developer settings → Personal access tokens*.
   Traffic data requires push access, so grant the **`repo`** scope (classic PAT) or *Contents: read* + *Administration: read* on a fine-grained token for the repos you want.
2. **Add it as a secret** — this repo → *Settings → Secrets and variables → Actions* → new secret named **`GITPULSE_TOKEN`**.
3. **Enable Pages** — *Settings → Pages* → deploy from branch `main`, folder `/docs`.
4. **Run once** — *Actions → GitPulse collect → Run workflow* to seed the first snapshot.

The dashboard then lives at `https://koua29.github.io/gitpulse/`.

### Run locally (optional)

```bash
export GITHUB_TOKEN=ghp_xxx
python collect.py
```

## License

MIT — see [LICENSE](LICENSE).
