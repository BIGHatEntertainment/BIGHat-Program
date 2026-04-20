import React, { useState } from 'react';
import { X, Download, Grid3X3, Music, Star, Heart } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/bingo`;

const STANDARD_CARDS = [
  { id: '1970s', name: '1970s', description: 'Disco era bingo cards' },
  { id: '1980s', name: '1980s', description: 'Synth pop bingo cards' },
  { id: '1990s', name: '1990s', description: 'Grunge & pop bingo cards' },
  { id: 'Y2K', name: 'Y2K', description: 'Y2K hits bingo cards' },
];

const SENIOR_CARDS = [
  { id: '1970s', name: '1970s' },
  { id: '1980s', name: '1980s' },
  { id: '1990s', name: '1990s' },
  { id: 'Y2K', name: 'Y2K' },
  { id: 'X-Mas', name: 'Christmas' },
];

const SPECIAL_CARDS = [
  { id: 'Pop Punk & Emo', name: 'Pop Punk & Emo' },
  { id: 'X-Mas', name: 'Christmas' },
];

export default function BingoCardsPopup({ open, onClose }) {
  const [downloading, setDownloading] = useState(null);
  const [showSenior, setShowSenior] = useState(false);
  const [showSpecial, setShowSpecial] = useState(false);

  if (!open) return null;

  const handleDownload = async (category, decade, displayName) => {
    setDownloading(`${category}-${decade}`);
    try {
      const res = await axios.get(`${API}/bingo-cards/download/${category}/${encodeURIComponent(decade)}`, {
        responseType: 'blob', timeout: 30000,
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `Bingo (${displayName}).pdf`;
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      link.remove();
    } catch (err) {
      console.error('Download failed:', err);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.85)' }}>
      <div className="relative w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto rounded-2xl" style={{ background: 'linear-gradient(135deg, #0a1940 0%, #000e2a 100%)', border: '2px solid rgba(251, 221, 104, 0.3)' }}>
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 rounded-t-2xl" style={{ backgroundColor: 'rgba(0, 14, 42, 0.95)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
          <div className="flex items-center gap-3">
            <Grid3X3 size={22} style={{ color: '#5973F7' }} />
            <div>
              <h2 className="text-lg font-bold" style={{ color: '#5973F7' }}>Bingo Cards</h2>
              <p className="text-xs" style={{ color: '#8892b0' }}>Download printable bingo cards by decade</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10">
            <X size={20} style={{ color: '#8892b0' }} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {/* Standard Cards */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: '#5973F7' }}>
              <Music size={14} /> Standard Bingo Cards
            </h3>
            <div className="space-y-2">
              {STANDARD_CARDS.map(card => (
                <CardRow key={card.id} name={card.name} desc={card.description} color="#5973F7"
                  loading={downloading === `standard-${card.id}`}
                  onDownload={() => handleDownload('standard', card.id, card.name)} />
              ))}
            </div>
          </div>

          {/* Senior Cards Toggle */}
          <div>
            <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl transition-all" style={{ backgroundColor: showSenior ? 'rgba(34, 197, 94, 0.1)' : 'rgba(20, 27, 80, 0.4)', border: `1px solid ${showSenior ? 'rgba(34, 197, 94, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
              <input type="checkbox" checked={showSenior} onChange={(e) => setShowSenior(e.target.checked)} className="w-4 h-4 accent-green-500 rounded" />
              <Heart size={16} style={{ color: '#22c55e' }} />
              <div>
                <span className="text-sm font-semibold text-white">Senior Bingo Cards</span>
                <p className="text-xs" style={{ color: '#8892b0' }}>Larger text, senior-friendly format</p>
              </div>
            </label>
            {showSenior && (
              <div className="mt-2 space-y-2 pl-4">
                {SENIOR_CARDS.map(card => (
                  <CardRow key={card.id} name={`Senior ${card.name}`} desc="" color="#22c55e"
                    loading={downloading === `senior-${card.id}`}
                    onDownload={() => handleDownload('senior', card.id, `Senior ${card.name}`)} />
                ))}
              </div>
            )}
          </div>

          {/* Special Event Cards Toggle */}
          <div>
            <label className="flex items-center gap-3 cursor-pointer p-3 rounded-xl transition-all" style={{ backgroundColor: showSpecial ? 'rgba(168, 85, 247, 0.1)' : 'rgba(20, 27, 80, 0.4)', border: `1px solid ${showSpecial ? 'rgba(168, 85, 247, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
              <input type="checkbox" checked={showSpecial} onChange={(e) => setShowSpecial(e.target.checked)} className="w-4 h-4 accent-purple-500 rounded" />
              <Star size={16} style={{ color: '#a855f7' }} />
              <div>
                <span className="text-sm font-semibold text-white">Special Event Cards</span>
                <p className="text-xs" style={{ color: '#8892b0' }}>Holiday & themed bingo cards</p>
              </div>
            </label>
            {showSpecial && (
              <div className="mt-2 space-y-2 pl-4">
                {SPECIAL_CARDS.map(card => (
                  <CardRow key={card.id} name={card.name} desc="" color="#a855f7"
                    loading={downloading === `special-${card.id}`}
                    onDownload={() => handleDownload('special', card.id, card.name)} />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="px-6 py-3 text-center" style={{ borderTop: '1px solid rgba(251, 221, 104, 0.1)' }}>
          <p className="text-[10px]" style={{ color: '#8892b0' }}>PDF format, ready to print</p>
        </div>
      </div>
    </div>
  );
}

function CardRow({ name, desc, color, loading, onDownload }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-xl" style={{ background: 'linear-gradient(135deg, #141b50, #0a1940)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
      <div>
        <span className="text-sm font-semibold text-white">{name}</span>
        {desc && <p className="text-xs" style={{ color: '#8892b0' }}>{desc}</p>}
      </div>
      <button onClick={onDownload} disabled={loading} className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all hover:shadow-lg disabled:opacity-50" style={{ backgroundColor: color, color: '#000' }}>
        <Download size={12} />
        {loading ? '...' : 'Download'}
      </button>
    </div>
  );
}
