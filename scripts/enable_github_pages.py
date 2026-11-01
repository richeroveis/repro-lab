"""Enable GitHub Pages for the gh-pages branch of this project's repo.

Reads GITHUB_TOKEN from this project's own .env and never prints it.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request

API = "https://api.github.com/repos/richeroveis/repro-lab/pages"
UA = {"User-Agent": "repro-lab-publish", "Accept": "application/vnd.github+json"}


def token() -> str:
    for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GITHUB_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GITHUB_TOKEN missing")


def headers() -> dict:
    return {**UA, "Authorization": "Bearer " + token()}


def main() -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(API, headers=headers()), timeout=30) as r:
            data = json.loads(r.read())
            print("pages status", r.status, data.get("status"), data.get("html_url"))
            return 0
    except urllib.error.HTTPError as err:
        if err.code != 404:
            print("read failed", err.code)
            return 1
    body = json.dumps({"source": {"branch": "gh-pages", "path": "/"}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            print("created", r.status, data.get("status"), data.get("html_url"))
            return 0
    except urllib.error.HTTPError as err:
        print("create failed", err.code, err.read()[:200].decode("utf-8", "replace"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
