/**
 * Shared native audience-window opener (Trivia / Bingo / Karaoke).
 *
 * Inside the desktop app pop-ups are NOT used at all: a real Tauri window is
 * created at the SAME ORIGIN as the host window (http://127.0.0.1:<port>) so
 * BroadcastChannel mirroring works. Browser/preview builds fall back to
 * window.open (sync, user-gesture safe).
 *
 * Returns { win, native } or throws Error(message) when native creation fails
 * in the desktop app (never silently falls back to a blocked pop-up).
 */
export const isTauri = () =>
  typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window);

export async function openNativeAudience({ label, path, title, onClosed }) {
  const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow');
  const existing = await WebviewWindow.getByLabel(label);
  if (existing) {
    try { await existing.setFocus(); } catch (_e) { /* best-effort */ }
    return { win: existing, native: true, reused: true };
  }
  const url = `${window.location.origin}${path}`; // absolute: same origin as host
  const w = new WebviewWindow(label, {
    url, title, width: 1280, height: 720, resizable: true, focus: true,
  });
  await new Promise((resolve, reject) => {
    w.once('tauri://created', resolve);
    w.once('tauri://error', (e) => reject(new Error(String(e?.payload || e || 'window create failed'))));
  });
  w.once('tauri://destroyed', () => { try { onClosed && onClosed(); } catch (_e) { /* noop */ } });
  try {
    const { availableMonitors, PhysicalPosition } = await import('@tauri-apps/api/window');
    const monitors = await availableMonitors();
    if (monitors.length > 1) {
      await w.setPosition(new PhysicalPosition(monitors[1].position.x, monitors[1].position.y));
    }
    await w.setFullscreen(true);
  } catch (e) {
    console.warn('[audience] monitor placement skipped:', e);
  }
  return { win: w, native: true, reused: false };
}
