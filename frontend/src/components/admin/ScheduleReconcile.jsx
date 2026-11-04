import React, { useState } from 'react';
import { CalendarCheck, Loader2, Check, AlertTriangle } from 'lucide-react';
import api from '../../lib/api';

/**
 * v32.2.11: "Update schedule from the Cloud".
 * Step 1 "Check" reads the Cloud's complete schedule and compares it with this PC. It changes NOTHING and lists what would happen.
 * Step 2 "Apply" runs only after the host confirms that same check. A backup is saved first.
 */
const muted = '#8892b0';
const Group = ({ title, rows, color, testid, empty }) => (
  rows && rows.length > 0 ? (
    <div data-testid={testid}>
      <p className="text-xs font-semibold mb-1" style={{ color }}>{title} ({rows.length})</p>
      <ul className="text-xs space-y-0.5 max-h-40 overflow-auto" style={{ color: '#cbd5f5' }}>
        {rows.map((r) => (
          <li key={r.cloud_id}>{(r.date || '').replace('T', ' ')} · {r.event_type} · {r.title || '(no title)'}{r.why ? <span style={{ color: muted }}> — {r.why}</span> : null}</li>
        ))}
      </ul>
    </div>
  ) : null
);

export default function ScheduleReconcile({ onDone }) {
  const [busy, setBusy] = useState('');
  const [res, setRes] = useState(null);       // the last check
  const [done, setDone] = useState(null);     // the last apply
  const [err, setErr] = useState('');

  const check = async () => {
    setBusy('check'); setErr(''); setDone(null);
    try { setRes((await api.cloudScheduleCheck()).data); }
    catch (e) { setRes(null); setErr(e?.response?.data?.detail || 'The check could not run. Nothing was changed.'); }
    finally { setBusy(''); }
  };
  const apply = async () => {
    if (!res?.token) return;
    setBusy('apply'); setErr('');
    try {
      const r = (await api.cloudScheduleApply(res.token)).data;
      setDone(r);
      if (r.ok) { setRes(null); onDone && onDone(); }
      else if (r.error === 'changed') setRes(null);          // the preview is out of date: check again
    } catch (e) { setErr(e?.response?.data?.detail || 'The update could not run. Nothing was changed.'); }
    finally { setBusy(''); }
  };

  const plan = res?.plan || {};
  return (
    <div className="mt-3 pt-3 space-y-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }} data-testid="schedule-reconcile">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-semibold text-white">Match the Cloud schedule</span>
        <button onClick={check} disabled={!!busy} data-testid="schedule-check-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68', border: '1px solid rgba(251,221,104,0.35)' }}>
          {busy === 'check' ? <Loader2 size={14} className="animate-spin" /> : <CalendarCheck size={14} />} Check the schedule
        </button>
      </div>
      <p className="text-xs" style={{ color: muted }}>
        Reads the Cloud's whole schedule and shows what differs on this computer. Nothing changes until you press Update.
        Events you made or edited on this computer are never overwritten or removed.
      </p>

      {err && <p className="text-xs" style={{ color: '#fca5a5' }} data-testid="schedule-error">{err}</p>}
      {res && res.ok === false && <p className="text-xs flex gap-1.5" style={{ color: '#fbbf24' }} data-testid="schedule-problem"><AlertTriangle size={14} />{res.message}</p>}

      {res && res.ok && (
        <div className="rounded-lg p-3 space-y-2" style={{ backgroundColor: 'rgba(20,27,80,0.6)' }} data-testid="schedule-preview">
          <p className="text-sm" style={{ color: res.can_apply ? '#e5edff' : '#4ade80' }} data-testid="schedule-summary">{res.message}</p>
          <p className="text-xs" style={{ color: muted }}>Cloud has {res.cloud_events} events. {res.on_this_pc_only > 0 ? `${res.on_this_pc_only} event(s) exist only on this computer and will stay.` : ''}</p>
          <Group title="Will be added" rows={plan.add} color="#4ade80" testid="schedule-add" />
          <Group title="Will be updated" rows={plan.update} color="#fbdd68" testid="schedule-update" />
          <Group title="Will be removed (no longer in the Cloud)" rows={plan.remove} color="#fca5a5" testid="schedule-remove" />
          <Group title="Kept as they are on this computer" rows={plan.left_alone} color="#93c5fd" testid="schedule-kept" />
          <Group title="Waiting (the venue or host is not on this computer yet)" rows={plan.waiting} color={muted} testid="schedule-waiting" />
          {res.can_apply && (
            <button onClick={apply} disabled={!!busy} data-testid="schedule-apply-btn"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                    style={{ backgroundColor: '#fbdd68', color: '#0a0e27' }}>
              {busy === 'apply' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Update this computer (a backup is saved first)
            </button>
          )}
        </div>
      )}

      {done && (
        <p className="text-xs flex gap-1.5" style={{ color: done.ok ? '#4ade80' : '#fbbf24' }} data-testid="schedule-done">
          {done.ok ? <Check size={14} /> : <AlertTriangle size={14} />}{done.message}{done.ok && done.kept ? ` ${done.kept} kept as they were.` : ''}
        </p>
      )}
    </div>
  );
}
