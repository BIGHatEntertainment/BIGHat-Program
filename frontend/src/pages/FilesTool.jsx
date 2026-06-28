/**
 * Files tool — the .bighat file manager.
 *
 * v32.0.0-alpha.18 redesign:
 *   • Typed subfolder tabs (All / Rounds / Bingo / Karaoke / Other) at
 *     the top — switches the listing without leaving the page.
 *   • Per-file "Load into…" dropdown so a saved round can be reopened
 *     in Round Generator / Build Wizard / Presenter with one click —
 *     fixing the "I uploaded it but there's nothing I can do with it"
 *     complaint.
 *   • Per-file "Reveal in Folder" opens the host OS file manager (calls
 *     POST /api/native/files/reveal).
 *   • Unified <PageHeader /> for back + home navigation.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Upload, Download, Trash2, FolderOpen, FileText, Loader2,
  AlertCircle, Play, Pencil, ExternalLink,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import PageHeader from '../components/PageHeader';

const API = process.env.REACT_APP_BACKEND_URL;

// On-disk folder names. Must exactly match SUBFOLDERS in
// /app/backend/native/files_router.py — the backend rejects anything
// else with a 400. "All" is a UI-only synthetic value that means
// "aggregate across every subfolder".
//
// Trivia is split by round_type at the filesystem level — clicking
// "Trivia" shows ALL round types; the host can drill into a specific
// type (MC / REG / MISC / MYS / BIG) via the sub-tabs that surface
// below the main row.
const FOLDERS = [
  { key: 'all',        label: 'All' },
  { key: 'Trivia',     label: 'Trivia' },
  { key: 'Bingo',      label: 'Bingo' },
  { key: 'Karaoke',    label: 'Karaoke' },
  { key: 'Hosts',      label: 'Hosts' },
  { key: 'Locations',  label: 'Locations' },
  { key: 'Scoreboard', label: 'Scoreboard' },
  { key: 'Other',      label: 'Other' },
];

// Trivia round_type sub-buckets — surfaced as a secondary row when the
// host has the Trivia tab selected so they can drill into one round
// type without scrolling through every round file.
const TRIVIA_BUCKETS = ['MC', 'REG', 'MISC', 'MYS', 'BIG', '_Other'];

// Which content_types are "loadable" into which destinations. The
// matrix here drives which "Load into…" buttons appear per row.
const LOAD_DESTINATIONS = {
  round:        [{ label: 'Round Generator', href: (f) => `/roundmaker?openFile=${encodeURIComponent(f.path)}` }],
  presentation: [{ label: 'Trivia Presenter', href: (f) => `/trivia/present?openFile=${encodeURIComponent(f.path)}` }],
  pack:         [{ label: 'Round Generator', href: (f) => `/roundmaker?openFile=${encodeURIComponent(f.path)}` }],
  bingo:        [{ label: 'Bingo Lobby',     href: (f) => `/bingo?openFile=${encodeURIComponent(f.path)}` }],
  karaoke:      [],   // karaoke .bighat loader lives inside the Karaoke add-on (P4)
};

const formatSize = (b) => {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
};

const formatDate = (iso) => {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

export default function FilesTool() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [folder, setFolder] = useState('');
  const [selectedFolder, setSelectedFolder] = useState('all');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(async (which = selectedFolder) => {
    setLoading(true);
    setError(null);
    try {
      const params = which && which !== 'all' ? { folder: which } : {};
      const r = await axios.get(`${API}/api/native/files`, { params });
      setFiles(r.data.files || []);
      setFolder(r.data.folder || '');
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'list_failed');
    } finally {
      setLoading(false);
    }
  }, [selectedFolder]);

  useEffect(() => { refresh(selectedFolder); }, [selectedFolder, refresh]);

  const onPickFile = () => fileInputRef.current?.click();

  const onFileChosen = async (ev) => {
    const f = ev.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.bighat')) {
      setError(`"${f.name}" isn't a .bighat file. Choose a file ending in .bighat.`);
      ev.target.value = '';
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', f);
      // If the user has a specific subfolder selected, send it as a
      // hint so the upload lands there even if the type-detection
      // would have put it elsewhere. "all" → let the backend auto-route.
      if (selectedFolder && selectedFolder !== 'all') {
        form.append('folder', selectedFolder);
      }
      await axios.post(`${API}/api/native/files/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await refresh(selectedFolder);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : (e.message || 'upload_failed'));
    } finally {
      setUploading(false);
      ev.target.value = '';   // allow re-selecting the same filename
    }
  };

  const onDownload = (f) => {
    const url = `${API}/api/native/files/download/${encodeURIComponent(f.name)}?folder=${encodeURIComponent(f.folder || '')}`;
    window.location.href = url;
  };

  const onDelete = async (f) => {
    if (!window.confirm(`Delete "${f.name}"? This can't be undone.`)) return;
    setError(null);
    try {
      await axios.delete(`${API}/api/native/files/${encodeURIComponent(f.name)}`, {
        params: { folder: f.folder || '' },
      });
      await refresh(selectedFolder);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : (e.message || 'delete_failed'));
    }
  };

  const onReveal = async (f) => {
    setError(null);
    try {
      const form = new FormData();
      if (f) {
        form.append('name', f.name);
        form.append('folder', f.folder || '');
      } else {
        form.append('folder', selectedFolder === 'all' ? '' : selectedFolder);
      }
      const r = await axios.post(`${API}/api/native/files/reveal`, form);
      if (!r.data.ok) {
        // Headless / sandboxed env — just show the path.
        setError(`Can't open the OS file manager in this environment. Path: ${r.data.path || folder}`);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'reveal_failed');
    }
  };

  const onLoadInto = (f, dest) => {
    // Internal navigation — the destination page reads ?openFile=<path>
    // and imports the round, same way the file-association handoff works
    // when a customer double-clicks a .bighat from Explorer.
    navigate(dest.href(f));
  };

  return (
    <div data-testid="files-tool" className="min-h-screen bg-gray-50">
      <PageHeader
        title="Files"
        subtitle="Saved trivia rounds, bingo cards, karaoke playlists"
        variant="light"
        actions={(
          <Button data-testid="upload-btn" onClick={onPickFile} disabled={uploading} className="bg-blue-600 hover:bg-blue-700 text-white" size="sm">
            {uploading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading…</> : <><Upload className="w-4 h-4 mr-2" /> Upload .bighat</>}
          </Button>
        )}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".bighat"
        onChange={onFileChosen}
        className="hidden"
        data-testid="file-input"
      />

      <div className="max-w-5xl mx-auto p-8">
        <div className="bg-white rounded-xl shadow-lg p-6 sm:p-8">
          {/* Folder selector */}
          <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="folder-tabs">
            {FOLDERS.map((f) => (
              <button
                key={f.key}
                data-testid={`folder-tab-${f.key}`}
                onClick={() => setSelectedFolder(f.key)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                  selectedFolder === f.key || selectedFolder.startsWith(`${f.key}/`)
                    ? 'bg-blue-50 border-blue-300 text-blue-700'
                    : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                }`}
              >
                {f.label}
              </button>
            ))}
            <div className="flex-1" />
            <Button
              data-testid="reveal-folder-btn"
              variant="ghost"
              size="sm"
              onClick={() => onReveal(null)}
              className="text-gray-600 hover:text-blue-600"
              title="Open the folder in your file manager"
            >
              <ExternalLink className="w-4 h-4 mr-1" /> Reveal in folder
            </Button>
          </div>

          {/* Trivia round-type sub-tabs — only visible when the Trivia
              tab (or a specific Trivia/<TYPE> bucket) is selected. Lets
              the host drill into one round type without leaving the
              page. The Build Wizard + Round Roulette use the same
              underlying buckets when assembling presentations. */}
          {(selectedFolder === 'Trivia' || selectedFolder.startsWith('Trivia/')) && (
            <div className="flex flex-wrap items-center gap-2 mb-4 pl-4 border-l-2 border-blue-100"
                 data-testid="trivia-bucket-tabs">
              <span className="text-xs uppercase tracking-wider text-gray-500 mr-1">Round type:</span>
              <button
                data-testid="trivia-bucket-all"
                onClick={() => setSelectedFolder('Trivia')}
                className={`px-2 py-1 rounded text-xs font-medium border ${
                  selectedFolder === 'Trivia'
                    ? 'bg-blue-100 border-blue-300 text-blue-800'
                    : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                All
              </button>
              {TRIVIA_BUCKETS.map((bucket) => (
                <button
                  key={bucket}
                  data-testid={`trivia-bucket-${bucket}`}
                  onClick={() => setSelectedFolder(`Trivia/${bucket}`)}
                  className={`px-2 py-1 rounded text-xs font-medium border ${
                    selectedFolder === `Trivia/${bucket}`
                      ? 'bg-blue-100 border-blue-300 text-blue-800'
                      : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {bucket === '_Other' ? 'Unclassified' : bucket}
                </button>
              ))}
            </div>
          )}

          {folder && (
            <div data-testid="files-folder" className="flex items-center gap-2 text-xs text-gray-500 mb-6">
              <FolderOpen className="w-4 h-4" />
              <span>
                Saved to:{' '}
                <span className="font-mono text-gray-700">
                  {folder}
                  {selectedFolder !== 'all' ? `\\${selectedFolder}` : ''}
                </span>
              </span>
            </div>
          )}

          {error && (
            <div data-testid="files-error" className="flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-red-800">{error}</div>
            </div>
          )}

          {loading ? (
            <div className="text-center text-gray-500 py-12"><Loader2 className="w-6 h-6 animate-spin inline mr-2" /> Loading files…</div>
          ) : files.length === 0 ? (
            <div data-testid="empty-state" className="text-center py-16 border-2 border-dashed border-gray-200 rounded-lg">
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <div className="text-gray-700 font-medium">No .bighat files yet</div>
              <div className="text-sm text-gray-500 mt-1">Upload your first file to get started.</div>
            </div>
          ) : (
            <div data-testid="files-list" className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                  <tr>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Folder</th>
                    <th className="px-4 py-2 font-medium">Summary</th>
                    <th className="px-4 py-2 font-medium">Size</th>
                    <th className="px-4 py-2 font-medium">Modified</th>
                    <th className="px-4 py-2 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {files.map((f) => {
                    const dests = LOAD_DESTINATIONS[f.type] || [];
                    return (
                      <tr key={`${f.folder}/${f.name}`} data-testid={`file-row-${f.name}`} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-gray-900 break-all">{f.name}</td>
                        <td className="px-4 py-3 text-gray-600">
                          <span className="inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100">
                            {f.folder}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {f.summary
                            ? <span data-testid={`summary-${f.name}`}>{f.summary}</span>
                            : <span className="text-gray-400 italic">—</span>}
                        </td>
                        <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatSize(f.size_bytes)}</td>
                        <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{formatDate(f.modified_at)}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1 flex-wrap">
                            {dests.map((d, i) => {
                              const Icon = i === 0 ? Play : Pencil;
                              return (
                                <Button
                                  key={d.label}
                                  data-testid={`load-${f.name}-${i}`}
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => onLoadInto(f, d)}
                                  className="text-blue-600 hover:bg-blue-50"
                                  title={`Load into ${d.label}`}
                                >
                                  <Icon className="w-4 h-4 mr-1" />
                                  <span className="hidden sm:inline">{d.label}</span>
                                </Button>
                              );
                            })}
                            <Button data-testid={`reveal-${f.name}`} size="sm" variant="ghost" onClick={() => onReveal(f)} title="Reveal in folder">
                              <ExternalLink className="w-4 h-4" />
                            </Button>
                            <Button data-testid={`download-${f.name}`} size="sm" variant="ghost" onClick={() => onDownload(f)} title="Download">
                              <Download className="w-4 h-4" />
                            </Button>
                            <Button data-testid={`delete-${f.name}`} size="sm" variant="ghost" onClick={() => onDelete(f)} className="text-red-600 hover:bg-red-50" title="Delete">
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
