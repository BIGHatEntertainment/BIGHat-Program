// alpha.75: manage the Story Generator's own images, stored on this PC in
// Documents/BIG Hat Entertainment/Files/Story/{Trivia,Bingo,Karaoke,Hosts}
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { X, Upload, Trash2, FolderOpen, Image as ImageIcon } from 'lucide-react';
import { toast } from '../../utils/toastCompat';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/story-generator`;

const TABS = [
  { kind: 'trivia', label: 'Trivia', color: '#fbdd68', help: 'A location image and a location background for each trivia location.', variants: true },
  { kind: 'bingo', label: 'Bingo', color: '#3B82F6', help: 'The location image used in the Bingo story.' },
  { kind: 'karaoke', label: 'Karaoke', color: '#22c55e', help: 'The location image used in the Karaoke story.' },
  { kind: 'hosts', label: 'Hosts', color: '#a855f7', help: 'The host picture or GIF shown in every story (same name as the host).', gif: true },
];

export default function StoryImagesManager({ onClose }) {
  const [tab, setTab] = useState(TABS[0]);
  const [files, setFiles] = useState([]);
  const [folder, setFolder] = useState('');
  const [name, setName] = useState('');
  const [variant, setVariant] = useState('location');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/story-images/${tab.kind}`);
      setFiles(res.data.files || []);
      setFolder(res.data.folder || '');
    } catch (e) {
      toast({ title: 'Error', description: 'Could not read the Story images folder', variant: 'destructive' });
    }
  }, [tab]);

  useEffect(() => { setVariant('location'); setName(''); load(); }, [tab, load]);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const useName = (name || file.name.replace(/\.[^.]+$/, '')).trim();
    if (!useName) { toast({ title: 'Name needed', description: 'Type the location name first', variant: 'destructive' }); return; }
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('name', useName);
      form.append('variant', variant);
      await axios.post(`${API}/story-images/${tab.kind}`, form, { timeout: 60000 });
      toast({ title: 'Saved', description: `${useName}${variant === 'background' ? ' (background)' : ''} saved` });
      setName('');
      await load();
    } catch (err) {
      toast({ title: 'Upload failed', description: err?.response?.data?.detail || 'Could not save the image', variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (f) => {
    if (!window.confirm(`Delete ${f.filename}?`)) return;
    try {
      await axios.delete(`${API}/story-images/${tab.kind}/file/${encodeURIComponent(f.filename)}`);
      await load();
    } catch (err) {
      toast({ title: 'Error', description: 'Could not delete that image', variant: 'destructive' });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }} data-testid="story-images-manager">
      <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl" style={{ backgroundColor: '#0a1940', border: '1px solid rgba(251,221,104,0.25)' }}>
        <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid rgba(251,221,104,0.15)' }}>
          <div className="flex items-center gap-2 text-white font-bold tracking-wider uppercase text-sm"><ImageIcon size={18} style={{ color: '#fbdd68' }} /> Story Images</div>
          <button onClick={onClose} className="p-2 rounded-lg" style={{ color: '#8892b0' }} data-testid="story-images-close"><X size={16} /></button>
        </div>

        <div className="flex gap-2 px-6 pt-4">
          {TABS.map(t => (
            <button key={t.kind} onClick={() => setTab(t)} data-testid={`story-images-tab-${t.kind}`}
              className="px-4 py-2 rounded-lg text-sm font-bold"
              style={tab.kind === t.kind ? { backgroundColor: t.color, color: t.kind === 'trivia' ? '#000' : '#fff' } : { border: '1px solid rgba(255,255,255,0.15)', color: '#8892b0' }}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="px-6 py-4">
          <p className="text-xs mb-3" style={{ color: '#8892b0' }}>{tab.help}</p>
          <div className="flex flex-wrap items-end gap-3 mb-4">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-[10px] uppercase tracking-widest mb-1" style={{ color: '#8892b0' }}>{tab.kind === 'hosts' ? 'Host name' : 'Location name'}</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder={tab.kind === 'hosts' ? 'e.g. Alex' : 'e.g. Monkey Pants'}
                className="w-full px-3 py-2 rounded-lg text-sm" style={{ backgroundColor: '#141b50', color: '#fff', border: '1px solid rgba(255,255,255,0.15)' }} data-testid="story-images-name" />
            </div>
            {tab.variants && (
              <select value={variant} onChange={(e) => setVariant(e.target.value)} className="px-3 py-2 rounded-lg text-sm" style={{ backgroundColor: '#141b50', color: '#fff', border: '1px solid rgba(255,255,255,0.15)' }} data-testid="story-images-variant">
                <option value="location">Location image</option>
                <option value="background">Location background</option>
              </select>
            )}
            <label className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold cursor-pointer" style={{ backgroundColor: tab.color, color: tab.kind === 'trivia' ? '#000' : '#fff', opacity: busy ? 0.6 : 1 }}>
              <Upload size={14} /> {busy ? 'Saving...' : 'Choose image'}
              <input type="file" accept={tab.gif ? 'image/png,image/jpeg,image/webp,image/gif' : 'image/png,image/jpeg,image/webp'} className="hidden" onChange={upload} disabled={busy} data-testid="story-images-file" />
            </label>
          </div>

          {files.length === 0 ? (
            <div className="text-center py-10 text-sm rounded-xl" style={{ color: '#8892b0', border: '1px dashed rgba(255,255,255,0.15)' }} data-testid="story-images-empty">
              No {tab.label} images yet. Type a name, then choose an image.
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {files.map(f => (
                <div key={f.filename} className="rounded-xl overflow-hidden" style={{ backgroundColor: '#141b50', border: '1px solid rgba(255,255,255,0.1)' }} data-testid="story-images-item">
                  <img src={`${API}/story-images/${tab.kind}/file/${encodeURIComponent(f.filename)}`} alt={f.name} className="w-full h-28 object-cover" />
                  <div className="p-2 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs text-white truncate">{f.name}</div>
                      {f.variant === 'background' && <div className="text-[10px]" style={{ color: tab.color }}>background</div>}
                    </div>
                    <button onClick={() => remove(f)} className="p-1.5 rounded" style={{ color: '#ef4444' }} title="Delete"><Trash2 size={13} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {folder && <p className="mt-4 flex items-center gap-2 text-[11px]" style={{ color: '#8892b0' }}><FolderOpen size={12} /> {folder}</p>}
        </div>
      </div>
    </div>
  );
}
