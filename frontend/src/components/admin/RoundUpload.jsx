import React, { useState } from 'react';
import { UploadCloud, Loader2, Check, AlertTriangle } from 'lucide-react';
import api from '../../lib/api';

/**
 * v32.2.11: send this computer's own round files to BIG Hat Cloud so the Cloud can stamp them with a permanent ID.
 * "Check" lists what would go up and what would not (and why). It changes NOTHING and sends nothing.
 * "Send" runs only after that same check. Nothing on this computer is changed, moved or deleted; the stamped copies come back on the next file sync.
 */
const muted = '#8892b0';
const List = ({ title, rows, color, testid, note }) => (
  rows && rows.length > 0 ? (
    <div data-testid={testid}>
      <p className="text-xs font-semibold mb-1" style={{ color }}>{title} ({rows.length})</p>
      {note && <p className="text-xs mb-1" style={{ color: muted }}>{note}</p>}
      <ul className="text-xs space-y-0.5 max-h-32 overflow-auto" style={{ color: '#cbd5f5' }}>
        {rows.map((r) => <li key={r.path}>{r.type} / {r.file}</li>)}
      </ul>
    </div>
  ) : null
);

export default function RoundUpload() {
  const [busy, setBusy] = useState('');
  const [res, setRes] = useState(null);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState('');

  const check = async () => {
    setBusy('check'); setErr(''); setDone(null);
    try { setRes((await api.roundUploadCheck()).data); }
    catch (e) { setRes(null); setErr(e?.response?.data?.detail || 'The check could not run. Nothing was sent.'); }
    finally { setBusy(''); }
  };
  const send = async () => {
    if (!res?.token) return;
    setBusy('send'); setErr('');
    try {
      const r = (await api.roundUploadSend(res.token)).data;
      setDone(r);
      if (r.ok || r.error === 'changed') setRes(null);
    } catch (e) { setErr(e?.response?.data?.detail || 'The upload could not run. Nothing on this computer was changed.'); }
    finally { setBusy(''); }
  };

  return (
    <div className="mt-3 pt-3 space-y-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }} data-testid="round-upload">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-semibold text-white">Send my rounds to the Cloud</span>
        <button onClick={check} disabled={!!busy} data-testid="round-upload-check-btn"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68', border: '1px solid rgba(251,221,104,0.35)' }}>
          {busy === 'check' ? <Loader2 size={14} className="animate-spin" /> : <UploadCloud size={14} />} Check what can go up
        </button>
      </div>
      <p className="text-xs" style={{ color: muted }}>
        Round files that exist only on this computer have no permanent ID, so a show built in the Cloud cannot use them. Sending them lets the Cloud
        stamp them. Nothing is sent until you confirm, a round whose name the Cloud already holds is never sent, and nothing on this computer is changed or deleted.
      </p>

      {err && <p className="text-xs" style={{ color: '#fca5a5' }} data-testid="round-upload-error">{err}</p>}
      {res && res.ok === false && <p className="text-xs flex gap-1.5" style={{ color: '#fbbf24' }} data-testid="round-upload-problem"><AlertTriangle size={14} />{res.message}</p>}

      {res && res.ok && (
        <div className="rounded-lg p-3 space-y-2" style={{ backgroundColor: 'rgba(20,27,80,0.6)' }} data-testid="round-upload-preview">
          <p className="text-sm" style={{ color: res.can_upload ? '#e5edff' : '#4ade80' }} data-testid="round-upload-summary">{res.message}</p>
          <List title="Will be sent" rows={res.send} color="#4ade80" testid="round-upload-send" />
          <List title="Not sent: a round with this name is already in the Cloud" rows={res.name_in_cloud} color="#fbbf24" testid="round-upload-clash"
                note="Sending it would replace the Cloud's round for every computer. Rename the file here if it is a different round." />
          <List title="Already sent, waiting for the stamped copy" rows={res.already_sent} color="#93c5fd" testid="round-upload-already" />
          <List title="Too large to send (over 50 MB)" rows={res.too_large} color={muted} testid="round-upload-big" />
          {res.can_upload > 0 && (
            <button onClick={send} disabled={!!busy} data-testid="round-upload-send-btn"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                    style={{ backgroundColor: '#fbdd68', color: '#0a0e27' }}>
              {busy === 'send' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Send {res.can_upload} round{res.can_upload === 1 ? '' : 's'} to the Cloud
            </button>
          )}
        </div>
      )}

      {done && (
        <p className="text-xs flex gap-1.5" style={{ color: done.ok ? '#4ade80' : '#fbbf24' }} data-testid="round-upload-done">
          {done.ok ? <Check size={14} /> : <AlertTriangle size={14} />}{done.message}
        </p>
      )}
    </div>
  );
}
