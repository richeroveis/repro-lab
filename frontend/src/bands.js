// Verdict band math, kept in sync with contracts/repro_lab.py so the notebook
// can preview a ruling before a lab stakes a bond. The contract is authoritative.
import {
  EXACT_DEV_CAP_BPS,
  EXACT_INTEGRITY_FLOOR_BPS,
  GRID_BPS,
  INTEGRITY_BUCKET_GRID,
  MAX_BPS,
  PARTIAL_DEV_CAP_BPS,
  PARTIAL_GRANT_BPS,
} from './chain.js';

export const snapToGrid = (value) => {
  const v = Math.round(Number(value) || 0);
  return Math.min(MAX_BPS, Math.max(0, Math.round(v / GRID_BPS) * GRID_BPS));
};

export const integrityBucket = (value) =>
  Math.floor(Math.max(0, Number(value) || 0) / INTEGRITY_BUCKET_GRID) * INTEGRITY_BUCKET_GRID;

export const BAND_ORDER = [
  'EXACT_REPLICATION_VERIFIED',
  'PARTIAL_CONVERGENCE_TIER',
  'INCONCLUSIVE_VARIANCE_REFUND',
  'FABRICATED_DATA_SLASH',
];

export function ruleFor(input) {
  const baseline = snapToGrid(input.baselineBps);
  const replicated = snapToGrid(input.replicatedBps);
  const integrity = integrityBucket(input.integrityBps);
  const deviation = Math.abs(baseline - replicated);
  let band;
  if (input.fabrication) {
    band = 'FABRICATED_DATA_SLASH';
  } else if (deviation <= EXACT_DEV_CAP_BPS && integrity >= EXACT_INTEGRITY_FLOOR_BPS) {
    band = 'EXACT_REPLICATION_VERIFIED';
  } else if (deviation <= PARTIAL_DEV_CAP_BPS && input.methodologyValid) {
    band = 'PARTIAL_CONVERGENCE_TIER';
  } else {
    band = 'INCONCLUSIVE_VARIANCE_REFUND';
  }
  const endowment = BigInt(Math.floor(Number(input.endowmentGen) || 0) * 10 ** 18);
  const bond = BigInt(Math.floor(Number(input.bondGen) || 0) * 10 ** 18);
  let grant = 0n;
  let piRefund = 0n;
  let slash = 0n;
  if (band === 'EXACT_REPLICATION_VERIFIED') {
    grant = endowment;
  } else if (band === 'PARTIAL_CONVERGENCE_TIER') {
    grant = (endowment * BigInt(PARTIAL_GRANT_BPS)) / 10000n;
    piRefund = endowment - grant;
  } else if (band === 'INCONCLUSIVE_VARIANCE_REFUND') {
    piRefund = endowment;
  } else {
    piRefund = endowment;
    slash = bond;
  }
  return {
    band,
    baseline,
    replicated,
    integrity,
    deviation,
    grantGen: Number(grant) / 1e18,
    piRefundGen: Number(piRefund) / 1e18,
    slashGen: Number(slash) / 1e18,
  };
}

export const gen = (atto) => Number(BigInt(atto || '0')) / 1e18;

export const short = (address) =>
  !address ? 'no claimant' : `${address.slice(0, 6)}...${address.slice(-4)}`;

export function countdown(targetEpoch, nowEpoch) {
  if (!targetEpoch) return { label: 'not scheduled', done: false, seconds: 0 };
  const left = targetEpoch - nowEpoch;
  if (left <= 0) return { label: 'elapsed', done: true, seconds: 0 };
  const m = Math.floor(left / 60);
  const s = left % 60;
  return { label: `${m}m ${String(s).padStart(2, '0')}s`, done: false, seconds: left };
}
