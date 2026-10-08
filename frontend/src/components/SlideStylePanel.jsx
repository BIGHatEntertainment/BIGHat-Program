import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Save, RotateCcw } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL || '';
const DEFAULT_COLOR = '#1657E8';
const opts = () => ({
  withCredentials: true,
  headers: localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {},
});

function previewCss(bg) {
  if (!bg || bg.mode !== 'custom') {
    return 'radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)';
  }
  return bg.fill === 'solid'
    ? bg.color
    : `radial-gradient(circle at center, ${bg.color} 5%, ${bg.color} 20%, #191919 90%)`;
}

/**
 * scope="global"  -> /api/native/slide-style/global
 * scope="location" (locationId) -> /api/native/locations/:id/slide-style
 */
export default function SlideStylePanel({ scope, locationId, canEdit = true, setError, setSuccess }) {
  const isLoc = scope === 'location';
  const url = isLoc
    ? `${API}/api/native/locations/${locationId}/slide-style`
    : `${API}/api/native/slide-style/global`;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [useGlobal, setUseGlobal] = useState(true);
  const [bg, setBg] = useState({ mode: 'default', color: DEFAULT_COLOR, fill: 'gradient' });
  const [globalBg, setGlobalBg] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(url, opts());
        if (!alive) return;
        setBg(r.data.background);
        if (isLoc) { setUseGlobal(r.data.use_global); setGlobalBg(r.data.global); }
      } catch (e) {
        setError?.(e.response?.data?.detail || 'Failed to load slide style');
      } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [url]);

  // alpha.97: a venue that "matches global" must show the global color AS IT IS NOW, not as it was when the panel first opened
  useEffect(() => {
    if (!isLoc) return undefined;
    let alive = true;
    const refresh = async () => {
      try {
        const r = await axios.get(url, opts());
        if (alive) setGlobalBg(r.data.global);          // only the global color: never flip the host's own checkboxes under them
      } catch (e) { /* keep what is shown */ }
    };
    window.addEventListener('focus', refresh);
    const t = setInterval(refresh, 4000);
    return () => { alive = false; window.removeEventListener('focus', refresh); clearInterval(t); };
  }, [url, isLoc]);

  const save = async (nextBg, nextUseGlobal) => {
    setSaving(true);
    try {
      const body = isLoc ? { use_global: nextUseGlobal, background: nextBg } : { background: nextBg };
      await axios.put(url, body, opts());
      setSuccess?.('Slide style saved');
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Failed to save slide style');
    } finally { setSaving(false); }
  };

  if (loading) return <div className="text-sm" style={{ color: '#8892b0' }}><Loader2 size={14} className="animate-spin inline" /> Loading…</div>;

  const locked = !canEdit || (isLoc && useGlobal);
  const shown = isLoc && useGlobal ? globalBg : bg;

  return (
    <div className="space-y-4" data-testid={`slide-style-${scope}`}>
      {isLoc && (
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm text-white">
            <input type="checkbox" checked={useGlobal} disabled={!canEdit}
                   data-testid="match-global-toggle"
                   onChange={(e) => { setUseGlobal(e.target.checked); save(bg, e.target.checked); }} />
            Match global slide settings
          </label>
          <button disabled={!canEdit || useGlobal} data-testid="match-global-btn"
                  onClick={() => { setUseGlobal(true); save(bg, true); }}
                  className="px-3 py-1.5 rounded-md text-xs"
                  style={{ border: '1px solid rgba(251,221,104,0.3)', color: '#fbdd68', opacity: useGlobal ? 0.4 : 1 }}>
            Revert to global
          </button>
        </div>
      )}

      <div>
        <div className="text-sm font-semibold text-white mb-2">Slide background color</div>
        <div className="flex flex-wrap items-center gap-4" style={{ opacity: locked ? 0.5 : 1 }}>
          <input type="color" value={(shown && shown.color) || DEFAULT_COLOR} disabled={locked}
                 data-testid="bg-color-input"
                 onChange={(e) => setBg({ ...bg, mode: 'custom', color: e.target.value })}
                 style={{ width: 56, height: 40, background: 'none', border: 'none', cursor: locked ? 'default' : 'pointer' }} />
          <select value={bg.fill} disabled={locked} data-testid="bg-fill-select"
                  onChange={(e) => setBg({ ...bg, mode: 'custom', fill: e.target.value })}
                  className="px-2 py-1.5 rounded-md text-sm"
                  style={{ background: '#141b50', color: '#fff', border: '1px solid rgba(251,221,104,0.3)' }}>
            <option value="gradient">Gradient</option>
            <option value="solid">Solid</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-white">
            <input type="checkbox" disabled={locked} data-testid="bg-reset-toggle"
                   checked={bg.mode === 'default'}
                   onChange={(e) => {
                     // alpha.97: ticking "Use default" SAVES it right away (it used to change only the preview, so nothing was reverted)
                     if (e.target.checked) {
                       const d = { mode: 'default', color: DEFAULT_COLOR, fill: 'gradient' };
                       setBg(d); save(d, useGlobal);
                     } else {
                       setBg({ ...bg, mode: 'custom' });
                     }
                   }} />
            Use default blue gradient
          </label>
          <div data-testid="bg-preview"
               style={{ width: 160, height: 90, borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: previewCss(shown) }} />
        </div>
      </div>

      <div className="flex gap-2">
        <button disabled={locked || saving} data-testid="slide-style-save"
                onClick={() => save(bg, useGlobal)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
                style={{ backgroundColor: '#fbdd68', color: '#000e2a', opacity: locked ? 0.4 : 1 }}>
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save
        </button>
        <button disabled={locked || saving} data-testid="slide-style-reset"
                onClick={() => { const d = { mode: 'default', color: DEFAULT_COLOR, fill: 'gradient' }; setBg(d); save(d, useGlobal); }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs"
                style={{ border: '1px solid rgba(251,221,104,0.3)', color: '#fbdd68', opacity: locked ? 0.4 : 1 }}>
          <RotateCcw size={12} /> Reset to default
        </button>
      </div>
      <p className="text-xs" style={{ color: '#8892b0' }}>
        Applies to newly loaded slides. Reopen a show to see changes.
      </p>
    </div>
  );
}
