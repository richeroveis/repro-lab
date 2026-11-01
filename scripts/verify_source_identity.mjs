// Rule 11 check: the same contract source must be identical in four places.
//
//   1. the local working tree file
//   2. the git blob in HEAD
//   3. the GitHub raw URL of the pushed commit
//   4. the code stored on chain by the studionet deployment
//
// usage: node scripts/verify_source_identity.mjs [contractFile] [address]
//        node scripts/verify_source_identity.mjs all
import crypto from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { createClient, chains } from 'genlayer-js';

const RAW_BASE = 'https://raw.githubusercontent.com/richeroveis/repro-lab/main/';
const PAIRS = [
  ['contracts/repro_lab.py', '0xdC4D683437C797438b0F96bA526101286111d9eB'],
  ['contracts/rlt_token.py', '0xbc813AF4E82072b063e5a925FdFAdf721a62800e'],
];

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const asBytes = (value) => {
  if (!value) return null;
  if (Buffer.isBuffer(value)) return value;
  if (Array.isArray(value)) return Buffer.from(value);
  if (typeof value === 'string') {
    if (value.startsWith('0x')) return Buffer.from(value.slice(2), 'hex');
    return Buffer.from(value, 'utf8');
  }
  if (value.type === 'Buffer' && Array.isArray(value.data)) return Buffer.from(value.data);
  return null;
};

async function onChainCode(client, address) {
  const tries = [
    () => client.getContractCode({ address }),
    () => client.request({ method: 'gen_getContractCode', params: [address, 'latest'] }),
    () => client.request({ method: 'gen_getContractCode', params: [{ contract_address: address }] }),
    () => client.getBytecode({ address }),
  ];
  for (const call of tries) {
    try {
      const raw = await call();
      const bytes = asBytes(raw?.result ?? raw);
      if (bytes && bytes.length > 32) return bytes;
    } catch (err) {
      // studionet currently rejects gen_getContractCode server side, so fall
      // through to the CLI, which reads the same state through its own path.
    }
  }
  try {
    // Windows resolves the global `genlayer` shim only through a shell.
    const res = spawnSync('genlayer', ['code', address], { encoding: 'buffer', shell: true, maxBuffer: 16 * 1024 * 1024 });
    if (res.error || res.status !== 0) return null;
    const text = res.stdout
      .toString('utf8')
      .replace(/\r\n/g, '\n')
      .replace(/\u001b\[[0-9;]*m/g, '')
      .replace(/^[\s\S]*?(?=# \{ "Depends")/, '')
      .replace(/\s+$/, '') + '\n';
    return text.length > 200 ? Buffer.from(text, 'utf8') : null;
  } catch (err) {
    return null;
  }
}

async function check(file, address) {
  const local = fs.readFileSync(file).toString().replace(/\r\n/g, '\n');
  const localBuf = Buffer.from(local, 'utf8');
  const blobRef = execFileSync('git', ['ls-files', '-s', file], { encoding: 'utf8' }).trim().split(/\s+/)[1];
  const blob = blobRef
    ? execFileSync('git', ['cat-file', 'blob', blobRef])
    : null;
  const raw = await fetch(RAW_BASE + file).then((r) => (r.ok ? r.arrayBuffer() : null));
  const rawBuf = raw ? Buffer.from(raw) : null;
  const client = createClient({ chain: chains.studionet });
  const chainBuf = await onChainCode(client, address);

  const hashes = {
    local: sha(localBuf),
    gitBlob: blob ? sha(blob) : 'unavailable',
    githubRaw: rawBuf ? sha(rawBuf) : 'unavailable',
    onChain: chainBuf ? sha(chainBuf) : 'unavailable',
  };
  const sizes = {
    local: localBuf.length,
    gitBlob: blob ? blob.length : 0,
    githubRaw: rawBuf ? rawBuf.length : 0,
    onChain: chainBuf ? chainBuf.length : 0,
  };
  const values = Object.values(hashes);
  const identical = values.every((h) => h === hashes.local);
  console.log(JSON.stringify({ file, address, hashes, sizes, fourWayIdentical: identical }, null, 2));
  if (!identical) {
    console.log('MISMATCH details:');
    if (chainBuf) fs.writeFileSync('evidence/onchain_' + file.split('/').pop(), chainBuf);
    if (rawBuf) fs.writeFileSync('evidence/raw_' + file.split('/').pop(), rawBuf);
  }
  return identical;
}

const arg = process.argv[2] || 'all';
const list = arg === 'all' ? PAIRS : [[arg, process.argv[3]]];
let ok = true;
for (const [file, address] of list) {
  ok = (await check(file, address)) && ok;
}
process.exit(ok ? 0 : 1);
