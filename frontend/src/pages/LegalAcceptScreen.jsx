import React, { useState, useEffect } from 'react';

// First-launch legal acceptance (Terms, Privacy Policy, California addendum).
// Bump LEGAL_VERSION when the documents change so users are asked again.
// The user is also asked again after a new app version is installed; the
// backend compares the app version stored with the acceptance record.
export const LEGAL_VERSION = '2026-10-10';
const KEY = 'bighat_legal_accepted'; // localStorage mirror (fallback only)
const API = process.env.REACT_APP_BACKEND_URL || '';

// Pages that guests' phones and TV windows open directly. They must never be
// blocked by the host's acceptance screen.
export const GUEST_PATHS = [
  '/karaoke/audience',
  '/karaoke/request',
  '/trivia/audience',
  '/bingo/audience',
];

function localAccepted() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null');
    return !!v && v.version === LEGAL_VERSION;
  } catch (e) {
    return false;
  }
}

// The persistent record lives in the backend's per-user data dir (survives
// restarts and updates). Resolves true only when it matches BOTH the current
// legal version and the installed app version. If the backend cannot be
// reached we do NOT silently trust localStorage for a changed app version; we
// fall back to it only when the backend errors, so the user is never locked out.
export async function checkLegalAccepted() {
  try {
    const r = await fetch(
      `${API}/api/native/system/legal/status?legal_version=${encodeURIComponent(LEGAL_VERSION)}`,
      { cache: 'no-store' },
    );
    if (!r.ok) throw new Error(`status ${r.status}`);
    const j = await r.json();
    return !!j.accepted;
  } catch (e) {
    return localAccepted();
  }
}

async function saveAccepted() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ version: LEGAL_VERSION, at: new Date().toISOString() }));
  } catch (e) { /* storage blocked: backend record is the source of truth */ }
  try {
    const r = await fetch(`${API}/api/native/system/legal/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ legal_version: LEGAL_VERSION }),
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

// Page images (public/legal/pages/<id>-<n>.png) are used instead of the browser's PDF viewer:
// the desktop webview draws an embedded PDF in a small strip and blocks "open in new window".
// Images scroll normally.
const DOCS = [
  { id: 'terms', label: 'Terms and Conditions', pages: 5 },
  { id: 'privacy', label: 'Privacy Policy', pages: 4 },
  { id: 'california', label: 'California Privacy Addendum', pages: 3 },
];

// Kept for App.js compatibility. Always false: the real answer is async (it
// comes from the backend's persistent record), so LegalAcceptScreen checks it
// itself on mount and passes straight through when already accepted.
export function hasAcceptedLegal() {
  return false;
}

export default function LegalAcceptScreen({ onAccept }) {
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    let alive = true;
    checkLegalAccepted().then((ok) => {
      if (!alive) return;
      if (ok) onAccept(); else setChecking(false);
    });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [tab, setTab] = useState(0);
  const [agreed, setAgreed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [warn, setWarn] = useState('');
  const doc = DOCS[tab];

  const accept = async () => {
    if (!agreed || saving) return;
    setSaving(true);
    const ok = await saveAccepted();
    setSaving(false);
    if (!ok) {
      // Let them in for this session, but tell them the record did not save.
      setWarn('Your agreement could not be saved to disk, so you may be asked again next launch.');
    }
    onAccept();
  };

  if (checking) return <div data-testid="legal-checking" style={{ minHeight: '100vh', background: '#000e2a' }} />;

  return (
    <div data-testid="legal-accept-screen"
         style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center',
                  background: '#000e2a', color: '#e5edff', padding: 20, boxSizing: 'border-box',
                  fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <h1 style={{ color: '#fbdd68', margin: '4px 0 2px', fontSize: 26 }}>Before you begin</h1>
      <p style={{ color: '#8892b0', margin: '0 0 12px', fontSize: 14, textAlign: 'center', maxWidth: 720 }}>
        Please read the Terms and Conditions, Privacy Policy and California Privacy Addendum for the BIG Hat Program.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
        {DOCS.map((d, i) => (
          <button key={d.id} onClick={() => setTab(i)} data-testid={`legal-tab-${d.id}`}
                  style={{ padding: '8px 14px', borderRadius: 8, border: 0, cursor: 'pointer', fontWeight: 600,
                           background: i === tab ? '#fbdd68' : '#0f1d3a', color: i === tab ? '#1a1a1a' : '#e5edff' }}>
            {d.label}
          </button>
        ))}
      </div>

      <div data-testid="legal-doc-scroll"
           style={{ width: '100%', maxWidth: 900, height: '55vh', minHeight: 260, overflowY: 'auto',
                    background: '#2b2f3a', borderRadius: 8, padding: 10, boxSizing: 'border-box' }}>
        {Array.from({ length: doc.pages }, (_, n) => (
          <img key={`${doc.id}-${n}`} src={`/legal/pages/${doc.id}-${n + 1}.png`}
               alt={`${doc.label}, page ${n + 1} of ${doc.pages}`}
               style={{ display: 'block', width: '100%', height: 'auto', background: '#fff',
                        borderRadius: 4, marginBottom: 10 }} />
        ))}
      </div>
      <p style={{ color: '#8892b0', fontSize: 12, margin: '6px 0' }}>
        Scroll to read all {doc.pages} pages of the {doc.label}.
      </p>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, margin: '6px 0 10px', cursor: 'pointer' }}>
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
               data-testid="legal-agree-checkbox" />
        I have read and agree to the Terms and Conditions, and I acknowledge the Privacy Policy and California Privacy Addendum.
      </label>
      <button onClick={accept} disabled={!agreed || saving} data-testid="legal-accept-btn"
              style={{ padding: '12px 28px', borderRadius: 10, border: 0, fontWeight: 700, fontSize: 15,
                       background: agreed ? '#fbdd68' : '#3a4560', color: agreed ? '#1a1a1a' : '#8892b0',
                       cursor: agreed && !saving ? 'pointer' : 'not-allowed' }}>
        {saving ? 'Saving...' : 'I Agree and Continue'}
      </button>
      {warn && <p data-testid="legal-save-warning" style={{ color: '#ffb4a2', fontSize: 12, marginTop: 8 }}>{warn}</p>}
      <p style={{ color: '#8892b0', fontSize: 12, marginTop: 10 }}>
        If you do not agree, close BIG Hat and uninstall it.
      </p>
    </div>
  );
}
