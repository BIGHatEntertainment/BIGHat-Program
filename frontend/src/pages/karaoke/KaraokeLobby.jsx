import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, Mic, MapPin, User, Music2, HardDrive, RefreshCw, QrCode, Settings, Play, AlertCircle } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import api from "../../lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const accent = "#22c55e";
const accentDim = "rgba(34,197,94,0.15)";
const accentBorder = "rgba(34,197,94,0.25)";
const card = { backgroundColor: "#0a1940", border: `1px solid ${accentBorder}` };
const field = { backgroundColor: "#141b50", color: "#fff", border: `1px solid ${accentBorder}` };

const DRIVE_MESSAGES = {
  no_folder: "No filler music folder yet. Open Karaoke Setup and choose one.",
  drive_missing: "The filler music folder was not found. Plug in the external drive, then press Refresh.",
  folder_not_found: "The saved filler path is not a folder. Check Karaoke Setup.",
  folder_not_readable: "The filler folder could not be read. Plug the drive in again and press Refresh.",
};

/**
 * Karaoke lobby (alpha.70) - the launch screen. Karaoke Setup is a button here, like Bingo Setup.
 * Location, host, which filler folder to play (from the saved external drive), and the request QR.
 */
export default function KaraokeLobby() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [location, setLocation] = useState("");
  const [host, setHost] = useState(user?.name || "");
  const [venues, setVenues] = useState([]);
  const [typedLocation, setTypedLocation] = useState(false);
  const [filler, setFiller] = useState(null);       // { ok, error, folders, tracks, loose_tracks }
  const [fillerFolder, setFillerFolder] = useState("");  // "" = all folders
  const [refreshing, setRefreshing] = useState(false);
  const [logoState, setLogoState] = useState("unknown");      // alpha.95: "yes" | "no" | "unknown" (nothing chosen yet)
  const [keySet, setKeySet] = useState(true);
  const [launching, setLaunching] = useState(false);

  const loadFiller = useCallback(async () => {
    setRefreshing(true);
    try {
      const { data } = await axios.get(`${API}/karaoke/filler/folders`);
      setFiller(data);
      setFillerFolder((cur) => (data.ok && data.folders.some((f) => f.name === cur) ? cur : ""));
    } catch {
      setFiller({ ok: false, error: "folder_not_readable", folders: [], tracks: 0 });
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadFiller();
    axios.get(`${API}/karaoke/setup`).then((r) => setKeySet(!!r.data.youtube_key_set)).catch(() => {});
    api.listLocations('karaoke').then((r) => {
      const list = r.data || [];
      setVenues(list);
      if (list.length === 1) setLocation(list[0].name);
    }).catch(() => setTypedLocation(true));
  }, [loadFiller]);

  useEffect(() => {      // alpha.95: does the chosen venue have a logo for the TV overlay?
    const name = (location || "").trim();
    if (!name) { setLogoState("unknown"); return undefined; }
    let stop = false;
    axios.get(`${API}/karaoke/venue-logo-status/${encodeURIComponent(name)}`)
      .then((r) => { if (!stop) setLogoState(r.data && r.data.has_logo ? "yes" : "no"); })
      .catch(() => { if (!stop) setLogoState("unknown"); });
    return () => { stop = true; };
  }, [location]);

  useEffect(() => {
    if (user?.name && !host) setHost(user.name);
  }, [user, host]);

  const launch = async () => {
    if (!location.trim()) {
      toast.error("Please choose a location");
      return;
    }
    setLaunching(true);
    try {
      const res = await axios.post(`${API}/karaoke/session/create`, {
        location: location.trim(), host, host_email: user?.email || "",
        filler_folder: fillerFolder,
      });
      if (res.data.success) navigate("/karaoke/player");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not start Karaoke");
      setLaunching(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: "#000e2a" }} data-testid="karaoke-lobby">
      <header style={{ backgroundColor: "rgba(0,14,42,0.9)", borderBottom: `1px solid ${accentBorder}`, backdropFilter: "blur(20px)" }}>
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate("/")} className="p-2 rounded-lg" style={{ border: `1px solid ${accentBorder}`, color: "#fff" }} data-testid="karaoke-lobby-back-btn">
              <ArrowLeft size={16} />
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: accentDim }}>
                <Mic size={22} style={{ color: accent }} />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white tracking-wide">KARAOKE</h1>
                <p className="text-[10px] uppercase tracking-[0.2em]" style={{ color: accent }}>Session Setup</p>
              </div>
            </div>
          </div>
          <button onClick={() => navigate("/karaoke/setup")} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accentDim, border: `1px solid ${accentBorder}`, color: accent }} data-testid="karaoke-setup-btn">
            <Settings size={16} /> Karaoke Setup
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {!keySet && (
          <p className="mb-5 text-sm flex items-center gap-2 text-yellow-400" data-testid="karaoke-no-key-warning">
            <AlertCircle size={16} /> No YouTube key saved. Song search still works, but songs the video owner has blocked from playing here may show up. Add the key in Karaoke Setup to hide them.
          </p>
        )}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-5">
            <div className="rounded-xl p-5" style={card}>
              <label className="text-xs uppercase tracking-wider font-bold flex items-center gap-2 mb-3" style={{ color: accent }}><MapPin size={13} /> Location</label>
              {typedLocation || venues.length === 0 ? (
                <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Venue name" className="w-full px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-location-input" />
              ) : (
                <select value={location} onChange={(e) => setLocation(e.target.value)} className="w-full px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-location">
                  <option value="">Select a location...</option>
                  {venues.map((v) => <option key={v.id || v.name} value={v.name}>{v.name}</option>)}
                </select>
              )}
            </div>

            {logoState !== "unknown" && (
              <div className="rounded-xl p-4 flex items-start gap-3" data-testid="karaoke-logo-status"
                   style={{ backgroundColor: logoState === "yes" ? "rgba(34,197,94,0.08)" : "rgba(251,221,104,0.10)", border: `1.5px solid ${logoState === "yes" ? "rgba(34,197,94,0.35)" : "rgba(251,221,104,0.45)"}` }}>
                <AlertCircle size={16} style={{ color: logoState === "yes" ? accent : "#fbdd68", marginTop: 2 }} />
                <div className="flex-1 text-sm" style={{ color: logoState === "yes" ? accent : "#fbdd68" }}>
                  {logoState === "yes" ? "This venue's logo is loaded and will show on the TV overlay." : "This venue has no logo yet. The TV overlay will show an empty logo box. Please load one in Karaoke Setup before the show."}
                  {logoState === "no" && (
                    <button onClick={() => navigate("/karaoke/setup")} className="block mt-2 underline font-bold" data-testid="karaoke-logo-setup-btn">Load a logo in Karaoke Setup</button>
                  )}
                </div>
              </div>
            )}

            <div className="rounded-xl p-5" style={card}>
              <label className="text-xs uppercase tracking-wider font-bold flex items-center gap-2 mb-3" style={{ color: accent }}><User size={13} /> Host</label>
              <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Host name" className="w-full px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-host" />
            </div>

            <div className="rounded-xl p-5" style={card}>
              <label className="text-xs uppercase tracking-wider font-bold flex items-center gap-2 mb-3" style={{ color: accent }}><QrCode size={13} /> Song request QR</label>
              <p className="text-sm text-white" data-testid="karaoke-qr-note">The request QR is always shown on the TV.</p>
            </div>
          </div>

          <div className="space-y-5">
            <div className="rounded-xl p-5" style={card} data-testid="karaoke-filler-card">
              <div className="flex items-center justify-between mb-3">
                <label className="text-xs uppercase tracking-wider font-bold flex items-center gap-2" style={{ color: accent }}><HardDrive size={13} /> Filler music</label>
                <button onClick={loadFiller} disabled={refreshing} className="flex items-center gap-1 text-xs text-zinc-300" data-testid="karaoke-filler-refresh-btn">
                  <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} /> Refresh
                </button>
              </div>
              {filler && filler.ok ? (
                <>
                  <select value={fillerFolder} onChange={(e) => setFillerFolder(e.target.value)} className="w-full px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-filler">
                    <option value="">All folders ({filler.tracks} tracks)</option>
                    {filler.folders.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.tracks})</option>)}
                  </select>
                  <p className="text-xs text-zinc-500 mt-2 flex items-center gap-1"><Music2 size={12} /> {filler.tracks} tracks ready</p>
                </>
              ) : (
                <p className="text-sm text-yellow-400 flex items-start gap-2" data-testid="karaoke-filler-message">
                  <AlertCircle size={16} className="shrink-0 mt-0.5" /> {DRIVE_MESSAGES[filler?.error] || "Loading filler music..."}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="mt-8 flex items-center gap-4">
          <button onClick={launch} disabled={launching} className="flex items-center gap-2 px-8 py-4 rounded-xl text-base font-bold disabled:opacity-50" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-launch">
            <Play size={18} /> {launching ? "Starting..." : "Launch Karaoke"}
          </button>
          {filler && !filler.ok && <p className="text-sm text-zinc-500">You can still launch without filler music.</p>}
        </div>
      </main>
    </div>
  );
}
