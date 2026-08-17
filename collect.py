#!/usr/bin/env python3
"""GitPulse — daily collector for GitHub traffic & popularity stats.

Runs on GitHub Actions (or locally). Walks every repo owned by the user,
pulls the 14-day traffic windows plus stars/forks/followers, and MERGES
them into per-repo history files so the data outlives GitHub's 14-day cap.
Then writes a single consolidated dashboard.json for the web UI.

Env:
  GITHUB_TOKEN  Personal access token with `repo` scope (traffic needs push).
  GH_USER       Account login (default: koua29).
"""

import os
import sys
import json
import time
import datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

USER = os.environ.get("GH_USER", "koua29")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPODIR = DATA / "repos"
TODAY = dt.date.today().isoformat()


def api(path, params=None):
    """GET a GitHub API path, returning parsed JSON (or None on 404/403)."""
    url = API + path
    if params:
        q = "&".join(f"{k}={v}" for k, v in params.items())
        url += ("&" if "?" in url else "?") + q
    req = Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as r:
                return json.load(r)
        except HTTPError as e:
            if e.code in (403, 404):
                # 403 on traffic = no push access to that repo; skip quietly.
                return None
            if e.code >= 500 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  ! HTTP {e.code} on {path}", file=sys.stderr)
            return None
        except URLError as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  ! {e} on {path}", file=sys.stderr)
            return None
    return None


def list_repos():
    """Public repos owned by USER, paginated.

    Private repos are excluded on purpose: this dashboard is meant to be
    published publicly, so private repo names/traffic must never leak.
    """
    repos, page = [], 1
    while True:
        batch = api("/user/repos", {
            "per_page": 100, "page": page,
            "affiliation": "owner", "visibility": "public",
            "sort": "full_name",
        })
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    # Defensive: never let a private repo through even if the API param slips.
    return [r for r in repos if not r.get("private")]


def load(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def merge_daily(store, items, key_map):
    """Merge a traffic API day-array into a {date: {...}} store.

    Past days are stable so we overwrite; today's partial bucket grows,
    so the latest fetch always wins. No day is ever lost once recorded.
    """
    for d in items or []:
        day = d["timestamp"][:10]
        row = store.setdefault(day, {})
        for src, dst in key_map.items():
            row[dst] = d.get(src, 0)


def collect():
    REPODIR.mkdir(parents=True, exist_ok=True)
    repos = list_repos()
    if not repos:
        print("No repos (bad token?). Aborting.", file=sys.stderr)
        sys.exit(1)
    print(f"{len(repos)} repos for {USER}")

    total_stars = total_forks = 0
    ranking = []

    for repo in repos:
        name = repo["name"]
        rf = REPODIR / f"{name}.json"
        rec = load(rf, {"name": name, "traffic": {}, "snapshots": {},
                        "referrers": [], "paths": []})
        rec["private"] = repo.get("private", False)
        rec["url"] = repo.get("html_url", "")

        views = api(f"/repos/{USER}/{name}/traffic/views")
        clones = api(f"/repos/{USER}/{name}/traffic/clones")
        if views:
            merge_daily(rec["traffic"], views.get("views"),
                        {"count": "views", "uniques": "view_uniques"})
        if clones:
            merge_daily(rec["traffic"], clones.get("clones"),
                        {"count": "clones", "uniques": "clone_uniques"})

        refs = api(f"/repos/{USER}/{name}/traffic/popular/referrers")
        paths = api(f"/repos/{USER}/{name}/traffic/popular/paths")
        rec["referrers"] = refs or []
        rec["paths"] = paths or []

        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        rec["snapshots"][TODAY] = {
            "stars": stars, "forks": forks,
            "watchers": repo.get("subscribers_count", 0),
            "open_issues": repo.get("open_issues_count", 0),
        }
        total_stars += stars
        total_forks += forks

        rf.write_text(json.dumps(rec, indent=1, sort_keys=True))

        recent = sum(v.get("views", 0) for d, v in rec["traffic"].items()
                     if d > (dt.date.today() - dt.timedelta(days=14)).isoformat())
        ranking.append({"name": name, "private": rec["private"],
                        "stars": stars, "forks": forks,
                        "views14": recent, "url": rec["url"]})
        print(f"  ✓ {name}  ★{stars}  views14={recent}")

    # Account-level timeline
    me = api(f"/users/{USER}") or {}
    acct = load(DATA / "account.json", {})
    acct[TODAY] = {
        "followers": me.get("followers", 0),
        "public_repos": me.get("public_repos", 0),
        "total_stars": total_stars,
        "total_forks": total_forks,
    }
    (DATA / "account.json").write_text(json.dumps(acct, indent=1, sort_keys=True))

    build_dashboard(repos, ranking, acct)
    print("done.")


def build_dashboard(repos, ranking, acct):
    """One consolidated JSON so the static dashboard fetches a single file."""
    # Aggregate daily views/clones across all repos.
    agg = {}
    for repo in repos:
        rec = load(REPODIR / f"{repo['name']}.json", None)
        if not rec:
            continue
        for day, v in rec["traffic"].items():
            row = agg.setdefault(day, {"views": 0, "view_uniques": 0,
                                       "clones": 0, "clone_uniques": 0})
            for k in row:
                row[k] += v.get(k, 0)
    series = [{"date": d, **agg[d]} for d in sorted(agg)]

    stars_series = [{"date": d, **acct[d]} for d in sorted(acct)]

    # Global referrers, summed across repos.
    ref_tot = {}
    for repo in repos:
        rec = load(REPODIR / f"{repo['name']}.json", None)
        if not rec:
            continue
        for r in rec.get("referrers", []):
            e = ref_tot.setdefault(r["referrer"], {"count": 0, "uniques": 0})
            e["count"] += r.get("count", 0)
            e["uniques"] += r.get("uniques", 0)
    referrers = sorted(
        ({"referrer": k, **v} for k, v in ref_tot.items()),
        key=lambda x: -x["count"])[:10]

    ranking.sort(key=lambda x: -x["views14"])
    latest = acct[max(acct)] if acct else {}
    dash = {
        "user": USER,
        "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "kpi": {
            "repos": len(repos),
            "views14": sum(r["views14"] for r in ranking),
            "stars": latest.get("total_stars", 0),
            "forks": latest.get("total_forks", 0),
            "followers": latest.get("followers", 0),
        },
        "series": series,
        "stars_series": stars_series,
        "ranking": ranking,
        "referrers": referrers,
    }
    (ROOT / "docs" / "dashboard.json").write_text(json.dumps(dash, indent=1))
    write_readme_badge(dash)


def write_readme_badge(dash):
    """Markdown snippet for a profile README (between BADGE markers)."""
    k = dash["kpi"]
    snippet = (
        f"<!--GITPULSE:START-->\n"
        f"📊 **{k['views14']}** views (14d) · ⭐ **{k['stars']}** stars · "
        f"🍴 **{k['forks']}** forks · 👥 **{k['followers']}** followers · "
        f"across **{k['repos']}** repos — _via [GitPulse](https://github.com/{USER}/gitpulse), "
        f"updated {dash['generated'][:10]}_\n"
        f"<!--GITPULSE:END-->\n"
    )
    (ROOT / "data" / "readme_badge.md").write_text(snippet)


if __name__ == "__main__":
    collect()
