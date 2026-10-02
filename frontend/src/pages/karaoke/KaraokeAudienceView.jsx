import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Music, Maximize } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import axios from "axios";

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
export default function KaraokeAudienceView() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [ended, setEnded] = useState(false);
  const [location, setLocation] = useState("");
  const [logoOk, setLogoOk] = useState(true);
  const [chyronText, setChyronText] = useState("");
  const [qrEnabled, setQrEnabled] = useState(true);
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [singer, setSinger] = useState(null);       // { id, name, song, artist, videoId }
  const [wantPlaying, setWantPlaying] = useState(false);
  const [isFading, setIsFading] = useState(false);
  const [ytProblem, setYtProblem] = useState(false);
  const [requestUrl, setRequestUrl] = useState(`${window.location.origin}/karaoke/request`);

  const rootRef = useRef(null);
  const playerRef = useRef(null);
  const playerHostRef = useRef(null);
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
  const apply = useCallback((pb, extras = {}) => {
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
    if (typeof extras.qr === "boolean") setQrEnabled(extras.qr);
    if (typeof extras.overlay === "boolean") setOverlayEnabled(extras.overlay);

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

  // ---- preload: load the NEXT singer's video silently so the song starts the moment the host presses Next Singer.
  // YouTube cannot show a percentage, so the honest signal is: "the video is cued and ready".
  const handlePreload = useCallback(async (pre) => {
    const cur = preloadRef.current;
    if (!pre || !pre.singer_id) {
      if (cur.player) { try { cur.player.destroy(); } catch { /* gone */ } }
      preloadRef.current = { singerId: null, player: null };
      return;
    }
    if (cur.singerId === pre.singer_id) return;              // already loading or loaded this one
    if (cur.player) { try { cur.player.destroy(); } catch { /* gone */ } }
    preloadRef.current = { singerId: pre.singer_id, player: null };
    const videoId = videoIdOf(pre.embed_url);
    if (!videoId) return;
    try {
      const YT = await loadYouTubeApi();
      if (preloadRef.current.singerId !== pre.singer_id) return;            // the host moved on while YouTube loaded
      const holder = document.createElement("div");
      holder.id = "karaoke-yt-preload";
      holder.style.cssText = "position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;left:-10px;top:-10px";
      document.body.appendChild(holder);
      const player = new YT.Player("karaoke-yt-preload", {
        videoId, width: "1", height: "1",
        playerVars: { autoplay: 0, controls: 0, mute: 1 },
        events: {
          onReady: (ev) => { try { ev.target.mute(); ev.target.cueVideoById(videoId); } catch { /* ignore */ } },
          onStateChange: (ev) => {
            // 5 = CUED: the video is loaded and waiting
            if (ev.data === 5 && preloadRef.current.singerId === pre.singer_id) {
              axios.post(`${API}/karaoke/session/preload-report`, { singer_id: pre.singer_id, ready: true }).catch(() => {});
            }
          },
        },
      });
      preloadRef.current.player = player;
    } catch { /* no YouTube: the host is told the song never became ready */ }
  }, []);

  // ---- instant messages from the host window
  useEffect(() => {
    const ch = new BroadcastChannel("karaoke-state");
    channelRef.current = ch;
    ch.onmessage = (ev) => {
      const m = ev.data || {};
      if (m.ended) { setEnded(true); return; }
      if (m.type === "karaoke-state" && m.pb) apply(m.pb, { qr: m.qrEnabled, overlay: m.overlayEnabled });
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
            apply(pbRes.data.playback, { qr: !!pbRes.data.qr_enabled, overlay: pbRes.data.overlay_enabled !== false });
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
  useEffect(() => {
    axios.get(`${API}/karaoke/request-info`).then((r) => { if (r.data && r.data.url) setRequestUrl(r.data.url); }).catch(() => {});
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

  if (!isFullscreen) {
    return (
      <div ref={rootRef} className="fixed inset-0 bg-black z-[9999] flex items-center justify-center cursor-pointer" onClick={enterFullscreen} data-testid="karaoke-audience-fullscreen-gate">
        <div className="text-center">
          <div className="w-32 h-32 mx-auto mb-8 rounded-full flex items-center justify-center" style={{ backgroundColor: "rgba(34,197,94,0.2)", border: `2px solid ${accent}50` }}>
            <Maximize size={56} style={{ color: accent }} />
          </div>
          <h2 className="text-5xl font-bold text-white mb-4">Click to Enter Fullscreen</h2>
          <p className="text-xl" style={{ color: "#8892b0" }}>Optimized for TV display</p>
          <p className="text-sm mt-6" style={{ color: "#555" }}>Press ESC at any time to exit</p>
        </div>
      </div>
    );
  }

  const showVideo = wantPlaying && singer && singer.videoId && !ytProblem;
  return (
    <div ref={rootRef} className="fixed inset-0 bg-black" style={{ overflow: "hidden" }} data-testid="karaoke-audience">
      {overlayEnabled && <img src={`${API}/karaoke/overlay/master`} alt="" className="absolute inset-0 w-full h-full" style={{ zIndex: 1, pointerEvents: "none", objectFit: "fill" }} data-testid="karaoke-audience-overlay" />}

      {/* 1. VIDEO */}
      <div className="absolute" style={{ ...OVERLAY.video, zIndex: 2, backgroundColor: "#000", overflow: "hidden", opacity: isFading ? 0 : 1, transition: "opacity 3s ease-out" }} data-testid="karaoke-audience-video">
        <div ref={playerHostRef} className="absolute inset-0" style={{ display: showVideo ? "block" : "none" }} />
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
      {qrEnabled && (
        <div className="absolute overflow-hidden flex items-center justify-center" style={{ ...OVERLAY.qr, zIndex: 2, backgroundColor: "#fff", borderRadius: "12px", padding: "1%" }} data-testid="karaoke-audience-qr">
          <QRCodeSVG value={requestUrl} size={200} style={{ width: "100%", height: "100%" }} />
        </div>
      )}
    </div>
  );
}
