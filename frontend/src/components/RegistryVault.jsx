import React, { useEffect, useMemo, useState } from 'react';
import { BANDS } from '../chain.js';
import { gen, short } from '../bands.js';
import { writeLedger } from '../useLedger.js';

const E1 = 10 ** 18;

function BandBadge({ band }) {
  const tone = BANDS[band]?.tone || 'none';
  return <span className={'band ' + tone}>{band || 'no ruling yet'}</span>;
}

function Action({ label, title, children, run, busy, setBusy, disabled }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid var(--edge)', padding: '0.6rem 0.7rem', marginTop: '0.7rem' }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <button onClick={() => setOpen(!open)} title={title}>
          {label}
        </button>
        <span className="hint">{open ? 'collapse' : 'expand'}</span>
      </div>
      {open ? (
        <div style={{ marginTop: '0.7rem' }}>
          {children({ disabled, busy, setBusy, run })}
        </div>
      ) : null}
    </div>
  );
}

export default function RegistryVault({
  overview,
  summary,
  index,
  meta,
  wallet,
  refreshWallet,
  selected,
  selectStudy,
  mode,
}) {
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [form, setForm] = useState({
    fundGen: '1',
    title: 'Cryogenic Noise Floor Reproduction',
    artifact: 'https://richeroveis.github.io/repro-lab/artifacts/meissner-artifact.html',
    target: 'meissner-flux-expulsion-fraction',
    baseline: '4000',
    endowmentGen: '1',
    trialWindow: '90',
    authorWindow: '120',
    timeoutWindow: '1800',
    studyId: '1',
    replicated: '4000',
    integrity: '9250',
    checksum: 'a4b7c9d0e1f23586a7b1c4d9e0f3a25c6b7d8e9f0a1b2c3d4e5f60718293a4b5',
    log: 'https://richeroveis.github.io/repro-lab/artifacts/meissner-log.html',
    bondGen: '0.5',
    withdrawGen: '0.1',
    rltAmount: '100',
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (form.withdrawGen && Number(form.withdrawGen) > (wallet.credit || 0)) {
      setForm((prev) => ({
        ...prev,
        withdrawGen: String(Math.max(0, Math.floor((wallet.credit || 0) * 10) / 10 || 0)),
      }));
    }
  }, [wallet.credit, form.withdrawGen]);

  const rows = useMemo(() => {
    const byId = new Map(index.map((r) => [String(r.study_id), r]));
    const ids = meta ? Object.keys(meta) : [...byId.keys()];
    return ids
      .map((id) => ({ id, chain: byId.get(String(id)) || null, info: meta ? meta[id] : null }))
      .sort((a, b) => Number(a.id) - Number(b.id));
  }, [index, meta]);

  async function run(fnName, args, valueGen = 0) {
    setBusy(true);
    setReceipt(null);
    try {
      const hash = await writeLedger(fnName, args, BigInt(Math.round(valueGen * E1)));
      setReceipt({ ok: true, hash, fnName });
      setTimeout(refreshWallet, 12000);
    } catch (err) {
      setReceipt({ ok: false, error: String(err?.shortMessage || err?.message || err), fnName });
    }
    setBusy(false);
  }

  const locked = gen(summary?.total_endowment_locked);
  const reserve = gen(summary?.reserve_required_atto);
  const pool = gen(summary?.endowment_pool_atto);
  const credits = gen(summary?.credits_outstanding_atto);

  return (
    <section className="card">
      <header>
        <h2>Empirical Study Registry and Endowment Custody Vault</h2>
        <span className="tag">RLT custody / GEN escrow</span>
      </header>
      <div className="body">
        <div className="strip">
          <div className="cell">
            <b>{overview?.study_count ?? '-'}</b>
            <span>registered studies</span>
          </div>
          <div className="cell">
            <b>{overview?.settled_studies ?? '-'}</b>
            <span>settled</span>
          </div>
          <div className="cell">
            <b>{pool.toFixed(3)} GEN</b>
            <span>collateral pool</span>
          </div>
          <div className="cell">
            <b>{locked.toFixed(3)} GEN</b>
            <span>endowment locked</span>
          </div>
          <div className="cell">
            <b>{reserve.toFixed(3)} GEN</b>
            <span>150 percent reserve</span>
          </div>
          <div className="cell">
            <b>{(gen(summary?.vault_custody_balance) / 1e0).toFixed(0)} RLT</b>
            <span>vault custody</span>
          </div>
          <div className="cell">
            <b>{overview?.soft_fail_count ?? '-'}</b>
            <span>soft fails absorbed</span>
          </div>
        </div>

        <table className="log">
          <thead>
            <tr>
              <th>id</th>
              <th>study</th>
              <th>status</th>
              <th>verdict band</th>
              <th>claims</th>
              <th>deviation</th>
              <th>gates open now</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const c = r.chain;
              const gates = c
                ? [
                    c.can_evaluate_now ? 'evaluate' : null,
                    c.can_settle_now ? 'settle' : null,
                    c.can_refund_zero_winner ? 'refund' : null,
                  ]
                    .filter(Boolean)
                    .join(', ') || 'none'
                : 'loading';
              return (
                <tr
                  key={r.id}
                  className={String(selected) === String(r.id) ? 'sel' : ''}
                  onClick={() => selectStudy(r.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{r.id}</td>
                  <td>
                    {r.info ? r.info.title : 'study ' + r.id}
                    <br />
                    <span style={{ color: 'var(--muted)' }}>
                      PI {short((r.info && r.info.pi) || '')}
                    </span>
                  </td>
                  <td>{c ? c.status : '-'}</td>
                  <td>
                    <BandBadge band={c ? c.band : ''} />
                  </td>
                  <td>{c ? c.claims : '-'}</td>
                  <td>{c ? c.deviation_bps + ' bps' : '-'}</td>
                  <td>{gates}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="hint">
          Status, band, claims and gates are read from the ledger. Titles and artifact links come
          from the published registry index, which the notebook treats as labels, never as authority.
        </p>

        <div className="spacer" />
        <h3 style={{ margin: '0 0 0.2rem', fontSize: '0.95rem' }}>Payable desk (soft fail, never revert)</h3>
        <p className="hint">
          Every payable entry below carries GEN with the call. If the ledger rejects the terms it
          credits the full value back to the sender instead of reverting, so a mistyped bond is never lost.
        </p>

        <Action label="Lock endowment principal" title="fund_endowment_payable" run={run} busy={busy} setBusy={setBusy} disabled={!wallet.address}>
          {({ run: go, busy: b }) => (
            <>
              <label className="hint">amount (GEN)</label>
              <input value={form.fundGen} onChange={set('fundGen')} />
              <div className="row" style={{ marginTop: '0.5rem' }}>
                <button disabled={b} onClick={() => go('fund_endowment_payable', [], Number(form.fundGen))}>
                  send and lock
                </button>
              </div>
            </>
          )}
        </Action>

        <Action label="Register replication bounty" title="register_study_bounty_payable" run={run} busy={busy} setBusy={setBusy} disabled={!wallet.address}>
          {({ run: go, busy: b }) => (
            <div className="sliders">
              <label>title<input value={form.title} onChange={set('title')} /></label>
              <label>paper artifact url<input value={form.artifact} onChange={set('artifact')} /></label>
              <label>target metric token<input value={form.target} onChange={set('target')} /></label>
              <label>reported baseline (bps, 250 grid)<input value={form.baseline} onChange={set('baseline')} /></label>
              <label>endowment (GEN)<input value={form.endowmentGen} onChange={set('endowmentGen')} /></label>
              <div className="row">
                <label style={{ flex: 1 }}>trial window s<input value={form.trialWindow} onChange={set('trialWindow')} /></label>
                <label style={{ flex: 1 }}>author window s<input value={form.authorWindow} onChange={set('authorWindow')} /></label>
                <label style={{ flex: 1 }}>audit timeout s<input value={form.timeoutWindow} onChange={set('timeoutWindow')} /></label>
              </div>
              <button
                className="go"
                disabled={b}
                onClick={() =>
                  go(
                    'register_study_bounty_payable',
                    [
                      form.title,
                      form.artifact,
                      form.target,
                      BigInt(form.baseline),
                      BigInt(Math.round(Number(form.endowmentGen) * E1)),
                      BigInt(form.trialWindow),
                      BigInt(form.authorWindow),
                      BigInt(form.timeoutWindow),
                    ],
                    Number(form.endowmentGen)
                  )
                }
              >
                register with endowment
              </button>
            </div>
          )}
        </Action>

        <Action label="Stake independent replication trial" title="stake_replication_trial_payable" run={run} busy={busy} setBusy={setBusy} disabled={!wallet.address}>
          {({ run: go, busy: b }) => (
            <div className="sliders">
              <div className="row">
                <label style={{ flex: 1 }}>study id<input value={form.studyId} onChange={set('studyId')} /></label>
                <label style={{ flex: 1 }}>bond (GEN)<input value={form.bondGen} onChange={set('bondGen')} /></label>
              </div>
              <div className="row">
                <label style={{ flex: 1 }}>replicated (bps)<input value={form.replicated} onChange={set('replicated')} /></label>
                <label style={{ flex: 1 }}>integrity (bps)<input value={form.integrity} onChange={set('integrity')} /></label>
              </div>
              <label>dataset sha256 checksum<input value={form.checksum} onChange={set('checksum')} /></label>
              <label>replication log url<input value={form.log} onChange={set('log')} /></label>
              <button
                className="go"
                disabled={b}
                onClick={() =>
                  go(
                    'stake_replication_trial_payable',
                    [BigInt(form.studyId), BigInt(form.replicated), BigInt(form.integrity), form.checksum, form.log],
                    Number(form.bondGen)
                  )
                }
              >
                stake bond and report
              </button>
            </div>
          )}
        </Action>

        <Action label="Deposit RLT into vault custody" title="deposit_rlt_custody" run={run} busy={busy} setBusy={setBusy} disabled={!wallet.address}>
          {({ run: go, busy: b }) => (
            <>
              <label className="hint">amount (RLT, after an approve on the token)</label>
              <input value={form.rltAmount} onChange={set('rltAmount')} />
              <div className="row" style={{ marginTop: '0.5rem' }}>
                <button disabled={b} onClick={() => go('deposit_rlt_custody', [BigInt(Math.round(Number(form.rltAmount) * E1))])}>
                  deposit
                </button>
              </div>
            </>
          )}
        </Action>

        <Action label="Refund drawer" title="claim_refundable_balance / withdraw_refund" run={run} busy={busy} setBusy={setBusy} disabled={!wallet.address}>
          {({ run: go, busy: b }) => (
            <>
              <div className="field">
                <span className="k">connected lab wallet</span>
                <span>{short(wallet.address)}</span>
              </div>
              <div className="field">
                <span className="k">GEN balance</span>
                <span>{wallet.balance === null ? 'unknown' : wallet.balance.toFixed(4)}</span>
              </div>
              <div className="field">
                <span className="k">outstanding soft-fail credit</span>
                <span>{(wallet.credit ?? 0).toFixed(4)} GEN</span>
              </div>
              <div className="field">
                <span className="k">RLT held</span>
                <span>{(wallet.rlt ?? 0).toFixed(2)}</span>
              </div>
              <div className="row" style={{ marginTop: '0.6rem' }}>
                <label style={{ flex: 1 }} className="hint">
                  withdraw partial (GEN)
                  <input value={form.withdrawGen} onChange={set('withdrawGen')} />
                </label>
              </div>
              <div className="row" style={{ marginTop: '0.5rem' }}>
                <button
                  disabled={b || !(Number(form.withdrawGen) > 0)}
                  onClick={() => go('withdraw_refund', [BigInt(Math.round(Number(form.withdrawGen) * E1))])}
                >
                  withdraw_refund
                </button>
                <button className="warn" disabled={b} onClick={() => go('claim_refundable_balance', [])}>
                  claim everything
                </button>
              </div>
            </>
          )}
        </Action>

        {receipt ? (
          <div className="proof" style={{ marginTop: '0.8rem' }}>
            {receipt.ok
              ? receipt.fnName + ' submitted\n' + receipt.hash + '\nwaiting for finalization, then the credit balance refreshes'
              : receipt.fnName + ' rejected locally\n' + receipt.error}
          </div>
        ) : null}
        {busy ? <p className="hint">signing and submitting on studionet...</p> : null}
        <p className="hint">
          pool {pool.toFixed(3)} GEN against reserve {reserve.toFixed(3)} GEN: {summary?.pool_covers_reserve ? 'covered' : 'SHORTFALL'}; credits outstanding {credits.toFixed(3)} GEN.
          Mode: {mode}.
        </p>
      </div>
    </section>
  );
}
