import React, { useEffect, useState } from 'react';
import { EXPLORER_TX } from '../chain.js';
import { countdown, short } from '../bands.js';
import { writeLedger } from '../useLedger.js';

const SEVEN = [
  ['verdict_band', 'band'],
  ['quantized_reported_baseline_bps', 'audited_baseline_bps'],
  ['quantized_replicated_score_bps', 'audited_replicated_bps'],
  ['dataset_integrity_bps', 'audited_integrity_bps'],
  ['derived_replicator_grant', 'derived_replicator_grant'],
  ['derived_pi_refund', 'derived_pi_refund'],
  ['derived_fraud_slash', 'derived_fraud_slash'],
];

function Clock({ label, epoch, now }) {
  const c = countdown(epoch, now);
  return (
    <div>
      <b className={c.done ? 'past' : 'soon'}>{epoch ? c.label : 'unset'}</b>
      {label}
    </div>
  );
}

export default function TranscriptDrawer({ card, trials, meta, proofs, now, onClose, wallet, refreshWallet, onLoadPreset }) {
  const [note, setNote] = useState('protocol frozen at the pinned commit, raw logs published');
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);

  useEffect(() => {
    setLog([]);
  }, [card?.study_id]);

  if (!card) {
    return (
      <section className="card">
        <header>
          <h2>Peer-Review Equivalence Transcript</h2>
          <span className="tag">safeguard drawer</span>
        </header>
        <div className="body">
          <p className="hint">Select a registry row to open the transcript for that study.</p>
        </div>
      </section>
    );
  }

  const id = BigInt(card.study_id);
  const info = meta ? meta[card.study_id] : null;

  async function act(label, fnName, args = [], valueGen = 0) {
    setBusy(true);
    try {
      const hash = await writeLedger(fnName, args, BigInt(Math.round(valueGen * 10 ** 18)));
      setLog((prev) => [`${label} submitted: ${hash}`, ...prev]);
      setTimeout(() => refreshWallet(), 12000);
    } catch (err) {
      setLog((prev) => [`${label} failed: ${String(err?.shortMessage || err?.message || err)}`, ...prev]);
    }
    setBusy(false);
  }

  const studyProofs = (proofs && proofs[card.study_id]) || [];

  return (
    <section className="card">
      <header>
        <h2>Peer-Review Equivalence Transcript</h2>
        <span className="tag">study {card.study_id}</span>
      </header>
      <div className="body">
        <h3 style={{ margin: 0, fontSize: '1rem' }}>{info ? info.title : 'study ' + card.study_id}</h3>
        <p className="hint">
          sponsor {short(card.pi_address || (info && info.pi))} / first replicating lab {short(card.first_claim_lab)} /
          status <b>{card.status}</b>
        </p>
        <div className="row" style={{ marginBottom: '0.7rem' }}>
          {info ? (
            <>
              <a href={info.artifact} target="_blank" rel="noreferrer">original artifact</a>
              <span className="hint">|</span>
              <a href={info.log} target="_blank" rel="noreferrer">replication log</a>
            </>
          ) : null}
        </div>

        <div className="countdowns">
          <Clock label="trial submission close" epoch={Number(card.trial_close_epoch)} now={now} />
          <Clock label="author response deadline" epoch={Number(card.author_response_deadline_epoch)} now={now} />
          <Clock label="peer challenge deadline" epoch={Number(card.peer_challenge_deadline_epoch)} now={now} />
          <Clock label="audit timeout" epoch={Number(card.audit_timeout_epoch)} now={now} />
        </div>

        <div className="spacer" />
        <h4 style={{ margin: '0 0 0.4rem', fontFamily: 'var(--mono)', fontSize: '0.72rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)' }}>
          Equivalence transcript: the seven fields validators must match exactly
        </h4>
        <table className="log">
          <thead>
            <tr>
              <th>consensus field</th>
              <th>bound value</th>
            </tr>
          </thead>
          <tbody>
            {SEVEN.map(([field, key]) => (
              <tr key={field}>
                <td>{field}</td>
                <td>{String(card[key] === undefined || card[key] === '' ? '-' : card[key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">
          Agreement is a veto rule, not a similarity score: one basis point of difference on any of the
          seven fields rejects the ruling and rotates the leader.
        </p>
        {onLoadPreset && card.band ? (
          <div className="row">
            <button
              onClick={() =>
                onLoadPreset({
                  baseline: Number(card.audited_baseline_bps || 0),
                  replicated: Number(card.audited_replicated_bps || 0),
                  integrity: Number(card.audited_integrity_bps || 0),
                  endowment: Number(card.endowment_atto || 10 ** 18) / 1e18,
                })
              }
            >
              load this ruling into the workbench
            </button>
          </div>
        ) : null}

        <div className="spacer" />
        <h4 className="hint" style={{ margin: 0, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Staked replication trials
        </h4>
        {(trials || []).length === 0 ? (
          <p className="hint">No lab has bonded a replication report for this study yet.</p>
        ) : (
          <table className="log">
            <thead>
              <tr>
                <th>lab</th>
                <th>bond</th>
                <th>replicated</th>
                <th>integrity</th>
                <th>checksum</th>
                <th>log</th>
              </tr>
            </thead>
            <tbody>
              {(trials || []).map((t, i) => (
                <tr key={i}>
                  <td>{short(t.lab_addr || t.lab)}</td>
                  <td>{(Number(t.bond_atto) / 1e18).toFixed(2)} GEN</td>
                  <td>{t.claimed_replicated_score_bps} bps</td>
                  <td>{t.claimed_dataset_integrity_bps} bps</td>
                  <td style={{ maxWidth: '180px', wordBreak: 'break-all' }}>{String(t.data_checksum_sha256).slice(0, 18)}...</td>
                  <td>
                    <a href={t.replication_log_url} target="_blank" rel="noreferrer">open</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="spacer" />
        <h4 className="hint" style={{ margin: 0, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Protocol safeguards
        </h4>
        <div className="field">
          <span className="k">reserve for this study (150 percent)</span>
          <span>{(Number(card.reserve_required_atto || 0) / 1e18).toFixed(3)} GEN</span>
        </div>
        <div className="field">
          <span className="k">pool covers the reserve</span>
          <span>{String(card.pool_covered)}</span>
        </div>
        <div className="field">
          <span className="k">author has responded</span>
          <span>{String(card.author_responded)}</span>
        </div>
        <div className="field">
          <span className="k">evaluable now / settleable now / refundable now</span>
          <span>
            {String(card.can_evaluate_now)} / {String(card.can_settle_now)} / {String(card.can_refund_zero_winner)}
          </span>
        </div>

        <div className="spacer" />
        <h4 className="hint" style={{ margin: 0, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Recorded consensus proofs
        </h4>
        {studyProofs.length === 0 ? (
          <p className="hint">No validator run has been recorded for this study in the published evidence set.</p>
        ) : (
          studyProofs.map((p, i) => (
            <div key={i} style={{ marginBottom: '0.6rem' }}>
              <div className="field">
                <span className="k">{p.method} at {p.at}</span>
                <span>{p.status_name} / {p.result_name} / {p.exec}</span>
              </div>
              <div className="proof">
                votes: {p.votes}
                {'\n'}tx: {p.hash}
                {'\n'}
                <a href={EXPLORER_TX(p.hash)} target="_blank" rel="noreferrer">
                  {EXPLORER_TX(p.hash)}
                </a>
              </div>
            </div>
          ))
        )}

        <div className="spacer" />
        <h4 className="hint" style={{ margin: 0, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
          Reviewer actions (signed by the connected wallet)
        </h4>
        <div className="row" style={{ marginTop: '0.5rem' }}>
          <button disabled={busy || !wallet.address} onClick={() => act('author response', 'submit_author_response', [id, note])}>
            submit author response
          </button>
          <button className="go" disabled={busy || !wallet.address} onClick={() => act('validator audit', 'evaluate_replication_trial', [id])}>
            request validator audit
          </button>
          <button disabled={busy || !wallet.address} onClick={() => act('settlement', 'settle_replication_grant', [id])}>
            settle grant
          </button>
          <button className="warn" disabled={busy || !wallet.address} onClick={() => act('challenge', 'challenge_replication_ruling_payable', [id, note], 1)}>
            challenge ruling (1 GEN bond)
          </button>
          <button disabled={busy || !wallet.address} onClick={() => act('zero winner refund', 'claim_unreplicated_or_expired_refund', [id])}>
            claim zero winner refund
          </button>
        </div>
        <label className="hint" style={{ display: 'block', marginTop: '0.6rem' }}>
          note attached to the response or challenge
          <input value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {log.length ? <div className="proof" style={{ marginTop: '0.7rem' }}>{log.join('\n\n')}</div> : null}
        <p className="hint">
          A challenge that arrives after the peer window, from a party to the dispute, or without the
          minimum bond is absorbed as a soft fail: the bond is credited back for withdrawal instead of
          reverted. {wallet.address ? '' : 'Connect a lab wallet to sign.'}
        </p>
        {onClose ? (
          <div className="row" style={{ marginTop: '0.8rem' }}>
            <button onClick={onClose}>close transcript</button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
