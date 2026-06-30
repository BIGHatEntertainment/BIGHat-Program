import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Download, CheckCircle2, AlertCircle, Loader2, RefreshCw, PlayCircle } from 'lucide-react';
import { Button } from '../components/ui/button';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';

const API = process.env.REACT_APP_BACKEND_URL;

// Manual update checker. Hits /api/native/updates/check, surfaces the
// manifest in plain language (version + what's new bullets), and lets
// the user trigger the download AND apply steps right here. The apply
// step is master-admin gated server-side (`/api/native/updates/apply`
// returns 403 for non-master roles), so a regular host who hits this
// page sees the "downloaded" banner without the install button.
// Pre-alpha.29 this page told master admins to "go to Admin → Updates
// → Install" — there was no such location, so the install never
// happened. Fixed by exposing the install action inline.
export default function UpdateTool() {
  const { user } = useAuth();
  const isMasterAdmin = user?.role === 'master_admin';
  const [status, setStatus] = useState(null);          // last known status snapshot
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);          // newest manifest after check
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

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

  // Master-admin only — backend enforces it via `require_master_admin`.
  // We hit /apply with the downloaded version; the backend writes a
  // `pending_apply.json` and the Tauri shell relaunches into the new
  // binary on next startup (or now, depending on the installer flag).
  const onApply = async () => {
    if (!isMasterAdmin) return;
    setError(null); setApplying(true);
    try {
      const v = result?.manifest?.latest_version || status?.latest_known?.latest_version;
      await axios.post(`${API}/api/native/updates/apply`, v ? { version: v } : {});
      setApplied(true);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message || 'apply_failed';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setApplying(false);
    }
  };

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
                {downloaded ? (
                  <div data-testid="update-downloaded" className="space-y-3">
                    <div className="flex items-center gap-2 text-sm text-green-800 font-medium">
                      <CheckCircle2 className="w-4 h-4" />
                      Update downloaded and ready to install.
                    </div>
                    {applied ? (
                      // Post-apply hint. The Tauri shell handles the
                      // restart itself — we just tell the user what to
                      // expect so they don't think the page is stuck.
                      <div data-testid="update-applied" className="text-sm bg-blue-50 border border-blue-200 text-blue-900 rounded-lg p-3">
                        Update queued. The app will relaunch into the new version momentarily — if it doesn&apos;t, close and reopen BIG Hat Entertainment to finish.
                      </div>
                    ) : isMasterAdmin ? (
                      <Button
                        data-testid="install-update-btn"
                        onClick={onApply}
                        disabled={applying}
                        className="bg-blue-600 hover:bg-blue-700 text-white"
                      >
                        {applying ? (
                          <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Installing…</>
                        ) : (
                          <><PlayCircle className="w-4 h-4 mr-2" /> Install update now</>
                        )}
                      </Button>
                    ) : (
                      <div className="text-xs text-green-800/80">
                        Ask a master admin to sign in and click <strong>Install update now</strong> on this page to apply it.
                      </div>
                    )}
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
