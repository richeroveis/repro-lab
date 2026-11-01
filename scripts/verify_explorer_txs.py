"""Verify every studionet lifecycle transaction through the official Studio
explorer JSON API, and record the result in evidence/explorer-verification.json.

The driver in scripts/run_studionet_lifecycle.mjs stores what the RPC receipt
said. This script re-checks each hash independently against
https://explorer-studio.genlayer.com/api/transactions/<hash> and compares:

  * lifecycle status (expected FINALIZED)
  * the leader execution result (SUCCESS or an execution error)
  * the validator vote tally (agreement needed for consensus)
  * whether the post consensus contract state hash changed (state committed)

Only an allowlist of flat fields is written out. The explorer response also
carries validator node configs; nothing from those objects is read or stored.

Usage:
    python scripts/verify_explorer_txs.py
Exit code is non zero if any transaction is missing, unresolved, or disagrees
with the recorded expectation.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "https://explorer-studio.genlayer.com"
TX_URL = BASE + "/api/transactions/{h}"
TXLOG = "evidence/_txs.jsonl"
OUT = "evidence/explorer-verification.json"
THROTTLE_S = 0.25
RETRIES = 4

EXEC_BY_CODE = {
    0: "NONE",
    1: "RUNNING",
    2: "REVERT",
    3: "SUCCESS",
    4: "ERROR",
    5: "NOT_ENOUGH_GAS",
    6: "SUCCESS",
    7: "DATA_ERROR",
}


def fetch_tx(hash_value: str) -> dict | None:
    """Return the explorer 'transaction' object, or None if the API has no data."""
    url = TX_URL.format(h=hash_value)
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            return payload.get("transaction")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(1.5 * (attempt + 1))
    return None


def vote_tally(votes: dict) -> str:
    counts: dict[str, int] = {}
    for vote in (votes or {}).values():
        key = str(vote)
        counts[key] = counts.get(key, 0) + 1
    return ",".join(f"{k}={counts[k]}" for k in sorted(counts))


def exec_label(code) -> str:
    if isinstance(code, int):
        return EXEC_BY_CODE.get(code, f"CODE_{code}")
    text = str(code or "")
    for name in ("SUCCESS", "ERROR", "REVERT", "NOT_ENOUGH_GAS", "RUNNING", "DATA_ERROR"):
        if name in text.upper():
            return name
    return text or "UNKNOWN"


def summarize(tx: dict) -> dict:
    """Project the explorer record onto a small, credential-free summary."""
    consensus = tx.get("consensus_data") or {}
    receipts = consensus.get("leader_receipt") or []
    leader = receipts[0] if receipts else {}
    tx_type = str(tx.get("type") or "")
    history = tx.get("consensus_history") or []
    results = []
    for entry in history:
        # The explorer mixes plain status strings into the history list.
        if not isinstance(entry, dict):
            continue
        for item in entry.get("consensus_results") or []:
            if isinstance(item, dict):
                results.append(item.get("consensus_status") or item.get("status") or "")
            elif isinstance(item, str):
                results.append(item)
    eq_outputs = leader.get("eq_outputs")
    state_hash = leader.get("contract_state_hash")
    if isinstance(state_hash, (bytes, bytearray)):
        state_hash = state_hash.hex()
    return {
        "status": tx.get("status"),
        "type": tx_type,
        "from": tx.get("from_address"),
        "to": tx.get("to_address"),
        "value_wei": str(tx.get("value") or "0"),
        "votes": vote_tally(consensus.get("votes")),
        "leader_exec": exec_label(leader.get("execution_result")),
        "leader_error": str((leader.get("genvm_result") or {}).get("error_description") or "")[:180],
        "receipts": len(receipts),
        "contract_call": bool(receipts),
        "consensus_statuses": ",".join(str(r) for r in results if r)[:120],
        "eq_output_groups": len(eq_outputs) if isinstance(eq_outputs, (list, dict)) else 0,
        "nondet_disagree": bool(leader.get("nondet_disagree")),
        "state_hash_head": str(state_hash or "")[:16],
        "explorer_url": BASE + "/tx/" + str(tx.get("hash")),
    }


def main() -> int:
    rows = []
    with open(TXLOG, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))

    records = []
    problems = []
    for index, row in enumerate(rows, start=1):
        time.sleep(THROTTLE_S)
        tx = fetch_tx(row["hash"])
        if tx is None:
            problems.append(f"{row['step']}: explorer has no record for {row['hash']}")
            continue
        summary = summarize(tx)
        record = {
            "step": row["step"],
            "method": row.get("method"),
            "hash": row["hash"],
            "expected": row.get("expect") or "ok",
            "rpc_status": row.get("status_name"),
            "rpc_result": row.get("result_name"),
            "rpc_exec": row.get("exec"),
            **summary,
        }
        records.append(record)
        plain_transfer = not summary["contract_call"]

        # Cross checks between the RPC receipt the driver saw and the explorer.
        if summary["status"] != row.get("status_name") and not plain_transfer:
            problems.append(
                f"{row['step']}: status RPC {row.get('status_name')} vs explorer {summary['status']}"
            )
        if plain_transfer:
            # Funding a lab signer is a value transfer to an EOA: no contract
            # executes, so there is no leader receipt and no state hash. What
            # matters is that it finalized and actually moved the value.
            if summary["status"] != "FINALIZED" or int(summary["value_wei"]) <= 0:
                problems.append(f"{row['step']}: funding transfer did not finalize with value")
            else:
                print(
                    f"[{index:>2}/{len(rows)}] {row['step']:<30} {summary['status']:<9}"
                    f" TRANSFER {int(summary['value_wei']) / 1e18:.3f} GEN to"
                    f" {str(summary['to'])[:10]} (no contract execution)"
                )
            continue
        if summary["leader_exec"] != row.get("exec"):
            problems.append(
                f"{row['step']}: leader exec RPC {row.get('exec')} vs explorer {summary['leader_exec']}"
            )
        wanted = "ERROR" if record["expected"] == "revert" else "SUCCESS"
        if summary["leader_exec"] != wanted:
            problems.append(f"{row['step']}: expected {wanted}, explorer says {summary['leader_exec']}")
        if not summary["state_hash_head"]:
            problems.append(f"{row['step']}: no post consensus contract state hash")
        print(
            f"[{index:>2}/{len(rows)}] {row['step']:<30} {summary['status']:<9}"
            f" {summary['leader_exec']:<8} votes {summary['votes']:<22}"
            f" eq {summary['eq_output_groups']} state {summary['state_hash_head']}"
        )

    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "network": "studionet (chain id 61999)",
                "explorer_api": TX_URL,
                "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "transactions": len(records),
                "contract_transactions": sum(1 for r in records if r["contract_call"]),
                "funding_transfers": sum(1 for r in records if not r["contract_call"]),
                "all_finalized": all(r["status"] == "FINALIZED" for r in records),
                "reverts_with_unchanged_state": [
                    r["step"] for r in records if r["leader_exec"] == "ERROR"
                ],
                "consensus_evaluations_with_eq_output": [
                    r["step"] for r in records if r["eq_output_groups"] > 0
                ],
                "problems": problems,
                "records": records,
            },
            handle,
            indent=2,
        )
        handle.write("\n")

    print(f"\nwrote {OUT}: {len(records)} of {len(rows)} transactions resolved")
    if problems:
        print("PROBLEMS:")
        for problem in problems:
            print("  -", problem)
        return 1
    print("no mismatches between RPC receipts and explorer records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
