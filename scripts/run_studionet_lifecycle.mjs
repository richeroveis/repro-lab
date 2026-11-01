// ReproLab studionet lifecycle driver.
//
// Deploys the RLT token and the ReproLab ledger, then drives a full multi-signer
// lifecycle (escrow funding, study registration, bonded replication trials,
// soft-fail payable refunds, live validator consensus evaluation, settlement,
// zero-winner and timeout refunds) and records every transaction for evidence.
//
// Private keys: the PI key comes from this project's .env. Lab keys are generated
// for the run and persisted only in the gitignored evidence/_checkpoint.json.
// Nothing secret is ever printed; only addresses and amounts are logged.
//
// usage: node scripts/run_studionet_lifecycle.mjs <deploy|seed|register|stake|
//        closed|evaluate|settle|reevaluate|zerowinner|expire|withdraw|verify|report|all>

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { createAccount, createClient, chains, generatePrivateKey } from 'genlayer-js';

const E1 = 10n ** 18n;
const ART_BASE =
  process.env.REPROLAB_ART_BASE || 'https://richeroveis.github.io/repro-lab/artifacts';
const CKPT_PATH = 'evidence/_checkpoint.json';
const TXLOG_PATH = 'evidence/_txs.jsonl';
const POOL_FUND = 8n * E1;
const ENDOWMENT = 1n * E1;
const BOND = 5n * 10n ** 17n;
const CHALLENGE_BOND = 1n * E1;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function readEnv() {
  const out = {};
  for (const line of fs.readFileSync('.env', 'utf8').split(/\r?\n/)) {
    const i = line.indexOf('=');
    if (i > 0 && !line.trim().startsWith('#')) {
      out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
    }
  }
  return out;
}

function loadCkpt() {
  if (!fs.existsSync(CKPT_PATH)) return { studies: {}, signers: {}, done: [] };
  return JSON.parse(fs.readFileSync(CKPT_PATH, 'utf8'));
}

function saveCkpt(ck) {
  fs.mkdirSync(path.dirname(CKPT_PATH), { recursive: true });
  fs.writeFileSync(CKPT_PATH, JSON.stringify(ck, null, 2), 'utf8');
}

// studionet is rate limited per IP, so all requests go through one throttle.
let lastAt = 0;
async function slot() {
  const wait = lastAt + 2200 - Date.now();
  if (wait > 0) await sleep(wait);
  lastAt = Date.now();
}

// The studio RPC intermittently answers with an HTML error page, so every call
// is retried with backoff before a step is declared failed.
async function attempt(label, fn, tries = 5) {
  let err;
  for (let i = 0; i < tries; i += 1) {
    try {
      return await fn();
    } catch (e) {
      err = e;
      console.log('retry', label, i + 1, String(e).slice(0, 110));
      await sleep(3000 * (i + 1));
      await slot();
    }
  }
  throw new Error('gave up on ' + label + ': ' + String(err).slice(0, 160));
}

function txRow(row) {
  fs.mkdirSync(path.dirname(TXLOG_PATH), { recursive: true });
  fs.appendFileSync(TXLOG_PATH, JSON.stringify(row) + '\n', 'utf8');
  const line = [
    row.step,
    row.method,
    row.hash,
    row.status_name ?? '?',
    row.result_name ?? '?',
    row.exec ?? '?',
    row.error ?? '',
  ]
    .join(' | ')
    .slice(0, 220);
  console.log(line);
}

function contractText(file) {
  return fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
}

class Lab {
  constructor() {
    this.ck = loadCkpt();
    const env = readEnv();
    let key = env.GENLAYER_PRIVATE_KEY || '';
    if (key && !key.startsWith('0x')) key = '0x' + key;
    this.pi = createAccount(key);
    this.client = createClient({ chain: chains.studionet, account: this.pi });
    this.accounts = { pi: this.pi };
    for (const name of ['labB', 'labC']) {
      const stored = this.ck.signers[name] && this.ck.signers[name].key;
      const pk = stored || generatePrivateKey();
      const acct = createAccount(pk);
      this.accounts[name] = acct;
      this.ck.signers[name] = { address: acct.address, key: pk };
    }
    this.ledger = this.ck.ledger;
    this.token = this.ck.token;
  }

  addrOf(name) {
    return this.accounts[name].address;
  }

  async view(functionName, args = []) {
    await slot();
    return attempt('view ' + functionName, () =>
      this.client.readContract({
        address: this.ledger,
        functionName,
        args,
        account: this.pi,
      })
    );
  }

  async tokenView(functionName, args = []) {
    await slot();
    return attempt('tokenView ' + functionName, () =>
      this.client.readContract({
        address: this.token,
        functionName,
        args,
        account: this.pi,
      })
    );
  }

  async write(step, signerName, to, functionName, args = [], value = 0n, expect = 'ok') {
    const account = this.accounts[signerName];
    await slot();
    const hash = await attempt('write ' + functionName, () =>
      this.client.writeContract({ account, address: to, functionName, args, value })
    );
    await slot();
    let rec;
    try {
      rec = await attempt('receipt ' + functionName, () =>
        this.client.waitForTransactionReceipt({
          hash,
          status: 'FINALIZED',
          interval: 5000,
          retries: 60,
        })
      );
    } catch (e) {
      rec = { status_name: 'WAIT_TIMEOUT', error: String(e).slice(0, 200) };
    }
    const leader = rec?.consensus_data?.leader_receipt?.[0] ?? {};
    const gv = leader.genvm_result ?? {};
    const votes = rec?.consensus_data?.votes ?? {};
    const row = {
      step,
      signer: account.address,
      contract: to,
      method: functionName,
      args: args.map((a) => (typeof a === 'bigint' ? a.toString() : a)),
      value_atto: value.toString(),
      hash,
      status_name: rec?.status_name ?? String(rec?.status ?? ''),
      result_name: rec?.result_name ?? String(rec?.result ?? ''),
      exec: leader.execution_result ?? '',
      error: gv.error_description ?? rec?.error ?? '',
      stderr: (gv.stderr ?? '').slice(-240),
      rounds: rec?.num_of_rounds ?? '',
      votes: Object.values(votes).join(','),
      at: new Date().toISOString(),
      expect,
    };
    txRow(row);
    return row;
  }

  async deployContract(step, file, args = [], key = 'deployed') {
    if (this.ck[key]) {
      this[key === 'token' ? 'token' : 'ledger'] = this.ck[key];
      console.log(step, 'reusing', key, this.ck[key]);
      return this.ck[key];
    }
    const account = this.accounts.pi;
    await slot();
    const hash = await this.client.deployContract({
      account,
      code: contractText(file),
      args,
    });
    await slot();
    const rec = await this.client.waitForTransactionReceipt({
      hash,
      status: 'FINALIZED',
      interval: 4000,
      retries: 90,
    });
    const address = rec?.data?.contract_address ?? rec?.to_address ?? '';
    const leader = rec?.consensus_data?.leader_receipt?.[0] ?? {};
    const gv = leader.genvm_result ?? {};
    txRow({
      step,
      signer: account.address,
      contract: address,
      method: 'constructor ' + path.basename(file),
      args: args.map(String),
      value_atto: '0',
      hash,
      status_name: rec?.status_name ?? '',
      result_name: rec?.result_name ?? '',
      exec: leader.execution_result ?? '',
      error: gv.error_description ?? '',
      stderr: (gv.stderr ?? '').slice(-240),
      rounds: rec?.num_of_rounds ?? '',
      votes: Object.values(rec?.consensus_data?.votes ?? {}).join(','),
      at: new Date().toISOString(),
      expect: 'ok',
    });
    if (!address) throw new Error('deploy produced no address: ' + hash);
    this.ck[key] = address;
    if (key === 'token') this.token = address;
    if (key === 'ledger') this.ledger = address;
    saveCkpt(this.ck);
    console.log(step, key, 'address', address);
    return address;
  }

  async sendGEN(signerName, to, value) {
    const account = this.accounts[signerName];
    await slot();
    return attempt('sendGEN', () => this.client.sendTransaction({ account, to, value }));
  }

  async balance(address) {
    await slot();
    const b = await attempt('balance', () => this.client.getBalance({ address }));
    return b.toString();
  }
}

const STUDIES = [
  {
    key: 'sequencing',
    title: 'Sanger Sequencing Read Accuracy Benchmark',
    target: 'sanger-basecall-accuracy',
    baseline: 8250n,
    tw: 30n,
    aw: 60n,
    twt: 3600n,
  },
  {
    key: 'drift',
    title: 'LLM Quantization Perplexity Drift Study',
    target: 'quantization-perplexity-drift',
    baseline: 5250n,
    tw: 600n,
    aw: 300n,
    twt: 1800n,
  },
  {
    key: 'crispr',
    title: 'CRISPR Off-Target Cleavage Dataset Benchmark',
    target: 'crispr-offtarget-cleavage-rate',
    baseline: 6750n,
    tw: 600n,
    aw: 300n,
    twt: 1800n,
  },
  {
    key: 'meissner',
    title: 'Superconductor Meissner Curve Reproduction',
    target: 'meissner-flux-expulsion-fraction',
    baseline: 4000n,
    tw: 600n,
    aw: 120n,
    twt: 900n,
  },
];

const CHECKSUMS = {
  sequencing: 'b7c9d0e1f23586a7b1c4d9e0f3a25c6b7d8e9f0a1b2c3d4e5f60718293a4b5c6',
  drift: '7d21c4b9f0a53e18c6d7a0b215e94c3d8a6f1b0c2d3e4f50617283a4b5c6d7e8',
  crispr: '1f3d9c2a7b5e4018d6c3a9b0e5f2741c8a3d6b9e0f51c72a4b8d3e69f0c15a72',
  meissner: 'a4b7c9d0e1f23586a7b1c4d9e0f3a25c6b7d8e9f0a1b2c3d4e5f60718293a4b5',
};

const CLAIMS = {
  sequencing: { rep: 8250n, integrity: 9000n },
  drift: { rep: 5250n, integrity: 9250n },
  crispr: { rep: 7500n, integrity: 9000n },
  meissner: { rep: 4000n, integrity: 9250n },
};

function spec(key) {
  return STUDIES.find((s) => s.key === key);
}

function artifactUrl(key) {
  return ART_BASE + '/' + key + '-artifact.html';
}

function logUrl(key) {
  return ART_BASE + '/' + key + '-log.html';
}

function sid(lab, key) {
  const entry = lab.ck.studies[key];
  if (!entry || !entry.id) throw new Error('study not registered: ' + key);
  return BigInt(entry.id);
}

async function card(lab, key) {
  return lab.view('get_study_card', [sid(lab, key)]);
}

async function waitChainTime(lab, epochSeconds, extra = 6) {
  for (;;) {
    const now = Math.floor(Date.now() / 1000);
    if (now >= epochSeconds + extra) return;
    console.log('waiting for chain clock', epochSeconds, 'now', now);
    await sleep(5000);
  }
}

async function stepDeploy(lab) {
  await lab.deployContract('deploy-rlt', 'contracts/rlt_token.py', [], 'token');
  await lab.deployContract('deploy-ledger', 'contracts/repro_lab.py', [lab.token], 'ledger');
}

async function waitUntil(label, fn, timeoutMs = 120000) {
  const stop = Date.now() + timeoutMs;
  for (;;) {
    const ok = await fn();
    if (ok) {
      console.log('ok', label);
      return true;
    }
    if (Date.now() > stop) {
      console.log('TIMEOUT waiting for', label);
      return false;
    }
    await sleep(5000);
  }
}

async function stepSeed(lab) {
  if (!lab.ck.signers.labB.key) throw new Error('checkpoint lost lab keys');
  saveCkpt(lab.ck);
  for (const name of ['labB', 'labC']) {
    const addr = lab.addrOf(name);
    if (BigInt(await lab.balance(addr)) < 2n * E1) {
      const hash = await lab.sendGEN('pi', addr, 2n * E1);
      txRow({
        step: 'seed-fund-signer',
        signer: lab.addrOf('pi'),
        contract: addr,
        method: 'native transfer GEN',
        args: [String(2n * E1)],
        value_atto: String(2n * E1),
        hash,
        status_name: 'SENT',
        at: new Date().toISOString(),
        expect: 'ok',
      });
    }
    console.log('balance', name, addr, await lab.balance(addr));
  }
  await lab.write('seed-pool', 'pi', lab.ledger, 'fund_endowment_payable', [], POOL_FUND);
  await lab.write('seed-rlt-approve', 'pi', lab.token, 'approve', [lab.ledger, 2000n * E1]);
  await lab.write('seed-rlt-deposit', 'pi', lab.ledger, 'deposit_rlt_custody', [1000n * E1]);
  const credited = await waitUntil('rlt vault credit', async () => {
    const s = await lab.view('get_custody_accounting_summary');
    console.log('vault_custody_balance', s.vault_custody_balance);
    return BigInt(s.vault_custody_balance) === 1000n * E1;
  });
  if (!credited) throw new Error('RLT custody credit did not land');
  console.log('token holds for ledger', (await lab.tokenView('balanceOf', [lab.ledger])).toString());
  await lab.write('seed-rlt-withdraw', 'pi', lab.ledger, 'withdraw_rlt_custody', [200n * E1]);
  const withdrawn = await waitUntil('rlt vault withdraw', async () => {
    const s = await lab.view('get_custody_accounting_summary');
    return BigInt(s.vault_custody_balance) === 800n * E1;
  });
  console.log('withdraw ok', withdrawn, 'pi RLT', (await lab.tokenView('balanceOf', [lab.addrOf('pi')])).toString());
}

async function stepRegister(lab) {
  // The pool must cover 150 percent of escrowed endowments plus every open
  // bond, so top it up to 12 GEN before opening four bounties.
  await lab.write('register-pool-topup', 'pi', lab.ledger, 'fund_endowment_payable', [], 4n * E1);
  const seq = spec('sequencing');
  await lab.write(
    'register-softfail-underfunded',
    'pi',
    lab.ledger,
    'register_study_bounty_payable',
    [seq.title, artifactUrl(seq.key), seq.target, seq.baseline, ENDOWMENT, seq.tw, seq.aw, seq.twt],
    2n * 10n ** 17n,
    'soft-fail'
  );
  console.log('underfunded rejection:', await lab.view('get_last_payable_rejection', [lab.addrOf('pi')]));
  for (const s of STUDIES) {
    const row = await lab.write(
      'register-' + s.key,
      'pi',
      lab.ledger,
      'register_study_bounty_payable',
      [s.title, artifactUrl(s.key), s.target, s.baseline, ENDOWMENT, s.tw, s.aw, s.twt],
      ENDOWMENT
    );
    if (row.exec !== 'SUCCESS') throw new Error('registration failed for ' + s.key);
  }
  const overview = await lab.view('get_lab_overview');
  const count = Number(overview.study_count);
  for (let id = 1; id <= count; id += 1) {
    const c = await lab.view('get_study_card', [BigInt(id)]);
    const match = STUDIES.find((s) => String(c.title).indexOf(s.title) === 0);
    if (match) {
      lab.ck.studies[match.key] = {
        id,
        trial_close_epoch: Number(c.trial_close_epoch),
        audit_timeout_epoch: Number(c.audit_timeout_epoch),
      };
    }
  }
  saveCkpt(lab.ck);
  const meta = {};
  for (const s of STUDIES) {
    const e = lab.ck.studies[s.key];
    if (!e) continue;
    meta[String(e.id)] = {
      title: s.title,
      target: s.target,
      pi: lab.addrOf('pi'),
      artifact: artifactUrl(s.key),
      log: logUrl(s.key),
      baseline_bps: Number(s.baseline),
      endowment_gen: 1,
    };
  }
  fs.mkdirSync('frontend/public', { recursive: true });
  fs.writeFileSync('frontend/public/study-meta.json', JSON.stringify(meta, null, 2) + '\n', 'utf8');
  console.log('registered', JSON.stringify(lab.ck.studies));
}

async function stepStake(lab) {
  const drift = sid(lab, 'drift');
  await lab.write(
    'gate-evaluate-too-early',
    'pi',
    lab.ledger,
    'evaluate_replication_trial',
    [drift],
    0n,
    'revert'
  );
  const d = CLAIMS.drift;
  await lab.write(
    'stake-pi-self-replication',
    'pi',
    lab.ledger,
    'stake_replication_trial_payable',
    [drift, d.rep, d.integrity, CHECKSUMS.drift, logUrl('drift')],
    BOND,
    'soft-fail'
  );
  const stakes = [
    ['stake-drift-labB', 'labB', 'drift'],
    ['stake-crispr-labC', 'labC', 'crispr'],
    ['stake-meissner-labB', 'labB', 'meissner'],
  ];
  for (const [step, signer, key] of stakes) {
    const s = spec(key);
    const cl = CLAIMS[key];
    const row = await lab.write(
      step,
      signer,
      lab.ledger,
      'stake_replication_trial_payable',
      [sid(lab, key), cl.rep, cl.integrity, CHECKSUMS[key], logUrl(key)],
      BOND
    );
    if (row.exec !== 'SUCCESS') throw new Error('stake failed: ' + key);
    lab.ck.studies[key].lab = lab.addrOf(signer);
  }
  await lab.write(
    'stake-drift-duplicate',
    'labB',
    lab.ledger,
    'stake_replication_trial_payable',
    [drift, d.rep, d.integrity, CHECKSUMS.drift, logUrl('drift')],
    BOND,
    'soft-fail'
  );
  for (const key of ['drift', 'crispr']) {
    await lab.write(
      'author-response-' + key,
      'pi',
      lab.ledger,
      'submit_author_response',
      [sid(lab, key), 'protocol frozen at the pinned commit, raw logs published'],
      0n
    );
  }
  await lab.write(
    'author-response-wrong-caller',
    'labC',
    lab.ledger,
    'submit_author_response',
    [sid(lab, 'crispr'), 'not the corresponding author'],
    0n,
    'revert'
  );
  saveCkpt(lab.ck);
}

async function stepClosedWindow(lab) {
  const s = spec('sequencing');
  await waitChainTime(lab, lab.ck.studies.sequencing.trial_close_epoch, 4);
  const cl = CLAIMS.sequencing;
  await lab.write(
    'stake-sequencing-after-close',
    'labC',
    lab.ledger,
    'stake_replication_trial_payable',
    [sid(lab, 'sequencing'), cl.rep, cl.integrity, CHECKSUMS.sequencing, logUrl('sequencing')],
    BOND,
    'soft-fail'
  );
}

async function stepEvaluate(lab) {
  const key = process.argv[3] === 'crispr' ? 'crispr' : 'drift';
  const entry = lab.ck.studies[key];
  await waitChainTime(lab, entry.trial_close_epoch, 3);
  const row = await lab.write('evaluate-' + key, 'pi', lab.ledger, 'evaluate_replication_trial', [sid(lab, key)]);
  const c = await card(lab, key);
  entry.band = c.verdict_band;
  entry.audited = [c.audited_baseline_bps, c.audited_replicated_bps, c.audited_integrity_bps].join('/');
  entry.peer_challenge_deadline_epoch = Number(c.peer_challenge_deadline_epoch);
  entry.deviation_bps = c.deviation_bps;
  entry.eval_exec = row.exec;
  entry.votes = row.votes;
  entry.evaluate_hash = row.hash;
  saveCkpt(lab.ck);
  console.log('evaluated', key, c.verdict_band, entry.audited, 'deviation', c.deviation_bps);
}

async function stepSettle(lab) {
  const entry = lab.ck.studies.drift;
  await lab.write('settle-too-early', 'labB', lab.ledger, 'settle_replication_grant', [sid(lab, 'drift')], 0n, 'revert');
  await lab.write(
    'challenge-by-party',
    'labB',
    lab.ledger,
    'challenge_replication_ruling_payable',
    [sid(lab, 'drift'), 'the replicator may not challenge its own ruling'],
    CHALLENGE_BOND,
    'soft-fail'
  );
  await lab.write(
    'challenge-crispr-labB',
    'labB',
    lab.ledger,
    'challenge_replication_ruling_payable',
    [sid(lab, 'crispr'), 'requesting an independent re-audit of the deviation band'],
    CHALLENGE_BOND
  );
  await waitChainTime(lab, entry.peer_challenge_deadline_epoch, 3);
  const row = await lab.write('settle-drift', 'pi', lab.ledger, 'settle_replication_grant', [sid(lab, 'drift')]);
  const c = await card(lab, 'drift');
  console.log('drift settled', c.status, 'grant', c.derived_replicator_grant, 'exec', row.exec);
  entry.status = c.status;
  saveCkpt(lab.ck);
}

async function stepReevaluate(lab) {
  const entry = lab.ck.studies.crispr;
  const row = await lab.write('reevaluate-crispr', 'pi', lab.ledger, 'evaluate_replication_trial', [sid(lab, 'crispr')]);
  const c = await card(lab, 'crispr');
  entry.band = c.verdict_band;
  entry.audited = [c.audited_baseline_bps, c.audited_replicated_bps, c.audited_integrity_bps].join('/');
  entry.peer_challenge_deadline_epoch = Number(c.peer_challenge_deadline_epoch);
  entry.reeval_exec = row.exec;
  entry.votes = row.votes;
  saveCkpt(lab.ck);
  await waitChainTime(lab, entry.peer_challenge_deadline_epoch, 3);
  await lab.write('settle-crispr', 'pi', lab.ledger, 'settle_replication_grant', [sid(lab, 'crispr')]);
  const c2 = await card(lab, 'crispr');
  entry.status = c2.status;
  console.log('crispr settled', c2.status, c2.verdict_band, c2.derived_replicator_grant, c2.derived_pi_refund);
  saveCkpt(lab.ck);
}

async function stepZeroWinner(lab) {
  const entry = lab.ck.studies.sequencing;
  await lab.write(
    'zerowinner-refund',
    'pi',
    lab.ledger,
    'claim_unreplicated_or_expired_refund',
    [sid(lab, 'sequencing')]
  );
  const c = await card(lab, 'sequencing');
  console.log('sequencing', c.status, 'claims', c.claims);
  entry.status = c.status;
  saveCkpt(lab.ck);
}

async function stepExpire(lab) {
  const entry = lab.ck.studies.meissner;
  await waitChainTime(lab, entry.audit_timeout_epoch, 3);
  await lab.write('expired-refund-meissner', 'pi', lab.ledger, 'claim_unreplicated_or_expired_refund', [sid(lab, 'meissner')]);
  const c = await card(lab, 'meissner');
  console.log('meissner', c.status, 'claims', c.claims, 'band', c.verdict_band);
  entry.status = c.status;
  saveCkpt(lab.ck);
}

async function stepWithdraw(lab) {
  for (const name of ['pi', 'labB', 'labC']) {
    const addr = lab.addrOf(name);
    const credit = BigInt(await lab.view('get_refundable_balance', [addr]));
    console.log('credit for', name, credit.toString());
    if (credit > 0n) {
      if (name === 'pi' && credit > 10n ** 17n) {
        await lab.write('withdraw-partial', name, lab.ledger, 'withdraw_refund', [10n ** 17n]);
      }
      await lab.write('claim-credits', name, lab.ledger, 'claim_refundable_balance', []);
      await waitUntil('credit cleared for ' + name, async () =>
        BigInt(await lab.view('get_refundable_balance', [addr])) === 0n
      );
    }
  }
}

async function stepVerify(lab) {
  const summary = await lab.view('get_custody_accounting_summary');
  const overview = await lab.view('get_lab_overview');
  const index = await lab.view('get_reproducibility_index', [0n, 10n]);
  const gen = BigInt(await lab.balance(lab.ledger));
  const pool = BigInt(summary.endowment_pool_atto);
  const locked = BigInt(summary.total_endowment_locked);
  const credits = BigInt(summary.credits_outstanding_atto);
  const openBonds = BigInt(overview.open_bonds_atto);
  const covered = gen === pool + locked + openBonds + credits;
  console.log('invariant', {
    ledger_gen: gen.toString(),
    pool: pool.toString(),
    locked: locked.toString(),
    open_bonds: openBonds.toString(),
    credits: credits.toString(),
    holds: covered,
    reserve_covers: summary.pool_covers_reserve,
  });
  lab.ck.final = {
    summary,
    overview,
    index,
    ledger_gen_atto: gen.toString(),
    invariant_holds: covered,
    rlt_vault: await lab.tokenView('balanceOf', [lab.ledger]),
    pi_rlt: await lab.tokenView('balanceOf', [lab.addrOf('pi')]),
    balances: {},
  };
  for (const name of ['pi', 'labB', 'labC']) {
    lab.ck.final.balances[name] = await lab.balance(lab.addrOf(name));
  }
  saveCkpt(lab.ck);
  const cards = {};
  const trials = {};
  for (let id = 1; id <= Number(overview.study_count); id += 1) {
    cards[String(id)] = await lab.view('get_study_card', [BigInt(id)]);
    trials[String(id)] = await lab.view('get_trial_book', [BigInt(id)]);
  }
  fs.mkdirSync('frontend/public', { recursive: true });
  fs.writeFileSync(
    'frontend/public/snapshot.json',
    JSON.stringify(
      {
        fetched_at: new Date().toISOString(),
        network: 'studionet 61999',
        ledger: lab.ledger,
        rlt_token: lab.token,
        overview,
        index,
        summary,
        cards,
        trials,
      },
      null,
      2
    ) + '\n',
    'utf8'
  );
  console.log('published frontend/public/snapshot.json');
  if (!covered) throw new Error('custody invariant does not hold');
}

async function stepReport(lab) {
  const rows = fs
    .readFileSync(TXLOG_PATH, 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l));
  const ck = lab.ck;
  const sha = (file) => {
    const buf = fs.readFileSync(file).toString().replace(/\r\n/g, '\n');
    return crypto.createHash('sha256').update(Buffer.from(buf, 'utf8')).digest('hex');
  };
  const lines = [];
  lines.push('# ReproLab studionet deployment evidence');
  lines.push('');
  lines.push('Network: studionet (chain id 61999, rpc https://studio.genlayer.com/api).');
  lines.push('Gas: studionet charges no gas; every GEN figure below is escrow principal,');
  lines.push('not a fee. Generated by `node scripts/run_studionet_lifecycle.mjs all`.');
  lines.push('');
  lines.push('## Deployed contracts');
  lines.push('');
  lines.push('| contract | address | source sha256 (LF) |');
  lines.push('| --- | --- | --- |');
  lines.push('| `contracts/rlt_token.py` | `' + ck.token + '` | ' + sha('contracts/rlt_token.py') + ' |');
  lines.push('| `contracts/repro_lab.py` | `' + ck.ledger + '` | ' + sha('contracts/repro_lab.py') + ' |');
  lines.push('');
  lines.push('## Signers');
  lines.push('');
  lines.push('| role | address |');
  lines.push('| --- | --- |');
  lines.push('| PI / deployer (endowment sponsor) | ' + lab.pi.address + ' |');
  lines.push('| independent lab B (replicator) | ' + lab.addrOf('labB') + ' |');
  lines.push('| independent lab C (replicator and challenger) | ' + lab.addrOf('labC') + ' |');
  lines.push('');
  lines.push('Lab keys are generated per run and are never committed; they hold only');
  lines.push('testnet GEN. The artifacts under `frontend/public/artifacts/` are the live');
  lines.push('evidence sources that validators fetched during consensus.');
  lines.push('');
  lines.push('## Registered studies');
  lines.push('');
  lines.push('| study | id | verdict band | audited bps (baseline / replicated / integrity) | final status |');
  lines.push('| --- | --- | --- | --- | --- |');
  for (const s of STUDIES) {
    const e = ck.studies[s.key] || {};
    lines.push(
      '| ' + s.title + ' | ' + (e.id ?? '') + ' | ' + (e.band || 'none') + ' | ' + (e.audited || '-') +
        ' | ' + (e.status || '-') + ' |'
    );
  }
  lines.push('');
  lines.push('## Transaction log');
  lines.push('');
  lines.push('Every row is the on-chain receipt read back from the RPC: lifecycle status,');
  lines.push('consensus result, leader execution result and the validator vote tally.');
  lines.push('');
  lines.push('| step | signer | method | value (GEN) | tx hash | status | consensus | leader | votes | expected |');
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |');
  for (const r of rows) {
    const gen = Number(BigInt(r.value_atto || '0')) / 1e18;
    lines.push(
      '| ' + r.step + ' | `' + String(r.signer).slice(0, 10) + '` | ' + r.method + ' | ' + gen +
        ' | `' + r.hash + '` | ' + (r.status_name || '') + ' | ' + (r.result_name || '') + ' | ' +
        (r.exec || '') + ' | ' + (r.votes || '') + ' | ' + (r.expect || 'ok') + ' |'
    );
  }
  lines.push('');
  if (ck.final) {
    lines.push('## Final custody accounting');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(ck.final, null, 2));
    lines.push('```');
    lines.push('');
    lines.push(
      'The ledger GEN balance equals `endowment_pool_atto + total_endowment_locked + open_bonds_atto + credits_outstanding_atto`: ' +
        (ck.final.invariant_holds ? 'it holds.' : 'IT DOES NOT HOLD.')
    );
  }
  fs.mkdirSync('docs', { recursive: true });
  fs.writeFileSync('docs/evidence.md', lines.join('\n'), 'utf8');
  const byStudy = {};
  const idOf = (method) => {
    const m = /study (\d+)/.exec(method);
    return m ? m[1] : null;
  };
  for (const r of rows) {
    if (!/evaluate|settle|challenge|refund|stake|author/.test(r.method)) continue;
    const key = r.step.includes('drift')
      ? '2'
      : r.step.includes('crispr')
        ? '3'
        : r.step.includes('meissner')
          ? '4'
          : r.step.includes('sequencing')
            ? '1'
            : idOf(r.method);
    if (!key) continue;
    byStudy[key] = byStudy[key] || [];
    byStudy[key].push({
      method: r.step,
      hash: r.hash,
      status_name: r.status_name,
      result_name: r.result_name,
      exec: r.exec,
      votes: r.votes,
      signer: r.signer,
      value_atto: r.value_atto,
      at: r.at,
    });
  }
  fs.writeFileSync(
    'frontend/public/consensus-proof.json',
    JSON.stringify(byStudy, null, 2) + '\n',
    'utf8'
  );
  console.log('wrote docs/evidence.md with', rows.length, 'transactions');
}

const STEPS = {
  deploy: stepDeploy,
  seed: stepSeed,
  register: stepRegister,
  stake: stepStake,
  closed: stepClosedWindow,
  evaluate: stepEvaluate,
  settle: stepSettle,
  reevaluate: stepReevaluate,
  zerowinner: stepZeroWinner,
  expire: stepExpire,
  withdraw: stepWithdraw,
  verify: stepVerify,
  report: stepReport,
};

async function main() {
  const name = process.argv[2] || 'all';
  const lab = new Lab();
  if (!lab.pi.address) throw new Error('no PI key in .env');
  console.log('PI', lab.pi.address, 'balance', await lab.balance(lab.pi.address));
  const order = [
    'deploy',
    'seed',
    'register',
    'stake',
    'closed',
    'evaluate',
    'settle',
    'zerowinner',
    'expire',
    'reevaluate',
    'withdraw',
    'verify',
    'report',
  ];
  const run = name === 'all' ? order : name.split(',').map((s) => s.trim()).filter(Boolean);
  for (const step of run) {
    const fn = STEPS[step];
    if (!fn) {
      console.log('unknown step', step);
      continue;
    }
    console.log('=== step', step);
    const before = BigInt(await lab.balance(lab.pi.address));
    await fn(lab);
    const after = BigInt(await lab.balance(lab.pi.address));
    lab.ck.balances = lab.ck.balances || [];
    lab.ck.balances.push({
      step,
      pi_before: before.toString(),
      pi_after: after.toString(),
      spent_gen: Number(before - after) / 1e18,
      at: new Date().toISOString(),
    });
    console.log('pi GEN', Number(before) / 1e18, '->', Number(after) / 1e18);
    saveCkpt(lab.ck);
  }
}

main().catch((e) => {
  console.error('FAILED', String(e).slice(0, 500));
  process.exit(1);
});
