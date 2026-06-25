import React, { useEffect, useState } from 'react';
import { Minus, Square, X } from 'lucide-react';

// Tauri v2 chromeless title bar — minimal, debug-loggable, with direct
// (non-wrapped) IPC calls. Right-click in the app → Inspect → Console:
// every click logs exactly what happened, so if a future regression hides
// behind another silent rejection we can diagnose without guessing.

function inTauri() {
  return typeof window !== 'undefined' &&
    (window.__TAURI_INTERNALS__ !== undefined || window.__TAURI__ !== undefined);
}

async function getWin() {
  // Prefer the dynamic import — it works in both withGlobalTauri:true and
  // withGlobalTauri:false setups, and the bundler resolves it statically.
  try {
    const mod = await import('@tauri-apps/api/window');
    const fn = mod.getCurrentWindow || mod.getCurrent;
    if (typeof fn === 'function') return fn();
  } catch (e) {
    console.error('[TitleBar] dynamic import failed', e);
  }
  // Last-resort fallback via the global.
  const g = window.__TAURI__ && window.__TAURI__.window;
  if (g && typeof g.getCurrentWindow === 'function') return g.getCurrentWindow();
  return null;
}

async function callWin(name) {
  console.log(`[TitleBar] ${name} clicked`);
  const w = await getWin();
  if (!w) {
    console.error(`[TitleBar] no window handle available for ${name}`);
    return;
  }
  try {
    if (name === 'minimize')       await w.minimize();
    else if (name === 'maximize')  await w.toggleMaximize();
    else if (name === 'close')     await w.close();
    console.log(`[TitleBar] ${name} OK`);
  } catch (e) {
    console.error(`[TitleBar] ${name} FAILED`, e);
  }
}

function Btn({ id, label, onClick, danger, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseDown={(e) => e.stopPropagation()}   // stop Tauri drag handler from eating the click
      title={label}
      aria-label={label}
      data-testid={`tauri-titlebar-${id}`}
      className={`tauri-titlebar__btn ${danger ? 'tauri-titlebar__btn--close' : ''}`}
    >
      {children}
    </button>
  );
}

function TitleBar() {
  const [isMax, setIsMax] = useState(false);

  useEffect(() => {
    if (!inTauri()) return;
    let unlisten = null;
    (async () => {
      const w = await getWin();
      if (!w) return;
      try {
        setIsMax(await w.isMaximized());
        unlisten = await w.onResized(async () => {
          try { setIsMax(await w.isMaximized()); } catch (_) { /* ignore */ }
        });
      } catch (e) {
        console.error('[TitleBar] resize listener setup failed', e);
      }
    })();
    return () => { try { unlisten && unlisten(); } catch (_) { /* ignore */ } };
  }, []);

  if (!inTauri()) return null;

  return (
    <div className="tauri-titlebar" data-testid="tauri-titlebar">
      <div className="tauri-titlebar__brand" data-tauri-drag-region>
        <img src="/logo.png" alt="" className="tauri-titlebar__logo" />
        <span className="tauri-titlebar__title">BIG HAT ENTERTAINMENT</span>
      </div>
      <div className="tauri-titlebar__controls">
        <Btn id="minimize" label="Minimize" onClick={() => callWin('minimize')}>
          <Minus size={14} strokeWidth={2} />
        </Btn>
        <Btn id="maximize" label={isMax ? 'Restore' : 'Maximize'} onClick={() => callWin('maximize')}>
          <Square size={12} strokeWidth={2} />
        </Btn>
        <Btn id="close" label="Close" onClick={() => callWin('close')} danger>
          <X size={14} strokeWidth={2} />
        </Btn>
      </div>
    </div>
  );
}

export default TitleBar;
