"""Query GitHub Actions for the latest run on main and print its conclusion.

Uses GITHUB_TOKEN from this project's own .env through an Authorization header.
The token is never printed, and the output is limited to workflow name, status,
conclusion, commit and the job log URL.

Usage:
    python scripts/check_ci_status.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

OWNER = "richeroveis"
REPO = "repro-lab"


def token() -> str:
    if not os.path.exists(".env"):
        raise SystemExit(".env missing from this project root")
    with open(".env", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GITHUB_TOKEN missing from .env")


def get(path: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": "Bearer " + token(),
            "Accept": "application/vnd.github+json",
            "User-Agent": "reprolab-ci-check",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


class _StopRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def job_log(job_id: int, tail: int = 60) -> str:
    """Return the last lines of a job log.

    The logs endpoint answers with a redirect to a signed bucket URL, and that
    URL must be requested without the Authorization header, so the redirect is
    captured here and followed by hand.
    """
    opener = urllib.request.build_opener(_StopRedirect)
    req = urllib.request.Request(
        f"https://api.github.com/repos/{OWNER}/{REPO}/actions/jobs/{job_id}/logs",
        headers={"Authorization": "Bearer " + token(), "User-Agent": "reprolab-ci-check"},
    )
    signed = None
    try:
        resp = opener.open(req, timeout=60)
        text = resp.read().decode("utf-8", "replace")
        return "\n".join([line for line in text.splitlines() if line.strip()][-tail:])
    except urllib.error.HTTPError as err:
        if err.code in (301, 302, 303, 307, 308):
            signed = err.headers.get("Location")
        else:
            raise
    plain = urllib.request.Request(signed, headers={"User-Agent": "reprolab-ci-check"})
    with urllib.request.urlopen(plain, timeout=90) as resp:
        text = resp.read().decode("utf-8", "replace")
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-tail:])


def main() -> int:
    runs = get(f"/repos/{OWNER}/{REPO}/actions/runs?per_page=5")
    if not runs.get("workflow_runs"):
        print("no workflow runs yet")
        return 1
    for run in runs["workflow_runs"][:3]:
        print(
            f"{run['name']} | run_number {run['run_number']} | event {run['event']} | "
            f"head_sha {run['head_sha'][:8]} | status {run['status']} | "
            f"conclusion {run['conclusion']}"
        )
    latest = runs["workflow_runs"][0]
    jobs = get(f"/repos/{OWNER}/{REPO}/actions/runs/{latest['id']}/jobs").get("jobs", [])
    for job in jobs:
        print(f"  job {job['name']}: status {job['status']} conclusion {job['conclusion']}")
        for step in job.get("steps", []):
            print(f"    - {step['name']}: {step['conclusion']}")
        if job["conclusion"] not in ("success", None):
            tail = int(os.environ.get("CI_LOG_TAIL", "60"))
            print("  ---- last log lines ----")
            print(job_log(job["id"], tail=tail))
    print("html_url", latest["html_url"])
    return 0 if latest["conclusion"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
