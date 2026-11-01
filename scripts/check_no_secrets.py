"""Pre commit gate: prove that no credential from .env exists in any git blob.

Reads this project's own .env, takes every value that looks like a secret, and
searches the staged tree and the full commit history for those exact bytes. It
prints only which file matched and which key name it was, never the value.

Usage:
    python scripts/check_no_secrets.py            # staged tree and history
    python scripts/check_no_secrets.py --staged   # staged tree only
"""

from __future__ import annotations

import os
import subprocess
import sys

SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "MNEMONIC")
MIN_LENGTH = 12


def env_values() -> dict[str, str]:
    if not os.path.exists(".env"):
        return {}
    out = {}
    with open(".env", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if name.upper().endswith("_PATH") or len(value) < MIN_LENGTH:
                continue
            if any(hint in name.upper() for hint in SECRET_HINTS):
                out[name] = value
    return out


def git(*args: str) -> str:
    res = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {res.stderr.strip()[:200]}")
    return res.stdout


def main() -> int:
    secrets = env_values()
    if not secrets:
        print("no secret shaped keys found in .env, nothing to check")
        return 0
    print(f"checking {len(secrets)} secret names from .env")

    staged = git("ls-files", "-s", "--cached").splitlines()
    history = git("rev-list", "--all").split() if "--staged" not in sys.argv else []

    hits = []
    for line in staged:
        parts = line.split()
        sha, path = parts[1], parts[-1]
        content = subprocess.run(["git", "cat-file", "blob", sha], capture_output=True)
        for name, value in secrets.items():
            if value.encode("utf-8") in content.stdout:
                hits.append(("staged", path, name))

    for commit in history:
        listing = git("ls-tree", "-r", commit).splitlines()
        for entry in listing:
            meta, path = entry.split("\t", 1)
            sha = meta.split()[2]
            content = subprocess.run(["git", "cat-file", "blob", sha], capture_output=True)
            for name, value in secrets.items():
                if value.encode("utf-8") in content.stdout:
                    hits.append((commit[:8], path, name))

    if hits:
        print("FAILED: secret material present in git content")
        for where, path, name in hits[:20]:
            print(f"  {where} {path} contains {name}")
        return 1
    print(f"clean: {len(staged)} staged files and {len(history)} commits contain no .env secret")
    ignored = git("check-ignore", "-v", ".env").strip()
    print(f".env ignore rule: {ignored or 'NOT IGNORED'}")
    return 0 if ignored else 1


if __name__ == "__main__":
    raise SystemExit(main())
