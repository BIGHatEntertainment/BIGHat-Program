import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Music, Maximize } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import axios from "axios";
import { bufferStatus, explainVideoError } from "./karaokeFlow";
import { makeSongClock, IFRAME_REFERRER } from "./iframePlayback";

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
 *  - alpha.98: it plays the song in a PLAIN YouTube iframe (exactly like the prototype). A clock started from the song's
 *    known length reports started / time / ended to the server. The host follows these reports.
 *  - A routine refresh never seeks or pauses the video. Only the host's play / pause / end commands do.
 *  - The video fades out over 3 s when a song is ending, then the screen goes back to the music view.
 *  - Layout: the master overlay image with the video, scrolling "up next" bar, venue logo and request QR placed in its windows.
 */
const waitingText = (list) => list.length ? "UP NEXT:  " + list.map((e) => `${e.singer_name}${e.song_title ? " \u2014 " + e.song_title : ""}`).join("   \u2022   ") : "";
const RETRY_AFTER_MS = 4000;     // alpha.93: a failed preload is tried again after this long
const MAX_TRIES = 6;


// alpha.101: YouTube's own player script, exactly as the alphas that played video used it. It gives the embed the page's origin.
let ytPromise = null;
function loadYouTubeApi() {
  if (ytPromise) return ytPromise;
  ytPromise = new Promise((resolve, reject) => {
    if (window.YT && window.YT.Player) return resolve(window.YT);
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (prev) prev(); resolve(window.YT); };
    const sc = document.createElement("script");
    sc.src = "https://www.youtube.com/iframe_api";
    sc.onerror = () => { ytPromise = null; reject(new Error("youtube_unreachable")); };
    document.head.appendChild(sc);
  });
  return ytPromise;
}

export default function KaraokeAudienceView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [ended, setEnded] = useState(false);
  const [location, setLocation] = useState("");
  const [logoOk, setLogoOk] = useState(true);
  const [chyronText, setChyronText] = useState("");
  const [singer, setSinger] = useState(null);       // { id, name, song, artist, videoId }
  const [wantPlaying, setWantPlaying] = useState(false);
  const [isFading, setIsFading] = useState(false);
  const clockRef = useRef(makeSongClock());          // alpha.98: the song clock (a plain iframe cannot report time)
  const frameRef = useRef(null);                    // alpha.98: the plain YouTube iframe
  const [frameSrc, setFrameSrc] = useState("");
  const [ytProblem, setYtProblem] = useState(false);
  const [ytReason, setYtReason] = useState("");          // alpha.96: YouTube's error code, shown as words
  const [requestUrl, setRequestUrl] = useState(`${window.location.origin}/karaoke/request`);

  const rootRef = useRef(null);
  const playerRef = useRef(null);
  const playerHostRef = useRef(null);
  const bufferHostRef = useRef(null);      // alpha.89: where the next song buffers
  const songRef = useRef({ id: null, videoId: null, startedReported: false, endedReported: false });
  const wantPlayingRef = useRef(false);
  const timerRef = useRef(null);
  const channelRef = useRef(null);
  const preloadRef = useRef({ singerId: null, player: null });   // the next singer's video, loading silently in the background
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
    try { playerRef.current && playerRef.current.destroy(); } catch { /* already gone */ }
    playerRef.current = null;
  }, []);

  // ---- start the video for a new song (alpha.98: a PLAIN YouTube iframe, exactly like the prototype)
  // The iframe plays the song. A small clock, started from the song's known length, reports started / time / ended to the host.
  const startSong = useCallback(async (videoId, singerId, lengthSeconds) => {
    destroyPlayer();
    stopTimer();
    songRef.current = { id: singerId, videoId, startedReported: false, endedReported: false };
    setYtProblem(false); setYtReason("");
    try {
      const YT = await loadYouTubeApi();
      if (songRef.current.videoId !== videoId || !playerHostRef.current) return;
      playerHostRef.current.innerHTML = "<div id='karaoke-yt'></div>";
      playerRef.current = new YT.Player("karaoke-yt", {
        videoId, width: "100%", height: "100%",
        playerVars: { autoplay: 1, controls: 0, rel: 0, modestbranding: 1, playsinline: 1, disablekb: 1, fs: 0 },
        events: {
          onReady: (ev) => { try { if (wantPlayingRef.current) ev.target.playVideo(); else ev.target.pauseVideo(); } catch { /* ignore */ } },
          onError: (ev) => { setYtProblem(true); setYtReason(String((ev && ev.data) || "5")); report({ error: String((ev && ev.data) || "5") }); },
        },
      });
      setFrameSrc("youtube-player:" + videoId);
    } catch { setYtProblem(true); setYtReason("no_youtube"); report({ error: "no_youtube" }); }
    const clock = clockRef.current;
    clock.start(lengthSeconds || 0);
    if (!wantPlayingRef.current) clock.pause();
    const song = songRef.current;
    if (!song.startedReported) { song.startedReported = true; report({ started: true, duration: lengthSeconds || 0 }); }
    timerRef.current = setInterval(() => {
      const t = clock.tick();
      if (!clock.isPaused()) report({ time: t.time });
      if (t.ended && !song.endedReported) { song.endedReported = true; stopTimer(); report({ ended: true }); }
    }, 1000);
  }, [destroyPlayer, report]);

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
    const clock = clockRef.current;
    if (playing && s && videoId) {
      if (song.id !== s.id || song.videoId !== videoId) startSong(videoId, s.id, Number(s.duration_seconds) || 0);
      else if (clock.isPaused()) {
        // the host pressed Play again on the SAME song: carry on from where it was (no seeking)
        clock.resume();
        try { playerRef.current && playerRef.current.playVideo(); } catch { /* ignore */ }
      }
    } else if (!playing && song.id && song.id === (s && s.id)) {
      // the host paused the song
      clock.pause();
      try { playerRef.current && playerRef.current.pauseVideo(); } catch { /* ignore */ }
    }
    if (!s || (!playing && !s)) {
      destroyPlayer();
      clock.stop();
      setFrameSrc("");
      songRef.current = { id: null, videoId: null, startedReported: false, endedReported: false };
    }
  }, [startSong, destroyPlayer]);

  // ---- preload (alpha.98): like the prototype, the NEXT singer's video is warmed with a plain, hidden YouTube iframe
  // (no second JavaScript player, no muted playback, no buffering percentage). The song itself plays in its own iframe when its turn comes.
  const hostWaitingRef = useRef([]);               // alpha.99: the waiting list the HOST sent
  const ownQueueRef = useRef(false);               // alpha.99: did the TV's own request bring a queue?
  const [warmSrc, setWarmSrc] = useState("");
  const [diag, setDiag] = useState({ polls: 0, ok: false, queue: -1, playback: "?", preload: "-", error: "" });   // alpha.99: what this TV window really sees
  const [showDiag, setShowDiag] = useState(() => /[?&]debug=1/.test(window.location.search));
  const handlePreload = useCallback((pre) => {
    const videoId = pre && pre.singer_id ? videoIdOf(pre.embed_url) : "";
    // never warm the SAME video that is playing right now (two copies of one video is what can make YouTube refuse one)
    if (!videoId || videoId === songRef.current.videoId) { setWarmSrc(""); return; }
    // muted + not autoplaying: it only gets the page and the first part of the video ready
    setWarmSrc(`https://www.youtube.com/embed/${encodeURIComponent(videoId)}?autoplay=0&mute=1&preload=auto`);
  }, []);

  // ---- instant messages from the host window
  useEffect(() => {
    const ch = new BroadcastChannel("karaoke-state");
    channelRef.current = ch;
    ch.onmessage = (ev) => {
      const m = ev.data || {};
      if (m.ended) { setEnded(true); return; }
      if (m.type === "karaoke-state" && m.pb) {
        apply(m.pb);
        if (Array.isArray(m.waiting)) {
          hostWaitingRef.current = m.waiting;
          if (!ownQueueRef.current) setChyronText(waitingText(m.waiting));        // the TV's own request has not brought anything: use the host's list
        }
      }
    };
    return () => ch.close();
  }, [apply]);

  // ---- slow refresh from the server (survives a refreshed window). Never seeks or pauses by itself.
  useEffect(() => {
    let active = true;
    const poll = async () => {
      while (active) {
        try {
          let why = "";                                           // alpha.99: remember WHY a request failed (the page still carries on with an empty answer)
          const [pbRes, qRes] = await Promise.all([
            axios.get(`${API}/karaoke/session/playback`).catch((e) => { why = "playback: " + ((e && e.message) || e); return { data: {} }; }),
            axios.get(`${API}/karaoke/queue`).catch((e) => { why = (why ? why + " | " : "") + "queue: " + ((e && e.message) || e); return { data: { queue: [] } }; }),
          ]);
          setDiag((d) => ({ polls: d.polls + 1, ok: !why && (!!pbRes.data.playback || pbRes.data.playback === null), queue: (qRes.data.queue || []).length, error: why,
            playback: pbRes.data.playback ? (pbRes.data.playback.song_playing ? "playing" : "not playing") : String(pbRes.data.playback),
            preload: pbRes.data.preload && pbRes.data.preload.singer_id ? "next=" + pbRes.data.preload.singer_id : "none" }));
          if (pbRes.data.playback === null) { setEnded(true); break; }
          if (pbRes.data.playback) {
            apply(pbRes.data.playback);
            if (pbRes.data.location) setLocation((cur) => (cur === pbRes.data.location ? cur : pbRes.data.location));
            handlePreload(pbRes.data.preload);
          }
          const q = (qRes.data.queue || []).filter((e) => e.status === "waiting").slice(0, 3);
          ownQueueRef.current = q.length > 0;
          setChyronText(q.length ? waitingText(q) : (hostWaitingRef.current.length ? waitingText(hostWaitingRef.current) : ""));
        } catch (e) { setDiag((d) => ({ ...d, ok: false, error: String((e && e.message) || e) })); /* try again next round */ }
        await new Promise((r) => setTimeout(r, 2500));
      }
    };
    poll();
    return () => { active = false; };
  }, [apply, handlePreload]);

  // alpha.99: press D on the TV window to show or hide the diagnostic strip (what this window really sees)
  useEffect(() => {
    const onKey = (e) => { if ((e.key === "d" || e.key === "D") && !e.ctrlKey && !e.metaKey && !e.altKey) setShowDiag((v) => !v); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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

  const showVideo = wantPlaying && singer && singer.videoId && !ytProblem;
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
      <div className="absolute" style={{ ...OVERLAY.video, zIndex: 2, backgroundColor: "#000", overflow: "hidden", opacity: isFading ? 0 : 1, transition: "opacity 3s ease-out" }} data-testid="karaoke-audience-video">
        <div ref={playerHostRef} className="absolute inset-0" style={{ display: showVideo ? "block" : "none" }}>
        </div>
        {showDiag && (
          <div className="absolute left-0 right-0 bottom-0 p-2 text-[12px] font-mono" style={{ zIndex: 9000, backgroundColor: "rgba(0,0,0,0.85)", color: "#9fe870", lineHeight: 1.5 }} data-testid="karaoke-audience-diag">
            <div>page: {window.location.origin} | server: {String(process.env.REACT_APP_BACKEND_URL || "(same address)")}</div>
            <div>polls: {diag.polls} | reached server: {String(diag.ok)} | queue entries: {diag.queue} | playback: {diag.playback} | next song handed over: {diag.preload}{diag.error ? " | ERROR: " + diag.error : ""}</div>
            <div>song iframe: {frameSrc ? frameSrc.replace("https://www.youtube.com/embed/", "").split("?")[0] : "(none)"} | warm iframe: {warmSrc ? warmSrc.replace("https://www.youtube.com/embed/", "").split("?")[0] : "(none)"} | clock: {clockRef.current.isRunning() ? (clockRef.current.isPaused() ? "paused" : "running") : "stopped"}</div>
            <div>Press D to hide this</div>
          </div>
        )}
        {/* alpha.98: the NEXT song is warmed here with a plain hidden iframe (like the prototype). It is never shown and never plays. */}
        <div ref={bufferHostRef} className="absolute" style={{ width: 2, height: 2, overflow: "hidden", opacity: 0, pointerEvents: "none", zIndex: 0 }} data-testid="karaoke-buffer-host">
          {warmSrc && <iframe key={warmSrc} src={warmSrc} title="Next song" width="2" height="2" style={{ border: 0 }} referrerPolicy={IFRAME_REFERRER} allow="encrypted-media" data-testid="karaoke-warm-iframe" />}
        </div>
        {!showVideo && singer && (
          <div className="w-full h-full flex flex-col items-center justify-center text-center px-8" data-testid="karaoke-audience-singer">
            <div className="w-20 h-20 rounded-full mx-auto flex items-center justify-center mb-4" style={{ backgroundColor: "rgba(34,197,94,0.15)", border: `3px solid ${accent}` }}>
              <Mic size={36} style={{ color: accent }} />
            </div>
            <p className="text-5xl font-black text-white mb-3" style={{ textShadow: `0 0 40px ${accent}40` }}>{singer.name}</p>
            <p className="text-2xl" style={{ color: accent }}>{singer.song}</p>
            {ytProblem && <p className="text-sm mt-4" style={{ color: "#fbdd68" }} data-testid="karaoke-audience-yt-problem">{ytReason ? explainVideoError(ytReason) : "The video could not load."} The host will pick another song.</p>}
          </div>
        )}
        {!showVideo && !singer && (
          <div className="w-full h-full flex flex-col items-center justify-center text-center">
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
