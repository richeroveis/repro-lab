"""Derive the account address from this project's own .env key.

Prints only the public address, never the key.
"""

import pathlib
import sys

from eth_account import Account


def load_env(path: pathlib.Path) -> dict:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def main() -> int:
    env = load_env(pathlib.Path(".env"))
    key = env.get("GENLAYER_PRIVATE_KEY", "")
    if not key:
        print("MISSING GENLAYER_PRIVATE_KEY")
        return 1
    if not key.startswith("0x"):
        key = "0x" + key
    address = Account.from_key(key).address
    print("ADDRESS", address.lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
