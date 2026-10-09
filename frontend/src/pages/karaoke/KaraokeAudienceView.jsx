import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Music, Maximize } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import axios from "axios";
import { explainVideoError } from "./karaokeFlow";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const accent = "#22c55e";

// Where each piece sits on the 1920x1080 master overlay (percent of the screen). Same as the prototype.
const OVERLAY = {
  video:  { left: "7.14%",  top: "10%",    width: "71.82%", height: "75.93%" },
  chyron: { left: "5.12%",  top: "87.74%", width: "75.79%", height: "10.54%" },
  logo:   { left: "82.66%", top: "10%",    width: "12.97%", height: "23.06%" },
  qr:     { left: "82.66%", top: "62.87%", width: "12.97%", height: "23.06%" },
};

export const videoIdOf = (embedUrl) => {
  const m = (embedUrl || "").match(/embed\/([^?]+)/);
  return m ? m[1] : null;
};

/**
 * Karaoke audience screen (alpha.70). THIS SCREEN IS THE CLOCK.
 *  - It plays the song itself and reports started / time / ended to the server. alpha.108: FIRST through a tiny relay page (/karaoke/embed) that holds the
 *    YouTube player with a proper origin; if YouTube refuses the song (101/150/153) or it never starts, it falls back to the yt-dlp download in a plain <video>.
 *    The host follows these reports. The host never guesses where the song is.
 *  - A routine refresh never seeks or pauses the video. Only the host's play / pause / end commands do.
 *  - The video fades out over 3 s when a song is ending, then the screen goes back to the music view.
 *  - Layout: the master overlay image with the video, scrolling "up next" bar, venue logo and request QR placed in its windows.
 */
const RETRY_AFTER_MS = 4000;     // alpha.93: a failed preload is tried again after this long
const RELAY_START_TIMEOUT_MS = 12000;   // alpha.108: if the YouTube relay has not started the song by then, use the download

export default function KaraokeAudienceView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [ended, setEnded] = useState(false);
  const [location, setLocation] = useState("");
  const [logoOk, setLogoOk] = useState(true);
  const [chyronText, setChyronText] = useState("");
  const [singer, setSinger] = useState(null);       // { id, name, song, artist, videoId }
  const [wantPlaying, setWantPlaying] = useState(false);
  const [isFading, setIsFading] = useState(false);
  const [ytProblem, setYtProblem] = useState(false);
  const [loadingSong, setLoadingSong] = useState(false);
  const [via, setVia] = useState("");               // alpha.108: "youtube" (relay) or "file" (yt-dlp download), for the host's information
  const [ytReason, setYtReason] = useState("");          // alpha.96: YouTube's error code, shown as words
  const [requestUrl, setRequestUrl] = useState(`${window.location.origin}/karaoke/request`);

  const rootRef = useRef(null);
  const playerRef = useRef(null);
  const playerHostRef = useRef(null);
  const songRef = useRef({ id: null, videoId: null, startedReported: false, endedReported: false });
  const wantPlayingRef = useRef(false);
  const timerRef = useRef(null);
  const channelRef = useRef(null);
  const preloadRef = useRef({ singerId: null, videoId: null });   // the next singer's video, loading silently in the background
  const relayTimerRef = useRef(null);
  const relayCleanupRef = useRef(null);
  const revRef = useRef(-1);        // newest host revision applied; anything older is a stale copy and is ignored

  const enterFullscreen = useCallback(() => {
    const el = rootRef.current || document.documentElement;
    const rfs = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (rfs) rfs.call(el).catch(() => {});
  }, []);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!(document.fullscreenElement || document.webkitFullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange", onFs);
    return () => { document.removeEventListener("fullscreenchange", onFs); document.removeEventListener("webkitfullscreenchange", onFs); };
  }, []);

  // ---- tell the server what this screen is really doing (the host follows this)
  const report = useCallback((body) => {
    const id = songRef.current.id;
    if (!id) return;
    axios.post(`${API}/karaoke/session/audience-report`, { singer_id: id, ...body }).catch(() => {});
  }, []);

  const stopTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };

  const destroyPlayer = useCallback(() => {
    stopTimer();
    if (relayTimerRef.current) { clearTimeout(relayTimerRef.current); relayTimerRef.current = null; }
    if (relayCleanupRef.current) { relayCleanupRef.current(); relayCleanupRef.current = null; }
    try { const v = playerRef.current; if (v && v.pause) { v.pause(); v.removeAttribute('src'); v.load(); } if (playerHostRef.current) playerHostRef.current.innerHTML = ''; } catch { /* already gone */ }
    playerRef.current = null;
  }, []);

  // alpha.105/107: the FALLBACK. The song is a plain <video> whose file is downloaded by the backend (yt-dlp), so YouTube's
  // embed rules never apply. Used when the YouTube relay is refused (101/150/153) or never starts.
  const startFile = useCallback((videoId, singerId) => {
    destroyPlayer();
    songRef.current = { id: singerId, videoId, startedReported: false, endedReported: false, mode: "file" };
    setVia("file");
    setYtProblem(false); setYtReason(""); setLoadingSong(true);
    const host = playerHostRef.current;
    if (!host) return;
    host.innerHTML = "";
    const v = document.createElement("video");
    v.style.cssText = "width:100%;height:100%;object-fit:contain;background:#000";
    v.playsInline = true;
    v.autoplay = false;
    v.preload = "auto";
    v.setAttribute("data-testid", "karaoke-audience-video-el");
    const mine = () => songRef.current.videoId === videoId && songRef.current.id === singerId && songRef.current.mode === "file";
    v.addEventListener("loadedmetadata", () => { if (mine()) report({ duration: v.duration || 0 }); });
    v.addEventListener("playing", () => {
      if (!mine()) return;
      setLoadingSong(false);
      const song = songRef.current;
      if (!song.startedReported) { song.startedReported = true; report({ started: true, duration: v.duration || 0, error: "" }); }   // error "" clears an earlier "YouTube gave up" note
      if (!timerRef.current) timerRef.current = setInterval(() => { if (mine()) report({ time: v.currentTime || 0 }); }, 1000);
    });
    v.addEventListener("pause", () => { if (!v.ended) stopTimer(); });
    v.addEventListener("ended", () => {
      stopTimer();
      const song = songRef.current;
      if (mine() && !song.endedReported) { song.endedReported = true; report({ ended: true }); }
    });
    v.addEventListener("error", async () => {
      if (!mine()) return;
      // alpha.107: ask the backend WHY the download failed (sign-in, 403, ffmpeg, no internet...) and show that
      let why = "stream";
      try { const r = await axios.get(`${API}/karaoke/stream/status/${videoId}`); if (r.data && r.data.error) why = `stream_${r.data.error}`; } catch { /* keep the generic reason */ }
      if (!mine()) return;
      setLoadingSong(false); setYtProblem(true); setYtReason(why);
      report({ error: why });
    });
    v.addEventListener("canplay", () => {
      if (!mine()) return;
      if (wantPlayingRef.current) v.play().catch(() => {});
    });
    host.appendChild(v);
    playerRef.current = v;
    v.src = `${API}/karaoke/stream/${videoId}`;     // the backend downloads the song with yt-dlp, then serves it with Range support
    v.load();
  }, [destroyPlayer, report]);

  // alpha.108: the FIRST choice. YouTube's own player, but inside a tiny relay page served by our backend (/karaoke/embed),
  // so YouTube sees a proper origin and Referer (the fix for error 153 in Tauri/webview apps). The relay tells us what the
  // player does with postMessage. If YouTube refuses the song, or it does not start in time, we switch to the download.
  const startSong = useCallback((videoId, singerId) => {
    destroyPlayer();
    songRef.current = { id: singerId, videoId, startedReported: false, endedReported: false, mode: "youtube" };
    setVia("youtube");
    setYtProblem(false); setYtReason(""); setLoadingSong(true);
    const host = playerHostRef.current;
    if (!host) return;
    host.innerHTML = "";
    const mine = () => songRef.current.videoId === videoId && songRef.current.id === singerId && songRef.current.mode === "youtube";
    const fallBack = (why) => { if (!mine()) return; console.warn("[karaoke audience] YouTube relay gave up (" + why + "), using the downloaded file"); report({ error: "fallback_" + why }); startFile(videoId, singerId); };
    const f = document.createElement("iframe");
    f.src = `${API}/karaoke/embed?v=${encodeURIComponent(videoId)}&autoplay=${wantPlayingRef.current ? 1 : 0}`;
    f.allow = "autoplay; encrypted-media; fullscreen";
    f.referrerPolicy = "strict-origin-when-cross-origin";
    f.style.cssText = "width:100%;height:100%;border:0;background:#000";
    f.setAttribute("data-testid", "karaoke-audience-youtube-relay");
    const onMsg = (ev) => {
      const m = ev.data;
      if (!m || !m.__karaoke || m.vid !== videoId || ev.source !== f.contentWindow || !mine()) return;
      const song = songRef.current;
      if (m.type === "started") {
        if (relayTimerRef.current) { clearTimeout(relayTimerRef.current); relayTimerRef.current = null; }
        setLoadingSong(false);
        if (!song.startedReported) { song.startedReported = true; report({ started: true, duration: m.duration || 0, error: "" }); }
      } else if (m.type === "time") {
        report({ time: m.time || 0, duration: m.duration || 0 });
      } else if (m.type === "ended") {
        if (!song.endedReported) { song.endedReported = true; report({ ended: true }); }
      } else if (m.type === "error") {
        fallBack(m.code || "error");
      }
    };
    window.addEventListener("message", onMsg);
    relayCleanupRef.current = () => window.removeEventListener("message", onMsg);
    host.appendChild(f);
    playerRef.current = f;
    // a song that never starts (YouTube can hang silently) must not leave the TV waiting forever
    relayTimerRef.current = setTimeout(() => { if (mine() && !songRef.current.startedReported) fallBack("timeout"); }, RELAY_START_TIMEOUT_MS);
  }, [destroyPlayer, report, startFile]);

  // alpha.108: send a command (play / pause) to the YouTube relay page
  const sendRelay = (cmd) => { try { const w = playerRef.current && playerRef.current.contentWindow; if (w) w.postMessage({ __karaoke_cmd: 1, cmd }, "*"); } catch { /* relay gone */ } };

  // ---- apply what the host says. A new song starts the video. The SAME song is never restarted or seeked.
  const apply = useCallback((pb) => {
    if (!pb) return;
    // The host sends every change twice: instantly over the channel, and to the server. The slow server copy
    // can arrive AFTER a newer channel message. Each carries a revision number; never go backwards.
    if (typeof pb.rev === "number") {
      if (pb.rev < revRef.current) return;
      revRef.current = pb.rev;
    }
    const s = pb.current_singer;
    const videoId = videoIdOf(s && s.embed_url);
    const playing = !!pb.song_playing;
    wantPlayingRef.current = playing;
    setWantPlaying(playing);
    setIsFading(!!pb.song_ending);
    if (s) setSinger({ id: s.id, name: s.singer_name, song: s.song_title, artist: s.song_artist, videoId });
    else if (!playing) setSinger(null);

    const song = songRef.current;
    if (playing && s && videoId) {
      if (song.id !== s.id || song.videoId !== videoId) startSong(videoId, s.id);
      else if (playerRef.current) {
        // deliberate host command on the SAME song: play it if it was paused (no seeking)
        if (song.mode === "youtube") sendRelay("play");
        else if (playerRef.current.paused && !playerRef.current.ended) playerRef.current.play().catch(() => {});
      }
    } else if (!playing && playerRef.current && song.id === (s && s.id)) {
      // host paused the song
      if (song.mode === "youtube") sendRelay("pause");
      else { try { playerRef.current.pause(); } catch { /* ignore */ } }
    }
    if (!s || (!playing && !s)) {
      destroyPlayer();
      songRef.current = { id: null, videoId: null, startedReported: false, endedReported: false };
    }
  }, [startSong, destroyPlayer]);

  // ---- preload: ask the backend to download the NEXT singer's song now, so it starts instantly.
  const handlePreload = useCallback((pre) => {
    const cur = preloadRef.current;
    if (!pre || !pre.singer_id) { preloadRef.current = { singerId: null, videoId: null }; return; }
    const videoId = videoIdOf(pre.embed_url);
    if (!videoId) return;
    if (cur.singerId === pre.singer_id && cur.videoId === videoId && (!pre.retry || pre.retry === cur.retry)) {
      if (cur.ready || (cur.failedAt && Date.now() - cur.failedAt < RETRY_AFTER_MS)) return;
      if (cur.asking) return;
    }
    const tries = cur.singerId === pre.singer_id ? (cur.tries || 0) + 1 : 1;
    const mine = { singerId: pre.singer_id, videoId, tries, asking: true, retry: pre.retry || null };
    preloadRef.current = mine;
    const say = (body) => axios.post(`${API}/karaoke/session/preload-report`, { singer_id: pre.singer_id, ...body }).catch(() => {});
    (async () => {
      try {
        await axios.post(`${API}/karaoke/stream/prepare/${videoId}`);
        for (let i = 0; i < 90 && preloadRef.current === mine; i++) {
          const r = await axios.get(`${API}/karaoke/stream/status/${videoId}`);
          if (r.data && r.data.ready) { mine.ready = true; mine.asking = false; say({ percent: 100, ready: true }); return; }
          if (r.data && r.data.error) { mine.reason = `stream_${r.data.error}`; throw new Error(r.data.error); }
          await new Promise((res) => setTimeout(res, 1500));
        }
        mine.asking = false;
      } catch { mine.asking = false; mine.failedAt = Date.now(); say({ error: mine.reason || "stream" }); }
    })();
  }, []);

  // ---- instant messages from the host window
  useEffect(() => {
    const ch = new BroadcastChannel("karaoke-state");
    channelRef.current = ch;
    ch.onmessage = (ev) => {
      const m = ev.data || {};
      if (m.ended) { setEnded(true); return; }
      if (m.type === "karaoke-state" && m.pb) apply(m.pb);
    };
    return () => ch.close();
  }, [apply]);

  // ---- slow refresh from the server (survives a refreshed window). Never seeks or pauses by itself.
  useEffect(() => {
    let active = true;
    const poll = async () => {
      while (active) {
        try {
          const [pbRes, qRes] = await Promise.all([
            axios.get(`${API}/karaoke/session/playback`).catch(() => ({ data: {} })),
            axios.get(`${API}/karaoke/queue`).catch(() => ({ data: { queue: [] } })),
          ]);
          if (pbRes.data.playback === null) { setEnded(true); break; }
          if (pbRes.data.playback) {
            apply(pbRes.data.playback);
            if (pbRes.data.location) setLocation((cur) => (cur === pbRes.data.location ? cur : pbRes.data.location));
            handlePreload(pbRes.data.preload);
          }
          const q = (qRes.data.queue || []).filter((e) => e.status === "waiting").slice(0, 3);
          setChyronText(q.length ? "UP NEXT:  " + q.map((e) => `${e.singer_name}${e.song_title ? " \u2014 " + e.song_title : ""}`).join("   \u2022   ") : "");
        } catch { /* try again next round */ }
        await new Promise((r) => setTimeout(r, 2500));
      }
    };
    poll();
    return () => { active = false; };
  }, [apply, handlePreload]);

  // what address should the phone QR point to?
  // alpha.82: only a link a PHONE can open (cloud relay) is shown; keep asking until it is ready.
  useEffect(() => {
    const ask = () => axios.get(`${API}/karaoke/request-info`).then((r) => {
      setRequestUrl(r.data && r.data.phone_reachable && r.data.url ? r.data.url : "");
    }).catch(() => {});
    ask();
    const t = setInterval(ask, 10000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => () => { destroyPlayer(); if (channelRef.current) channelRef.current.close(); }, [destroyPlayer]);

  if (ended) {
    return (
      <div ref={rootRef} className="fixed inset-0 bg-black flex items-center justify-center" data-testid="karaoke-audience-ended">
        <div className="text-center">
          <Mic size={48} style={{ color: accent }} className="mx-auto mb-4" />
          <p className="text-2xl font-bold text-white">Thanks for singing!</p>
        </div>
      </div>
    );
  }

  const showVideo = wantPlaying && singer && singer.videoId && !ytProblem && !loadingSong;
  return (
    <div ref={rootRef} className="fixed inset-0 bg-black" style={{ overflow: "hidden" }} data-testid="karaoke-audience">
      {!isFullscreen && (
        <div className="fixed inset-0 bg-black z-[9999] flex items-center justify-center cursor-pointer" onClick={enterFullscreen} data-testid="karaoke-audience-fullscreen-gate">
          <div className="text-center">
            <div className="w-32 h-32 mx-auto mb-8 rounded-full flex items-center justify-center" style={{ backgroundColor: "rgba(34,197,94,0.2)", border: `2px solid ${accent}50` }}>
              <Maximize size={56} style={{ color: accent }} />
            </div>
            <h2 className="text-5xl font-bold text-white mb-4">Click to Enter Fullscreen</h2>
            <p className="text-xl" style={{ color: "#8892b0" }}>Optimized for TV display</p>
            <p className="text-sm mt-6" style={{ color: "#555" }}>Press ESC at any time to exit</p>
          </div>
        </div>
      )}
      <img src={`${API}/karaoke/overlay/master`} alt="" className="absolute inset-0 w-full h-full" style={{ zIndex: 1, pointerEvents: "none", objectFit: "fill" }} data-testid="karaoke-audience-overlay" />

      {/* 1. VIDEO */}
      <div className="absolute" style={{ ...OVERLAY.video, zIndex: 2, backgroundColor: "#000", overflow: "hidden", opacity: isFading ? 0 : 1, transition: "opacity 3s ease-out" }} data-testid="karaoke-audience-video" data-via={via}>
        <div ref={playerHostRef} className="absolute inset-0" style={{ visibility: (wantPlaying && singer && singer.videoId && !ytProblem) ? "visible" : "hidden" }} />
        {/* alpha.89: the NEXT song buffers here, invisible but full size, so when it starts it is simply revealed
            (the player is never moved or rebuilt, which would throw the buffer away). */}
        {!showVideo && singer && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-8" style={{ backgroundColor: "#000", zIndex: 1 }} data-testid="karaoke-audience-singer">
            <div className="w-20 h-20 rounded-full mx-auto flex items-center justify-center mb-4" style={{ backgroundColor: "rgba(34,197,94,0.15)", border: `3px solid ${accent}` }}>
              <Mic size={36} style={{ color: accent }} />
            </div>
            <p className="text-5xl font-black text-white mb-3" style={{ textShadow: `0 0 40px ${accent}40` }}>{singer.name}</p>
            <p className="text-2xl" style={{ color: accent }}>{singer.song}</p>
            {loadingSong && !ytProblem && <p className="text-sm mt-4" style={{ color: "#8892b0" }} data-testid="karaoke-audience-loading">Loading your song...</p>}
            {ytProblem && <p className="text-sm mt-4" style={{ color: "#fbdd68" }} data-testid="karaoke-audience-yt-problem">{ytReason ? explainVideoError(ytReason) : "The video could not load."} The host will pick another song.</p>}
          </div>
        )}
        {!showVideo && !singer && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center" style={{ backgroundColor: "#000", zIndex: 1 }}>
            <Music size={40} style={{ color: accent, opacity: 0.5 }} className="mx-auto mb-3" />
            <p className="text-2xl text-white">Music Playing</p>
          </div>
        )}
      </div>

      {/* 2. UP NEXT bar */}
      <div className="absolute overflow-hidden flex items-center" style={{ ...OVERLAY.chyron, zIndex: 2, backgroundColor: "#000", borderRadius: "9999px" }} data-testid="karaoke-audience-chyron">
        {chyronText ? (
          <div className="whitespace-nowrap" style={{ animation: `chyronScroll ${Math.max(25, chyronText.length * 0.375)}s linear infinite`, color: "#fff", fontSize: "2.1vw", fontWeight: 600, paddingLeft: "100%" }}>{chyronText}</div>
        ) : (
          <p className="text-center w-full text-white text-lg" style={{ opacity: 0.3 }}>Karaoke Night</p>
        )}
        <style>{"@keyframes chyronScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-200%); } }"}</style>
      </div>

      {/* 3. VENUE LOGO (from Karaoke Setup) - fits inside the window, never cropped */}
      <div className="absolute overflow-hidden flex items-center justify-center" style={{ ...OVERLAY.logo, zIndex: 2, backgroundColor: "#000", borderRadius: "12px" }} data-testid="karaoke-audience-logo">
        {location && logoOk ? (
          <img src={`${API}/karaoke/venue-logo/${encodeURIComponent(location)}`} alt="" className="w-full h-full" style={{ objectFit: "contain" }} onError={() => setLogoOk(false)} />
        ) : (
          <Mic size={32} style={{ color: accent, opacity: 0.2 }} />
        )}
      </div>

      {/* 4. REQUEST QR */}
      <div className="absolute overflow-hidden flex items-center justify-center" style={{ ...OVERLAY.qr, zIndex: 2, backgroundColor: "#fff", borderRadius: "12px", padding: "1%" }} data-testid="karaoke-audience-qr">
        {requestUrl ? (
          <QRCodeSVG value={requestUrl} size={200} style={{ width: "100%", height: "100%" }} />
        ) : (
          <p className="text-center font-bold" style={{ color: "#334155", fontSize: "1.1vw" }} data-testid="karaoke-audience-qr-wait">Request QR<br />getting ready...</p>
        )}
      </div>
    </div>
  );
}
