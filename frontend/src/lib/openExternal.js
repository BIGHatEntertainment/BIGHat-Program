// alpha.78: open a web link in the user's own browser (Chrome / Edge / whatever is their default).
//
// Inside the desktop app the page is a "remote" page (http://127.0.0.1:<port>), so window.open() is blocked and
// the Tauri shell plugin did not work for the customer (alpha.70 and alpha.71 both failed).  So the page asks the
// app's own backend, which runs on the PC, to open the link.  Order of attempts:
//   1) the backend  (POST /api/native/system/open-url)       <- reliable in the desktop app
//   2) the Tauri shell plugin
//   3) window.open  (normal web browser)
// If nothing worked we show the link in a message so the click is never silent.
const API = process.env.REACT_APP_BACKEND_URL || "";

export const isTauri = () =>
  typeof window !== "undefined" && (window.__TAURI_INTERNALS__ != null || window.__TAURI__ != null);

// Only ever open real web links.  Anything else (file:, javascript:, a bare path) is refused.
export const isWebLink = (url) => {
  try {
    const u = new URL(String(url));
    return u.protocol === "https:" || u.protocol === "http:";
  } catch {
    return false;
  }
};

async function viaBackend(url) {
  try {
    const res = await fetch(`${API}/api/native/system/open-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: String(url) }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return !!data.ok;
  } catch {
    return false;
  }
}

export async function openExternal(url, onFail) {
  if (!isWebLink(url)) return false;
  if (isTauri()) {
    if (await viaBackend(url)) return true;
    try {
      const { open } = await import("@tauri-apps/plugin-shell");
      await open(String(url));
      return true;
    } catch {
      /* fall through */
    }
  }
  const w = window.open(String(url), "_blank", "noopener,noreferrer");
  if (w) return true;
  // Nothing opened.  Do not fail silently: tell the user where to go.
  const message = `Could not open your browser. Please go to: ${url}`;
  if (typeof onFail === "function") onFail(message);
  else if (typeof window !== "undefined") window.alert(message);
  return false;
}

// alpha.78: the address of a "Buy" page, from the app's own backend (editable without a new release).
// key: 'karaoke' | 'standalone' | 'story' | 'bingo' | 'default'
export async function openStore(key = "default", onFail) {
  let url = "https://bighat.live/";
  try {
    const res = await fetch(`${API}/api/native/system/store-links`);
    if (res.ok) {
      const links = await res.json();
      url = links[key] || links.default || url;
    }
  } catch {
    /* offline or older backend: use the default above */
  }
  return openExternal(url, onFail);
}
