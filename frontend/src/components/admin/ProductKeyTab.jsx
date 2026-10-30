import React, { useEffect, useRef, useState } from 'react';
import api from '../../lib/api';
import { useNative } from '../../context/NativeContext';
import { KeyRound, CheckCircle2, Lock, Loader2, AlertTriangle } from 'lucide-react';

const ADDON_LABELS = { music_bingo: 'Music Bingo', karaoke: 'Karaoke' };

// v32.2.5: what to tell the owner when the license server has not confirmed this program's key yet.
const PROBLEMS = {
  unknown_key: "The license server does not know that key. Check it for typos, or contact support@bighat.live if it is new.",
  invalid_key: "The license server does not know that key. Check it for typos, or contact support@bighat.live if it is new.",
  hwid_not_activated: "This computer is not registered for that key yet.",
};
const problemText = (p) => {
  if (!p) return '';
  if (PROBLEMS[p]) return PROBLEMS[p];
  if (String(p).startsWith('seat_limit_reached')) return 'All seats on this license are in use. Free one from another computer first, then enter the key again.';
  if (String(p).startsWith('revoked')) return 'This license has been revoked. Please contact support@bighat.live.';
  return `The license server did not confirm it (${p}).`;
};

function errorText(err) {
  const d = err?.response?.data?.detail;
  if (d && typeof d === 'object') return d.message || d.error || 'That key was not accepted.';
  if (err?.response?.status === 403) return 'Only the master admin can enter product keys.';
  return typeof d === 'string' ? d : 'Could not reach the license server. Check the internet connection and try again.';
}

export default function ProductKeyTab({ setError, setSuccess }) {
  const { refresh } = useNative();
  const [status, setStatus] = useState(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);

  const load = async () => {
    try {
      const res = await api.getProductKeys();
      setStatus(res.data);
    } catch (err) {
      setError(errorText(err));
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!key.trim() || sending.current) return;
    sending.current = true;
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      const res = await api.addProductKey(key.trim());
      setStatus(res.data);
      setKey('');
      // refresh the app-wide license info so the dashboard cards unlock right away
      try { await refresh(); } catch (e) { /* the key itself was accepted */ }
      setSuccess(res.data?.verified ? 'Product key accepted and verified. Your program has been updated.' : 'Product key accepted. Your program has been updated.');
    } catch (err) {
      setError(errorText(err));
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };

  const addons = status?.addons || {};
  return (
    <div className="space-y-6" data-testid="product-key-tab">
      {status?.needs_verification && (
        <div className="rounded-xl p-4 flex gap-3" data-testid="product-key-unverified"
             style={{ backgroundColor: 'rgba(251, 191, 36, 0.10)', border: '1px solid rgba(251, 191, 36, 0.4)' }}>
          <AlertTriangle size={20} style={{ color: '#fbbf24', flexShrink: 0 }} />
          <div className="text-sm space-y-1" style={{ color: '#fde68a' }}>
            <p className="font-semibold text-white">This program's key has not been verified yet</p>
            <p>
              Setup was finished without checking the key with the license server, so some features stay locked and this program cannot be linked to BIG Hat Cloud.
              Type your product key below and press Unlock while this computer is online. Use the key from your purchase email.
            </p>
            {status.verify_problem && <p data-testid="product-key-problem" style={{ color: '#fca5a5' }}>{problemText(status.verify_problem)}</p>}
          </div>
        </div>
      )}
      <form onSubmit={submit} className="rounded-xl p-5 space-y-3"
            style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <KeyRound size={18} style={{ color: '#fbdd68' }} /> Enter a Product Key
        </h3>
        <p className="text-sm" style={{ color: '#8892b0' }}>
          {status?.needs_verification
            ? 'Paste your product key to activate this program. This computer needs an internet connection for this step.'
            : 'Bought a new add-on? Paste the product key you received and the new area unlocks. This computer needs an internet connection for this step.'}
        </p>
        <div className="flex gap-2">
          <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="BHE-XXXX-XXXX-XXXX-XXXX"
                 className="flex-1 px-3 py-2 rounded-lg text-white"
                 style={{ backgroundColor: '#000e2a', border: '1px solid rgba(251, 221, 104, 0.2)' }}
                 data-testid="product-key-input" autoComplete="off" spellCheck={false} />
          <button type="submit" disabled={busy || !key.trim()}
                  className="px-4 py-2 rounded-lg font-semibold flex items-center gap-2"
                  style={{ backgroundColor: '#fbdd68', color: '#000e2a', opacity: busy || !key.trim() ? 0.5 : 1 }}
                  data-testid="product-key-submit">
            {busy && <Loader2 size={16} className="animate-spin" />} Unlock
          </button>
        </div>
      </form>

      <div className="rounded-xl p-5 space-y-3"
           style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
        <h3 className="text-lg font-bold text-white">What you have unlocked</h3>
        {!status ? (
          <p className="text-sm" style={{ color: '#8892b0' }}>Loading...</p>
        ) : (
          <ul className="space-y-2" data-testid="product-key-list">
            {[['standalone', 'BIG Hat Program', status.owns_standalone],
              ...Object.keys(ADDON_LABELS).map((k) => [k, ADDON_LABELS[k], addons[k]])].map(([id, label, on]) => (
              <li key={id} className="flex items-center gap-2 text-sm" data-testid={`product-${id}`}
                  style={{ color: on ? '#4ade80' : '#8892b0' }}>
                {on ? <CheckCircle2 size={16} /> : <Lock size={16} />}
                {label}: {on ? 'Unlocked' : 'Locked'}
              </li>
            ))}
          </ul>
        )}
        {status?.main_key && (
          <p className="text-xs" style={{ color: '#8892b0' }}>
            Main key: {status.main_key}{status.verified ? ' (verified)' : ' (not verified yet)'}
          </p>
        )}
        {(status?.extra_keys || []).map((e) => (
          <p key={e.key} className="text-xs" style={{ color: '#8892b0' }}>
            Extra key {e.key}{e.unlocks?.length ? ` (${e.unlocks.map((u) => ADDON_LABELS[u] || u).join(', ')})` : ''}
          </p>
        ))}
      </div>
    </div>
  );
}
