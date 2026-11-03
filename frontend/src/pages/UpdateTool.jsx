import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Download, CheckCircle2, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import PageHeader from '../components/PageHeader';
import { openExternal } from '../lib/openExternal';

const API = process.env.REACT_APP_BACKEND_URL;

// Manual update checker. Hits /api/native/updates/check and shows the newest version in plain language.
// v32.2.10: the green button now DOWNLOADS the installer itself (real progress, a real file in Downloads, shown only when the whole file is on disk).
// Before, it asked the OS to open a link and showed "your browser is downloading" without any proof that anything happened.
// v32.2.1: the green button now opens this PC's installer download in the user's own browser (or the release page when the update
// channel has no installer for this OS). Before, it copied the installer into a hidden folder and showed nothing, and the
// "Install update now" step that followed could not install an .exe / .dmg. The user runs the downloaded setup, which replaces the old version.
export default function UpdateTool() {
  const [status, setStatus] = useState(null);          // last known status snapshot
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);          // newest manifest after check
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [opened, setOpened] = useState(null);          // {url, filename, direct} fallback only: the plain link when the program could not download it
  const [dl, setDl] = useState(null);                  // real download state from the backend: {state, percent, bytes, total, filename, path, message}
  const [shown, setShown] = useState(null);            // result of "Show in folder"
  const pollRef = useRef(null);

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
    setError(null); setOpened(null); setResult(null); setChecking(true);
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

  // v32.2.10: ask the program to download the installer, then watch the REAL status until the file is on disk (or it failed).
  const stopPolling = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  const poll = () => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const r = await axios.get(`${API}/api/native/updates/download-installer/status`, { timeout: 8000 });
        setDl(r.data);
        if (r.data.state !== 'running') stopPolling();
      } catch { /* the program is busy for a moment; keep watching */ }
    }, 700);
  };
  useEffect(() => {
    // closing and reopening the page (or the program) must not lose a download that is running or finished
    axios.get(`${API}/api/native/updates/download-installer/status`).then((r) => {
      if (r.data?.state === 'running') { setDl(r.data); poll(); } else if (r.data?.state === 'done') setDl(r.data);
    }).catch(() => {});
    return stopPolling;
  }, []);                                                                        // eslint-disable-line react-hooks/exhaustive-deps

  const onDownload = async () => {
    setError(null); setShown(null); setOpened(null); setDownloading(true);
    try {
      if (dl?.state === 'failed') await axios.post(`${API}/api/native/updates/download-installer/reset`).catch(() => {});
      const r = await axios.post(`${API}/api/native/updates/download-installer`, {}, { timeout: 30000 });
      const info = r.data || {};
      if (info.reason === 'no_update_available') { setDl(null); setError('You already have the newest version.'); return; }
      if (info.no_direct_link) {                                                 // the update server has no installer for this PC: the release page is the honest answer
        setDl(null);
        const ok = info.url ? await openExternal(info.url, () => {}) : false;
        setOpened({ url: info.url, filename: info.filename, direct: false, ok });
        return;
      }
      setDl(info);
      if (info.state === 'running') poll();
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message || 'download_failed';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setDownloading(false);
    }
  };

  const onShow = async () => {
    try {
      const r = await axios.post(`${API}/api/native/updates/download-installer/show`);
      setShown(r.data);
    } catch { setShown({ ok: false, message: 'Could not open the folder.' }); }
  };

  const mb = (n) => `${(Number(n || 0) / 1048576).toFixed(1)} MB`;

  // v32.0.0-alpha.20: belt-and-suspenders. Backend `update_available`
  // is authoritative when present, but if both sides disagree on the
  // version strings displayed in the cards (e.g. installed=18,
  // latest=19), trust the strings — they're the ground truth the user
  // can see. Fixes the alpha.18 → alpha.19 false "You're up to date".
  const installedStr = status?.installed_version || result?.installed_version || '';
  const latestStr    = result?.manifest?.latest_version || status?.latest_known?.latest_version || '';
  const stringsDiffer = installedStr && latestStr && installedStr !== latestStr;
  const hasUpdate = result?.update_available === true || stringsDiffer === true;
  const m = result?.manifest || status?.latest_known || {};
  const notes = m?.release_notes || m?.notes || m?.changelog || '';
  const noteLines = (Array.isArray(notes) ? notes : String(notes).split('\n'))
    .map((s) => String(s).trim())
    .filter(Boolean);

  return (
    <div data-testid="update-tool" className="min-h-screen bg-gray-50">
      <PageHeader title="Update" subtitle="Check for new features and improvements" variant="light" />
      <div className="max-w-3xl mx-auto p-8">
        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold text-gray-900">Check for updates</h2>
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
            <div data-testid="update-error" className="flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-lg mb-4 min-w-0">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-red-900">Couldn&apos;t check for updates</div>
                {/*
                  Error detail can be a 1KB+ pre-signed S3 URL when GitHub
                  redirects fail. Cap height + scroll + break long tokens so it
                  never overflows the card. Use a code-like block so the
                  customer can still copy-paste it into a support ticket.
                  v32.0.0-alpha.22 UX fix.
                */}
                <pre data-testid="update-error-detail"
                     className="text-xs text-red-700 mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono p-2 bg-red-100/40 rounded border border-red-200">
{String(error)}
                </pre>
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
                <Button data-testid="download-update-btn" onClick={onDownload}
                        disabled={downloading || dl?.state === 'running'} className="bg-green-600 hover:bg-green-700 text-white">
                  {downloading || dl?.state === 'running'
                    ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Downloading…</>
                    : dl?.state === 'failed' ? <><Download className="w-4 h-4 mr-2" /> Try again</>
                    : dl?.state === 'done' ? <><Download className="w-4 h-4 mr-2" /> Download again</>
                    : <><Download className="w-4 h-4 mr-2" /> Download update</>}
                </Button>

                {dl?.state === 'running' && (
                  <div data-testid="update-progress" className="mt-4 text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-lg p-3">
                    <div className="mb-2">Downloading <strong>{dl.filename || 'the installer'}</strong>{dl.total ? ` (${mb(dl.bytes)} of ${mb(dl.total)})` : ''}</div>
                    <div className="h-2 w-full bg-blue-100 rounded"><div className="h-2 bg-blue-600 rounded transition-all" style={{ width: `${dl.percent || 3}%` }} /></div>
                  </div>
                )}
                {dl?.state === 'done' && (
                  <div data-testid="update-downloaded" className="mt-4 text-sm bg-green-50 border border-green-300 text-green-900 rounded-lg p-3 space-y-2">
                    <div><strong>Downloaded:</strong> {dl.filename} ({mb(dl.total || dl.bytes)}). It is saved in your Downloads folder.</div>
                    <div>To finish: <strong>close BIG Hat Entertainment</strong>, then open the downloaded file. It replaces the old version and keeps your files.</div>
                    <Button data-testid="show-installer-btn" onClick={onShow} variant="outline" className="border-green-600 text-green-800">Show the file in its folder</Button>
                    {shown && <div className={shown.ok ? 'text-green-800' : 'text-red-700'} data-testid="show-result">{shown.ok ? 'Opened your Downloads folder.' : (shown.message || 'Could not open the folder. Look for the file in your Downloads folder.')}</div>}
                  </div>
                )}
                {dl?.state === 'failed' && (
                  <div data-testid="update-failed" className="mt-4 text-sm bg-red-50 border border-red-300 text-red-900 rounded-lg p-3 space-y-1">
                    <div><strong>The update did not download.</strong> {dl.message || 'Try again.'}</div>
                    <div className="text-xs text-red-800">Nothing was installed and your files are untouched. Press <strong>Try again</strong>.</div>
                  </div>
                )}
                {opened && (
                  <div data-testid="update-opened" className="mt-4 text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-lg p-3 space-y-2">
                    {opened.ok ? (
                      <div>
                        Your browser opened the download page. Pick the installer for your computer, then close BIG Hat Entertainment and open the downloaded file.
                      </div>
                    ) : (
                      <div>Your browser could not be opened from here. Copy this link into your browser to download the update:</div>
                    )}
                    <div className="break-all font-mono text-xs bg-white/70 rounded p-2 select-all" data-testid="update-link">{opened.url}</div>
                  </div>
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
