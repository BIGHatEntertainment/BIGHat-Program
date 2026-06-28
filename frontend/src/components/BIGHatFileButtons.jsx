import React, { useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Upload, X, FileBadge, ShieldCheck, ShieldAlert } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const TYPE_LABELS = {
  round:        'Round Maker round',
  presentation: 'Trivia presentation',
  bingo:        'Bingo card',
  scoreboard:   'Scoreboard theme',
};

export default function BIGHatFileButtons({ type, itemId, itemName, onImported }) {
  const inputRef = useRef(null);
  const [preview, setPreview] = useState(null);   // {manifest, payload} after inspect
  const [pendingFile, setPendingFile] = useState(null);
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

  const handleFilePick = async (e) => {
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
      setPreview(res.data);
      setPendingFile(file);
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
      const res = await axios.post(`${API}/api/bighat-files/import`, form);
      toast.success(`Imported "${res.data.name}"`);
      setPreview(null);
      setPendingFile(null);
      if (onImported) onImported(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed');
    } finally {
      setBusy(false);
    }
  };

  const cancelImport = () => {
    setPreview(null);
    setPendingFile(null);
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
        <input
          ref={inputRef}
          type="file"
          accept=".bighat,application/x-bighat"
          onChange={handleFilePick}
          style={{ display: 'none' }}
          data-testid={`bighat-import-input-${type}`}
        />
      </div>

      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
          }}
          data-testid="bighat-import-confirm-modal"
        >
          <div style={{
            background: '#0b1220', border: '1px solid rgba(251,221,104,0.3)',
            borderRadius: 12, padding: 24, maxWidth: 480, width: 'calc(100% - 32px)',
            color: '#e7e7ec',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <FileBadge size={20} color="#fbdd68" />
              <strong>Import .bighat — preview</strong>
              <button onClick={cancelImport} style={iconBtn} aria-label="Close"
                      data-testid="bighat-import-confirm-close">
                <X size={16} />
              </button>
            </div>

            <p style={{ margin: '6px 0', fontSize: 13, color: '#cbd5e1' }}>
              {preview.summary || preview.type}
            </p>

            <div style={{ marginTop: 14, padding: 12, background: '#0a1326', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                {preview.signature_valid ? (
                  <>
                    <ShieldCheck size={16} color="#86efac" />
                    <span style={{ color: '#86efac' }}>Signed &amp; verified</span>
                  </>
                ) : (
                  <>
                    <ShieldAlert size={16} color="#fbbf24" />
                    <span style={{ color: '#fbbf24' }}>Unsigned (import will still work)</span>
                  </>
                )}
              </div>
              {preview.signed_by && (
                <p style={{ margin: '4px 0 0 24px', fontSize: 11, color: '#94a3b8' }}>
                  Signed by: {preview.signed_by}
                </p>
              )}
            </div>

            <div style={{ marginTop: 14, fontSize: 12, color: '#94a3b8' }}>
              File: {preview.filename || pendingFile?.name}
              <br />
              Size: {pendingFile ? `${(pendingFile.size / 1024).toFixed(1)} KB` : '—'}
              <br />
              Assets: {preview.asset_count ?? '—'}
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 18 }}>
              <button onClick={cancelImport} data-testid="bighat-import-confirm-cancel" style={ghostBtn}>Cancel</button>
              <button onClick={confirmImport} disabled={busy}
                      data-testid="bighat-import-confirm-ok" style={primaryBtn}>
                {busy ? 'Importing...' : 'Import to library'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ──────── styles (kept inline so this component drops anywhere without CSS hookup) ────────
const btnStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 12px', borderRadius: 8, border: '1px solid rgba(251,221,104,0.25)',
  background: 'rgba(251,221,104,0.08)', color: '#fbdd68', cursor: 'pointer',
  fontSize: 13, fontWeight: 600,
};
const iconBtn = {
  marginLeft: 'auto', background: 'transparent', border: 0, color: '#94a3b8', cursor: 'pointer',
};
const ghostBtn = {
  padding: '8px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #334155',
  color: '#cbd5e1', cursor: 'pointer',
  fontSize: 14, fontWeight: 600,
};
const primaryBtn = {
  padding: '8px 14px', borderRadius: 8, background: '#fbdd68', border: 0, color: '#0b1220',
  cursor: 'pointer',
  fontSize: 14, fontWeight: 600,
};
