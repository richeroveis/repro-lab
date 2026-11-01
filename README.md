# ReproLab

Empirical replication notebook and peer review ledger on GenLayer studionet.

A principal investigator locks an endowment against a published study. Independent
labs post a bond to attempt a replication. GenLayer validators fetch the study
artifact and the replication log themselves, agree on one of four verdict bands
with an exact seven field match, and only then does money move. Nothing about a
payout can be decided by the contract owner, because there is no owner privileged
path in the contract.

Live site: https://richeroveis.github.io/repro-lab/

| thing | value |
| --- | --- |
| Ledger contract | `0xdC4D683437C797438b0F96bA526101286111d9eB` |
| Ledger on explorer | https://explorer-studio.genlayer.com/address/0xdC4D683437C797438b0F96bA526101286111d9eB |
| RLT endowment token | `0xbc813AF4E82072b063e5a925FdFAdf721a62800e` |
| RLT on explorer | https://explorer-studio.genlayer.com/address/0xbc813AF4E82072b063e5a925FdFAdf721a62800e |
| Network | studionet, chain id 61999, gasless |
| Runner | pinned `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |
| Evidence | [docs/evidence.md](docs/evidence.md), 37 transactions, all explorer verified |
| Security review | [docs/adversarial-review.md](docs/adversarial-review.md) |
| Deployment guide | [docs/deployment.md](docs/deployment.md) |
| Demo brief | [docs/demo-video-subtitled.mp4](docs/demo-video-subtitled.mp4), 50 s, subtitled, with audio |

### Deployment provenance

The deployed pair is frozen. It came from this commit and nothing in it changed
afterwards, which is what the four way identity check proves.

| item | value |
| --- | --- |
| Deployed source commit | `5413ae6de3662a8d3849c8727d2e06a6fc387976` |
| Release tag | `studionet-v1` at the final `main` HEAD; the contract files there are byte identical to the deployed source |
| Ledger deploy tx | `0xd578c7c292c9f4e190c89f75498376c31caa1dd71027841310737c541f0faf15`, FINALIZED, MAJORITY_AGREE, leader SUCCESS |
| RLT deploy tx | `0x72361c8eda984a9b53c8c1434d72c69ae04b4adc6d40a669b29b73fe110ea8ca`, FINALIZED, MAJORITY_AGREE, leader SUCCESS |
| `contracts/repro_lab.py` sha256 | `aae87959b8da96073cebfb0bb888da0299e1f05daa05864547dd52b1673a6a65`, 37,497 bytes |
| `contracts/rlt_token.py` sha256 | `9fc8b49f3b9ed0493d390018908cc6f36959a12f2e0cd471eb31fee5368aa7d7`, 4,173 bytes |

Reproduce with `node scripts/verify_source_identity.mjs all`, which requires the
local file, the git blob, the GitHub raw file and the code the network returns for
the deployed address to hash identically. Current result: `fourWayIdentical: true`
for both contracts, recorded in `evidence/identity.txt`.

## Where the boundary sits

**Frontend owns:** the notebook UI, the burner lab wallet, the workbench that
previews a band before a lab spends a bond, and the countdowns. It never computes
a result that moves money.

**GenLayer contract owns:** the escrow and bond custody, the 150 percent
reservation, the temporal gates, the independent fetch of artifact and log, the
band binding under `prompt_comparative` with an exact seven field match, the
payout derivation from the bound band, and every refund and appeal path.

**External sources own:** the raw numbers. A study artifact is only trusted
because leader and validator each fetch it again and must agree, not because the
contract read it once. The artifact pages used by the live run are published in
this repository under `frontend/public/artifacts/` so any validator can reach
them.

## The three modules of the notebook

1. **Empirical Study Registry and Endowment Custody Vault.** The four studies
   that were registered live, their endowments, the pool, the RLT custody figure,
   the reservation state, and the refund drawer that shows any soft failed
   payable as withdrawable credit.
2. **Statistical Convergence and Effect Size Deviation Matrix.** Baseline,
   replicated and integrity scores drawn on the same 250 basis point grid the
   contract quantizes onto, with the bound band and the payout split it implies.
   The workbench side lets you move a claim and see which band would bind before
   a bond is spent.
3. **Peer Review Equivalence Transcript and Protocol Safeguard Drawer.** The
   validator vote tally for the live evaluation, the seven decision fields that
   had to match, the challenge and re evaluation history, and the countdowns for
   trial close, rebuttal, audit timeout and the peer challenge window.

The page issues three read calls on first load (`get_lab_overview`,
`get_reproducibility_index`, `get_custody_accounting_summary`), which is inside the
four call budget, then two more when a study is selected (`get_study_card` and
`get_trial_book`). Selecting a study is a user action, not part of the first
paint. The studionet RPC does not send CORS headers, so a page served from GitHub
Pages falls back to `frontend/public/snapshot.json`, which the driver regenerates
from chain after every run. The UI always stamps which mode it is in, live read or
published snapshot.

## Lifecycle, as it ran on chain

```
fund pool        ->  register 4 studies   ->  labs stake bonds
->  trial close  ->  validator consensus evaluation (live fetch, exact match)
->  peer challenge window  ->  settle grant or re evaluate after a challenge
->  zero winner refund, expired refund  ->  credit claims and withdrawals
->  custody invariant read back
```

Every step is a transaction with a hash, a status, a consensus result and a
leader execution result in [docs/evidence.md](docs/evidence.md). The failing side
of each gate was run too: evaluating before trial close, settling before the
challenge deadline, a PI self replication, a duplicate lab, a late stake and a
party self challenge.

## Running the code

```bash
genvm-lint check contracts/repro_lab.py
genvm-lint check contracts/rlt_token.py
python -m pytest tests/ -q
node scripts/run_studionet_lifecycle.mjs deploy
node scripts/run_studionet_lifecycle.mjs verify,report
python scripts/verify_explorer_txs.py
node scripts/verify_source_identity.mjs all
python scripts/verify_published_site.py
python scripts/check_no_secrets.py
```

GitHub Actions runs the runner pin check, the 37,500 byte budget, the LF check and
the direct mode suite on every push that touches `contracts/`, `tests/` or the
workflow. The GenVM linter is a local binary, so linting stays a local gate and
its output is recorded in [docs/deployment.md](docs/deployment.md).

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
```

`scripts/run_studionet_lifecycle.mjs` reads `GENLAYER_PRIVATE_KEY` from `.env` and
generates two additional lab signers for the run, keeping their keys in the
gitignored `evidence/_checkpoint.json`. Copy `.env.example` to `.env` first.
Studionet is gasless, so a zero GEN balance is normal, but the lifecycle sends
real endowment value between three accounts, so the PI account is funded from the
faucet.

## Known findings, stated plainly

[docs/adversarial-review.md](docs/adversarial-review.md) lists nine findings with
the test that pins each one. Five are OPEN, and none of them locks a user out of
their own money:

- a challenger's bond is paid to the replicator at settlement instead of back to
  the challenger, and is forfeited with no recipient if the study expires while a
  challenge is open
- released bonds leave a 1.50 GEN residue above the published liability buckets
  that no method can sweep, in the over custody direction, so nobody is shorted
- one failed RLT deposit callback blocks the RLT deposit path for everyone, with
  no time based recovery
- the custody summary view omits open bonds, so liabilities have to be summed
  across two views, which is cosmetic

They are left unfixed because this release must point at the exact contract pair
that the evidence and the four way source identity check describe, and each fix
changes payout routing or storage layout, which means a new address.

## Repository map

```
contracts/            repro_lab.py, rlt_token.py
tests/                94 direct mode tests, no server needed
frontend/             Vite and React notebook, published to gh-pages
scripts/              lifecycle driver, explorer verifier, identity checker,
                      artifact generator, insignia and demo video compilers
docs/                 evidence, adversarial review, deployment guide, media
evidence/             transaction log, explorer verification, identity report
```
