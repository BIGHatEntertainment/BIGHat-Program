import React, { useState, useEffect, useCallback } from 'react';
import { X, Download, Grid3X3, FolderOpen, RefreshCw, ChevronLeft, Music, Image as ImageIcon } from 'lucide-react';
import axios from 'axios';
import { saveBlob } from '../../lib/saveFile';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/bingo/cards`;

// alpha.109: the Bingo card generator. There are NO preset cards any more.
// Step 1: every theme found in the user's Bingo folder (the one set in Bingo Setup) that has a song list.
// Step 2: how many cards. The PDF is built from ONLY that theme's songs (24 per card, free space in the middle).
// alpha.110: a theme with "Loteria" in its name makes PICTURE cards instead (16 pictures from its Cards folder, 4 x 4, no free space).
const COUNTS = [8, 20, 40, 60, 100];

export default function BingoCardsPopup({ open, onClose }) {
  const [data, setData] = useState(null);       // { folder, themes, min_songs, max_cards } | { error }
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState(null);   // the chosen theme
  const [count, setCount] = useState(40);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setMessage('');
    try {
      const res = await axios.get(`${API}/themes`, { timeout: 15000 });
      setData(res.data);
    } catch (e) {
      setData({ error: true, themes: [] });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (open) { setPicked(null); load(); } }, [open, load]);

  if (!open) return null;

  const maxCards = (data && data.max_cards) || 200;
  const isLoteria = (t) => !!t && t.kind === 'loteria';
  const themes = (data && data.themes) || [];

  const generate = async () => {
    if (!picked) return;
    setBusy(true); setMessage('');
    try {
      const res = await axios.post(`${API}/generate`, { theme: picked.id, count }, { responseType: 'blob', timeout: 60000 });
      const made = res.headers['x-cards'] || count;
      const saved = await saveBlob(new Blob([res.data], { type: 'application/pdf' }), `Bingo Cards - ${picked.name} (${made} cards).pdf`);
      setMessage(saved.ok ? `Saved ${made} bingo cards for ${picked.name}.` : `Could not save the cards: ${saved.error || 'unknown error'}`);
    } catch (err) {
      let why = 'Could not make the cards. Please try again.';
      try {
        const body = err.response && err.response.data && JSON.parse(await err.response.data.text());
        if (body && body.detail === 'need_24_songs') why = `${picked.name} needs at least ${(data && data.min_songs) || 24} different songs in its list.`;
        else if (body && body.detail === 'need_16_pictures') why = `${picked.name} needs at least ${(data && data.min_pictures) || 16} pictures in its Cards folder.`;
        else if (body && body.detail === 'no_cards_folder') why = `${picked.name} has no "Cards" folder with pictures yet.`;
        else if (body && body.detail === 'theme_not_found') why = 'That theme is no longer available. Check Bingo Setup.';
      } catch { /* keep the generic message */ }
      setMessage(why);
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.85)' }} data-testid="bingo-cards-popup">
      <div className="relative w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto rounded-2xl" style={{ background: 'linear-gradient(135deg, #0a1940 0%, #000e2a 100%)', border: '2px solid rgba(251, 221, 104, 0.3)' }}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 rounded-t-2xl" style={{ backgroundColor: 'rgba(0, 14, 42, 0.95)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
          <div className="flex items-center gap-3">
            {picked ? (
              <button onClick={() => { setPicked(null); setMessage(''); }} className="p-1 rounded-lg hover:bg-white/10" data-testid="bingo-cards-back"><ChevronLeft size={22} style={{ color: '#5973F7' }} /></button>
            ) : <Grid3X3 size={22} style={{ color: '#5973F7' }} />}
            <div>
              <h2 className="text-lg font-bold" style={{ color: '#5973F7' }}>Bingo Card Generator</h2>
              <p className="text-xs" style={{ color: '#8892b0' }}>{picked ? `${picked.name}: how many cards?` : 'Pick a Bingo theme'}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10" data-testid="bingo-cards-close"><X size={20} style={{ color: '#8892b0' }} /></button>
        </div>

        <div className="p-6 space-y-3">
          {loading && <p className="text-sm text-center py-6" style={{ color: '#8892b0' }}>Looking for your Bingo themes...</p>}

          {!loading && !picked && data && data.error && (
            <Notice text="The Bingo themes could not be loaded." onRetry={load} />
          )}
          {!loading && !picked && data && !data.error && !data.folder && (
            <Notice icon text="No Bingo folder is set yet. Choose it in Bingo Setup, and your themes will show up here." onRetry={load} />
          )}
          {!loading && !picked && data && !data.error && data.folder && themes.length === 0 && (
            <Notice icon text={`No Bingo themes with a song list (.csv or .xlsx) were found in ${data.folder}, or they are switched off in Bingo Setup.`} onRetry={load} />
          )}

          {!loading && !picked && themes.map((t) => (
            <button key={t.id} disabled={!t.usable} onClick={() => { setPicked(t); setMessage(''); }} data-testid={`bingo-cards-theme-${t.id}`}
              className="w-full flex items-center justify-between px-4 py-3 rounded-xl text-left transition-all disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg, #141b50, #0a1940)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
              <div className="flex items-center gap-3">
                {isLoteria(t) ? <ImageIcon size={16} style={{ color: '#fbdd68' }} /> : <Music size={16} style={{ color: '#5973F7' }} />}
                <div>
                  <span className="text-sm font-semibold text-white">{t.name}</span>
                  <p className="text-xs" style={{ color: t.usable ? '#8892b0' : '#fbdd68' }}>
                    {isLoteria(t)
                      ? (t.usable ? `Loteria, ${t.songs} pictures` : `Loteria, ${t.songs} pictures in its Cards folder, needs at least ${t.need}`)
                      : (t.usable ? `${t.songs} songs` : `${t.songs} songs, needs at least ${t.need}`)}
                  </p>
                </div>
              </div>
              {t.usable && <span className="text-xs font-bold px-3 py-1.5 rounded-lg" style={{ backgroundColor: '#5973F7', color: '#000' }}>Choose</span>}
            </button>
          ))}

          {picked && (
            <div className="space-y-4">
              <div className="grid grid-cols-5 gap-2">
                {COUNTS.map((n) => (
                  <button key={n} onClick={() => setCount(n)} data-testid={`bingo-cards-count-${n}`} className="py-2 rounded-lg text-sm font-bold"
                    style={{ backgroundColor: count === n ? '#5973F7' : 'rgba(20,27,80,0.6)', color: count === n ? '#000' : '#fff', border: '1px solid rgba(251,221,104,0.15)' }}>{n}</button>
                ))}
              </div>
              <label className="flex items-center justify-between text-xs" style={{ color: '#8892b0' }}>
                Or type a number (1 to {maxCards})
                <input type="number" min={1} max={maxCards} value={count} data-testid="bingo-cards-count-input"
                  onChange={(e) => setCount(Math.max(1, Math.min(maxCards, parseInt(e.target.value || '1', 10) || 1)))}
                  className="w-24 px-2 py-1 rounded-lg text-white text-sm" style={{ backgroundColor: 'rgba(20,27,80,0.8)', border: '1px solid rgba(251,221,104,0.2)' }} />
              </label>
              <p className="text-xs" style={{ color: '#8892b0' }}>
                {isLoteria(picked)
                  ? `Every card is a 4 x 4 grid of 16 different pictures from the ${picked.songs} in ${picked.name}, with no free space. Printed sideways, 2 cards per page with a dashed line down the middle to cut along${count % 2 ? ` (rounded up to ${count + 1} to fill the last page)` : ''}.`
                  : `Every card is made only from the ${picked.songs} songs in ${picked.name}: 24 different songs and a FREE space in the center. 4 cards per page${count % 4 ? ` (rounded up to ${count + (4 - (count % 4))} to fill the last page)` : ''}.`}
              </p>
              <button onClick={generate} disabled={busy} data-testid="bingo-cards-generate"
                className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold disabled:opacity-50" style={{ backgroundColor: '#5973F7', color: '#000' }}>
                <Download size={16} />{busy ? 'Making your cards...' : 'Generate Bingo Cards (PDF)'}
              </button>
            </div>
          )}

          {message && <p className="text-sm text-center pt-1" style={{ color: message.startsWith('Saved') ? '#22c55e' : '#fbdd68' }} data-testid="bingo-cards-message">{message}</p>}
        </div>

        <div className="px-6 py-3 text-center" style={{ borderTop: '1px solid rgba(251, 221, 104, 0.1)' }}>
          <p className="text-[10px]" style={{ color: '#8892b0' }}>PDF format, ready to print. Themes come from your Bingo folder.</p>
        </div>
      </div>
    </div>
  );
}

function Notice({ text, icon, onRetry }) {
  return (
    <div className="text-center py-6 space-y-3">
      {icon && <FolderOpen size={28} className="mx-auto" style={{ color: '#8892b0' }} />}
      <p className="text-sm" style={{ color: '#8892b0' }}>{text}</p>
      <button onClick={onRetry} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold" style={{ backgroundColor: 'rgba(89,115,247,0.2)', color: '#5973F7' }}><RefreshCw size={12} />Check again</button>
    </div>
  );
}
