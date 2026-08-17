#!/usr/bin/env python3
"""Inject the freshly-generated GitPulse badge into the profile README.

Runs after collect.py in the daily Action. Uses the GitHub Contents API to
read koua29/koua29's README.md, replace the text between the GITPULSE
markers with data/readme_badge.md, and commit it back — no second checkout.

Env:
  GITHUB_TOKEN  PAT with `repo` scope (same secret as the collector).
  GH_USER       Account login (default: koua29). The profile repo is
                assumed to be {USER}/{USER}.
"""

import os
import sys
import json
import base64
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

USER = os.environ.get("GH_USER", "koua29")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = f"{USER}/{USER}"
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent
START, END = "<!--GITPULSE:START-->", "<!--GITPULSE:END-->"


def gh(method, path, payload=None):
    req = Request(API + path, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, data, timeout=30) as r:
        return json.load(r)


def main():
    if not TOKEN:
        print("No token; skipping profile update.", file=sys.stderr)
        return
    badge = (ROOT / "data" / "readme_badge.md").read_text().strip()

    try:
        cur = gh("GET", f"/repos/{REPO}/contents/README.md")
    except HTTPError as e:
        print(f"Profile README not found ({e.code}); skipping.", file=sys.stderr)
        return

    sha = cur["sha"]
    readme = base64.b64decode(cur["content"]).decode()

    if START in readme and END in readme:
        pre = readme[:readme.index(START)]
        post = readme[readme.index(END) + len(END):]
        new = pre + badge + post
    else:
        # No markers yet: append the badge block at the end.
        new = readme.rstrip() + "\n\n" + badge + "\n"

    if new == readme:
        print("Profile badge already up to date.")
        return

    gh("PUT", f"/repos/{REPO}/contents/README.md", {
        "message": "chore: refresh GitPulse badge",
        "content": base64.b64encode(new.encode()).decode(),
        "sha": sha,
        "committer": {
            "name": USER,
            "email": "24193002+koua29@users.noreply.github.com",
        },
    })
    print("Profile badge updated.")


if __name__ == "__main__":
    main()
