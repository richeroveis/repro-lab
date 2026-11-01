import React, { useEffect, useMemo, useState } from 'react';
import { EXPLORER_ADDRESS, LEDGER, NETWORK, RLT_TOKEN } from './chain.js';
import { useLedger, useWallet } from './useLedger.js';
import RegistryVault from './components/RegistryVault.jsx';
import DeviationMatrix from './components/DeviationMatrix.jsx';
import TranscriptDrawer from './components/TranscriptDrawer.jsx';

async function loadStatic(file) {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}${file}`, { cache: 'no-store' });
    return res.ok ? await res.json() : null;
  } catch (err) {
    return null;
  }
}

function WalletBar({ wallet, connectBurner, connectMetaMask, refreshWallet }) {
  return (
    <div className="row">
      <button onClick={connectBurner}>1 click burner lab wallet</button>
      <button onClick={connectMetaMask}>MetaMask</button>
      {wallet.address ? (
        <span className="stamp live">
          {wallet.kind} {wallet.address.slice(0, 10)}...{wallet.address.slice(-6)}
          {wallet.balance !== null ? ` | ${wallet.balance.toFixed(3)} GEN` : ''}
          {wallet.credit !== null ? ` | credit ${wallet.credit.toFixed(3)}` : ''}
        </span>
      ) : null}
      {wallet.address ? (
        <button onClick={refreshWallet} title="re-read balance and soft-fail credit">
          refresh
        </button>
      ) : null}
    </div>
  );
}

export default function App() {
  const ledger = useLedger();
  const [meta, setMeta] = useState(null);
  const [proofs, setProofs] = useState(null);
  const [now, setNow] = useState(Math.floor(Date.now() / 1000));
  const [preset, setPreset] = useState(null);
  const walletApi = useWallet();

  useEffect(() => {
    loadStatic('study-meta.json').then(setMeta);
    loadStatic('consensus-proof.json').then(setProofs);
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (ledger.selected && !ledger.card) ledger.selectStudy(ledger.selected);
  }, [ledger]);

  const stamp = useMemo(() => {
    if (ledger.mode === 'live') return { cls: 'live', text: 'live read from studionet' };
    if (ledger.mode === 'snapshot')
      return { cls: 'snapshot', text: 'published chain state at ' + ledger.snapshotAt };
    if (ledger.mode === 'connecting') return { cls: '', text: 'reading the ledger...' };
    return { cls: 'snapshot', text: 'ledger unreachable from this origin' };
  }, [ledger.mode, ledger.snapshotAt]);

  const card = ledger.card || { study_id: String(ledger.selected || ''), status: 'LOADING' };

  return (
    <div className="frame">
      <div className="masthead">
        <div className="row" style={{ gap: 18, alignItems: 'center' }}>
          <img className="insignia" src="./logo.png" alt="ReproLab insignia" width="72" height="72" />
          <div>
            <h1>ReproLab</h1>
            <div className="sub">
              Empirical replication notebook and peer-review ledger / GenLayer studionet
            </div>
          </div>
        </div>
        <div className="row">
          <span className={'stamp ' + stamp.cls}>{stamp.text}</span>
          <WalletBar {...walletApi} />
        </div>
      </div>

      <div className="strip">
        <div className="cell">
          <b style={{ wordBreak: 'break-all' }}>
            <a href={EXPLORER_ADDRESS(LEDGER)} target="_blank" rel="noreferrer">
              {LEDGER}
            </a>
          </b>
          <span>ledger contract, studio explorer</span>
        </div>
        <div className="cell">
          <b style={{ wordBreak: 'break-all' }}>
            <a href={EXPLORER_ADDRESS(RLT_TOKEN)} target="_blank" rel="noreferrer">
              {RLT_TOKEN}
            </a>
          </b>
          <span>RLT endowment token</span>
        </div>
        <div className="cell">
          <b>{NETWORK.chainId}</b>
          <span>chain id</span>
        </div>
        <div className="cell">
          <b>{new Date(now * 1000).toISOString().slice(0, 19)}Z</b>
          <span>lab clock</span>
        </div>
      </div>

      {ledger.error ? <p className="hint">{ledger.error}</p> : null}

      <details className="brief">
        <summary>Field brief: 50 seconds, burned-in subtitles and synthesized lab ambience</summary>
        <video
          controls
          preload="metadata"
          width="1280"
          height="720"
          src="./demo-video-subtitled.mp4"
          title="ReproLab demo brief"
        />
        <p className="hint">
          Every number in the brief is read from this deployment by
          scripts/compile_empirical_video_brief.py.
        </p>
      </details>

      <div className="grid">
        <div>
          <RegistryVault
            overview={ledger.overview || {}}
            summary={ledger.summary || {}}
            index={ledger.index || []}
            meta={meta}
            wallet={walletApi.wallet}
            refreshWallet={walletApi.refreshWallet}
            selected={ledger.selected}
            selectStudy={ledger.selectStudy}
            mode={ledger.mode}
          />
          <div className="spacer" />
          <TranscriptDrawer
            card={ledger.card}
            trials={ledger.trials}
            meta={meta}
            proofs={proofs}
            now={now}
            wallet={walletApi.wallet}
            refreshWallet={walletApi.refreshWallet}
            onLoadPreset={setPreset}
          />
        </div>
        <div>
          <DeviationMatrix card={ledger.card} preset={preset} />
        </div>
      </div>

      <footer className="colophon">
        <span>
          Verdict bands, reservations and refunds are enforced on chain by ReproLab. The workbench
          only previews them.
        </span>
        <span>
          <a href="./artifacts/drift-artifact.html">artifact set</a> /{' '}
          <a href="https://github.com/richeroveis/repro-lab">source</a>
        </span>
      </footer>
    </div>
  );
}
