import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Loader2, Upload, Trash2, ArrowUp, ArrowDown } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || '';
const base = `${API}/api/native/global-slides`;
const opts = () => ({
  withCredentials: true,
  headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
});

function ImageGroup({ title, hint, kind, state, canEdit, onChange, busy, setBusy, setError }) {
  const input = useRef(null);
  const upload = async (files) => {
    setBusy(true);
    try {
      let last = null;
      for (const f of files) {
        const fd = new FormData();
        fd.append('file', f);
        last = (await axios.post(`${base}/${kind}/upload`, fd, opts())).data;
      }
      if (last) onChange(last);
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Upload failed');
    } finally { setBusy(false); if (input.current) input.current.value = ''; }
  };
  const remove = async (name) => {
    setBusy(true);
    try { onChange((await axios.delete(`${base}/file/${name}`, opts())).data); }
    catch (e) { setError?.(e.response?.data?.detail || 'Delete failed'); }
    finally { setBusy(false); }
  };
  const move = async (i, d) => {
    const imgs = [...state.images];
    const j = i + d;
    if (j < 0 || j >= imgs.length) return;
    [imgs[i], imgs[j]] = [imgs[j], imgs[i]];
    setBusy(true);
    try { onChange((await axios.put(base, { [kind]: { images: imgs } }, opts())).data); }
    catch (e) { setError?.(e.response?.data?.detail || 'Reorder failed'); }
    finally { setBusy(false); }
  };
  const toggle = async (enabled) => {
    setBusy(true);
    try { onChange((await axios.put(base, { [kind]: { enabled } }, opts())).data); }
    catch (e) { setError?.(e.response?.data?.detail || 'Save failed'); }
    finally { setBusy(false); }
  };
  return (
    <div className="rounded-lg p-4" style={{ border: '1px solid rgba(251,221,104,0.2)' }} data-testid={`global-${kind}`}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-sm font-semibold text-white">{title}</div>
        <label className="flex items-center gap-2 text-xs text-white">
          <input type="checkbox" checked={state.enabled} disabled={!canEdit || busy}
                 data-testid={`global-${kind}-enabled`} onChange={(e) => toggle(e.target.checked)} />
          Show in presentations
        </label>
      </div>
      <p className="text-xs mb-3" style={{ color: '#8892b0' }}>{hint}</p>
      <div className="flex flex-wrap gap-3 mb-3">
        {state.images.length === 0 && <div className="text-xs" style={{ color: '#8892b0' }}>Nothing uploaded yet.</div>}
        {state.images.map((f, i) => (
          <div key={f} className="relative" style={{ width: 170 }} data-testid={`global-${kind}-img-${i}`}>
            <img src={`${base}/file/${f}`} alt="" style={{ width: 170, height: 96, objectFit: 'cover', borderRadius: 6, border: '1px solid rgba(255,255,255,0.2)' }} />
            <div className="absolute top-1 left-1 text-[10px] px-1.5 rounded" style={{ background: 'rgba(0,0,0,0.7)', color: '#fbdd68' }}>{i + 1}</div>
            {canEdit && (
              <div className="flex gap-1 mt-1">
                <button disabled={busy || i === 0} onClick={() => move(i, -1)} title="Move earlier" className="p-1 rounded" style={{ border: '1px solid rgba(255,255,255,0.2)', color: '#fff', opacity: i === 0 ? 0.3 : 1 }}><ArrowUp size={12} /></button>
                <button disabled={busy || i === state.images.length - 1} onClick={() => move(i, 1)} title="Move later" className="p-1 rounded" style={{ border: '1px solid rgba(255,255,255,0.2)', color: '#fff', opacity: i === state.images.length - 1 ? 0.3 : 1 }}><ArrowDown size={12} /></button>
                <button disabled={busy} onClick={() => remove(f)} title="Remove" className="p-1 rounded ml-auto" style={{ border: '1px solid rgba(239,68,68,0.5)', color: '#ef4444' }}><Trash2 size={12} /></button>
              </div>
            )}
          </div>
        ))}
      </div>
      {canEdit && (
        <>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple className="hidden"
                 data-testid={`global-${kind}-file`} onChange={(e) => e.target.files?.length && upload([...e.target.files])} />
          <button disabled={busy} onClick={() => input.current?.click()} data-testid={`global-${kind}-upload`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
                  style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}>
            <Upload size={12} /> Upload slide image(s)
          </button>
        </>
      )}
    </div>
  );
}

/** Company intro, Rules, and the auto Format slide. Played after the location slides, before round 1. */
export default function GlobalSlidesPanel({ canEdit, setError, setSuccess }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const bgInput = useRef(null);

  useEffect(() => {
    axios.get(base, opts()).then((r) => setState(r.data)).catch((e) => setError?.(e.response?.data?.detail || 'Failed to load global slides'));
  }, []);

  if (!state) return <div className="text-sm" style={{ color: '#8892b0' }}><Loader2 size={14} className="animate-spin inline" /> Loading…</div>;

  const put = async (patch) => {
    setBusy(true);
    try { setState((await axios.put(base, patch, opts())).data); setSuccess?.('Saved'); }
    catch (e) { setError?.(e.response?.data?.detail || 'Save failed'); }
    finally { setBusy(false); }
  };
  const uploadBg = async (file) => {
    setBusy(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      setState((await axios.post(`${base}/format_bg/upload`, fd, opts())).data);
      setSuccess?.('Format background saved');
    } catch (e) { setError?.(e.response?.data?.detail || 'Upload failed'); }
    finally { setBusy(false); if (bgInput.current) bgInput.current.value = ''; }
  };
  const removeBg = async () => {
    setBusy(true);
    try { setState((await axios.delete(`${base}/file/${state.format.background}`, opts())).data); }
    catch (e) { setError?.(e.response?.data?.detail || 'Delete failed'); }
    finally { setBusy(false); }
  };
  const common = { canEdit, busy, setBusy, setError, onChange: (s) => { setState(s); setSuccess?.('Saved'); } };

  return (
    <div className="space-y-4" data-testid="global-slides-panel">
      <p className="text-xs" style={{ color: '#8892b0' }}>
        Order in every presentation: host, rewards slot, location images, <b>company</b>, <b>rules</b>, <b>format</b>, then round 1.
        These are global; locations cannot change them.
      </p>
      <ImageGroup title="Company slides (About BIG Hat Entertainment)" hint="Upload 16:9 images (1920x1080 recommended). They play in the order shown."
                  kind="company" state={state.company} {...common} />
      <ImageGroup title="Rules slides" hint="Upload your house rules as 16:9 images. They play in the order shown."
                  kind="rules" state={state.rules} {...common} />
      <div className="rounded-lg p-4" style={{ border: '1px solid rgba(251,221,104,0.2)' }} data-testid="global-format">
        <div className="flex items-center justify-between mb-1">
          <div className="text-sm font-semibold text-white">Format slide (automatic)</div>
          <label className="flex items-center gap-2 text-xs text-white">
            <input type="checkbox" checked={state.format.enabled} disabled={!canEdit || busy}
                   data-testid="global-format-enabled" onChange={(e) => put({ format: { enabled: e.target.checked } })} />
            Show in presentations
          </label>
        </div>
        <p className="text-xs mb-3" style={{ color: '#8892b0' }}>
          Built for each show from its real rounds: one colored line per round with its points. Works for any number of rounds (3 to 10).
        </p>
        <label className="flex items-center gap-2 text-sm text-white mb-3">
          <input type="checkbox" checked={state.format.show_themes} disabled={!canEdit || busy}
                 data-testid="global-format-themes" onChange={(e) => put({ format: { show_themes: e.target.checked } })} />
          Show the theme on General Topic and Specific Topic rounds (Mystery is never shown)
        </label>
        <div className="text-xs mb-2" style={{ color: '#8892b0' }}>
          Background: {state.format.background ? 'your custom image' : 'built-in curtain (replace with your own artwork below)'}
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <input ref={bgInput} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                   data-testid="global-format-bg-file" onChange={(e) => e.target.files?.[0] && uploadBg(e.target.files[0])} />
            <button disabled={busy} onClick={() => bgInput.current?.click()} data-testid="global-format-bg-upload"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
                    style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}><Upload size={12} /> Upload background (no pills)</button>
            {state.format.background && (
              <button disabled={busy} onClick={removeBg} className="px-3 py-1.5 rounded-md text-xs"
                      style={{ border: '1px solid rgba(239,68,68,0.5)', color: '#ef4444' }}>Use built-in</button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
