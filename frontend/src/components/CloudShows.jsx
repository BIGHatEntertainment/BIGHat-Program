import React, { useEffect, useState, useCallback } from 'react';
import { Cloud, Download, Check, AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import api from '../lib/api';

/**
 * v32.2.6: "Cloud shows" - trivia shows built in the BIG Hat Cloud wizard, ready to pull onto this PC for the Trivia player.
 * Shows only when the Cloud has something for this PC. Nothing imports on its own: the host presses Import.
 * A locked round (already used at this venue in the last 180 days) stops the import and asks first.
 */
export default function CloudShows({ onImported }) {
  const [state, setState] = useState({ loading: true, shows: [], problem: null });
  const [busy, setBusy] = useState(null);
  const [result, setResult] = useState({});          // plan id -> { ok, message }
  const [askLocked, setAskLocked] = useState(null);  // plan id waiting for "import anyway"

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const { data } = await api.cloudShows();
      setState({ loading: false, shows: data.shows || [], problem: data.ok === false && data.error !== 'unlinked' ? data.message : null, unlinked: data.error === 'unlinked' });
    } catch {
      setState({ loading: false, shows: [], problem: null });
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const doImport = async (show, allowLocked = false) => {
    setBusy(show.id); setAskLocked(null);
    try {
      const { data } = await api.cloudShowImport(show.id, allowLocked);
      if (data.ok) {
        setResult((r) => ({ ...r, [show.id]: { ok: true, message: `Imported. ${data.rounds} rounds for ${data.location}, ready to host.` } }));
        onImported && onImported();
      } else if (data.code === 'locked' && data.can_override) {
        setResult((r) => ({ ...r, [show.id]: { ok: false, message: data.message } }));
        setAskLocked(show.id);
      } else {
        setResult((r) => ({ ...r, [show.id]: { ok: false, message: data.message || 'The show could not be imported.' } }));
      }
    } catch (e) {
      setResult((r) => ({ ...r, [show.id]: { ok: false, message: e?.response?.data?.detail || 'The show could not be imported. Nothing was changed.' } }));
    } finally { setBusy(null); }
  };

  if (state.loading && !state.shows.length) return null;
  if (state.unlinked || (!state.shows.length && !state.problem)) return null;   // not linked, or nothing waiting: stay out of the way

  return (
    <div className="glass-card rounded-xl p-4 mb-6" data-testid="cloud-shows"
         style={{ border: '1px solid rgba(251, 221, 104, 0.25)' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Cloud size={18} style={{ color: '#fbdd68' }} />
          <h3 className="text-white font-semibold text-sm">Cloud shows</h3>
          <span className="text-xs" style={{ color: '#8892b0' }}>built in BIG Hat Cloud, ready for this PC</span>
        </div>
        <button onClick={load} className="p-1.5 rounded-lg" title="Check the Cloud again" data-testid="cloud-shows-refresh"
                style={{ color: '#8892b0' }}><RefreshCw size={14} className={state.loading ? 'animate-spin' : ''} /></button>
      </div>
      {state.problem && (
        <p className="text-xs flex gap-2" style={{ color: '#fbbf24' }} data-testid="cloud-shows-problem"><AlertTriangle size={14} />{state.problem}</p>
      )}
      <div className="space-y-2">
        {state.shows.map((s) => {
          const r = result[s.id];
          return (
            <div key={s.id} className="rounded-lg p-3" style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)' }} data-testid={`cloud-show-${s.id}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-white text-sm font-medium truncate">{s.name}</p>
                  <p className="text-xs" style={{ color: '#8892b0' }}>
                    {s.venue_name} · {s.host_name} · {s.round_count} rounds{s.parts > 1 ? ` · ${s.parts} parts` : ''}
                  </p>
                </div>
                <button onClick={() => doImport(s)} disabled={busy === s.id || s.complete === false}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold flex-shrink-0 disabled:opacity-50"
                        style={{ backgroundColor: '#fbdd68', color: '#0a0e27' }} data-testid={`cloud-show-import-${s.id}`}>
                  {busy === s.id ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  {busy === s.id ? 'Importing...' : 'Import'}
                </button>
              </div>
              {s.complete === false && (
                <p className="text-xs mt-2" style={{ color: '#fbbf24' }}>A round in this show is missing in the Cloud. Fix it there first.</p>
              )}
              {r && (
                <p className="text-xs mt-2 flex gap-1.5" style={{ color: r.ok ? '#4ade80' : '#fca5a5' }} data-testid={`cloud-show-result-${s.id}`}>
                  {r.ok ? <Check size={14} /> : <AlertTriangle size={14} />}{r.message}
                </p>
              )}
              {askLocked === s.id && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => doImport(s, true)} className="px-3 py-1.5 rounded-lg text-xs font-semibold" data-testid="cloud-show-import-anyway"
                          style={{ backgroundColor: 'rgba(251, 191, 36, 0.2)', color: '#fbbf24', border: '1px solid rgba(251, 191, 36, 0.4)' }}>Import anyway</button>
                  <button onClick={() => setAskLocked(null)} className="px-3 py-1.5 rounded-lg text-xs" style={{ color: '#8892b0' }}>Cancel</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
