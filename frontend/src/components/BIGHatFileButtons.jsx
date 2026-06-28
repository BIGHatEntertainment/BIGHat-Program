/**
 * BIGHatFileButtons — drop-in export/import widget for any content type.
 *
 * Usage:
 *
 *   <BIGHatFileButtons
 *     type="bingo"                 // round | presentation | bingo | scoreboard
 *     itemId="bingo-game-abc-123"  // omit to render only the Import button
 *     itemName="80s Music Bingo"
 *     onImported={(result) => loadList()}  // callback after a successful import
 *   />
 *
 * Renders:
 *   - "Export .bighat" button (only when `itemId` is set)
 *   - "Import .bighat" button (always; pops the file picker → confirmation
 *     dialog → DB insert)
 *
 * Confirmation dialog uses POST /api/bighat-files/inspect to peek at the
 * file's manifest before committing — shows the file's name, type, asset
 * count, signed-vs-unsigned status, source app version. Lets the user
 * cancel out of an accidentally-clicked file.
 */
import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Upload, X, FileBadge, ShieldCheck, ShieldAlert, Play } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const TYPE_LABELS = {
  round:        'Round Maker round',
  presentation: 'Trivia presentation',
  bingo:        'Bingo card',
  scoreboard:   'Scoreboard theme',
};

export default function BIGHatFileButtons({ type, itemId, itemName, onImported, allowPlayDirect = false }) {
  const inputRef = useRef(null);
  const playInputRef = useRef(null);
  const navigate = useNavigate();
  const [preview, setPreview] = useState(null);   // {manifest, payload} after inspect
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingMode, setPendingMode] = useState('import'); // 'import' | 'play-direct'
  const [busy, setBusy] = useState(false);

  const handleExport = () => {
    if (!itemId) return;
    const url = `${API}/api/bighat-files/export/${type}/${itemId}`;
    // Browser-native download — works in native (relative URL) and webapp.
    const a = document.createElement('a');
    a.href = url;
    a.download = `${(itemName || 'BIG Hat').replace(/[\\/:*?"<>|]/g, '')}.bighat`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`Exporting "${itemName || 'BIG Hat file'}"`);
  };

  const handleFilePick = (mode) => async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.bighat')) {
      toast.error('Please choose a .bighat file');
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await axios.post(`${API}/api/bighat-files/inspect`, form);
      // Play-direct only makes sense for ROUND .bighat files — surface the
      // error before we commit. The backend enforces the same rule but
      // failing here gives the user a clearer message.
      if (mode === 'play-direct' && res.data.type !== 'round') {
        toast.error(
          `Play Direct needs a Round .bighat (this is a ${TYPE_LABELS[res.data.type] || res.data.type}). ` +
          `Use Import instead.`
        );
        setBusy(false);
        return;
      }
      setPreview(res.data);
      setPendingFile(file);
      setPendingMode(mode);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not read .bighat file');
    } finally {
      setBusy(false);
    }
  };

  const confirmImport = async () => {
    if (!pendingFile) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append('file', pendingFile);
      if (pendingMode === 'play-direct') {
        const res = await axios.post(`${API}/api/bighat-files/play-direct`, form);
        toast.success(`Preparing "${res.data.name}"…`);
        setPreview(null);
        setPendingFile(null);
        // Drop into the same view a regular presentation opens in.
        // The "Open in Trivia Presenter" CTA on that page is what
        // actually launches the slide editor.
        navigate(`/trivia/present?id=${res.data.presentation_id}`);
      } else {
        const res = await axios.post(`${API}/api/bighat-files/import`, form);
        toast.success(`Imported "${res.data.name}"`);
        setPreview(null);
        setPendingFile(null);
        if (onImported) onImported(res.data);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || `${pendingMode === 'play-direct' ? 'Play Direct' : 'Import'} failed`);
    } finally {
      setBusy(false);
    }
  };

  const cancelImport = () => {
    setPreview(null);
    setPendingFile(null);
    setPendingMode('import');
  };

  return (
    <>
      <div style={{ display: 'inline-flex', gap: 8 }}>
        {itemId && (
          <button
            type="button"
            onClick={handleExport}
            data-testid={`bighat-export-${type}-${itemId}`}
            title={`Save as .bighat (portable ${TYPE_LABELS[type] || type} file)`}
            style={btnStyle}
          >
            <Download size={14} />
            <span>Export</span>
          </button>
        )}
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          data-testid={`bighat-import-${type}`}
          title={`Import a .bighat ${TYPE_LABELS[type] || type} file`}
          disabled={busy}
          style={btnStyle}
        >
          <Upload size={14} />
          <span>Import</span>
        </button>
        {allowPlayDirect && (
          <button
            type="button"
            onClick={() => playInputRef.current?.click()}
            data-testid="bighat-play-direct"
            title="Pick a .bighat round file and present it immediately, skipping Round Maker / Build Wizard."
            disabled={busy}
            style={playBtnStyle}
          >
            <Play size={14} />
            <span>Play .bighat</span>
          </button>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".bighat,application/x-bighat"
          onChange={handleFilePick('import')}
          style={{ display: 'none' }}
          data-testid={`bighat-import-input-${type}`}
        />
        {allowPlayDirect && (
          <input
            ref={playInputRef}
            type="file"
            accept=".bighat,application/x-bighat"
            onChange={handleFilePick('play-direct')}
            style={{ display: 'none' }}
            data-testid="bighat-play-direct-input"
          />
        )}
      </div>

      {preview && (
        <div
          data-testid="bighat-import-confirm"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={cancelImport}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#0f1d3a', color: '#e5edff',
              border: '1px solid rgba(251,221,104,0.25)',
              borderRadius: 14, padding: 28, maxWidth: 440, width: '90%',
              fontFamily: 'system-ui, sans-serif',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <FileBadge size={36} color="#fbdd68" />
              <button onClick={cancelImport} aria-label="Close" data-testid="bighat-import-cancel"
                      style={{ background: 'transparent', color: '#8892b0', border: 0, cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>
            <h2 style={{ margin: '14px 0 4px', fontSize: 20, color: '#fff' }}>{preview.name}</h2>
            <p style={{ margin: 0, color: '#8892b0', fontSize: 13 }}>
              {TYPE_LABELS[preview.type] || preview.type}
              {preview.asset_count > 0 && ` · ${preview.asset_count} bundled asset${preview.asset_count === 1 ? '' : 's'}`}
              {' · '}{(preview.file_size / 1024).toFixed(0)} KB
            </p>
            <div style={{ margin: '16px 0', padding: '10px 12px', borderRadius: 8,
                          background: 'rgba(255,255,255,0.04)', display: 'flex',
                          alignItems: 'center', gap: 10, fontSize: 13 }}>
              {preview.signed ? (
                <>
                  <ShieldCheck size={18} color="#7be0a3" />
                  <span><strong style={{ color: '#7be0a3' }}>Signed</strong> by a verified BIG Hat publisher.</span>
                </>
              ) : (
                <>
                  <ShieldAlert size={18} color="#fbdd68" />
                  <span>Unsigned — exported from a personal BIG Hat install.</span>
                </>
              )}
            </div>
            <p style={{ color: '#8892b0', fontSize: 12, marginBottom: 20 }}>
              Created with v{preview.app_version} on {preview.created_at ? new Date(preview.created_at).toLocaleDateString() : 'unknown date'}.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={cancelImport} data-testid="bighat-import-confirm-cancel" style={ghostBtn}>Cancel</button>
              <button onClick={confirmImport} disabled={busy}
                      data-testid="bighat-import-confirm-ok" style={primaryBtn}>
                {busy
                  ? (pendingMode === 'play-direct' ? 'Preparing…' : 'Importing...')
                  : (pendingMode === 'play-direct' ? 'Play Now' : 'Import to library')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const btnStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px', borderRadius: 8, border: '1px solid rgba(251,221,104,0.25)',
  background: 'rgba(251,221,104,0.08)', color: '#fbdd68', cursor: 'pointer',
  fontSize: 13, fontWeight: 600,
};

const playBtnStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px', borderRadius: 8, border: '1px solid rgba(34, 197, 94, 0.4)',
  // Slightly louder than the import button so the host's eye lands here
  // when their job is "play this thing the generator just emailed me".
  background: 'rgba(34, 197, 94, 0.12)', color: '#86efac', cursor: 'pointer',
  fontSize: 13, fontWeight: 700,
};

const primaryBtn = {
  padding: '10px 18px', borderRadius: 10, border: 0,
  background: '#fbdd68', color: '#1a1a1a', cursor: 'pointer',
  fontSize: 14, fontWeight: 700,
};

const ghostBtn = {
  padding: '10px 18px', borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.15)',
  background: 'transparent', color: '#e5edff', cursor: 'pointer',
  fontSize: 14, fontWeight: 600,
};
