import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Upload, Download, Trash2, FolderOpen, FileText, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '../components/ui/button';

const API = process.env.REACT_APP_BACKEND_URL;

const formatSize = (b) => {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
};

const formatDate = (iso) => {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

// .bighat file manager. Lists, uploads, downloads, deletes files stored in
// the user's BIGHat Entertainment/Files folder.
export default function FilesTool() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [folder, setFolder] = useState('');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API}/api/native/files`);
      setFiles(r.data.files || []);
      setFolder(r.data.folder || '');
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'list_failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

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
      await axios.post(`${API}/api/native/files/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await refresh();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : (e.message || 'upload_failed'));
    } finally {
      setUploading(false);
      ev.target.value = '';   // allow re-selecting the same filename
    }
  };

  const onDownload = (name) => {
    // Same-origin download; the backend sets a filename header.
    window.location.href = `${API}/api/native/files/download/${encodeURIComponent(name)}`;
  };

  const onDelete = async (name) => {
    if (!window.confirm(`Delete "${name}"? This can't be undone.`)) return;
    setError(null);
    try {
      await axios.delete(`${API}/api/native/files/${encodeURIComponent(name)}`);
      await refresh();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : (e.message || 'delete_failed'));
    }
  };

  return (
    <div data-testid="files-tool" className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <Button data-testid="back-btn" variant="ghost" onClick={() => navigate('/')} className="mb-4">
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to dashboard
        </Button>

        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Files</h1>
              <p className="text-sm text-gray-500 mt-1">
                Save and organise your <code className="font-mono bg-gray-100 px-1">.bighat</code> files (trivia rounds, bingo cards, karaoke playlists, etc.).
              </p>
            </div>
            <Button data-testid="upload-btn" onClick={onPickFile} disabled={uploading} className="bg-blue-600 hover:bg-blue-700 text-white">
              {uploading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading…</> : <><Upload className="w-4 h-4 mr-2" /> Upload .bighat</>}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".bighat"
              onChange={onFileChosen}
              className="hidden"
              data-testid="file-input"
            />
          </div>

          {folder && (
            <div data-testid="files-folder" className="flex items-center gap-2 text-xs text-gray-500 mb-6 mt-2">
              <FolderOpen className="w-4 h-4" />
              <span>Files are saved to: <span className="font-mono text-gray-700">{folder}</span></span>
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
                    <th className="px-4 py-2 font-medium">Summary</th>
                    <th className="px-4 py-2 font-medium">Size</th>
                    <th className="px-4 py-2 font-medium">Modified</th>
                    <th className="px-4 py-2 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {files.map((f) => (
                    <tr key={f.name} data-testid={`file-row-${f.name}`} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-gray-900">{f.name}</td>
                      <td className="px-4 py-3 text-gray-700">
                        {f.summary
                          ? <span data-testid={`summary-${f.name}`}>{f.summary}</span>
                          : <span className="text-gray-400 italic">—</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{formatSize(f.size_bytes)}</td>
                      <td className="px-4 py-3 text-gray-600">{formatDate(f.modified_at)}</td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <Button data-testid={`download-${f.name}`} size="sm" variant="ghost" onClick={() => onDownload(f.name)}>
                          <Download className="w-4 h-4" />
                        </Button>
                        <Button data-testid={`delete-${f.name}`} size="sm" variant="ghost" onClick={() => onDelete(f.name)} className="text-red-600 hover:bg-red-50">
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
