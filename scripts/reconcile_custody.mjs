// Reconciles every studionet transaction against the ledger's on-chain
// custody buckets, so docs/evidence.md can state the invariant with numbers.
// Read only: sends nothing and changes no state.
import fs from 'node:fs';

const LEDGER = '0xdC4D683437C797438b0F96bA526101286111d9eB';
const E1 = 10n ** 18n;

const rows = fs
  .readFileSync('evidence/_txs.jsonl', 'utf8')
  .split('\n')
  .filter(Boolean)
  .map((l) => JSON.parse(l));

const toLedger = rows.filter((r) => (r.contract || '').toLowerCase() === LEDGER.toLowerCase());
let inNative = 0n;
const byMethod = {};
for (const r of toLedger) {
  const v = BigInt(r.value_atto || '0');
  inNative += v;
  const key = `${r.method}|${r.exec}`;
  byMethod[key] = (byKey => byKey)(byMethod[key] || 0n) + v;
  if (v > 0n) {
    console.log(
      `${r.at.slice(0, 19)} ${(r.step || '').padEnd(28)} ${r.method.padEnd(36)}` +
        ` ${(Number(v) / 1).toFixed(4).padStart(8)} GEN  ${r.exec}`
    );
  }
}
console.log('\ntx rows total', rows.length, '| to ledger', toLedger.length, '| inbound native', gen(inNative));

function gen(wei) {
  return (Number(wei) / Number(E1)).toFixed(4);
}
