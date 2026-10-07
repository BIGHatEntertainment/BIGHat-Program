import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Music, Maximize } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import axios from "axios";
import { bufferStatus } from "./karaokeFlow";

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

// YouTube's IFrame API, loaded once. It is what tells us the REAL play time and when a video ENDS.
let ytPromise = null;
export function loadYouTubeApi() {
  if (ytPromise) return ytPromise;
  ytPromise = new Promise((resolve, reject) => {
    if (window.YT && window.YT.Player) return resolve(window.YT);
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (prev) prev(); resolve(window.YT); };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = () => { ytPromise = null; reject(new Error("youtube_unreachable")); };
    document.head.appendChild(s);
  });
  return ytPromise;
}

/**
 * Karaoke audience screen (alpha.70). THIS SCREEN IS THE CLOCK.
 *  - It plays the song itself (YouTube IFrame API) and reports started / time / ended to the server.
 *    The host follows these reports. The host never guesses where the song is.
 *  - A routine refresh never seeks or pauses the video. Only the host's play / pause / end commands do.
 *  - The video fades out over 3 s when a song is ending, then the screen goes back to the music view.
 *  - Layout: the master overlay image with the video, scrolling "up next" bar, venue logo and request QR placed in its windows.
 */
const RETRY_AFTER_MS = 4000;     // alpha.93: a failed preload is tried again after this long
const MAX_TRIES = 6;

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

  const onYtState = useCallback((e) => {
    const YT = window.YT;
    const p = playerRef.current;
    if (!YT || !p) return;
    const song = songRef.current;
    if (e.data === YT.PlayerState.PLAYING) {
      if (!song.startedReported) {
        song.startedReported = true;
        let duration = 0;
        try { duration = p.getDuration() || 0; } catch { /* not ready */ }
        report({ started: true, duration });
      }
      if (!timerRef.current) {
        timerRef.current = setInterval(() => {
          try { report({ time: p.getCurrentTime() || 0 }); } catch { /* player gone */ }
        }, 1000);
      }
    } else if (e.data === YT.PlayerState.ENDED) {
      stopTimer();
      if (!song.endedReported) { song.endedReported = true; report({ ended: true }); }
    } else if (e.data === YT.PlayerState.PAUSED) {
      stopTimer();
    }
  }, [report]);

  // ---- start the video for a new song
  const startSong = useCallback(async (videoId, singerId) => {
    // alpha.89: if this exact song was already buffered in the background, REVEAL that player instead of building a new one.
    const buf = preloadRef.current;
    if (buf && buf.singerId === singerId && buf.videoId === videoId && buf.player && buf.ready && !buf.adopted && playerHostRef.current && bufferHostRef.current) {
      try {
        destroyPlayer();
        songRef.current = { id: singerId, videoId, startedReported: false, endedReported: false };
        setYtProblem(false);
        buf.adopted = true;
        if (buf.timer) { clearInterval(buf.timer); buf.timer = null; }
        const player = buf.player;
        playerRef.current = player;
        // the buffered player was made inside bufferHostRef; show it by raising that holder over the video box
        bufferHostRef.current.style.opacity = "1";
        bufferHostRef.current.style.zIndex = "1";
        // events set at creation time cannot be swapped, so listen to the state through the player itself
        player.addEventListener("onStateChange", onYtState);
        player.addEventListener("onError", () => setYtProblem(true));
        player.unMute();
        player.seekTo(0, true);
        if (wantPlayingRef.current) player.playVideo();
        preloadRef.current = { singerId: null, player: null };       // consumed: the next preload starts fresh
        return;
      } catch (err) {
        console.warn("[karaoke audience] could not reuse the buffered song, loading it normally:", err);
        try { bufferHostRef.current.style.opacity = "0"; bufferHostRef.current.style.zIndex = "0"; } catch { /* gone */ }
      }
    }
    destroyPlayer();
    songRef.current = { id: singerId, videoId, startedReported: false, endedReported: false };
    setYtProblem(false);
    try {
      const YT = await loadYouTubeApi();
      if (songRef.current.videoId !== videoId || !playerHostRef.current) return;   // song changed while loading
      playerHostRef.current.innerHTML = "<div id='karaoke-yt'></div>";
      playerRef.current = new YT.Player("karaoke-yt", {
        videoId, width: "100%", height: "100%",
        playerVars: { autoplay: 1, controls: 0, rel: 0, modestbranding: 1, playsinline: 1, disablekb: 1, fs: 0 },
        events: {
          onReady: (ev) => { if (wantPlayingRef.current) { try { ev.target.playVideo(); } catch { /* ignore */ } } else { try { ev.target.pauseVideo(); } catch { /* ignore */ } } },
          onStateChange: onYtState,
          onError: () => setYtProblem(true),
        },
      });
    } catch {
      setYtProblem(true);
    }
  }, [destroyPlayer, onYtState]);

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
      else if (playerRef.current && playerRef.current.getPlayerState) {
        // deliberate host command on the SAME song: play it if it was paused (no seeking)
        try { if (playerRef.current.getPlayerState() === window.YT.PlayerState.PAUSED) playerRef.current.playVideo(); } catch { /* ignore */ }
      }
    } else if (!playing && playerRef.current && song.id === (s && s.id)) {
      // host paused the song
      try { playerRef.current.pauseVideo(); } catch { /* ignore */ }
    }
    if (!s || (!playing && !s)) {
      destroyPlayer();
      songRef.current = { id: null, videoId: null, startedReported: false, endedReported: false };
    }
  }, [startSong, destroyPlayer]);

  // ---- preload (alpha.89): really BUFFER the NEXT singer's video so the song starts with no stop.
  // A "cued" video downloads nothing, so the video is STARTED muted, left to buffer, and held paused at 0:00.
  // Progress is YouTube's own getVideoLoadedFraction(), reported as a percent of the first BUFFER_NEED_SECONDS.
  const handlePreload = useCallback(async (pre) => {
    const stop = () => {
      const c = preloadRef.current;
      if (c.timer) clearInterval(c.timer);
      if (c.player && !c.adopted) { try { c.player.destroy(); } catch { /* gone */ } }
      if (c.holder && !c.adopted) { try { c.holder.innerHTML = ""; } catch { /* gone */ } }
      preloadRef.current = { singerId: null, player: null };
    };
    const cur = preloadRef.current;
    if (!pre || !pre.singer_id) { stop(); return; }
    const hostRetry = !!pre.retry && pre.retry !== cur.retryStamp;      // the host pressed "Retry loading": start this one afresh
    if (cur.singerId === pre.singer_id && !hostRetry) {
      // alpha.93: already loading or loaded this one, UNLESS it failed: then try again after a short pause (never gives up for good)
      const failed = cur.failedAt && Date.now() - cur.failedAt > RETRY_AFTER_MS && (cur.tries || 0) < MAX_TRIES;
      if (!failed) return;
    }
    const tries = cur.singerId === pre.singer_id && !hostRetry ? (cur.tries || 0) + 1 : 1;
    stop();
    preloadRef.current = { singerId: pre.singer_id, player: null, videoId: null, adopted: false, timer: null, holder: null, ready: false, tries, failedAt: 0, retryStamp: pre.retry || null };
    const fail = (why) => { const c = preloadRef.current; if (c.singerId === pre.singer_id) c.failedAt = Date.now(); report({ error: why }); };
    const videoId = videoIdOf(pre.embed_url);
    if (!videoId) return;
    const report = (body) => axios.post(`${API}/karaoke/session/preload-report`, { singer_id: pre.singer_id, ...body }).catch(() => {});
    try {
      const YT = await loadYouTubeApi();
      if (preloadRef.current.singerId !== pre.singer_id) return;            // the host moved on while YouTube loaded
      const holder = bufferHostRef.current;
      if (!holder) { fail("no_holder"); return; }
      // full size and in the page (opacity 0): Chromium will not buffer a video it considers hidden
      holder.innerHTML = "<div id='karaoke-yt-preload'></div>";
      let started = false;
      const player = new YT.Player("karaoke-yt-preload", {
        videoId, width: "100%", height: "100%",
        playerVars: { autoplay: 0, controls: 0, mute: 1, rel: 0, playsinline: 1, disablekb: 1, fs: 0 },
        events: {
          onReady: (ev) => { try { ev.target.mute(); ev.target.playVideo(); } catch { /* ignore */ } },
          onStateChange: (ev) => {
            if (preloadRef.current.singerId !== pre.singer_id) return;
            // 1 = playing: it has begun to download. Hold it at the start so nothing is "sung" yet.
            if (ev.data === 1 && !started) { started = true; try { const pl = preloadRef.current.player; pl.pauseVideo(); pl.seekTo(0, true); } catch (e) { console.warn("[karaoke audience] could not hold the buffering player:", e); } }
          },
          onError: () => fail("youtube_error"),
        },
      });
      const c = preloadRef.current;
      c.player = player; c.holder = holder; c.videoId = videoId;
      c.timer = setInterval(() => {
        const cc = preloadRef.current;
        if (cc.singerId !== pre.singer_id || !cc.player || !cc.player.getVideoLoadedFraction) return;
        let frac = 0, dur = 0;
        try { frac = cc.player.getVideoLoadedFraction(); dur = cc.player.getDuration(); } catch { return; }
        if (!dur) return;
        const b = bufferStatus(frac, dur);
        if (b.ready && !cc.ready) { cc.ready = true; report({ percent: 100, buffered_seconds: b.bufferedSeconds, ready: true }); }
        else if (!cc.ready) report({ percent: b.percent, buffered_seconds: b.bufferedSeconds });
      }, 800);
    } catch { /* no YouTube yet: say so, and try again shortly */ fail("no_youtube"); }
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
        <div ref={playerHostRef} className="absolute inset-0" style={{ display: showVideo ? "block" : "none" }} />
        {/* alpha.89: the NEXT song buffers here, invisible but full size, so when it starts it is simply revealed
            (the player is never moved or rebuilt, which would throw the buffer away). */}
        <div ref={bufferHostRef} className="absolute inset-0" style={{ opacity: 0, pointerEvents: "none", zIndex: 0 }} data-testid="karaoke-buffer-host" />
        {!showVideo && singer && (
          <div className="w-full h-full flex flex-col items-center justify-center text-center px-8" data-testid="karaoke-audience-singer">
            <div className="w-20 h-20 rounded-full mx-auto flex items-center justify-center mb-4" style={{ backgroundColor: "rgba(34,197,94,0.15)", border: `3px solid ${accent}` }}>
              <Mic size={36} style={{ color: accent }} />
            </div>
            <p className="text-5xl font-black text-white mb-3" style={{ textShadow: `0 0 40px ${accent}40` }}>{singer.name}</p>
            <p className="text-2xl" style={{ color: accent }}>{singer.song}</p>
            {ytProblem && <p className="text-sm mt-4" style={{ color: "#fbdd68" }} data-testid="karaoke-audience-yt-problem">The video could not load. Check the internet connection.</p>}
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
