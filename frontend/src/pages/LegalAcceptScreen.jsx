import React, { useState } from 'react';

// First-launch legal acceptance (Terms, Privacy Policy, California addendum).
// Bump LEGAL_VERSION when the documents change so users are asked again.
export const LEGAL_VERSION = '2026-10-10';
const KEY = 'bighat_legal_accepted';

// Pages that guests' phones and TV windows open directly. They must never be
// blocked by the host's acceptance screen.
export const GUEST_PATHS = [
  '/karaoke/audience',
  '/karaoke/request',
  '/trivia/audience',
  '/bingo/audience',
];

export function hasAcceptedLegal() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null');
    return !!v && v.version === LEGAL_VERSION;
  } catch (e) {
    return false;
  }
}

function saveAccepted() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ version: LEGAL_VERSION, at: new Date().toISOString() }));
  } catch (e) { /* storage blocked: the screen will simply show again next launch */ }
}

// Page images (public/legal/pages/<id>-<n>.png) are used instead of the browser's PDF viewer: the desktop
// webview draws an embedded PDF in a small strip and blocks "open in new window". Images scroll normally.
const DOCS = [
  { id: 'terms', label: 'Terms and Conditions', pages: 5 },
  { id: 'privacy', label: 'Privacy Policy', pages: 4 },
  { id: 'california', label: 'California Privacy Addendum', pages: 3 },
];

export default function LegalAcceptScreen({ onAccept }) {
  const [tab, setTab] = useState(0);
  const [agreed, setAgreed] = useState(false);
  const doc = DOCS[tab];

  const accept = () => {
    if (!agreed) return;
    saveAccepted();
    onAccept();
  };

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
      <button onClick={accept} disabled={!agreed} data-testid="legal-accept-btn"
              style={{ padding: '12px 28px', borderRadius: 10, border: 0, fontWeight: 700, fontSize: 15,
                       background: agreed ? '#fbdd68' : '#3a4560', color: agreed ? '#1a1a1a' : '#8892b0',
                       cursor: agreed ? 'pointer' : 'not-allowed' }}>
        I Agree and Continue
      </button>
      <p style={{ color: '#8892b0', fontSize: 12, marginTop: 10 }}>
        If you do not agree, close BIG Hat and uninstall it.
      </p>
    </div>
  );
}
