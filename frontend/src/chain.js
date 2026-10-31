// Chain constants for the ReproLab notebook. Redeploying the ledger changes the
// address, so this is the only file that has to be touched.
export const LEDGER = '0xdC4D683437C797438b0F96bA526101286111d9eB';
export const RLT_TOKEN = '0xbc813AF4E82072b063e5a925FdFAdf721a62800e';
export const NETWORK = {
  name: 'studionet',
  chainId: 61999,
  rpc: 'https://studio.genlayer.com/api',
  explorer: 'https://genlayer-explorer.vercel.app',
};
export const EXPLORER_TX = (hash) => `${NETWORK.explorer}/tx/${hash}`;

// Verdict grid constants, mirrored from contracts/repro_lab.py so the
// workbench can preview a ruling before a lab spends a bond.
export const GRID_BPS = 250;
export const MAX_BPS = 10000;
export const EXACT_DEV_CAP_BPS = 250;
export const EXACT_INTEGRITY_FLOOR_BPS = 9000;
export const PARTIAL_DEV_CAP_BPS = 1000;
export const PARTIAL_GRANT_BPS = 6000;
export const INTEGRITY_BUCKET_GRID = 1000;
export const RESERVE_BPS = 15000;

export const BANDS = {
  EXACT_REPLICATION_VERIFIED: {
    tone: 'verified',
    blurb: 'Deviation at or under 250 bps with integrity at or above 9000 bps.',
  },
  PARTIAL_CONVERGENCE_TIER: {
    tone: 'partial',
    blurb: 'Deviation at or under 1000 bps with valid methodology: 60 percent grant.',
  },
  INCONCLUSIVE_VARIANCE_REFUND: {
    tone: 'variance',
    blurb: 'Environmental or hardware variance without fabrication: full refund.',
  },
  FABRICATED_DATA_SLASH: {
    tone: 'fraud',
    blurb: 'Checksum tampering, p-hacking or synthetic logs: bond slashed.',
  },
};
