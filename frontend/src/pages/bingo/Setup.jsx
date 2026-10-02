import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, FolderOpen, RefreshCw, CheckCircle2, AlertCircle, Music2 } from "lucide-react";
import { Button } from "../../components/ui/button";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const inTauri = () => typeof window !== "undefined" && (window.__TAURI_INTERNALS__ != null || window.__TAURI__ != null);

const ERRORS = {
  no_folder: "No folder chosen yet.",
  folder_not_found: "That folder was not found. Check the path.",
  folder_not_readable: "That folder could not be read.",
};

/**
 * Bingo Setup (alpha.67)
 *   1. Global setting: the MAIN BINGO FOLDER. Every sub folder is a theme:
 *        <main folder>/<Theme>/songs.xlsx|csv   (number, song, artist)
 *        <main folder>/<Theme>/01_Song.mp4 ...  (videos, matched by number)
 *   2. Which themes Music Bingo may offer (on / off).
 * No SharePoint.
 */
export default function BingoSetup() {
  const navigate = useNavigate();
  const [folder, setFolder] = useState("");
  const [savedFolder, setSavedFolder] = useState("");
  const [themes, setThemes] = useState([]);      // [{id, name, ready, problems, videos, song_list, enabled}]
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const apply = (data) => {
    setThemes(data.themes || []);
    setError(data.ok ? null : data.error);
  };

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/bingo/setup`);
        setFolder(data.main_folder || "");
        setSavedFolder(data.main_folder || "");
        apply(data);
      } catch {
        setError("load_failed");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const check = useCallback(async (path) => {
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/bingo/setup/scan`, { main_folder: path, themes: {} });
      // keep toggles the user already set for themes that are still there
      setThemes((old) => (data.themes || []).map((t) => {
        const prev = old.find((o) => o.id === t.id);
        return prev ? { ...t, enabled: prev.enabled } : t;
      }));
      setError(data.ok ? null : data.error);
      setDirty(true);
    } catch {
      setError("load_failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const browse = async () => {
    if (!inTauri()) {
      toast.info("Paste the folder path into the box, then press Check folder.");
      return;
    }
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const picked = await open({ title: "Choose your main Bingo folder", directory: true, multiple: false, defaultPath: folder || undefined });
      if (!picked) return;
      const path = Array.isArray(picked) ? picked[0] : picked;
      setFolder(path);
      await check(path);
    } catch (e) {
      toast.error("Could not open the folder picker. Paste the path instead.");
    }
  };

  const toggle = (id) => {
    setThemes((ts) => ts.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t)));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const map = {};
      themes.forEach((t) => { map[t.id] = { enabled: t.enabled }; });
      const { data } = await axios.post(`${API}/bingo/setup`, { main_folder: folder.trim(), themes: map });
      setSavedFolder(data.main_folder);
      apply(data);
      setDirty(false);
      toast.success("Bingo Setup saved");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(ERRORS[d] || "Could not save Bingo Setup");
      if (d) setError(d);
    } finally {
      setSaving(false);
    }
  };

  const ready = themes.filter((t) => t.ready);
  const on = ready.filter((t) => t.enabled);

  return (
    <div className="bingo-theme min-h-screen bg-gradient-radial p-8" data-theme="blue" data-testid="bingo-setup-page">
      <div className="max-w-3xl mx-auto">
        <button onClick={() => navigate("/bingo")} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/80 text-zinc-300 hover:text-white mb-6" data-testid="setup-back-btn">
          <ArrowLeft size={18} /> Back to Bingo
        </button>

        <h1 className="font-display text-5xl neon-text text-fuchsia-400 mb-2">Bingo Setup</h1>
        <p className="text-zinc-400 mb-8">Choose the main Bingo folder. Every folder inside it is a theme for Music Bingo.</p>

        <section className="rounded-2xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-6 mb-8">
          <h2 className="text-xl font-semibold text-zinc-100 mb-1">Main Bingo folder</h2>
          <p className="text-zinc-500 text-sm mb-4">
            Each theme folder holds its song list (.xlsx or .csv: number, song, artist) and its videos
            (named like <span className="font-mono">01_Song.mp4</span>).
          </p>
          <div className="flex gap-3">
            <input
              value={folder}
              onChange={(e) => { setFolder(e.target.value); setDirty(true); }}
              onKeyDown={(e) => e.key === "Enter" && check(folder)}
              placeholder="C:\Users\You\Documents\BIG Hat\Bingo"
              className="flex-1 px-4 py-3 rounded-lg bg-zinc-900 border border-zinc-700 text-white font-mono text-sm"
              data-testid="setup-folder-input"
            />
            <Button className="btn-primary" onClick={browse} data-testid="setup-browse-btn">
              <FolderOpen size={18} className="mr-2" /> Browse
            </Button>
            <Button variant="outline" onClick={() => check(folder)} data-testid="setup-check-btn">
              <RefreshCw size={18} className="mr-2" /> Check folder
            </Button>
          </div>
          {error && ERRORS[error] && (
            <p className="mt-3 text-sm text-yellow-400 flex items-center gap-2" data-testid="setup-error"><AlertCircle size={16} /> {ERRORS[error]}</p>
          )}
          {error === "load_failed" && (
            <p className="mt-3 text-sm text-red-400 flex items-center gap-2" data-testid="setup-error"><AlertCircle size={16} /> Could not reach the app. Try again.</p>
          )}
        </section>

        <section className="mb-8">
          <h2 className="text-xl font-semibold text-zinc-100 mb-1">Music Bingo themes</h2>
          <p className="text-zinc-500 text-sm mb-4">Switch a theme off to hide it from the Music Bingo screen.</p>
          {loading ? (
            <p className="text-zinc-500">Looking in your folder...</p>
          ) : themes.length === 0 ? (
            <p className="text-zinc-500" data-testid="setup-no-themes">
              {error ? "Fix the folder above to see your themes." : "No theme folders found inside this folder."}
            </p>
          ) : (
            <div className="space-y-3">
              {themes.map((t) => (
                <div key={t.id} data-testid={`theme-row-${t.id}`}
                  className={`flex items-center justify-between gap-4 rounded-xl border p-4 ${t.ready ? "border-fuchsia-500/30 bg-zinc-900/60" : "border-zinc-700 bg-zinc-900/40 opacity-80"}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <Music2 className={t.ready ? "text-fuchsia-400" : "text-zinc-600"} size={24} />
                    <div className="min-w-0">
                      <p className="font-semibold text-white truncate">{t.name}</p>
                      {t.ready ? (
                        <p className="text-sm text-green-400 flex items-center gap-1"><CheckCircle2 size={14} /> {t.videos} videos · {t.song_list}</p>
                      ) : (
                        <p className="text-sm text-yellow-400 flex items-center gap-1"><AlertCircle size={14} /> Not ready: {t.problems.join(", ")}</p>
                      )}
                    </div>
                  </div>
                  <button
                    type="button" role="switch" aria-checked={t.enabled} disabled={!t.ready}
                    onClick={() => toggle(t.id)} data-testid={`theme-toggle-${t.id}`}
                    className={`w-14 h-7 rounded-full relative transition-colors ${t.ready && t.enabled ? "bg-fuchsia-500" : "bg-zinc-600"} ${!t.ready ? "cursor-not-allowed opacity-50" : ""}`}>
                    <span className={`absolute top-0.5 left-0.5 w-6 h-6 rounded-full bg-white transition-transform ${t.ready && t.enabled ? "translate-x-7" : "translate-x-0"}`} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="flex items-center gap-4">
          <Button className="btn-success" onClick={save} disabled={saving || !dirty} data-testid="setup-save-btn">
            {saving ? "Saving..." : "Save Bingo Setup"}
          </Button>
          <p className="text-sm text-zinc-500" data-testid="setup-summary">
            {savedFolder ? `${on.length} of ${themes.length} theme${themes.length === 1 ? "" : "s"} available for Music Bingo` : "Not saved yet"}
          </p>
        </div>
      </div>
    </div>
  );
}
