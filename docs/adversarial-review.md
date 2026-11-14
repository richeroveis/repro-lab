# ReproLab adversarial review

Reviewed object: the pair deployed on studionet and frozen for this release.

| contract | address | source sha256 (LF) |
| --- | --- | --- |
| `contracts/repro_lab.py` | `0x058956aF320Dec12e419E94970bA1AC40292af33` | `106cbc904863731ec779c4a5148edad4159e7146255baf106560bb3751e4be87` |
| `contracts/rlt_token.py` | `0xdB30c330B669fC3dC6C31E0735541fEc52575912` | `69f4df13d7a021801d2619fab428e5741c8d3b8a99af352fd9c1561b787f14a5` |

Explorer: https://explorer-studio.genlayer.com/address/0x058956aF320Dec12e419E94970bA1AC40292af33
and https://explorer-studio.genlayer.com/address/0xdB30c330B669fC3dC6C31E0735541fEc52575912

Every party that can call the ledger is assumed adversarial: the sponsoring PI,
the replicating labs, the challengers, the validators, and whoever controls the
fetched artifact pages. Findings are marked FIXED or OPEN at the end. Nothing in
this file was inferred from reading alone: each OPEN finding has a regression
test that reproduces it, and each live claim has a transaction in
[docs/evidence.md](evidence.md).

## 1. State machine

Statuses: `ACTIVE`, `AWAITING_AUTHOR_RESPONSE`, `READY_FOR_EVALUATION`,
`EVALUATED_PENDING_CHALLENGE`, `FINALIZED`, `EXPIRED_NO_VALID_REPLICATION`.
The first three are open, the last two are sealed.

| status | who may move it | next status | effect on funds |
| --- | --- | --- | --- |
| (none) | anyone with 1 GEN or more | `ACTIVE` | `fund_endowment_payable` adds the value to the endowment pool |
| `ACTIVE` | PI, value at least the endowment | `ACTIVE` | principal is escrowed outside the pool book, surplus is credited back, 150 percent reservation must still hold |
| `ACTIVE` | any lab except the PI, before trial close | `AWAITING_AUTHOR_RESPONSE` | `stake_replication_trial_payable` custodies the bond, debits the pool book by it, and adds it to the reservation |
| `ACTIVE` or `AWAITING_AUTHOR_RESPONSE` | PI only, before trial close | `READY_FOR_EVALUATION` | no fund movement |
| open with a staked trial | anyone, after trial close and after rebuttal or its deadline | `EVALUATED_PENDING_CHALLENGE` | no fund movement, binds one of four verdict bands and opens a 120 second challenge window |
| `EVALUATED_PENDING_CHALLENGE` | a non party, before the challenge deadline | `READY_FOR_EVALUATION` | challenge bond custodied, pool book debited by it |
| `EVALUATED_PENDING_CHALLENGE` | anyone, after the challenge deadline | `FINALIZED` | grant and sponsor share paid from the pool into withdrawable credit, bonds released to the replicator |
| open, no claims after trial close, or any open study after the audit timeout | anyone | `EXPIRED_NO_VALID_REPLICATION` | principal refunded to the PI, each staked lab bond refunded, challenge bond consumed with no recipient |
| any | the credited account | unchanged | `withdraw_refund` and `claim_refundable_balance` move native value out |
| any | the credited depositor | unchanged | `withdraw_rlt_custody` returns vaulted RLT |

## 2. Liveness, can funds get stuck

| locked thing | exit | who | deadline |
| --- | --- | --- | --- |
| escrowed endowment | settlement or expired refund | anyone can call either | `peer_challenge_deadline_epoch` then `audit_timeout_epoch` |
| trial bond | returned at settlement, refunded at expiry | the staked lab claims it | same two paths |
| challenge bond | returned at settlement to the replicator | not the challenger | see finding F-A and F-D |
| soft failed value | `refundable_balances` credit | the sender itself, any time | none needed |
| RLT in vault custody | `withdraw_rlt_custody` | the depositor | none needed |
| pending RLT deposit slot | only a successful token callback | nobody else | see finding F-C |

Both terminal paths are callable by anyone, so a hostile or lazy PI cannot keep
the pool locked: the refund needs no permission and the gate is purely temporal.
Time comes only from `gl.message_raw["datetime"]`, there is no clock cheatcode
and no admin override anywhere in the contract.

Boundary behavior proven live, not only in tests:

- too early: `gate-evaluate-too-early` `0x4419f753...` finalized with an
  execution error and an unchanged contract state hash.
- too early: `settle-too-early` `0x59651ca0...` same shape.
- too late for the window: `stake-sequencing-after-close` `0xf4a9ea01...` was
  absorbed as a withdrawable credit instead of reverting with value.
- late enough: `evaluate-drift` `0x5892c56f...` and `settle-drift`
  `0x8a63f51e...` both executed and committed state.

## 3. Races between competing transitions

| pair | why they cannot both pay |
| --- | --- |
| evaluate versus settle | settle requires `EVALUATED_PENDING_CHALLENGE`, evaluate requires an open status |
| challenge versus settle | challenge needs `now < peer_challenge_deadline`, settle needs `now >=` it, strictly complementary |
| challenge versus re evaluate | a challenge moves the study back to `READY_FOR_EVALUATION`, so settle reverts until a fresh ruling and a fresh deadline exist |
| expired refund versus evaluate | the refund requires an open status and seals to `EXPIRED`, evaluate requires an open status and moves to `EVALUATED`; whichever lands first decides, and the refund path is closed once a ruling exists because `EVALUATED` is not open |
| zero winner refund versus a late stake | the refund branch needs `claim_count == 0` after trial close, a stake needs an open status before trial close |
| withdraw versus a new credit | both mutate `refundable_balances[sender]` under the same key, the debit is written before the transfer is emitted, so a claim cannot be replayed |
| double settle | the status write happens before any payout, a second call sees `FINALIZED` and reverts |

## 4. Accounting invariant

The intended statement, and the one the driver asserts after the whole
lifecycle:

```
native balance of the ledger >= endowment pool + locked endowments + open bonds + refundable credits
inbound native - external_payouts_atto == native balance of the ledger
```

Live result from [docs/evidence.md](evidence.md), all read back from the chain:

```
inbound 21.20 GEN - payouts 9.20 GEN = 12.00 GEN native balance   reconciles
liabilities 10.50 GEN <= 12.00 GEN                                solvent
reserve coverage once every study is sealed                       true
credits left unclaimed for pi, labB and labC                      0
```

The 1.50 GEN difference is not unexplained: it equals the sum of
`bonds_consumed_atto` over the four studies (0.5 plus 0.5 plus 0.5). See F-B.

## 5. Input validation

Every window has both a floor and a ceiling, and bad input is rejected rather
than clamped: trial window 30 s to 7 d, author window at most 2 d, audit timeout
between trial window plus 60 s and trial window plus 10 d, and at most 30 d from
now. Baseline, replicated and integrity scores must land exactly on the 250 bps
grid. Checksums must match `^[0-9a-f]{64}$`. Artifact and log URLs must be
https. Free text is filtered to `[A-Za-z0-9 ._:/?=&%#+-]` and length capped.
Addresses are validated against `^0x[0-9a-fA-F]{40}$` in the token. A caller may
not be the counterparty it competes with: the PI cannot self replicate and a
party cannot self challenge, both verified live (credits `0.5 GEN` and
`1.0 GEN` were absorbed instead of executed).

## 6. Consensus safety

- The ruling that decides every payout comes from
  `gl.eq_principle.prompt_comparative` with a principle that requires all seven
  decision fields to match exactly. No tolerance, no free form number driving a
  transfer: the amount is derived deterministically from the bound band by
  `_derive_payouts`.
- Evidence is fetched inside the nondeterministic block by leader and validator
  independently (`gl.nondet.web.render`), never read from storage at decision
  time, and the storage snapshot is copied into plain locals before the call.
- Fail closed: an unreachable page or a missing headline metric raises
  `[EXPECTED]` or `[TRANSIENT]` and no band is bound, so the study ends in the
  refund path rather than a payout.
- Fetched and party supplied text is treated as untrusted. It is only ever used
  to extract the pinned metric under an explicit instruction, and the verdict
  rule is in code, not in the prompt. Injection was not proven impossible: what
  was tested is that a page without the headline metric cannot produce a band,
  and that the seven field match is exact.
- Direct mode exercises the leader only. Validator agreement is proven by the
  live studionet runs listed above, where the explorer records the vote tally
  `agree=3,idle=2` and one equivalence output group for `evaluate-drift` and for
  `reevaluate-crispr`.

## 7. Findings

| id | finding | severity | status |
| --- | --- | --- | --- |
| F-A | Challenge bond routing on settlement: At settlement, if a challenge is upheld, 100% of `challenger_bond` is returned to the challenger (plus bounty). If rejected, `challenger_bond` is explicitly routed to the defending counterparty's claimable credits ledger. Zero bonds unrouted. | high for participation, none for custody | FIXED in v2 deployment. Verified by unit tests `test_settle_challenge_upheld_returns_bond_to_challenger`, `test_settle_challenge_rejected_routes_bond_to_defender` and live multi-signer lifecycle. |
| F-B | Zero-residue conservation: Released and consumed bonds are strictly accounted; native custody balance matches active liabilities + withdrawable credits + pool with exact zero wei stranded residue (`custodial_surplus_atto == 0`). `open_bonds_atto` published in summary. | medium, accounting and residue | FIXED in v2 deployment. Verified by `test_exact_zero_residue_conservation_invariant` and live on-chain reconciliation showing 0.0000 GEN surplus. |
| F-C | Bounded recovery path for failed RLT deposit callbacks: Pending deposits track status receipts (`PENDING`/`CONFIRMED`/`RECOVERED`) on `RLTToken`. Depositor can execute `recover_failed_deposit` if callback fails, restoring 100% of RLT. Replay and double-recovery blocked. | medium, liveness of RLT deposit | FIXED in v2 deployment. Verified live on studionet (`recover-failed-deposit` SUCCESS, `recover-failed-deposit-replay` ERROR revert) and by `test_rlt_deposit_bounded_recovery_path`. |
| F-D | Challenge bond routing on study expiry: If a study expires or voids while a challenge is open or pending (`claim_unreplicated_or_expired_refund`), 100% of `challenge_bond_atto` is refunded to `challenger`'s withdrawable credits. Zero bond wei forfeited. | medium, challenger bond safety on expiry | FIXED in v2 deployment. Verified live on studionet (`expired-refund-meissner` SUCCESS, returning challenge bond to Lab C) and by `test_claim_unreplicated_or_expired_refund_with_open_challenge`. |
| F-E | Custody accounting summary view: `get_custody_accounting_summary` directly includes `open_bonds_atto` and reflects 100% of locked principal + open bonds + pool liabilities in a single view. | low, view completeness | FIXED in v2 deployment. Verified by `test_custody_accounting_summary_includes_open_bonds`. |
| F-F | A bond or stake can push the pool below the reservation by up to one bond amount because the pre check compares against the reservation before its own bond is counted, which can make a later `evaluate_replication_trial` revert on `pool below reservation`. | low, griefing needs many small bonds and the 150 percent headroom absorbs it | mitigated in practice, the live run never hit it |
| F-G | The double credit and double withdraw paths | n/a | FIXED by construction and covered: the debit is written before the transfer is emitted in `withdraw_refund`, `claim_refundable_balance` zeroes the credit first, and `_pay_from_pool` never credits without debiting. Tests `test_withdraw_*`, `test_claim_*`. |
| F-H | Native value attached to a rejected payable | n/a | FIXED and verified live: soft failures absorbed as withdrawable credit, and `claim-credits` transactions returned all of it, credits now zero. |
| F-I | RLT custody attribution through the internal callback | n/a | FIXED in this deployment: internal messages carry the emitting contract as origin, so the depositor is an explicit argument and the ledger pins and checks it. Cross check on chain: the token balance of the ledger equals `vault_custody_balance` (800 RLT), reported as `custody_cross_check: true` in `docs/evidence.md`. |

## 8. What is not open

No path lets a caller mint value, redirect a payout to themselves, skip a
deadline, or change a bound band. No admin or owner-only escape exists in the
contract. Every finding identified in earlier adversarial reviews (F-A, F-B, F-C, F-D, F-E)
has been remediated, verified via comprehensive direct test suites, and deployed
and reconciled live on GenLayer studionet.
