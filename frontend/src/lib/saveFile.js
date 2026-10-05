// alpha.78: give the user a file they asked for (a PDF, a video, a .bighat, an image...).
//
// A normal browser downloads with <a download>.  The desktop app's window ignores that, so the button looked dead.
// In the desktop app we send the file to the app's own backend, which saves it into the PC's Downloads folder and
// shows it in File Explorer.  Everything else keeps the normal browser download.
//
//   await saveBlob(blob, "bingo-cards.pdf")           -> { ok, path }   (path only in the desktop app)
//   await saveUrl("https://.../x.mp4", "x.mp4")        -> same, downloads the URL first
import { isTauri } from "./openExternal";

const API = process.env.REACT_APP_BACKEND_URL || "";

function browserDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => window.URL.revokeObjectURL(url), 10000);
}

export async function saveBlob(blob, filename, { toast } = {}) {
  const name = filename || "download";
  if (!isTauri()) {
    browserDownload(blob, name);
    return { ok: true };
  }
  try {
    const form = new FormData();
    form.append("file", blob, name);
    form.append("filename", name);
    const res = await fetch(`${API}/api/native/system/save-download`, { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) throw new Error(data.detail || "The app could not save the file");
    if (toast) toast({ title: "Saved to Downloads", description: data.path });
    return { ok: true, path: data.path };
  } catch (e) {
    if (toast) toast({ title: "Download failed", description: String(e.message || e), variant: "destructive" });
    return { ok: false, error: String(e.message || e) };
  }
}

export async function saveUrl(url, filename, opts = {}) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  return saveBlob(await res.blob(), filename, opts);
}
