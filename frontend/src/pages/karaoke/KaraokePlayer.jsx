import { usePointerDrag } from "./pointerDrag";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { isTauri, openNativeAudience } from "../../lib/audienceWindow";
import KaraokeRightPanel from "./KaraokeRightPanel";
import { QRCodeSVG } from "qrcode.react";
import {
  Mic, Music, Play, Pause, SkipForward, Shuffle, Repeat, Volume2, QrCode, Layers, Monitor, Home,
  Plus, Trash2, GripVertical, Check, X, ListMusic, UserPlus, Settings, AlertCircle, RefreshCw,
} from "lucide-react";
import {
  AMP_FACTOR, FADE_SECONDS, FILLER_FADE_STEPS, fillerVolume as calcFillerVolume, splitVolume, nextSingerState,
  readAudience, songProgress, clock, groupByArtist, shuffle, nextTrackIndex, fadeVolume, explainVideoError } from "./karaokeFlow";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const accent = "#22c55e";
const accentDim = "rgba(34,197,94,0.15)";
const accentBorder = "rgba(34,197,94,0.25)";
const panel = { backgroundColor: "#0a1940", border: `1px solid ${accentBorder}` };
const field = { backgroundColor: "#141b50", color: "#fff", border: `1px solid ${accentBorder}` };


// alpha.89: what travels with a drag. The desktop window (WebView2) only reliably delivers the STANDARD
// "text/plain" type, so the payload is written there (and under the old key); a small prefix tells a song from a singer.
const DRAG_SONG = "bighat-song:";
const DRAG_SINGER = "bighat-singer:";
export const dragPayload = (kind, value) => (kind === "song" ? DRAG_SONG : DRAG_SINGER) + (typeof value === "string" ? value : JSON.stringify(value));
export const readDrag = (dt) => {
  let raw = "";
  try { raw = dt.getData("text/plain") || ""; } catch { /* some engines throw */ }
  if (raw.startsWith(DRAG_SONG)) { try { return { kind: "song", song: JSON.parse(raw.slice(DRAG_SONG.length)) }; } catch { return null; } }
  if (raw.startsWith(DRAG_SINGER)) { const i = parseInt(raw.slice(DRAG_SINGER.length), 10); return Number.isNaN(i) ? null : { kind: "singer", index: i }; }
  return null;      // anything else (a file, a link, text from another page) is not ours
};

/**
 * Karaoke host Player (alpha.70). Two tabs, like the prototype:
 *   Filler  - between-singer music from your folder (auto-play, shuffle, next, volume to 150%)
 *   Karaoke - singer queue, song search, QR requests, Next Singer
 * The AUDIENCE screen is the clock. This screen follows what the audience reports (started / time / ended)
 * and never counts seconds by itself.
 */
export default function KaraokePlayer() {
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [mode, setMode] = useState("filler");       // what the TV is showing (filler or a song)
  const [tab, setTab] = useState("filler");         // alpha.96: which tab the HOST is looking at. A song ending never moves it.

  // ---- filler
  const [tracks, setTracks] = useState([]);
  const [fillerNote, setFillerNote] = useState("");
  const [folderName, setFolderName] = useState("");
  const [folders, setFolders] = useState([]);
  const [trackIdx, setTrackIdx] = useState(-1);
  const [isFillerPlaying, setIsFillerPlaying] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [isShuffled, setIsShuffled] = useState(false);
  const [masterVolume, setMasterVolume] = useState(0.8);
  const [fillerVol, setFillerVol] = useState(0.5);

  // ---- karaoke
  const [queue, setQueue] = useState([]);
  const [newSinger, setNewSinger] = useState("");
  const [songSearch, setSongSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [pendingRequests, setPendingRequests] = useState([]);
  const [contextMenu, setContextMenu] = useState(null);
  // alpha.92: drag a song onto a singer (or a singer up/down the list) with the pointer itself
  const { drag, startDrag } = usePointerDrag((payload, overId) => {
    if (payload.kind === "song") { assignSong(overId, payload.song); return; }
    const to = queue.filter((e) => e.status === "waiting" || !e.status).findIndex((e) => String(e.id) === String(overId));
    if (to >= 0) reorder(payload.index, to);
  });
  const [currentSinger, setCurrentSinger] = useState(null);
  const [songPlaying, setSongPlaying] = useState(false);
  const [songEnding, setSongEnding] = useState(false);
  const [audience, setAudience] = useState({ started: false, time: 0, duration: 0, ending: false, ended: false });

  // ---- shared
  const [requestUrl, setRequestUrl] = useState("");
  const [qrOnline, setQrOnline] = useState(true);
  const [audienceOpen, setAudienceOpen] = useState(false);   // alpha.89: is the TV screen open? (the buffer needs it)

  const audioRef = useRef(null);
  const audioCtxRef = useRef(null);
  const gainRef = useRef(null);
  const channelRef = useRef(null);
  const audienceWinRef = useRef(null);
  const revRef = useRef(0);
  const fadeTimerRef = useRef(null);
  const endingHandledRef = useRef(null);      // singer id whose ending we already handled
  const stateRef = useRef({});

  stateRef.current = { currentSinger, songPlaying, songEnding, mode, autoPlay, trackIdx, tracks, masterVolume, fillerVol, isFillerPlaying };

  // ======================================================================== session + data
  useEffect(() => {
    axios.get(`${API}/karaoke/session/active`).then((r) => {
      if (!r.data.session) { navigate("/karaoke"); return; }
      setSession(r.data.session);
      setFolderName(r.data.session.filler_folder || "");
      setLoadingSession(false);
    }).catch(() => navigate("/karaoke"));
    // alpha.82: the QR must be a link a PHONE can open (cloud relay). Keep asking until it is ready, and notice if it drops.
    const askQr = () => axios.get(`${API}/karaoke/request-info`).then((r) => {
      setRequestUrl(r.data.phone_reachable ? (r.data.url || "") : "");
      setQrOnline(r.data.online !== false);
    }).catch(() => {});
    askQr();
    const qrTimer = setInterval(askQr, 10000);
    channelRef.current = new BroadcastChannel("karaoke-state");
    return () => { clearInterval(qrTimer); channelRef.current && channelRef.current.close(); };
  }, [navigate]);

  const loadFiller = useCallback(async (folder) => {
    try {
      const [f, t] = await Promise.all([
        axios.get(`${API}/karaoke/filler/folders`),
        axios.get(`${API}/karaoke/filler/tracks`, { params: { folder } }),
      ]);
      setFolders(f.data.folders || []);
      setTracks(t.data.tracks || []);
      setFillerNote(t.data.tracks && t.data.tracks.length ? "" : "That folder has no music in it.");
    } catch {
      setTracks([]);
      setFillerNote("Filler music is not available. Plug in the external drive and press Reload.");
    }
  }, []);
  useEffect(() => { if (session) loadFiller(folderName); }, [session, folderName, loadFiller]);

  const loadQueue = useCallback(async () => {
    try { setQueue((await axios.get(`${API}/karaoke/queue`)).data.queue || []); } catch { /* keep what we have */ }
  }, []);
  const loadRequests = useCallback(async () => {
    try { setPendingRequests((await axios.get(`${API}/karaoke/requests/pending`)).data.requests || []); } catch { /* keep */ }
  }, []);
  useEffect(() => {
    if (!session) return undefined;
    loadQueue(); loadRequests();
    const t = setInterval(() => { loadQueue(); loadRequests(); }, 4000);
    return () => clearInterval(t);
  }, [session, loadQueue, loadRequests]);

  // ======================================================================== telling the audience
  const sendState = useCallback(async (patch = {}) => {
    const s = stateRef.current;
    const pb = {
      song_playing: patch.song_playing ?? s.songPlaying,
      song_ending: patch.song_ending ?? s.songEnding,
      current_singer: patch.current_singer === undefined ? s.currentSinger : patch.current_singer,
      mode: patch.mode ?? s.mode,
    };
    let rev = revRef.current + 1;
    try {
      // the server numbers every change; the channel copy carries the SAME number so the audience can ignore stale copies
      const r = await axios.post(`${API}/karaoke/session/playback`, pb);
      if (r.data && typeof r.data.rev === "number") rev = r.data.rev;
    } catch { /* the channel copy below still reaches the screen */ }
    revRef.current = rev;
    if (channelRef.current) channelRef.current.postMessage({ type: "karaoke-state", pb: { ...pb, rev } });
  }, []);

  // ======================================================================== filler player
  const connectGain = useCallback((audio) => {
    try {
      if (!audioCtxRef.current) audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      const ctx = audioCtxRef.current;
      const source = ctx.createMediaElementSource(audio);
      const gain = ctx.createGain();
      source.connect(gain); gain.connect(ctx.destination);
      gainRef.current = gain;
    } catch { gainRef.current = null; }
  }, []);

  const applyVolume = useCallback((v) => {
    const audio = audioRef.current;
    if (!audio) return;
    const { element, gain } = splitVolume(v);
    audio.volume = Math.max(0, Math.min(1, element));
    if (gainRef.current) gainRef.current.gain.value = gain;
  }, []);
  const targetVolume = useCallback(() => calcFillerVolume(stateRef.current.masterVolume, stateRef.current.fillerVol), []);
  useEffect(() => { applyVolume(targetVolume()); }, [masterVolume, fillerVol, applyVolume, targetVolume]);

  const stopFade = () => { if (fadeTimerRef.current) { clearInterval(fadeTimerRef.current); fadeTimerRef.current = null; } };
  const fadeFiller = useCallback((from, to, seconds, done) => {
    stopFade();
    let step = 0;
    const steps = FILLER_FADE_STEPS;
    fadeTimerRef.current = setInterval(() => {
      step += 1;
      applyVolume(fadeVolume(from, to, step, steps));
      if (step >= steps) { stopFade(); if (done) done(); }
    }, (seconds * 1000) / steps);
  }, [applyVolume]);

  const playTrack = useCallback((idx) => {
    const t = stateRef.current.tracks[idx];
    const audio = audioRef.current;
    if (!t || !audio) return;
    setTrackIdx(idx);
    audio.src = `${API}/karaoke/filler/play/${t.id.split("/").map(encodeURIComponent).join("/")}`;
    if (!gainRef.current) connectGain(audio);
    applyVolume(targetVolume());
    audio.play().then(() => setIsFillerPlaying(true)).catch(() => setIsFillerPlaying(false));
  }, [applyVolume, connectGain, targetVolume]);

  const playNext = useCallback(() => {
    const s = stateRef.current;
    const n = nextTrackIndex(s.trackIdx, s.tracks.length);
    if (n >= 0) playTrack(n);
  }, [playTrack]);

  const toggleFiller = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isFillerPlaying) { audio.pause(); setIsFillerPlaying(false); }
    else if (trackIdx >= 0 && audio.src) { audio.play().then(() => setIsFillerPlaying(true)).catch(() => {}); }
    else if (tracks.length) playTrack(0);
  };
  const toggleShuffle = () => {
    setIsShuffled((v) => !v);
    setTracks((cur) => (isShuffled ? [...cur].sort((a, b) => a.id.toLowerCase().localeCompare(b.id.toLowerCase())) : shuffle(cur)));
    setTrackIdx(-1);
  };
  const onFillerEnded = () => {
    setIsFillerPlaying(false);
    if (stateRef.current.autoPlay && stateRef.current.mode === "filler") playNext();
  };

  // ======================================================================== songs
  const searchCatalog = useCallback(async (text) => {
    setSearchError("");
    if (!text || text.trim().length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await axios.get(`${API}/karaoke/youtube/search`, { params: { q: text.trim() } });
      setResults(r.data.results || []);
      if (r.data.quota_warning) setSearchError("YouTube search is out of quota for today. Songs you searched before still work.");
    } catch (err) {
      setResults([]);
      setSearchError(err.response?.data?.detail || "Search failed. Check the internet connection.");
    } finally { setSearching(false); }
  }, []);
  const searchTimer = useRef(null);
  const onSearchChange = (v) => {
    setSongSearch(v);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => searchCatalog(v), 450);
  };

  const addSinger = async () => {
    const name = newSinger.trim();
    if (!name) return;
    await axios.post(`${API}/karaoke/queue/add`, { singer_name: name });
    setNewSinger(""); loadQueue();
  };
  const assignSong = async (entryId, song) => {
    await axios.post(`${API}/karaoke/queue/add`, {
      assign_to: entryId, song_title: song.title, song_artist: song.artist, embed_url: song.embed_url,
      source: song.source, duration_seconds: song.duration_seconds,
    });
    setContextMenu(null); loadQueue();
  };
  const addSingerWithSong = async (song) => {
    const name = window.prompt("Singer name?");
    if (!name || !name.trim()) return;
    await axios.post(`${API}/karaoke/queue/add`, {
      singer_name: name.trim(), song_title: song.title, song_artist: song.artist, embed_url: song.embed_url,
      source: song.source, duration_seconds: song.duration_seconds,
    });
    setContextMenu(null); loadQueue();
  };
  const removeFromQueue = async (id) => { await axios.delete(`${API}/karaoke/queue/${id}`); loadQueue(); };
  const reorder = async (from, to) => {
    if (from === to || from == null) return;
    const ids = queue.map((e) => e.id);
    const [moved] = ids.splice(from, 1);
    ids.splice(to, 0, moved);
    await axios.post(`${API}/karaoke/queue/reorder`, { order: ids });
    loadQueue();
  };
  const acceptRequest = async (id) => { await axios.post(`${API}/karaoke/requests/${id}/accept`); loadRequests(); loadQueue(); };
  const rejectRequest = async (id) => { await axios.post(`${API}/karaoke/requests/${id}/reject`); loadRequests(); };

  const waiting = queue.filter((e) => e.status === "waiting");
  const next = nextSingerState(queue);

  // preload (alpha.89): the audience screen is the only thing that can load video. We tell it which song is next
  // and it reports how much is REALLY buffered (percent of the first 45 seconds). The host sees that as a bar on
  // the queued singer, and is told once when the song has loaded enough.
  const nextId = next.singer && next.singer.id;
  const nextUrl = next.singer && next.singer.embed_url;
  // alpha.98: the host only tells the audience screen which song is next; the audience warms it in a plain hidden iframe.
  useEffect(() => {
    if (!session) return;
    axios.post(`${API}/karaoke/session/preload`, nextId && nextUrl ? { singer_id: nextId, embed_url: nextUrl } : {}).catch(() => {});
  }, [session, nextId, nextUrl]);

  // ---- start the next singer
  const startNextSinger = async (force = false) => {
    if (!force && !nextSingerState(queue).enabled) return;
    try {
      const r = await axios.post(`${API}/karaoke/queue/next`);
      const cur = r.data.current;
      if (!cur) { toast.info("No one is waiting"); return; }
      endingHandledRef.current = null;
      setCurrentSinger(cur);
      setMode("karaoke"); setTab("karaoke");
      setSongEnding(false);
      setAudience({ started: false, time: 0, duration: 0, ending: false, ended: false });
      // filler music fades out while the song comes in
      if (audioRef.current && isFillerPlaying) {
        fadeFiller(targetVolume(), 0, FADE_SECONDS, () => { audioRef.current.pause(); setIsFillerPlaying(false); });
      }
      setSongPlaying(true);
      await sendState({ song_playing: true, song_ending: false, current_singer: cur, mode: "karaoke" });
      loadQueue();
    } catch { toast.error("Could not start the next singer"); }
  };

  const pauseResumeSong = async () => {
    const playing = !songPlaying;
    setSongPlaying(playing);
    await sendState({ song_playing: playing });
  };

  // the song is over (the audience said so, or the host pressed End Song)
  const finishSong = useCallback(async () => {
    const s = stateRef.current;
    if (!s.currentSinger) return;
    const wasId = s.currentSinger.id;
    setSongPlaying(false); setSongEnding(false); setCurrentSinger(null);
    setAudience({ started: false, time: 0, duration: 0, ending: false, ended: false });
    try { await axios.post(`${API}/karaoke/queue/finish-current`); } catch { /* queue refresh below shows the truth */ }
    await sendState({ song_playing: false, song_ending: false, current_singer: null, mode: "filler" });
    loadQueue();
    // filler comes back
    setMode("filler");
    if (audioRef.current && audioRef.current.src) {
      applyVolume(0);
      audioRef.current.play().then(() => { setIsFillerPlaying(true); fadeFiller(0, targetVolume(), FADE_SECONDS); }).catch(() => {});
    } else if (stateRef.current.autoPlay && stateRef.current.tracks.length) {
      playTrack(0);
    }
    return wasId;
  }, [sendState, loadQueue, applyVolume, fadeFiller, targetVolume, playTrack]);

  // host pressed End Song: fade the picture 3 s, then finish
  const endSongNow = async () => {
    if (!currentSinger) return;
    setSongEnding(true);
    await sendState({ song_ending: true });
    setTimeout(() => finishSong(), FADE_SECONDS * 1000);
  };

  // ---- follow the AUDIENCE clock (never our own timer)
  useEffect(() => {
    if (!session || !currentSinger) return undefined;
    const t = setInterval(async () => {
      try {
        const r = await axios.get(`${API}/karaoke/session/playback`);
        const a = readAudience(r.data.playback);
        setAudience(a);
        if (a.ended && endingHandledRef.current !== currentSinger.id) {
          endingHandledRef.current = currentSinger.id;
          finishSong();
        } else if (a.ending && !stateRef.current.songEnding) {
          setSongEnding(true);
          sendState({ song_ending: true });
        }
      } catch { /* try again */ }
    }, 1000);
    return () => clearInterval(t);
  }, [session, currentSinger, finishSong, sendState]);

  // ======================================================================== header actions
  const switchMode = async (m) => { setMode(m); setTab(m); await axios.post(`${API}/karaoke/session/mode`, { mode: m }).catch(() => {}); };
  // alpha.89: same as the Bingo player. In the desktop app the audience screen is a REAL window
  // ("karaoke-audience"); a pop-up never opens there, which is why the button used to do nothing.
  const openAudience = async () => {
    if (audienceWinRef.current && !audienceWinRef.current.closed) { audienceWinRef.current.focus(); return; }
    if (isTauri()) {
      try {
        const { win } = await openNativeAudience({
          label: "karaoke-audience",
          path: "/karaoke/audience",
          title: "BIG Hat - Karaoke Audience",
          onClosed: () => { audienceWinRef.current = null; setAudienceOpen(false); },
        });
        audienceWinRef.current = {
          closed: false,
          focus: () => { try { win.setFocus(); } catch (_e) { /* best-effort */ } },
          close: () => { try { win.close(); } catch (_e) { /* already gone */ } },
        };
        setAudienceOpen(true);
      } catch (err) {
        console.error("[karaoke audience] native window failed:", err);
        toast.error(`The audience screen could not open: ${err && err.message ? err.message : err}`);
      }
      return;
    }
    const w = window.open(`${window.location.origin}/karaoke/audience`, "karaoke-audience", "width=1280,height=720");
    if (!w) { toast.error("The audience screen was blocked. Allow pop-ups for this page and try again."); return; }
    audienceWinRef.current = w;
    setAudienceOpen(true);
  };
  const endNight = async () => {
    if (!window.confirm("End Karaoke for tonight?")) return;
    if (audioRef.current) audioRef.current.pause();
    await axios.post(`${API}/karaoke/session/end`).catch(() => {});
    channelRef.current && channelRef.current.postMessage({ ended: true });
    navigate("/karaoke");
  };

  if (loadingSession) {
    return <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#000e2a", color: "#8892b0" }} data-testid="karaoke-player-loading">Loading Karaoke...</div>;
  }

  const prog = songProgress(audience.time, audience.duration || (currentSinger && currentSinger.duration_seconds) || 0);
  const groups = groupByArtist(tracks);
  const currentTrack = tracks[trackIdx];

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#000e2a" }} data-testid="karaoke-player" onClick={() => contextMenu && setContextMenu(null)}>
      <audio ref={audioRef} onEnded={onFillerEnded} onPause={() => setIsFillerPlaying(false)} data-testid="karaoke-filler-audio" />

      {/* ============ header ============ */}
      <header style={{ backgroundColor: "rgba(0,14,42,0.9)", borderBottom: `1px solid ${accentBorder}` }}>
        <div className="px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <button onClick={endNight} className="p-2 rounded-lg" style={{ border: `1px solid ${accentBorder}`, color: "#fff" }} title="End the night" data-testid="karaoke-end-night-btn"><Home size={16} /></button>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{ backgroundColor: accentDim }}>
              <Mic size={16} style={{ color: accent }} /><span className="text-sm font-black tracking-wide" style={{ color: accent }}>KARAOKE</span>
            </div>
            <span className="text-sm text-white" data-testid="karaoke-location-label">{session.location}</span>
          </div>

          <div className="flex rounded-lg overflow-hidden" style={{ border: `1px solid ${accentBorder}` }}>
            {[["filler", "Filler", Music], ["karaoke", "Karaoke", Mic]].map(([m, label, Icon]) => (
              <button key={m} onClick={() => switchMode(m)} className="flex items-center gap-2 px-4 py-2 text-sm font-bold"
                style={{ backgroundColor: tab === m ? accent : "transparent", color: tab === m ? "#000e2a" : "#8892b0" }} data-testid={`karaoke-tab-${m}`}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2" title="Master volume (up to 150%)">
              <Volume2 size={16} style={{ color: accent }} />
              <input type="range" min="0" max="1" step="0.01" value={masterVolume} onChange={(e) => setMasterVolume(parseFloat(e.target.value))} className="w-28" style={{ accentColor: accent }} data-testid="karaoke-master-volume" />
              <span className="text-[10px] font-bold w-10" style={{ color: masterVolume > 0.67 ? "#fbdd68" : accent }}>{Math.round(masterVolume * AMP_FACTOR * 100)}%</span>
            </div>
            <button onClick={openAudience} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-audience-btn"><Monitor size={14} /> Audience View</button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex gap-4 p-4 overflow-hidden" data-testid="karaoke-body">
      <main className="flex-1 min-w-0 overflow-hidden">
        {/* ============ FILLER TAB ============ */}
        {tab === "filler" && (
          <div className="max-w-3xl mx-auto" data-testid="karaoke-filler-tab">
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <button onClick={toggleFiller} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-filler-play-btn">
                {isFillerPlaying ? <Pause size={16} /> : <Play size={16} />} {isFillerPlaying ? "Pause" : "Play"}
              </button>
              <button onClick={playNext} disabled={!tracks.length} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-white disabled:opacity-40" style={{ border: `1px solid ${accentBorder}` }} data-testid="karaoke-filler-next-btn"><SkipForward size={16} /> Next Song</button>
              <button onClick={() => setAutoPlay((v) => !v)} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ backgroundColor: autoPlay ? accentDim : "transparent", border: `1px solid ${accentBorder}`, color: autoPlay ? accent : "#8892b0" }} data-testid="karaoke-filler-autoplay-btn"><Repeat size={14} /> Auto-Play {autoPlay ? "On" : "Off"}</button>
              <button onClick={toggleShuffle} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ backgroundColor: isShuffled ? accentDim : "transparent", border: `1px solid ${accentBorder}`, color: isShuffled ? accent : "#8892b0" }} data-testid="karaoke-filler-shuffle-btn"><Shuffle size={14} /> Shuffle</button>
              <select value={folderName} onChange={(e) => setFolderName(e.target.value)} className="px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-filler-folder">
                <option value="">All folders</option>
                {folders.map((f) => <option key={f.name} value={f.name}>{f.name} ({f.tracks})</option>)}
              </select>
              <button onClick={() => loadFiller(folderName)} className="p-2 rounded-lg text-zinc-300" style={{ border: `1px solid ${accentBorder}` }} title="Reload the music folder" data-testid="karaoke-filler-reload-btn"><RefreshCw size={14} /></button>
            </div>

            <div className="rounded-xl p-4 mb-4" style={panel} data-testid="karaoke-filler-now">
              <p className="text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: accent }}>Now Playing</p>
              <p className="text-lg text-white truncate">{currentTrack ? currentTrack.name.replace(/\.[^.]+$/, "") : "Nothing playing"}</p>
              <p className="text-xs" style={{ color: "#8892b0" }}>{currentTrack ? currentTrack.artist : `${tracks.length} tracks ready`}</p>
              <div className="flex items-center gap-2 mt-3">
                <Volume2 size={14} style={{ color: accent }} />
                <input type="range" min="0" max="1" step="0.01" value={fillerVol} onChange={(e) => setFillerVol(parseFloat(e.target.value))} className="flex-1" style={{ accentColor: accent }} data-testid="karaoke-filler-volume" />
                <span className="text-[10px] w-10 text-right" style={{ color: accent }}>{Math.round(fillerVol * 100)}%</span>
              </div>
            </div>

            {fillerNote && <p className="text-sm mb-3 flex items-center gap-2" style={{ color: "#fbdd68" }} data-testid="karaoke-filler-note"><AlertCircle size={16} /> {fillerNote}</p>}

            <div className="rounded-xl overflow-y-auto" style={{ ...panel, maxHeight: "calc(100vh - 380px)" }} data-testid="karaoke-filler-list">
              {isShuffled ? (
                tracks.map((t, i) => (
                  <button key={t.id} onClick={() => playTrack(i)} className="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-white/5" data-testid={`karaoke-track-${i}`}>
                    <span className="text-xs w-6" style={{ color: "#8892b0" }}>{i + 1}</span>
                    <span className="flex-1 text-sm truncate" style={{ color: i === trackIdx ? accent : "#fff" }}>{t.name.replace(/\.[^.]+$/, "")}</span>
                    <span className="text-[10px]" style={{ color: "#8892b0" }}>{t.artist}</span>
                  </button>
                ))
              ) : (
                groups.map((g) => (
                  <div key={g.artist}>
                    <p className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider font-bold" style={{ color: accent }}>{g.artist}</p>
                    {g.tracks.map((t) => {
                      const i = tracks.indexOf(t);
                      return (
                        <button key={t.id} onClick={() => playTrack(i)} className="w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-white/5" data-testid={`karaoke-track-${i}`}>
                          <Music size={12} style={{ color: i === trackIdx ? accent : "#555" }} />
                          <span className="flex-1 text-sm truncate" style={{ color: i === trackIdx ? accent : "#fff" }}>{t.name.replace(/\.[^.]+$/, "")}</span>
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
              {!tracks.length && !fillerNote && <p className="text-sm text-center py-8" style={{ color: "#8892b0" }}>No filler music loaded</p>}
            </div>
          </div>
        )}

        {/* ============ KARAOKE TAB ============ */}
        {tab === "karaoke" && (
          <div className="flex gap-4 h-full" data-testid="karaoke-karaoke-tab">
            {/* left: now singing + queue */}
            <div className="w-[340px] xl:w-[420px] shrink-0 flex flex-col gap-3">
              {currentSinger ? (
                <div className="rounded-xl p-4" style={{ ...panel, borderColor: accent }} data-testid="karaoke-now-singing">
                  <p className="text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: accent }}>Now Singing</p>
                  <p className="text-xl font-bold text-white" data-testid="karaoke-current-name">{currentSinger.singer_name}</p>
                  <p className="text-sm" style={{ color: accent }}>{currentSinger.song_title}</p>
                  <div className="mt-3">
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: "rgba(255,255,255,0.1)" }}>
                      <div className="h-full" style={{ width: `${prog.percent}%`, backgroundColor: songEnding ? "#fbdd68" : accent, transition: "width 1s linear" }} data-testid="karaoke-progress" />
                    </div>
                    <div className="flex justify-between text-[10px] mt-1" style={{ color: "#8892b0" }}>
                      <span data-testid="karaoke-elapsed">{clock(prog.elapsed)}</span>
                      <span>{audience.started ? "on the TV" : "starting on the TV..."}</span>
                      <span>{prog.remaining == null ? "" : clock(prog.remaining)}</span>
                    </div>
                  </div>
                  {audience.error && (
                    <div className="mt-3 rounded-lg p-3" style={{ backgroundColor: "rgba(251,221,104,0.10)", border: "1.5px solid rgba(251,221,104,0.45)" }} data-testid="karaoke-song-error">
                      <p className="text-sm font-bold" style={{ color: "#fbdd68" }}>This song could not play on the TV.</p>
                      <p className="text-xs mt-1" style={{ color: "#fbdd68" }} data-testid="karaoke-song-error-why">{explainVideoError(audience.error)}</p>
                      <p className="text-xs mt-1" style={{ color: "#8892b0" }}>{currentSinger.singer_name} goes back in the line with no song. Drag a different song onto them.</p>
                      <button onClick={() => finishSong()} className="mt-2 w-full py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: "#fbdd68", color: "#000e2a" }} data-testid="karaoke-song-error-pick-another">Pick another song</button>
                    </div>
                  )}
                  <div className="flex gap-2 mt-3">
                    <button onClick={pauseResumeSong} className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: accentDim, border: `1px solid ${accentBorder}`, color: accent }} data-testid="karaoke-pause-song-btn">{songPlaying ? <Pause size={14} /> : <Play size={14} />} {songPlaying ? "Pause" : "Play"}</button>
                    <button onClick={endSongNow} className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)", color: "#ef4444" }} data-testid="karaoke-end-song-btn"><X size={14} /> End Song</button>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl p-4 text-center" style={panel} data-testid="karaoke-no-singer"><p className="text-sm" style={{ color: "#8892b0" }}>No one singing</p></div>
              )}

              <div className="rounded-xl p-3" style={panel}>
                <div className="flex gap-2">
                  <input value={newSinger} onChange={(e) => setNewSinger(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addSinger()} placeholder="Add a singer..." className="flex-1 px-3 py-2 rounded-lg text-sm" style={field} data-testid="karaoke-add-singer-input" />
                  <button onClick={addSinger} className="px-3 py-2 rounded-lg" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-add-singer-btn"><UserPlus size={16} /></button>
                </div>
                <button onClick={() => startNextSinger(false)} disabled={!next.enabled} className="w-full mt-3 flex items-center justify-center gap-2 py-3 rounded-lg text-sm font-bold disabled:opacity-40" style={{ backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-next-singer-btn">
                  <SkipForward size={16} />
                  {next.reason === "ready" && `Next Singer: ${next.singer.singer_name}`}
                  {next.reason === "no_song" && `Pick a song for ${next.singer.singer_name}`}
                  {next.reason === "no_one_waiting" && "No one waiting"}
                </button>
                {/* alpha.98: no loading bar / Start anyway / Retry: the next song is a plain iframe (like the prototype) and Next Singer is ready as soon as they have a song */}
              </div>

              <div className="overflow-y-auto space-y-1 rounded-xl p-2 flex-1" style={{ maxHeight: "calc(100vh - 460px)", backgroundColor: "rgba(0,14,42,0.3)", border: `1.5px solid ${accentBorder}` }} data-testid="karaoke-queue" data-drop-list>
                {waiting.map((entry, i) => (
                  <div key={entry.id} data-testid={`karaoke-queue-${entry.id}`} data-drop-singer={entry.id} data-drop-index={i}
                    onPointerDown={(e) => startDrag(e, { kind: "singer", index: i }, entry.singer_name)}
                    onContextMenu={(e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, entry }); }}
                    className="flex items-center justify-between px-3 py-2 rounded-lg cursor-grab select-none"
                    style={{ touchAction: "none", backgroundColor: drag && String(drag.overId) === String(entry.id) ? "rgba(34,197,94,0.28)" : "rgba(255,255,255,0.03)", border: `1px solid ${drag && String(drag.overId) === String(entry.id) ? accent : "rgba(255,255,255,0.06)"}` }}>
                    <div className="flex items-center gap-2 min-w-0">
                      <GripVertical size={14} style={{ color: "#555" }} />
                      <span className="text-xs font-bold w-5 text-center" style={{ color: accent }}>{i + 1}</span>
                      <div className="min-w-0"><p className="text-sm font-medium text-white truncate">{entry.singer_name}</p>{entry.song_title && <p className="text-[10px] truncate" style={{ color: "#8892b0" }}>{entry.song_title}</p>}</div>
                    </div>
                    <button onClick={() => removeFromQueue(entry.id)} className="p-1 rounded hover:bg-red-500/10" data-testid={`karaoke-remove-${entry.id}`}><Trash2 size={12} style={{ color: "#ef4444" }} /></button>
                  </div>
                ))}
                {waiting.length === 0 && <p className="text-xs text-center py-6" style={{ color: "#8892b0" }}>Add singers above</p>}
              </div>
            </div>

            {/* right: song catalog */}
            <div className="flex-1 flex flex-col overflow-hidden">
              <h3 className="text-sm font-bold uppercase tracking-wider mb-2 flex items-center gap-2" style={{ color: accent }}><ListMusic size={14} /> Song Catalog <span className="text-[10px] font-normal normal-case tracking-normal" style={{ color: "#8892b0" }}>drag a song onto a singer</span></h3>
              <input value={songSearch} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search karaoke songs..." className="px-4 py-2 rounded-lg text-sm mb-3" style={field} data-testid="karaoke-song-search" />
              <div className="overflow-y-auto rounded-xl flex-1" style={{ backgroundColor: "rgba(0,14,42,0.5)", border: `1.5px solid ${accentBorder}` }} data-testid="karaoke-results">
                {searching && <p className="text-sm text-center py-6" style={{ color: "#8892b0" }}>Searching...</p>}
                {!searching && results.length > 0 && results.map((song) => (
                  <div key={song.id} onPointerDown={(e) => startDrag(e, { kind: "song", song }, song.title)}
                    onContextMenu={(e) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, song }); }}
                    className="flex items-center gap-3 px-4 py-2 hover:bg-white/5 cursor-grab select-none" style={{ touchAction: "none" }} data-testid={`karaoke-result-${song.id}`}>
                    {song.thumbnail && <img src={song.thumbnail} alt="" className="w-16 h-10 rounded object-cover shrink-0" />}
                    <div className="flex-1 min-w-0"><p className="text-sm text-white truncate">{song.title}</p><p className="text-[10px]" style={{ color: "#8892b0" }}>{song.artist}{song.duration_seconds ? ` \u2022 ${clock(song.duration_seconds)}` : ""}</p></div>
                    <GripVertical size={14} style={{ color: "#555" }} />
                  </div>
                ))}
                {!searching && !results.length && songSearch && (
                  <div className="text-center py-8"><p className="text-sm" style={{ color: "#8892b0" }}>No results for "{songSearch}"</p>{searchError && <p className="text-xs mt-2 px-4" style={{ color: "#fbdd68" }} data-testid="karaoke-search-error">{searchError}</p>}</div>
                )}
                {!songSearch && <p className="text-sm text-center py-8" style={{ color: "#8892b0" }}>Search all karaoke catalogs</p>}
              </div>
            </div>
          </div>
        )}
      </main>

      <KaraokeRightPanel
        mode={mode} currentSinger={currentSinger} songPlaying={songPlaying} isFillerPlaying={isFillerPlaying}
        currentTrackName={currentTrack ? String(currentTrack.name || currentTrack.id || "").replace(/\.[a-z0-9]+$/i, "") : ""}
        audienceOpen={audienceOpen} onOpenAudience={openAudience}
        requestUrl={requestUrl}
        pendingRequests={pendingRequests} onAccept={acceptRequest} onReject={rejectRequest}
        queueCount={waiting.length}
      />
      </div>


      {/* right-click menu */}
      {drag && (
        <div className="fixed z-[60] pointer-events-none px-3 py-1.5 rounded-lg text-xs font-bold shadow-xl"
          style={{ left: drag.x + 14, top: drag.y + 10, maxWidth: 260, backgroundColor: accent, color: "#000e2a" }} data-testid="karaoke-drag-chip">
          <span className="block truncate">{drag.overId != null ? "Drop to give: " : ""}{drag.label}</span>
        </div>
      )}
      {contextMenu && (
        <div className="fixed z-50 rounded-lg py-1 shadow-xl" style={{ left: contextMenu.x, top: contextMenu.y, backgroundColor: "#0a1940", border: `1px solid ${accentBorder}`, minWidth: 220 }} data-testid="karaoke-context-menu">
          {contextMenu.song && (
            <>
              <p className="px-3 py-1 text-[10px] uppercase tracking-wider font-bold" style={{ color: accent }}>Give this song to...</p>
              {waiting.map((e) => <button key={e.id} onClick={() => assignSong(e.id, contextMenu.song)} className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/5" data-testid={`karaoke-assign-${e.id}`}>{e.singer_name}</button>)}
              <button onClick={() => addSingerWithSong(contextMenu.song)} className="w-full text-left px-3 py-2 text-sm hover:bg-white/5" style={{ color: accent }} data-testid="karaoke-assign-new"><Plus size={12} className="inline mr-1" /> New singer...</button>
            </>
          )}
          {contextMenu.entry && (
            <>
              <p className="px-3 py-1 text-[10px] uppercase tracking-wider font-bold" style={{ color: accent }}>{contextMenu.entry.singer_name}</p>
              <button onClick={() => { removeFromQueue(contextMenu.entry.id); setContextMenu(null); }} className="w-full text-left px-3 py-2 text-sm hover:bg-white/5" style={{ color: "#ef4444" }}>Remove from queue</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
