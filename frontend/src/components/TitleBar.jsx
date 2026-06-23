import React, { useEffect, useState } from 'react';

/**
 * Native chromeless title bar — renders ONLY when the app is running
 * inside the Tauri shell (v32.0.0+). Inside a regular browser dev preview
 * it's a no-op so the React routes look identical.
 *
 * Visual contract (LYRX-style, locked in by user 2026-06-21):
 *   - Slim 36px bar
 *   - Solid navy background (#0a1428) with 1px gold-tinted bottom border
 *   - Hat logo (18px) + "BIG HAT ENTERTAINMENT" wordmark on the left
 *   - Minimize / Maximize-Restore / Close buttons on the right
 *   - The entire bar is a drag region EXCEPT for the buttons
 *   - Close button hovers red, others hover gold-tinted
 *
 * Tauri Window API (v2):
 *   - getCurrentWindow().minimize()    → minimize
 *   - getCurrentWindow().toggleMaximize() → max/restore
 *   - getCurrentWindow().close()        → close
 *   - startDragging() is auto-wired via CSS `app-region: drag` (no IPC).
 */

const isTauri = typeof window !== 'undefined'
  && (window.__TAURI_INTERNALS__ !== undefined || window.__TAURI__ !== undefined);

function useTauriWindow() {
  const [api, setApi] = useState(null);
  useEffect(() => {
    if (!isTauri) return;
    let cancelled = false;
    // Tauri 2.x global is exposed via withGlobalTauri=true in tauri.conf.json.
    // Falls back to dynamic import for callers that disable the global.
    const wnd = window.__TAURI__?.window || window.__TAURI__;
    if (wnd?.getCurrentWindow) {
      setApi(wnd.getCurrentWindow());
      return;
    }
    // Async fallback — import the ESM module shipped by @tauri-apps/api.
    import('@tauri-apps/api/window')
      .then((mod) => {
        if (cancelled) return;
        const w = mod.getCurrentWindow?.() || mod.getCurrent?.();
        if (w) setApi(w);
      })
      .catch(() => {
        // Module not installed in dev preview — silently fall back to no-op.
      });
    return () => { cancelled = true; };
  }, []);
  return api;
}

function WindowButton({ label, onClick, variant = 'default', children, testid }) {
  return (
    <button
      type="button"
      className={`tauri-titlebar__btn tauri-titlebar__btn--${variant}`}
      onClick={onClick}
      aria-label={label}
      title={label}
      data-testid={testid}
    >
      {children}
    </button>
  );
}

export function TitleBar() {
  const wnd = useTauriWindow();
  const [isMax, setIsMax] = useState(false);

  // Keep the maximize icon in sync with the actual window state.
  useEffect(() => {
    if (!wnd) return;
    let unlisten = null;
    let mounted = true;
    (async () => {
      try {
        const m = await wnd.isMaximized();
        if (mounted) setIsMax(Boolean(m));
        // Tauri 2.x: onResized fires on max/restore/snap.
        unlisten = await wnd.onResized?.(async () => {
          if (!mounted) return;
          try { setIsMax(Boolean(await wnd.isMaximized())); } catch { /* ignore */ }
        });
      } catch { /* ignore */ }
    })();
    return () => { mounted = false; if (typeof unlisten === 'function') unlisten(); };
  }, [wnd]);

  if (!isTauri) return null;

  const safe = (fn) => async () => {
    if (!wnd) return;
    try { await fn(wnd); } catch { /* swallow — best-effort window control */ }
  };

  return (
    <div
      className="tauri-titlebar"
      data-tauri-drag-region
      data-testid="tauri-titlebar"
    >
      <div className="tauri-titlebar__brand" data-tauri-drag-region>
        <img
          src="/hat-logo.png"
          alt=""
          className="tauri-titlebar__logo"
          draggable={false}
        />
        <span className="tauri-titlebar__wordmark">BIG HAT ENTERTAINMENT</span>
      </div>
      <div className="tauri-titlebar__controls">
        <WindowButton
          label="Minimize"
          variant="default"
          onClick={safe((w) => w.minimize())}
          testid="tauri-titlebar-minimize"
        >
          {/* Minus */}
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <rect x="1" y="4.5" width="8" height="1" fill="currentColor" />
          </svg>
        </WindowButton>
        <WindowButton
          label={isMax ? 'Restore' : 'Maximize'}
          variant="default"
          onClick={safe((w) => w.toggleMaximize())}
          testid="tauri-titlebar-maximize"
        >
          {isMax ? (
            // Restore — two stacked squares
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <rect x="2" y="0" width="8" height="8" fill="none" stroke="currentColor" />
              <rect x="0" y="2" width="8" height="8" fill="#0a1428" stroke="currentColor" />
            </svg>
          ) : (
            // Maximize — single square
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" />
            </svg>
          )}
        </WindowButton>
        <WindowButton
          label="Close"
          variant="close"
          onClick={safe((w) => w.close())}
          testid="tauri-titlebar-close"
        >
          {/* X */}
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <line x1="1" y1="1" x2="9" y2="9" stroke="currentColor" strokeWidth="1.2" />
            <line x1="9" y1="1" x2="1" y2="9" stroke="currentColor" strokeWidth="1.2" />
          </svg>
        </WindowButton>
      </div>
    </div>
  );
}

export default TitleBar;
