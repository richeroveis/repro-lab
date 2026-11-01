"""Check that the published GitHub Pages notebook really serves every asset.

Compares each live response against the local build where the file exists, so a
stale gh-pages branch is caught instead of trusted.

Usage:
    python scripts/verify_published_site.py
"""

from __future__ import annotations

import hashlib
import os
import urllib.request

BASE = "https://richeroveis.github.io/repro-lab/"
PATHS = [
    "",
    "logo.png",
    "demo-video-subtitled.mp4",
    "snapshot.json",
    "consensus-proof.json",
    "custody-reconciliation.json",
    "study-meta.json",
    "artifacts/drift-artifact.html",
    "artifacts/drift-log.html",
    "artifacts/crispr-artifact.html",
    "artifacts/crispr-log.html",
    "artifacts/meissner-artifact.html",
    "artifacts/meissner-log.html",
    "artifacts/sequencing-artifact.html",
]
LOCAL = {
    "": "frontend/dist/index.html",
    "logo.png": "frontend/public/logo.png",
    "demo-video-subtitled.mp4": "frontend/public/demo-video-subtitled.mp4",
    "snapshot.json": "frontend/public/snapshot.json",
    "consensus-proof.json": "frontend/public/consensus-proof.json",
    "custody-reconciliation.json": "frontend/public/custody-reconciliation.json",
    "study-meta.json": "frontend/public/study-meta.json",
}


def fetch(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, resp.read()


def main() -> int:
    failures = []
    for path in PATHS:
        url = BASE + path
        try:
            status, body = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {path or 'index.html'}: {type(exc).__name__} {str(exc)[:80]}")
            failures.append(path)
            continue
        local = LOCAL.get(path)
        if local is None and path.startswith("artifacts/"):
            local = "frontend/public/" + path
        note = ""
        if local and os.path.exists(local):
            with open(local, "rb") as handle:
                want = hashlib.sha256(handle.read()).hexdigest()
            got = hashlib.sha256(body).hexdigest()
            note = "sha256 matches local" if want == got else "DIFFERS FROM LOCAL"
            if want != got:
                failures.append(path)
        else:
            failures.append(path)
        print(f"{status} {len(body):>9} bytes  {(path or 'index.html'):<34} {note}")
    if failures:
        print("FAILED paths:", failures)
        return 1
    print(f"all {len(PATHS)} published paths serve 200 and match the local build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
