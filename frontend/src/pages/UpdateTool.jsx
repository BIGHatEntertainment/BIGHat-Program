import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, CheckCircle2, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';

const API = process.env.REACT_APP_BACKEND_URL;

// Manual update checker. Hits /api/native/updates/check, surfaces the
// manifest in plain language (version + what's new bullets), and lets the
// user trigger the download step. Apply step still requires master-admin
// auth so we link them to it but don't try to invoke it inline.
export default function UpdateTool() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);          // last known status snapshot
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);          // newest manifest after check
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  // Load the cached status on mount so we can show "last checked" even
  // before the user clicks Check Now.
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/api/native/updates/status`)
      .then((r) => { if (!cancelled) setStatus(r.data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const onCheck = async () => {
    setError(null); setDownloaded(false); setResult(null); setChecking(true);
    try {
      const r = await axios.post(`${API}/api/native/updates/check`);
      setResult(r.data);
      setStatus(r.data);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message || 'check_failed';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setChecking(false);
    }
  };

  const onDownload = async () => {
    setError(null); setDownloading(true);
    try {
      await axios.post(`${API}/api/native/updates/download`);
      setDownloaded(true);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message || 'download_failed';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setDownloading(false);
    }
  };

  const hasUpdate = result?.update_available === true ||
                    (status?.latest_known?.latest_version && status?.installed_version &&
                     status.latest_known.latest_version !== status.installed_version);
  const m = result?.manifest || status?.latest_known || {};
  const notes = m?.release_notes || m?.notes || m?.changelog || '';
  const noteLines = (Array.isArray(notes) ? notes : String(notes).split('\n'))
    .map((s) => String(s).trim())
    .filter(Boolean);

  return (
    <div data-testid="update-tool" className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <Button data-testid="back-btn" variant="ghost" onClick={() => navigate('/')} className="mb-4">
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to dashboard
        </Button>

        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Update</h1>
              <p className="text-sm text-gray-500 mt-1">
                Check for new features and improvements to BIG Hat Entertainment.
              </p>
            </div>
            <Button data-testid="check-update-btn" onClick={onCheck} disabled={checking} className="bg-blue-600 hover:bg-blue-700 text-white">
              {checking ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Checking…</> : <><RefreshCw className="w-4 h-4 mr-2" /> Check now</>}
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="border rounded-lg p-4">
              <div className="text-xs text-gray-500 uppercase tracking-wide">Installed version</div>
              <div data-testid="installed-version" className="text-2xl font-mono font-semibold text-gray-900 mt-1">
                {status?.installed_version || result?.installed_version || '—'}
              </div>
            </div>
            <div className="border rounded-lg p-4">
              <div className="text-xs text-gray-500 uppercase tracking-wide">Latest available</div>
              <div data-testid="latest-version" className="text-2xl font-mono font-semibold text-gray-900 mt-1">
                {result?.manifest?.latest_version || status?.latest_known?.latest_version || '—'}
              </div>
            </div>
          </div>

          {error && (
            <div data-testid="update-error" className="flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-lg mb-4">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium text-red-900">Couldn&apos;t check for updates</div>
                <div className="text-sm text-red-700 mt-1">{error}</div>
                <div className="text-xs text-red-600 mt-2">
                  {String(error).includes('channel_not_configured')
                    ? 'This installer wasn\'t built with the canonical update channel. Re-install the latest version from your post-purchase email to fix this.'
                    : 'Make sure you\'re connected to the internet, then click "Check now" again.'}
                </div>
              </div>
            </div>
          )}

          {result && !error && (
            hasUpdate ? (
              <div data-testid="update-available" className="border-2 border-green-200 bg-green-50 rounded-lg p-5 mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-5 h-5 text-green-600" />
                  <span className="font-semibold text-green-900">
                    Update available: {m.latest_version || m.version}
                  </span>
                </div>
                {noteLines.length > 0 && (
                  <>
                    <div className="text-sm font-medium text-gray-800 mb-1">What&apos;s new:</div>
                    <ul className="list-disc list-inside text-sm text-gray-700 space-y-1 mb-4">
                      {noteLines.slice(0, 10).map((line, i) => <li key={i}>{line.replace(/^[-•*]\s*/, '')}</li>)}
                    </ul>
                  </>
                )}
                {downloaded ? (
                  <div data-testid="update-downloaded" className="text-sm text-green-800 font-medium">
                    ✅ Update downloaded. A master admin can apply it from Admin → Updates → Install.
                  </div>
                ) : (
                  <Button data-testid="download-update-btn" onClick={onDownload} disabled={downloading} className="bg-green-600 hover:bg-green-700 text-white">
                    {downloading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Downloading…</> : <><Download className="w-4 h-4 mr-2" /> Download update</>}
                  </Button>
                )}
              </div>
            ) : (
              <div data-testid="up-to-date" className="border-2 border-gray-200 bg-gray-50 rounded-lg p-5 mb-4 flex items-start gap-3">
                <CheckCircle2 className="w-5 h-5 text-gray-500 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold text-gray-900">You&apos;re up to date</div>
                  <div className="text-sm text-gray-600 mt-1">
                    The latest version of BIG Hat Entertainment is already installed. We&apos;ll check again the next time you click &quot;Check now&quot;.
                  </div>
                </div>
              </div>
            )
          )}

          <p className="text-xs text-gray-500 mt-6">
            Updates require an internet connection. The app keeps working offline using your installed version.
          </p>
        </div>
      </div>
    </div>
  );
}
