// alpha.71: open a web link in the user's own browser (Chrome / Edge / whatever is their default).
//
// Inside the desktop app the page is a "remote" page (http://127.0.0.1:<port>), so a plain
// window.open('https://...') is blocked and the Purchase button did nothing (alpha.70).
// Tauri's shell plugin hands the link to the operating system, which opens the default browser
// in a normal browser window.  In a normal web browser (or if the plugin is not there) we use window.open.
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

export async function openExternal(url) {
  if (!isWebLink(url)) return false;
  if (isTauri()) {
    try {
      const { open } = await import("@tauri-apps/plugin-shell");
      await open(String(url));
      return true;
    } catch {
      /* fall through to the browser way below */
    }
  }
  const w = window.open(String(url), "_blank", "noopener,noreferrer");
  return !!w;
}
