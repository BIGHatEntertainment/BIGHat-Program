/**
 * Native-OS file picker for .bighat files.
 *
 * When running inside the Tauri shell, uses `@tauri-apps/plugin-dialog`'s
 * `open()` with `defaultPath` set to the canonical Files folder
 * (`~/Documents/BIG Hat Entertainment/Files/Trivia` post-alpha.26),
 * then sends the absolute path to the local FastAPI sidecar at
 * `/api/bighat-files/import-from-path` (no need to round-trip the file
 * bytes over HTTP since the backend runs on localhost and can read
 * the file directly).
 *
 * When running in a plain browser (dev preview), falls back to the
 * standard hidden-input upload because browsers don't expose a way to
 * set an initial folder for security reasons.
 *
 * Returns:
 *   { path: <str> }    — Tauri path, ready for /import-from-path
 *   { file: <File> }   — browser File object, ready for /import
 *   null               — user cancelled
 *
 * v32.0.0-alpha.19, layout update v32.0.0-alpha.26 (Rounds → Trivia).
 */
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

function inTauri() {
  return typeof window !== 'undefined'
    && (window.__TAURI_INTERNALS__ != null || window.__TAURI__ != null);
}

let _cachedFilesRoot = null;
async function defaultFilesRoot(subfolder = 'Trivia') {
  if (!_cachedFilesRoot) {
    try {
      const r = await axios.get(`${API}/api/native/files/folder`);
      _cachedFilesRoot = r.data.folder;
    } catch {
      _cachedFilesRoot = null;
    }
  }
  if (!_cachedFilesRoot) return null;
  const sep = _cachedFilesRoot.includes('\\') ? '\\' : '/';
  // `subfolder` may be a plain top-level name (`Trivia`, `Bingo`) or
  // a Trivia round-type bucket (`Trivia/MC`). Normalise the separator
  // for the host OS so the native dialog opens at the right path.
  const normalised = subfolder.replace(/[\\/]/g, sep);
  return _cachedFilesRoot + sep + normalised;
}

/**
 * Open the native picker (Tauri) or hidden input (browser). See
 * module docstring for return shape.
 */
export async function pickBighatFile({ subfolder = 'Trivia' } = {}) {
  if (inTauri()) {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const defaultPath = await defaultFilesRoot(subfolder);
      const picked = await open({
        title: 'Open .bighat file',
        multiple: false,
        directory: false,
        defaultPath: defaultPath || undefined,
        filters: [{ name: 'BIG Hat file', extensions: ['bighat'] }],
      });
      if (!picked) return null;
      const path = Array.isArray(picked) ? picked[0] : picked;
      return { path };
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('[pickBighatFile] Tauri picker failed, falling back:', e);
    }
  }
  // Browser fallback — hidden file input.
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.bighat,application/x-bighat';
    input.onchange = () => {
      const f = input.files?.[0] || null;
      input.remove();
      resolve(f ? { file: f } : null);
    };
    document.body.appendChild(input);
    input.click();
  });
}

/**
 * High-level helper: open the picker, then POST the file to the
 * `/api/bighat-files/import` endpoint (or `import-from-path` when we
 * have a Tauri absolute path). Returns the backend's ImportResult, or
 * null on cancel.
 */
export async function pickAndImportBighat({ subfolder = 'Trivia' } = {}) {
  const picked = await pickBighatFile({ subfolder });
  if (!picked) return null;
  if (picked.path) {
    const form = new FormData();
    form.append('path', picked.path);
    const r = await axios.post(`${API}/api/bighat-files/import-from-path`, form);
    return r.data;
  }
  const form = new FormData();
  form.append('file', picked.file);
  const r = await axios.post(`${API}/api/bighat-files/import`, form);
  return r.data;
}
