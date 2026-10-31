// Chain access for the notebook. Initial load performs at most four reads:
// overview, reproducibility index and custody summary together, then a study
// card plus its trial book once a registry row is opened. If the browser cannot
// reach the RPC (the studionet endpoint sends no CORS headers for a static
// origin) the notebook falls back to the snapshot published with the build and
// labels the mode, so the numbers on screen are never presented as live.
import { useCallback, useEffect, useRef, useState } from 'react';
import { createAccount, createClient, chains, generatePrivateKey } from 'genlayer-js';
import { LEDGER, NETWORK, RLT_TOKEN } from './chain.js';

const READ_TIMEOUT = 9000;

// A throwaway signer is enough for eth_call style reads.
const reader = createAccount(generatePrivateKey());

// The active signer for writes: a burner Account object or a MetaMask address.
const signer = { current: null };

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('rpc timeout')), ms)),
  ]);
}

export function clientFor(account) {
  return createClient({ chain: chains.studionet, account: account || reader });
}

export async function readLedger(functionName, args = [], account) {
  const client = clientFor(account || reader);
  return withTimeout(
    client.readContract({ address: LEDGER, functionName, args, account: account || reader }),
    READ_TIMEOUT
  );
}

export async function writeLedger(functionName, args = [], value = 0n) {
  if (!signer.current) throw new Error('connect a lab wallet first');
  const account = signer.current;
  const client = clientFor(account);
  return client.writeContract({
    account: typeof account === 'string' ? undefined : account,
    address: LEDGER,
    functionName,
    args,
    value,
  });
}

async function fetchSnapshot() {
  const res = await fetch(`${import.meta.env.BASE_URL}snapshot.json`, { cache: 'no-store' });
  if (!res.ok) throw new Error('no published snapshot');
  return res.json();
}

export function useLedger() {
  const [state, setState] = useState({
    mode: 'connecting',
    overview: null,
    index: [],
    summary: null,
    card: null,
    trials: [],
    selected: null,
    error: '',
    snapshotAt: '',
  });
  const modeRef = useRef('connecting');

  const load = useCallback(async () => {
    try {
      const [overview, index, summary] = await Promise.all([
        readLedger('get_lab_overview'),
        readLedger('get_reproducibility_index', [0n, 10n]),
        readLedger('get_custody_accounting_summary'),
      ]);
      modeRef.current = 'live';
      setState((prev) => ({
        ...prev,
        mode: 'live',
        overview,
        index,
        summary,
        error: '',
        selected: prev.selected ?? Number(index[0]?.study_id ?? 1),
      }));
    } catch (err) {
      try {
        const snap = await fetchSnapshot();
        modeRef.current = 'snapshot';
        setState((prev) => ({
          ...prev,
          mode: 'snapshot',
          overview: snap.overview,
          index: snap.index,
          summary: snap.summary,
          snapshotAt: snap.fetched_at,
          error: 'live read failed (' + String(err.message || err) + '), showing the published chain state',
          selected: prev.selected ?? Number(snap.index[0]?.study_id ?? 1),
        }));
      } catch (inner) {
        modeRef.current = 'offline';
        setState((prev) => ({ ...prev, mode: 'offline', error: String(err.message || err) }));
      }
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectStudy = useCallback(
    async (studyId) => {
      const id = Number(studyId);
      setState((prev) => ({ ...prev, selected: id, card: null, trials: [] }));
      if (modeRef.current !== 'live') {
        const snap = await fetchSnapshot().catch(() => null);
        if (snap) {
          setState((prev) => ({
            ...prev,
            card: snap.cards[String(id)] || null,
            trials: snap.trials[String(id)] || [],
          }));
        }
        return;
      }
      try {
        const [card, trials] = await Promise.all([
          readLedger('get_study_card', [BigInt(id)]),
          readLedger('get_trial_book', [BigInt(id)]),
        ]);
        setState((prev) => ({ ...prev, card, trials }));
      } catch (err) {
        setState((prev) => ({ ...prev, error: String(err.message || err) }));
      }
    },
    []
  );

  return { ...state, reload: load, selectStudy };
}

export function useWallet(onChange) {
  const [wallet, setWallet] = useState({
    kind: null,
    address: null,
    balance: null,
    credit: null,
    rlt: null,
    note: 'read only mode: connect a lab wallet to stake bonds or claim refunds',
  });

  const refresh = useCallback(async () => {
    const account = signer.current;
    if (!account) return;
    const address = typeof account === 'string' ? account : account.address;
    try {
      const client = clientFor(account);
      const [balance, credit, rlt] = await Promise.all([
        withTimeout(client.getBalance({ address }), READ_TIMEOUT),
        withTimeout(
          client.readContract({
            address: LEDGER,
            functionName: 'get_refundable_balance',
            args: [address],
            account: typeof account === 'string' ? undefined : account,
          }),
          READ_TIMEOUT
        ),
        withTimeout(
          client.readContract({
            address: RLT_TOKEN,
            functionName: 'balanceOf',
            args: [address],
            account: typeof account === 'string' ? undefined : account,
          }),
          READ_TIMEOUT
        ),
      ]);
      setWallet((prev) => ({
        ...prev,
        address,
        balance: Number(BigInt(balance)) / 1e18,
        credit: Number(BigInt(credit)) / 1e18,
        rlt: Number(BigInt(rlt)) / 1e18,
      }));
      if (onChange) onChange(address);
    } catch (err) {
      setWallet((prev) => ({ ...prev, note: 'wallet read failed: ' + String(err.message || err) }));
    }
  }, [onChange]);

  const connectBurner = useCallback(async () => {
    let key = sessionStorage.getItem('reprolab.burner');
    if (!key) {
      key = generatePrivateKey();
      sessionStorage.setItem('reprolab.burner', key);
    }
    signer.current = createAccount(key);
    setWallet((prev) => ({
      ...prev,
      kind: 'burner',
      note: 'burner lab wallet stays in this tab only; fund it with studionet GEN before staking',
    }));
    await refresh();
  }, [refresh]);

  const connectMetaMask = useCallback(async () => {
    if (!window.ethereum) {
      setWallet((prev) => ({ ...prev, note: 'no injected wallet detected in this browser' }));
      return;
    }
    try {
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      const address = accounts[0];
      const hexChain = '0x' + NETWORK.chainId.toString(16);
      try {
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: hexChain }],
        });
      } catch (switchError) {
        if (switchError?.code !== 4902) throw switchError;
        await window.ethereum.request({
          method: 'wallet_addEthereumChain',
          params: [
            {
              chainId: hexChain,
              chainName: NETWORK.name,
              nativeCurrency: { name: 'GEN', symbol: 'GEN', decimals: 18 },
              rpcUrls: [NETWORK.rpc],
              blockExplorerUrls: [NETWORK.explorer],
            },
          ],
        });
      }
      signer.current = address;
      setWallet((prev) => ({
        ...prev,
        kind: 'metamask',
        note: 'MetaMask connected on studionet; writes are signed by the extension',
      }));
      await refresh();
    } catch (err) {
      setWallet((prev) => ({ ...prev, note: 'MetaMask setup interrupted: ' + String(err.message || err) }));
    }
  }, [refresh]);

  return { wallet, connectBurner, connectMetaMask, refreshWallet: refresh };
}
