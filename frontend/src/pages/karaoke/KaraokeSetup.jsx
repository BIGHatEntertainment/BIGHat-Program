import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, FolderOpen, RefreshCw, CheckCircle2, AlertCircle, Music2, Image as ImageIcon,
  Upload, Trash2, KeyRound, HardDrive, MapPin,
} from "lucide-react";
import api from "../../lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const inTauri = () => typeof window !== "undefined" && (window.__TAURI_INTERNALS__ != null || window.__TAURI__ != null);

const accent = "#22c55e";
const accentDim = "rgba(34,197,94,0.15)";
const accentBorder = "rgba(34,197,94,0.25)";
const card = { backgroundColor: "#0a1940", border: `1px solid ${accentBorder}` };
const field = { backgroundColor: "#141b50", color: "#fff", border: `1px solid ${accentBorder}` };

const FILLER_ERRORS = {
  no_folder: "No folder chosen yet.",
  drive_missing: "That folder was not found. If it is on an external drive, plug the drive in and press Check.",
  folder_not_found: "That path is not a folder.",
  folder_not_readable: "That folder could not be read.",
};
const IMAGE_PROBLEMS = {
  not_an_image: "That file is not a picture.",
  wrong_size: (r) => `The overlay must be exactly 1920 x 1080. This one is ${r.width} x ${r.height}.`,
  too_small: (r) => `Too small (${r.width} x ${r.height}). Use at least 145 x 145.`,
  not_square: (r) => `Logos should be square. This one is ${r.width} x ${r.height}.`,
};
const problemText = (r) => {
  const p = IMAGE_PROBLEMS[r.error];
  return typeof p === "function" ? p(r) : p || "Could not save that image.";
};

/**
 * Karaoke Setup (alpha.70) - lives inside the Karaoke player lobby, like Bingo Setup.
 *   1. Folders: made for you under Documents/BIG Hat Entertainment/Files/Karaoke
 *   2. Master overlay: the audience-screen template (1920 x 1080). The venue logo and QR are placed on it.
 *   3. Venue logos: one per location (145 x 145 minimum; 150 x 150 is what venues use).
 *   4. Filler music folder: can be on an external drive; the lobby shows its folders as a drop-down.
 *   5. YouTube key: for song search.
 */
export default function KaraokeSetup() {
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [filler, setFiller] = useState("");
  const [fillerInfo, setFillerInfo] = useState(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ytKey, setYtKey] = useState("");
  const [overlayNote, setOverlayNote] = useState(null);
  const [overlayBust, setOverlayBust] = useState(Date.now());
  const [locations, setLocations] = useState([]);
  const [typedVenue, setTypedVenue] = useState("");
  const [logoNotes, setLogoNotes] = useState({});
  const [logoBust, setLogoBust] = useState(Date.now());
  const overlayInput = useRef(null);
  const logoInputs = useRef({});

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/karaoke/setup`);
      setState(data);
      setFiller(data.filler_folder || "");
      setFillerInfo(data.filler);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    load();
    api.listLocations('karaoke').then((r) => setLocations(r.data || [])).catch(() => setLocations([]));
  }, [load]);

  // ---- filler music
  const checkFiller = async (path = filler) => {
    setChecking(true);
    try {
      const { data } = await axios.post(`${API}/karaoke/setup/filler-scan`, { filler_folder: path });
      setFillerInfo(data);
    } catch {
      setFillerInfo({ ok: false, error: "folder_not_readable", folders: [], tracks: 0 });
    } finally {
      setChecking(false);
    }
  };

  const browse = async () => {
    if (!inTauri()) {
      toast.info("Paste the folder path into the box, then press Check folder.");
      return;
    }
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const picked = await open({ title: "Choose your filler music folder", directory: true, multiple: false, defaultPath: filler || undefined });
      if (!picked) return;
      const path = Array.isArray(picked) ? picked[0] : picked;
      setFiller(path);
      await checkFiller(path);
    } catch {
      toast.error("Could not open the folder picker. Paste the path instead.");
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const body = { filler_folder: filler };
      if (ytKey.trim()) body.youtube_api_key = ytKey.trim();
      const { data } = await axios.post(`${API}/karaoke/setup`, body);
      setState(data);
      setFillerInfo(data.filler);
      setYtKey("");
      toast.success("Karaoke Setup saved");
    } catch {
      toast.error("Could not save Karaoke Setup");
    } finally {
      setSaving(false);
    }
  };

  // ---- master overlay
  const uploadOverlay = async (e) => {
    const file = (e.target.files || [])[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setOverlayNote(null);
    try {
      const { data } = await axios.post(`${API}/karaoke/overlay/master`, form);
      if (data.saved) {
        setOverlayNote({ ok: true, text: "New master overlay saved." });
        setOverlayBust(Date.now());
        load();
      } else {
        setOverlayNote({ ok: false, text: problemText(data) });
      }
    } catch (err) {
      setOverlayNote({ ok: false, text: "Could not upload that file (use .png, .jpg or .webp)." });
    }
  };

  const resetOverlay = async () => {
    try {
      await axios.delete(`${API}/karaoke/overlay/master`);
      setOverlayNote({ ok: true, text: "Back to the BIG Hat overlay." });
      setOverlayBust(Date.now());
      load();
    } catch {
      toast.error("Could not reset the overlay");
    }
  };

  // ---- venue logos
  const venueNames = locations.length ? locations.map((l) => l.name) : (typedVenue ? [typedVenue] : []);
  const uploadLogo = async (venue, e) => {
    const file = (e.target.files || [])[0];
    e.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await axios.post(`${API}/karaoke/venue-logo/${encodeURIComponent(venue)}`, form);
      setLogoNotes((n) => ({ ...n, [venue]: data.saved ? { ok: true, text: `Saved (${data.width} x ${data.height})` } : { ok: false, text: problemText(data) } }));
      if (data.saved) setLogoBust(Date.now());
    } catch {
      setLogoNotes((n) => ({ ...n, [venue]: { ok: false, text: "Could not upload that file." } }));
    }
  };
  const removeLogo = async (venue) => {
    try {
      await axios.delete(`${API}/karaoke/venue-logo/${encodeURIComponent(venue)}`);
      setLogoNotes((n) => ({ ...n, [venue]: { ok: true, text: "Removed" } }));
      setLogoBust(Date.now());
    } catch {
      /* no logo to remove */
    }
  };

  if (loadError) {
    return (
      <div className="min-h-screen p-8" style={{ backgroundColor: "#000e2a" }} data-testid="karaoke-setup-page">
        <p className="text-yellow-400 flex items-center gap-2" data-testid="karaoke-setup-error"><AlertCircle size={16} /> Could not reach the program. Close and reopen it, then try again.</p>
      </div>
    );
  }

  const hint = state?.youtube_key_hint;
  return (
    <div className="min-h-screen p-8" style={{ backgroundColor: "#000e2a" }} data-testid="karaoke-setup-page">
      <div className="max-w-4xl mx-auto">
        <button onClick={() => navigate("/karaoke")} className="flex items-center gap-2 px-3 py-2 rounded-lg mb-6 text-zinc-300 hover:text-white" style={{ border: `1px solid ${accentBorder}` }} data-testid="karaoke-setup-back-btn">
          <ArrowLeft size={18} /> Back to Karaoke
        </button>
        <h1 className="text-3xl font-bold text-white mb-1">Karaoke Setup</h1>
        <p className="text-zinc-400 mb-8">Global settings for every Karaoke night.</p>

        {/* 1. folders */}
        <section className="rounded-xl p-5 mb-6" style={card} data-testid="karaoke-folders-section">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><FolderOpen size={18} style={{ color: accent }} /> Karaoke folders</h2>
          <p className="text-zinc-500 text-sm mb-3">Made for you. Open them in File Explorer to add or swap files.</p>
          {state && (
            <ul className="text-sm space-y-1" data-testid="karaoke-folder-list">
              <li className="text-zinc-300 break-all">Main: <span className="text-zinc-500">{state.folders.root}</span></li>
              <li className="text-zinc-300 break-all">Master overlay: <span className="text-zinc-500">{state.folders.overlay}</span></li>
              <li className="text-zinc-300 break-all">Venue logos: <span className="text-zinc-500">{state.folders.logos}</span></li>
              <li className="text-zinc-300 break-all">Song library: <span className="text-zinc-500">{state.folders.songs}</span></li>
            </ul>
          )}
        </section>

        {/* 2. master overlay */}
        <section className="rounded-xl p-5 mb-6" style={card} data-testid="karaoke-overlay-section">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><ImageIcon size={18} style={{ color: accent }} /> Master overlay</h2>
          <p className="text-zinc-500 text-sm mb-3">
            The template the audience TV shows: video in the middle, a scrolling "up next" bar along the bottom, and the venue logo and
            request QR on the right. Each location's logo is placed on it. A new overlay must be exactly <span className="text-zinc-300">1920 x 1080</span> and keep
            the same window positions (green boxes in the BIG Hat one).
          </p>
          <img src={`${API}/karaoke/overlay/master?v=${overlayBust}`} alt="Master overlay" className="w-full max-w-xl rounded-lg mb-3" style={{ border: `1px solid ${accentBorder}` }} data-testid="karaoke-overlay-preview" />
          <div className="flex flex-wrap items-center gap-3">
            <input ref={overlayInput} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={uploadOverlay} data-testid="karaoke-overlay-input" />
            <button onClick={() => overlayInput.current && overlayInput.current.click()} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accent, color: "#000" }} data-testid="karaoke-overlay-upload-btn">
              <Upload size={16} /> Upload master overlay
            </button>
            {state?.overlay?.custom && (
              <button onClick={resetOverlay} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-zinc-300" style={{ border: `1px solid ${accentBorder}` }} data-testid="karaoke-overlay-reset-btn">
                <RefreshCw size={16} /> Use the BIG Hat overlay
              </button>
            )}
            <span className="text-xs text-zinc-500">{state?.overlay?.custom ? "Using your own overlay" : "Using the BIG Hat overlay"}</span>
          </div>
          {overlayNote && (
            <p className={`mt-3 text-sm flex items-center gap-2 ${overlayNote.ok ? "text-green-400" : "text-yellow-400"}`} data-testid="karaoke-overlay-note">
              {overlayNote.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />} {overlayNote.text}
            </p>
          )}
        </section>

        {/* 3. venue logos */}
        <section className="rounded-xl p-5 mb-6" style={card} data-testid="karaoke-logos-section">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><MapPin size={18} style={{ color: accent }} /> Venue logos</h2>
          <p className="text-zinc-500 text-sm mb-3">
            One square logo per location, at least <span className="text-zinc-300">145 x 145</span> (venues use 150 x 150). It shows in the logo window
            (about 249 x 249 on a 1080p TV) without being cropped.
          </p>
          {locations.length === 0 && (
            <div className="flex gap-2 mb-3">
              <input value={typedVenue} onChange={(e) => setTypedVenue(e.target.value)} placeholder="Venue name, exactly as in Trivia Setup..." className="flex-1 px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-venue-typed" />
            </div>
          )}
          <div className="space-y-3">
            {venueNames.map((v) => (
              <div key={v} className="flex items-center justify-between gap-4 rounded-lg p-3" style={{ backgroundColor: "rgba(255,255,255,0.03)", border: `1px solid ${accentBorder}` }} data-testid={`karaoke-logo-row-${v}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <img src={`${API}/karaoke/venue-logo/${encodeURIComponent(v)}?v=${logoBust}`} alt="" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} onLoad={(e) => { e.currentTarget.style.visibility = "visible"; }} className="w-14 h-14 rounded-lg object-contain bg-black" />
                  <div className="min-w-0">
                    <p className="text-white truncate">{v}</p>
                    {logoNotes[v] && <p className={`text-xs ${logoNotes[v].ok ? "text-green-400" : "text-yellow-400"}`} data-testid={`karaoke-logo-note-${v}`}>{logoNotes[v].text}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" ref={(el) => { logoInputs.current[v] = el; }} onChange={(e) => uploadLogo(v, e)} data-testid={`karaoke-logo-input-${v}`} />
                  <button onClick={() => logoInputs.current[v] && logoInputs.current[v].click()} className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold" style={{ backgroundColor: accentDim, border: `1px solid ${accentBorder}`, color: accent }} data-testid={`karaoke-logo-upload-${v}`}>
                    <Upload size={14} /> Upload logo
                  </button>
                  <button onClick={() => removeLogo(v)} className="text-zinc-500 hover:text-red-400" title="Remove logo" data-testid={`karaoke-logo-remove-${v}`}><Trash2 size={16} /></button>
                </div>
              </div>
            ))}
            {venueNames.length === 0 && <p className="text-zinc-500 text-sm" data-testid="karaoke-no-venues">Add a location in Trivia Setup, or type the venue name above.</p>}
          </div>
        </section>

        {/* 4. filler music */}
        <section className="rounded-xl p-5 mb-6" style={card} data-testid="karaoke-filler-section">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><HardDrive size={18} style={{ color: accent }} /> Filler music folder</h2>
          <p className="text-zinc-500 text-sm mb-3">
            The folder with your between-singer music, for example on an external drive. Inside it, make one folder per artist or playlist.
            The Karaoke lobby then lets you pick which folder to play.
          </p>
          <div className="flex gap-2 mb-3">
            <input value={filler} onChange={(e) => setFiller(e.target.value)} placeholder="Example: E:\Karaoke Filler" className="flex-1 px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-filler-input" />
            <button onClick={browse} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accent, color: "#000" }} data-testid="karaoke-filler-browse-btn">Browse</button>
            <button onClick={() => checkFiller()} disabled={checking} className="px-4 py-2 rounded-lg text-sm text-zinc-300" style={{ border: `1px solid ${accentBorder}` }} data-testid="karaoke-filler-check-btn">
              {checking ? "Checking..." : "Check folder"}
            </button>
          </div>
          {fillerInfo && !fillerInfo.ok && fillerInfo.error && (
            <p className="text-sm text-yellow-400 flex items-center gap-2" data-testid="karaoke-filler-error"><AlertCircle size={16} /> {FILLER_ERRORS[fillerInfo.error] || "Problem with that folder."}</p>
          )}
          {fillerInfo && fillerInfo.ok && (
            <div data-testid="karaoke-filler-ok">
              <p className="text-sm text-green-400 flex items-center gap-2 mb-2"><CheckCircle2 size={16} /> {fillerInfo.tracks} tracks found</p>
              <ul className="text-sm text-zinc-300 grid grid-cols-2 gap-x-4">
                {fillerInfo.folders.map((f) => (
                  <li key={f.name} className="flex items-center gap-2" data-testid={`karaoke-filler-folder-${f.name}`}><Music2 size={14} style={{ color: accent }} /> {f.name} <span className="text-zinc-500">({f.tracks})</span></li>
                ))}
              </ul>
              {fillerInfo.loose_tracks > 0 && <p className="text-xs text-zinc-500 mt-1">{fillerInfo.loose_tracks} loose tracks sit directly in the folder.</p>}
            </div>
          )}
        </section>

        {/* 5. YouTube key */}
        <section className="rounded-xl p-5 mb-6" style={card} data-testid="karaoke-key-section">
          <h2 className="text-lg font-semibold text-white mb-1 flex items-center gap-2"><KeyRound size={18} style={{ color: accent }} /> YouTube key</h2>
          <p className="text-zinc-500 text-sm mb-3">Used to search for karaoke videos. It is stored on this PC only.</p>
          <input value={ytKey} onChange={(e) => setYtKey(e.target.value)} type="password" autoComplete="off" placeholder={hint ? `Saved (${hint}). Paste a new key to replace it.` : "Paste your YouTube Data API key..."} className="w-full px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-key-input" />
          <p className="text-xs mt-2" style={{ color: state?.youtube_key_set ? accent : "#8892b0" }} data-testid="karaoke-key-status">{state?.youtube_key_set ? "A key is saved." : "No key saved yet."}</p>
        </section>

        <div className="flex items-center gap-4">
          <button onClick={saveSettings} disabled={saving} className="px-6 py-3 rounded-xl text-sm font-bold disabled:opacity-50" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-setup-save-btn">
            {saving ? "Saving..." : "Save Karaoke Setup"}
          </button>
          <p className="text-sm text-zinc-500">Overlay and logo uploads save on their own. This button saves the filler folder and the key.</p>
        </div>
      </div>
    </div>
  );
}
