# Deploying ReproLab to studionet

This is the exact path that produced the addresses in the README and the
transactions in [docs/evidence.md](evidence.md). Studionet is chain id 61999 and
is gasless, so a zero GEN balance does not block anything, but this project moves
real endowment value between three accounts, so the PI account is funded from the
testnet faucet before a run.

## Prerequisites

```bash
npm install -g genlayer
python -m pip install genlayer-test pytest pillow numpy
npm install                      # genlayer-js for the driver, at the repo root
cd frontend && npm install && cd ..
genlayer network set studionet   # never use --rpc for built in networks
```

`.env` needs `GENLAYER_PRIVATE_KEY` for the PI and deployer account, and
`GITHUB_TOKEN` for publishing. Copy `.env.example` to `.env`. The driver generates
two extra lab signers per run and stores their keys in the gitignored
`evidence/_checkpoint.json`, because the lifecycle needs distinct signers for the
replicator, the challenger and the PI.

## Lint and test before anything touches the network

```bash
genvm-lint check contracts/repro_lab.py
genvm-lint check contracts/rlt_token.py
python -m pytest tests/ -q
```

Both contracts must stay under 37,500 bytes and line 1 must pin the runner hash
`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`. `test` and
`latest` aliases are rejected by every GenLayer network.

## Deploy

The CLI cannot attach native value to a payable call, its `--fee-value` is a
validator fee deposit, so deployment and the whole lifecycle go through
genlayer-js:

```bash
node scripts/run_studionet_lifecycle.mjs deploy
```

That deploys `rlt_token.py`, then `repro_lab.py` with the token address as the
constructor argument, waits for `FINALIZED`, and records both addresses in the
checkpoint. Every subsequent step reads the ledger address from there, and
`frontend/src/chain.js` must be updated to match before a rebuild.

The address changes whenever code or storage layout changes. The field
`pending_rlt_credit_depositor` was appended at the end of the storage layout for
exactly that reason.

## Run the lifecycle

```bash
node scripts/run_studionet_lifecycle.mjs seed
node scripts/run_studionet_lifecycle.mjs register,stake,closed,evaluate,settle,zerowinner,expire,reevaluate,withdraw,verify,report
```

Steps are individually addressable and idempotent through the checkpoint, so a
run that dies halfway can resume. `verify` reads the custody state back from
chain, asserts the invariant and writes `frontend/public/snapshot.json` plus
`frontend/public/custody-reconciliation.json`. `report` writes
`docs/evidence.md` and `frontend/public/consensus-proof.json`.

Studionet is rate limited per IP, roughly 60 requests a minute and at most 32
in flight transactions per sender. The driver throttles to one write every 2.2
seconds and waits for each receipt before the next submission, and it retries the
studio RPC, which intermittently answers with an HTML error page instead of JSON.

## Verify through the explorer, not only the CLI

```bash
python scripts/verify_explorer_txs.py
```

This re-queries every recorded hash against
`https://explorer-studio.genlayer.com/api/transactions/<hash>` and compares the
lifecycle status, the leader execution result and the validator vote tally with
what the RPC receipt said. It writes `evidence/explorer-verification.json` and
exits non zero on any mismatch. Two things it handles explicitly:

- plain funding transfers to a lab EOA have no leader receipt and no state hash,
  so they are checked for finalization and value instead
- a gated attempt that reverts must show an execution error and the same contract
  state hash as the transaction before it, which is how "too early really failed"
  is proven rather than asserted

The explorer response also embeds validator node configuration. The script reads
an allowlist of flat fields only, and nothing from those objects is stored or
printed.

## Prove source identity

```bash
node scripts/verify_source_identity.mjs all
```

Four sources must produce the same SHA-256 for each contract: the local file with
LF endings, the git blob, the GitHub raw file, and the code the network returns
for the deployed address. `gen_getContractCode` currently fails server side on
studionet, so the checker falls back to `genlayer code <address>` and normalizes
ANSI codes, CRLF and any leading banner before hashing. The result is stored in
`evidence/identity.txt`.

## Publish the notebook

```bash
cd frontend && npm run build && cd ..
python scripts/enable_github_pages.py
node scripts/git_publish.mjs both
```

`git_publish.mjs` pushes `main` and rebuilds the `gh-pages` branch from
`frontend/dist` in a standalone working repo under `.gh-pages-work`, which is
gitignored. The token is passed to git only through `GIT_ASKPASS` and any error
text is scrubbed, so it never appears in a log. Pages serves
`https://richeroveis.github.io/repro-lab/`.

The published `dist` must contain `logo.png`, `demo-video-subtitled.mp4`,
`snapshot.json`, `consensus-proof.json`, `custody-reconciliation.json`,
`study-meta.json` and the seven `artifacts/` pages that validators fetch.

## CORS reality

`https://studio.genlayer.com/api` answers a browser read with no
`Access-Control-Allow-Origin`, on GET and on OPTIONS. A static Pages origin
therefore cannot always read live state. The UI tries at most four live
`genlayer-js` reads, then falls back to the published `snapshot.json` and stamps
the mode in the header, so a reviewer never sees a silent substitution.

## Regenerating the media

```bash
python scripts/render_reprolab_insignia.py     # 512x512 logo into public and docs
python scripts/compile_empirical_video_brief.py  # 50 s subtitled mp4 with audio
python scripts/render_study_artifacts.py         # the validator facing artifact pages
```

The video compiler reads the published snapshot and the explorer verification, so
it must run after `verify`. It fails loudly if the captions contain an em dash or
a comma artifact, if the duration leaves 48 to 52 seconds, or if the file exceeds
15 MB.
