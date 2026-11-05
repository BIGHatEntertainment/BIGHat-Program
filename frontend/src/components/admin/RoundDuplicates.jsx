import React, { useState } from 'react';
import { Copy, Loader2, Check, AlertTriangle } from 'lucide-react';
import api from '../../lib/api';

/**
 * v32.2.11: duplicate round files on this computer.
 * "Check" lists only CERTAIN duplicates (the same permanent ID, or identical questions and answers) and changes NOTHING.
 * "Move the extra copies aside" runs only after that same check. Files are MOVED to Files/_retired_duplicates, never deleted.
 */
const muted = '#8892b0';

export default function RoundDuplicates() {
  const [busy, setBusy] = useState('');
  const [res, setRes] = useState(null);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState('');

  const check = async () => {
    setBusy('check'); setErr(''); setDone(null);
    try { setRes((await api.roundDuplicatesCheck()).data); }
    catch (e) { setRes(null); setErr(e?.response?.data?.detail || 'The check could not run. Nothing was changed.'); }
    finally { setBusy(''); }
  };
  const retire = async () => {
    if (!res?.token) return;
    setBusy('retire'); setErr('');
    try {
      const r = (await api.roundDuplicatesRetire(res.token)).data;
      setDone(r);
      if (r.ok || r.error === 'changed') setRes(null);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not move the files. Nothing was deleted.'); }
    finally { setBusy(''); }
  };

  return (
    <div className="mt-3 pt-3 space-y-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }} data-testid="round-duplicates">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-semibold text-white">Duplicate round files</span>
        <button onClick={check} disabled={!!busy} data-testid="round-dup-check-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68', border: '1px solid rgba(251,221,104,0.35)' }}>
          {busy === 'check' ? <Loader2 size={14} className="animate-spin" /> : <Copy size={14} />} Check for duplicates
        </button>
      </div>
      <p className="text-xs" style={{ color: muted }}>
        Finds round files that are certainly the same round (the same permanent ID, or identical questions and answers). A file that only
        shares a name is never counted. Nothing changes until you confirm, and nothing is ever deleted.
      </p>

      {err && <p className="text-xs" style={{ color: '#fca5a5' }} data-testid="round-dup-error">{err}</p>}

      {res && (
        <div className="rounded-lg p-3 space-y-2" style={{ backgroundColor: 'rgba(20,27,80,0.6)' }} data-testid="round-dup-preview">
          <p className="text-sm" style={{ color: res.group_count ? '#e5edff' : '#4ade80' }} data-testid="round-dup-summary">{res.message}</p>
          {(res.groups || []).map((g, i) => (
            <div key={i} className="text-xs" data-testid="round-dup-group">
              <p style={{ color: '#4ade80' }}>Keep: {g.type} / {g.keep.file} <span style={{ color: muted }}>({g.basis})</span></p>
              <ul className="ml-3" style={{ color: '#cbd5f5' }}>
                {g.extras.map((r) => (
                  <li key={r.path}>{r.can_retire ? 'Move aside' : 'Stays'}: {r.file}{r.kept_because ? <span style={{ color: muted }}> ({r.kept_because})</span> : null}</li>
                ))}
              </ul>
            </div>
          ))}
          {res.can_retire > 0 && (
            <button onClick={retire} disabled={!!busy} data-testid="round-dup-retire-btn"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                    style={{ backgroundColor: '#fbdd68', color: '#0a0e27' }}>
              {busy === 'retire' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Move {res.can_retire} extra cop{res.can_retire === 1 ? 'y' : 'ies'} aside (not deleted)
            </button>
          )}
        </div>
      )}

      {done && (
        <p className="text-xs flex gap-1.5" style={{ color: done.ok ? '#4ade80' : '#fbbf24' }} data-testid="round-dup-done">
          {done.ok ? <Check size={14} /> : <AlertTriangle size={14} />}{done.message}
        </p>
      )}
    </div>
  );
}
