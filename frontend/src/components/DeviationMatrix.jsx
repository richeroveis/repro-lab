import React, { useEffect, useMemo, useState } from 'react';
import { BANDS, GRID_BPS, MAX_BPS } from '../chain.js';
import { BAND_ORDER, integrityBucket, ruleFor, snapToGrid } from '../bands.js';

const STEP = 500;
const CELLS = Math.floor(MAX_BPS / STEP) + 1;

function cellClass(baseline, replicated, integrity, methodologyValid, fabrication) {
  const r = ruleFor({
    baselineBps: baseline,
    replicatedBps: replicated,
    integrityBps: integrity,
    methodologyValid,
    fabrication,
    endowmentGen: 1,
    bondGen: 0.5,
  });
  if (r.band === 'EXACT_REPLICATION_VERIFIED') return 'exact';
  if (r.band === 'PARTIAL_CONVERGENCE_TIER') return 'partial';
  if (r.band === 'FABRICATED_DATA_SLASH') return 'fraud';
  return 'inconclusive';
}

export default function DeviationMatrix({ card, preset }) {
  const [baseline, setBaseline] = useState(5250);
  const [replicated, setReplicated] = useState(5250);
  const [integrity, setIntegrity] = useState(9250);
  const [methodologyValid, setMethodology] = useState(true);
  const [fabrication, setFabrication] = useState(false);
  const [endowment, setEndowment] = useState(1);

  useEffect(() => {
    if (!preset) return;
    setBaseline(Number(preset.baseline) || 0);
    setReplicated(Number(preset.replicated) || 0);
    setIntegrity(Number(preset.integrity) || 0);
    setFabrication(false);
    setMethodology(true);
    if (preset.endowment) setEndowment(Number(preset.endowment));
  }, [preset]);

  const verdict = useMemo(
    () =>
      ruleFor({
        baselineBps: baseline,
        replicatedBps: replicated,
        integrityBps: integrity,
        methodologyValid,
        fabrication,
        endowmentGen: endowment,
        bondGen: endowment / 2,
      }),
    [baseline, replicated, integrity, methodologyValid, fabrication, endowment]
  );

  const pinnedRow = Math.round(baseline / STEP);
  const pinnedCol = Math.round(replicated / STEP);

  const cells = useMemo(() => {
    const out = [];
    for (let row = 0; row < CELLS; row += 1) {
      for (let col = 0; col < CELLS; col += 1) {
        const cls = cellClass(row * STEP, col * STEP, integrity, methodologyValid, fabrication);
        const pin = row === pinnedRow && col === pinnedCol;
        out.push(<i key={row + '-' + col} className={cls + (pin ? ' pin' : '')} title={`baseline ${row * STEP} / replicated ${col * STEP}`} />);
      }
    }
    return out;
  }, [integrity, methodologyValid, fabrication, pinnedRow, pinnedCol]);

  const onChain = card && card.status !== 'NOT_FOUND' ? card : null;

  return (
    <section className="card">
      <header>
        <h2>Statistical Convergence and Effect-Size Deviation Matrix</h2>
        <span className="tag">250 bps grid</span>
      </header>
      <div className="body">
        <div className="sliders">
          <label>
            reported baseline, quantized ({snapToGrid(baseline)} bps)
            <input type="range" min={0} max={MAX_BPS} step={GRID_BPS} value={baseline} onChange={(e) => setBaseline(Number(e.target.value))} />
          </label>
          <label>
            replicated convergence score ({snapToGrid(replicated)} bps)
            <input type="range" min={0} max={MAX_BPS} step={GRID_BPS} value={replicated} onChange={(e) => setReplicated(Number(e.target.value))} />
          </label>
          <label>
            dataset checksum integrity ({integrity} bps, bucket {integrityBucket(integrity)} bps)
            <input type="range" min={0} max={MAX_BPS} step={GRID_BPS} value={integrity} onChange={(e) => setIntegrity(Number(e.target.value))} />
          </label>
          <label>
            endowment under reservation ({endowment.toFixed(2)} GEN)
            <input type="range" min={1} max={20} step={0.5} value={endowment} onChange={(e) => setEndowment(Number(e.target.value))} />
          </label>
          <div className="checks">
            <label>
              <input type="checkbox" checked={methodologyValid} onChange={(e) => setMethodology(e.target.checked)} /> methodology valid
            </label>
            <label>
              <input type="checkbox" checked={fabrication} onChange={(e) => setFabrication(e.target.checked)} /> fabrication detected
            </label>
          </div>
        </div>

        <div className="matrix">{cells}</div>
        <div className="legend">
          <span><i className="exact" style={{ background: 'var(--emerald)' }} />exact verified</span>
          <span><i style={{ background: 'var(--cyan)' }} />partial convergence</span>
          <span><i style={{ background: '#35507a' }} />inconclusive refund</span>
          <span><i style={{ background: 'var(--rose)' }} />fabricated slash</span>
          <span>rows: reported baseline, columns: replicated score</span>
        </div>

        <div className="verdict">
          <h3>
            Preview ruling: <span className={'band ' + (BANDS[verdict.band]?.tone || 'none')}>{verdict.band}</span>
          </h3>
          <p className="hint">{BANDS[verdict.band]?.blurb}</p>
          <div className="nums">
            <div>
              <b>{verdict.deviation} bps</b>
              <span>deviation</span>
            </div>
            <div>
              <b>{verdict.integrity} bps</b>
              <span>integrity bucket</span>
            </div>
            <div>
              <b>{verdict.grantGen.toFixed(3)} GEN</b>
              <span>replicator grant</span>
            </div>
            <div>
              <b>{verdict.piRefundGen.toFixed(3)} GEN</b>
              <span>principal to sponsor</span>
            </div>
            <div>
              <b>{verdict.slashGen.toFixed(3)} GEN</b>
              <span>offending bond slash</span>
            </div>
          </div>
        </div>

        <div className="spacer" />
        {onChain ? (
          <div>
            <h3 style={{ margin: '0 0 0.3rem', fontSize: '0.95rem' }}>Consensus-bound ruling on chain (study {onChain.study_id})</h3>
            <div className="field"><span className="k">verdict band</span><span>{onChain.band || 'not evaluated'}</span></div>
            <div className="field"><span className="k">quantized reported baseline</span><span>{onChain.audited_baseline_bps || 0} bps</span></div>
            <div className="field"><span className="k">quantized replicated score</span><span>{onChain.audited_replicated_bps || 0} bps</span></div>
            <div className="field"><span className="k">dataset integrity</span><span>{onChain.audited_integrity_bps || 0} bps</span></div>
            <div className="field"><span className="k">derived replicator grant</span><span>{(Number(onChain.derived_replicator_grant || 0) / 1e18).toFixed(3)} GEN</span></div>
            <div className="field"><span className="k">derived sponsor refund</span><span>{(Number(onChain.derived_pi_refund || 0) / 1e18).toFixed(3)} GEN</span></div>
            <div className="field"><span className="k">derived fraud slash</span><span>{(Number(onChain.derived_fraud_slash || 0) / 1e18).toFixed(3)} GEN</span></div>
            <div className="row" style={{ marginTop: '0.6rem' }}>
              <span className="hint">
                preview deviation {verdict.deviation} bps vs on chain {onChain.deviation_bps} bps
              </span>
            </div>
          </div>
        ) : (
          <p className="hint">Open a registry row to compare the workbench against the ruling the validators bound on chain.</p>
        )}
        <p className="hint">
          The matrix is a planning tool. Only the validator consensus inside
          <code> evaluate_replication_trial</code> binds a band, and it must agree on all seven
          decision fields: {BAND_ORDER.length} bands, one grid, no tolerance.
        </p>
      </div>
    </section>
  );
}
