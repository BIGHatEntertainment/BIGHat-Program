import React, { useState } from 'react';
import { Images, Loader2, Check, AlertTriangle } from 'lucide-react';
import api from '../../lib/api';

/**
 * v32.2.12: make this computer's Branding images and Round overlays match BIG Hat Cloud (only when the Cloud is linked).
 * New and changed pictures arrive on their own. "Check" lists the pictures the Cloud no longer has, and changes NOTHING.
 * "Remove" runs only after that same check. Pictures you added yourself on this computer are never removed.
 */
const muted = '#8892b0';

export default function PictureMatch() {
  const [busy, setBusy] = useState('');
  const [res, setRes] = useState(null);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState('');

  const check = async () => {
    setBusy('check'); setErr(''); setDone(null);
    try { setRes((await api.picturesCheck()).data); }
    catch (e) { setRes(null); setErr(e?.response?.data?.detail || 'The check could not run. Nothing was changed.'); }
    finally { setBusy(''); }
  };
  const remove = async () => {
    if (!res?.token) return;
    setBusy('remove'); setErr('');
    try {
      const r = (await api.picturesRemove(res.token)).data;
      setDone(r);
      if (r.ok || r.error === 'changed') setRes(null);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not remove the pictures. Nothing was changed.'); }
    finally { setBusy(''); }
  };

  return (
    <div className="mt-3 pt-3 space-y-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }} data-testid="picture-match">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-semibold text-white">Match the Cloud pictures</span>
        <button onClick={check} disabled={!!busy} data-testid="picture-check-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68', border: '1px solid rgba(251,221,104,0.35)' }}>
          {busy === 'check' ? <Loader2 size={14} className="animate-spin" /> : <Images size={14} />} Check branding images and overlays
        </button>
      </div>
      <p className="text-xs" style={{ color: muted }}>
        New and changed Branding images and Round overlays arrive from the Cloud on their own. This shows the ones the Cloud no longer has.
        Nothing is removed until you confirm, and pictures you added yourself on this computer are never removed.
      </p>

      {err && <p className="text-xs" style={{ color: '#fca5a5' }} data-testid="picture-error">{err}</p>}
      {res && res.ok === false && <p className="text-xs flex gap-1.5" style={{ color: '#fbbf24' }} data-testid="picture-problem"><AlertTriangle size={14} />{res.message}</p>}

      {res && res.ok && (
        <div className="rounded-lg p-3 space-y-2" style={{ backgroundColor: 'rgba(20,27,80,0.6)' }} data-testid="picture-preview">
          <p className="text-sm" style={{ color: res.can_remove ? '#e5edff' : '#4ade80' }} data-testid="picture-summary">{res.message}</p>
          {(res.remove || []).length > 0 && (
            <ul className="text-xs space-y-0.5 max-h-40 overflow-auto" style={{ color: '#cbd5f5' }} data-testid="picture-remove-list">
              {res.remove.map((r) => <li key={`${r.location_id}-${r.id}`}>{r.venue} · {r.kind === 'overlay' ? 'Overlay' : 'Branding'} · {r.file}</li>)}
            </ul>
          )}
          {(res.kept || []).length > 0 && (
            <div data-testid="picture-kept">
              <p className="text-xs font-semibold" style={{ color: '#fbbf24' }}>Not removed ({res.kept.length})</p>
              <ul className="text-xs space-y-0.5 max-h-28 overflow-auto" style={{ color: muted }}>
                {res.kept.map((r) => <li key={`${r.id}`}>{r.venue} · {r.file}: {r.why}</li>)}
              </ul>
            </div>
          )}
          {res.can_remove > 0 && (
            <button onClick={remove} disabled={!!busy} data-testid="picture-remove-btn"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                    style={{ backgroundColor: '#fbdd68', color: '#0a0e27' }}>
              {busy === 'remove' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Remove {res.can_remove} picture{res.can_remove === 1 ? '' : 's'} (a backup is saved first)
            </button>
          )}
        </div>
      )}

      {done && (
        <p className="text-xs flex gap-1.5" style={{ color: done.ok ? '#4ade80' : '#fbbf24' }} data-testid="picture-done">
          {done.ok ? <Check size={14} /> : <AlertTriangle size={14} />}{done.message}
        </p>
      )}
    </div>
  );
}
