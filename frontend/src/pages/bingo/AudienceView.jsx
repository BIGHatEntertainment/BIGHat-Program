import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Music, Maximize } from "lucide-react";
import confetti from "canvas-confetti";
import axios from "axios";
import { BingoBall } from "../../components/bingo/BingoComponents";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Fixed stage resolution — all content renders at this virtual size
// then gets scaled uniformly to fill any physical screen
const STAGE_W = 1920;
const STAGE_H = 1080;

export default function AudienceView() {
  // ==================== STATE ====================
  // Use refs for game state to avoid re-renders from polling.
  // Only the specific UI-driving values get promoted to state.
  const gameStateRef = useRef(null);

  // Only these values cause re-renders when they change:
  const [bingo_type, setBingoType] = useState(null);
  const [roundNumber, setRoundNumber] = useState(1);
  const [roundType, setRoundType] = useState("traditional");
  const [musicDecade, setMusicDecade] = useState("");
  const [isActive, setIsActive] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [bingoClaimed, setBingoClaimed] = useState(false);
  const [currentNumber, setCurrentNumber] = useState(null);
  const [calledNumbers, setCalledNumbers] = useState([]);
  const [calledSongs, setCalledSongs] = useState([]);
  const [showCelebration, setShowCelebration] = useState(false);
  const [winnerName, setWinnerName] = useState("");

  // Video mirroring state (from BroadcastChannel only — not polling)
  const videoRef = useRef(null);
  const [mirrorVideoUrl, setMirrorVideoUrl] = useState(null);
  const [showSongInfo, setShowSongInfo] = useState(true);
  const [broadcastSong, setBroadcastSong] = useState(null);
  const [bingoVerifying, setBingoVerifying] = useState(false);
  const [winnerVideoUrl, setWinnerVideoUrl] = useState(null);
  const winnerVideoRef = useRef(null);

  // Fullscreen + viewport scaling state
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [stageScale, setStageScale] = useState(1);
  const rootRef = useRef(null);

  const isMusicBingo = bingo_type === "music";
  const mirrorVideoUrlRef = useRef(null);
  const winnerNameRef = useRef("");
  const showCelebrationRef = useRef(false);

  // ==================== FULLSCREEN ====================
  const enterFullscreen = useCallback(() => {
    const el = rootRef.current || document.documentElement;
    const rfs = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (rfs) rfs.call(el).catch(() => {});
  }, []);

  useEffect(() => {
    const onFsChange = () => {
      const fs = !!(document.fullscreenElement || document.webkitFullscreenElement);
      setIsFullscreen(fs);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    document.addEventListener("webkitfullscreenchange", onFsChange);
    return () => {
      document.removeEventListener("fullscreenchange", onFsChange);
      document.removeEventListener("webkitfullscreenchange", onFsChange);
    };
  }, []);

  // ==================== VIEWPORT SCALING ====================
  useEffect(() => {
    const computeScale = () => {
      const scaleX = window.innerWidth / STAGE_W;
      const scaleY = window.innerHeight / STAGE_H;
      setStageScale(Math.min(scaleX, scaleY));
    };
    computeScale();
    window.addEventListener("resize", computeScale);
    return () => window.removeEventListener("resize", computeScale);
  }, []);

  // ==================== BROADCAST CHANNEL ====================
  // Stable — never recreated. Handles video + song info in real-time.
  useEffect(() => {
    const channel = new BroadcastChannel("music-bingo-video");

    channel.onmessage = (event) => {
      const { type, videoUrl, isPlaying, currentTime, volume, showSongInfo: songInfoFlag, currentSong, bingoVerifying: verifying, bingoWinner, winnerVideo, roundEnded } = event.data;
      if (type !== "video-state") return;

      // Handle bingo verification state
      if (verifying !== undefined) setBingoVerifying(verifying);
      
      // Handle winner video
      if (bingoWinner !== undefined) {
        if (bingoWinner && winnerVideo) {
          setWinnerVideoUrl(winnerVideo);
          setBingoVerifying(false);
        } else {
          setWinnerVideoUrl(null);
        }
      }
      
      // Handle round ended
      if (roundEnded) {
        setWinnerVideoUrl(null);
        setBingoVerifying(false);
      }

      if (songInfoFlag !== undefined) setShowSongInfo(songInfoFlag);
      if (currentSong !== undefined) setBroadcastSong(currentSong);

      if (videoUrl && videoUrl !== mirrorVideoUrlRef.current) {
        mirrorVideoUrlRef.current = videoUrl;
        setMirrorVideoUrl(videoUrl);
      }

      // Direct DOM manipulation for video — no state updates, no re-renders
      const vid = videoRef.current;
      if (vid && !bingoWinner) {
        if (currentTime !== undefined && Math.abs(vid.currentTime - currentTime) > 2) {
          vid.currentTime = currentTime;
        }
        if (isPlaying && vid.paused) vid.play().catch(() => {});
        else if (!isPlaying && !vid.paused) vid.pause();
      }
    };

    return () => channel.close();
  }, []);

  // Auto-play when mirror video source changes
  useEffect(() => {
    if (videoRef.current && mirrorVideoUrl) {
      videoRef.current.play().catch(() => {});
    }
  }, [mirrorVideoUrl]);

  // ==================== GAME STATE POLLING ====================
  // Uses refs to avoid callback recreation. Only updates individual state
  // values that actually changed — prevents unnecessary re-renders.
  useEffect(() => {
    const poll = async () => {
      try {
        const response = await axios.get(`${API}/bingo/game/state`);
        if (!response.data.game) return;
        const g = response.data.game;
        gameStateRef.current = g;

        // Only update state for values that actually changed
        setBingoType(prev => g.settings?.bingo_type !== prev ? g.settings?.bingo_type : prev);
        setRoundNumber(prev => g.round_number !== prev ? g.round_number : prev);
        setRoundType(prev => g.settings?.round_type !== prev ? g.settings?.round_type : prev);
        setMusicDecade(prev => g.settings?.music_decade !== prev ? g.settings?.music_decade : prev);
        setIsActive(prev => g.is_active !== prev ? g.is_active : prev);
        setIsPaused(prev => g.is_paused !== prev ? g.is_paused : prev);
        setBingoClaimed(prev => g.bingo_claimed !== prev ? g.bingo_claimed : prev);
        setCurrentNumber(prev => g.current_number !== prev ? g.current_number : prev);

        // Arrays — compare by length + last element for cheap diff
        setCalledNumbers(prev => {
          if (prev.length !== (g.called_numbers?.length || 0)) return g.called_numbers || [];
          return prev;
        });
        setCalledSongs(prev => {
          if (prev.length !== (g.called_songs?.length || 0)) return g.called_songs || [];
          return prev;
        });

        // Celebration logic — only use old overlay if NO winner video from BroadcastChannel
        if (g.winner_name && g.winner_name !== winnerNameRef.current) {
          winnerNameRef.current = g.winner_name;
          setWinnerName(g.winner_name);
          // Only show old celebration if winner video is NOT playing
          if (!winnerVideoUrl) {
            setShowCelebration(true);
            showCelebrationRef.current = true;
            triggerCelebration();
          }
        } else if (!g.bingo_claimed && showCelebrationRef.current && !g.winner_name) {
          showCelebrationRef.current = false;
          setShowCelebration(false);
        }
      } catch (error) {
        // Silent — don't disrupt the view
      }
    };

    poll();
    const interval = setInterval(poll, 2000); // Slower poll — BroadcastChannel handles real-time
    return () => clearInterval(interval);
  }, []); // Empty deps — stable forever

  const triggerCelebration = () => {
    const duration = 5000;
    const end = Date.now() + duration;
    const colors = ["#D946EF", "#06B6D4", "#EAB308", "#22C55E", "#8B5CF6"];
    const frame = () => {
      confetti({ particleCount: 10, angle: 60, spread: 100, origin: { x: 0, y: 0.6 }, colors });
      confetti({ particleCount: 10, angle: 120, spread: 100, origin: { x: 1, y: 0.6 }, colors });
      if (Date.now() < end) requestAnimationFrame(frame);
    };
    frame();
  };

  const getLetterForNumber = (num) => {
    if (!num) return "";
    if (num <= 15) return "B";
    if (num <= 30) return "I";
    if (num <= 45) return "N";
    if (num <= 60) return "G";
    return "O";
  };

  const activeSong = broadcastSong || gameStateRef.current?.current_song;
  const currentLetter = getLetterForNumber(currentNumber);

  // ==================== FULLSCREEN PROMPT ====================
  if (!isFullscreen) {
    return (
      <div
        ref={rootRef}
        className="fixed inset-0 bg-black z-[9999] flex items-center justify-center cursor-pointer"
        onClick={enterFullscreen}
        data-testid="fullscreen-prompt"
      >
        <div className="text-center">
          <div className="w-32 h-32 mx-auto mb-8 rounded-full bg-fuchsia-500/20 flex items-center justify-center border-2 border-fuchsia-500/50">
            <Maximize size={56} className="text-fuchsia-400" />
          </div>
          <h2 className="font-display text-5xl text-white mb-4">Click to Enter Fullscreen</h2>
          <p className="text-zinc-400 text-xl">Optimized for TV display</p>
          <p className="text-zinc-600 text-sm mt-6">Press ESC at any time to exit</p>
        </div>
      </div>
    );
  }

  // ==================== STAGE (inline styles, not a component) ====================
  const stageStyle = {
    width: STAGE_W,
    height: STAGE_H,
    transform: `scale(${stageScale})`,
    transformOrigin: "center center",
    position: "relative",
    overflow: "hidden",
  };

  // =====================================================
  // MUSIC BINGO AUDIENCE VIEW
  // =====================================================
  if (isMusicBingo) {
    return (
      <div ref={rootRef} className="fixed inset-0 bg-black overflow-hidden flex items-center justify-center" data-testid="audience-view">
        <div style={stageStyle}>
          {/* VIDEO LAYER — always mounted, never inside AnimatePresence */}
          {mirrorVideoUrl && (
            <video
              ref={videoRef}
              src={mirrorVideoUrl}
              className="absolute inset-0 w-full h-full object-contain bg-black"
              data-testid="audience-video-player"
              playsInline
              muted
              style={{ zIndex: 1 }}
            />
          )}

          {/* OVERLAY LAYERS — on top of video */}
          {/* Header */}
          <header className="absolute top-0 left-0 right-0 flex items-center justify-between px-10 py-5"
            style={{ zIndex: 20, background: "linear-gradient(to bottom, rgba(0,0,0,0.85) 0%, transparent 100%)" }}
          >
            <div className="flex items-center gap-5">
              <h1 className="font-display text-4xl text-white">Music Bingo</h1>
              <span className="text-fuchsia-400 font-bold text-2xl">{musicDecade}</span>
            </div>
            <div className="text-right">
              <p className="text-zinc-500 text-sm">Round</p>
              <p className="font-display text-3xl text-fuchsia-400">{roundNumber}</p>
            </div>
          </header>

          {/* Song info overlay — above video, only when toggled on */}
          {showSongInfo && activeSong && !showCelebration && !isPaused && (
            <div
              className="absolute left-0 right-0 text-center pointer-events-none"
              style={{ bottom: 120, zIndex: 15 }}
              data-testid="audience-song-overlay"
            >
              <div className="inline-block bg-black/80 backdrop-blur-lg rounded-2xl px-10 py-5 border border-fuchsia-500/40"
                style={{ boxShadow: "0 8px 32px rgba(217, 70, 239, 0.3)" }}
              >
                <span className="font-mono text-fuchsia-400 text-xl">#{activeSong.number}</span>
                <p className="font-display text-4xl text-white mt-1">{activeSong.title}</p>
                <p className="text-zinc-300 text-xl mt-1">{activeSong.artist}</p>
              </div>
            </div>
          )}

          {/* Center content — only for non-video states (celebration, waiting, not started) */}
          {!mirrorVideoUrl && (
            <div className="absolute inset-0 flex items-center justify-center" style={{ zIndex: 5 }}>
              <AnimatePresence mode="wait">
                {showCelebration ? (
                  <motion.div key="celebration" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }} className="text-center">
                    <motion.div animate={{ scale: [1, 1.1, 1], rotate: [0, -5, 5, 0] }} transition={{ duration: 0.5, repeat: Infinity, repeatType: "reverse" }}>
                      <Trophy size={200} className="text-yellow-400 mx-auto mb-8 fill-yellow-400" />
                    </motion.div>
                    <h2 className="celebration-text mb-4">BINGO!</h2>
                    <p className="font-display text-6xl text-white mt-8">Congratulations, {winnerName}!</p>
                  </motion.div>
                ) : activeSong ? (
                  <motion.div key={`song-${activeSong.number}`} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }} transition={{ duration: 0.5 }} className="text-center w-full px-8">
                    <motion.div initial={{ scale: 0, rotate: -180 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 200, damping: 15 }} className="mb-12">
                      <div className="w-64 h-64 mx-auto rounded-full bg-gradient-to-br from-fuchsia-500 via-purple-600 to-fuchsia-700 flex items-center justify-center relative"
                        style={{ boxShadow: "inset -15px -15px 40px rgba(0,0,0,0.4), inset 15px 15px 40px rgba(255,255,255,0.2), 0 30px 80px rgba(217, 70, 239, 0.6)" }}
                      >
                        <div className="absolute w-[40%] h-[40%] rounded-full bg-zinc-900 flex items-center justify-center">
                          <span className="font-display text-8xl text-fuchsia-400">{activeSong.number}</span>
                        </div>
                        <div className="absolute top-[10%] left-[20%] w-[30%] h-[20%] bg-gradient-to-br from-white/40 to-transparent rounded-full" />
                      </div>
                    </motion.div>
                    <motion.h2 initial={{ y: 50, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }} className="font-display text-8xl text-white mb-6 leading-tight">
                      {showSongInfo ? activeSong.title : "Now Playing..."}
                    </motion.h2>
                    {showSongInfo && (
                      <motion.p initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.3 }} className="text-5xl text-zinc-400">
                        {activeSong.artist}
                      </motion.p>
                    )}
                  </motion.div>
                ) : isActive ? (
                  <motion.div key="waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
                    <div className="loading-balls justify-center mb-12">
                      {[...Array(5)].map((_, i) => <div key={i} className="loading-ball" style={{ width: 40, height: 40 }} />)}
                    </div>
                    <p className="font-display text-6xl text-zinc-500">Get Ready...</p>
                  </motion.div>
                ) : (
                  <motion.div key="not-started" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
                    <Music size={120} className="text-zinc-800 mx-auto mb-8" />
                    <h2 className="font-display text-8xl text-zinc-700 mb-6">Music Bingo</h2>
                    <p className="text-4xl text-zinc-600">Waiting for game to start...</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Celebration overlay — shows ON TOP of video too */}
          {mirrorVideoUrl && showCelebration && (
            <div className="absolute inset-0 bg-black/80 flex items-center justify-center" style={{ zIndex: 25 }}>
              <div className="text-center">
                <Trophy size={200} className="text-yellow-400 mx-auto mb-8 fill-yellow-400" />
                <h2 className="celebration-text mb-4">BINGO!</h2>
                <p className="font-display text-6xl text-white mt-8">Congratulations, {winnerName}!</p>
              </div>
            </div>
          )}

          {/* Paused Indicator */}
          {isPaused && !showCelebration && (
            <div className="absolute inset-0 bg-black/90 flex items-center justify-center" style={{ zIndex: 30 }}>
              <div className="text-center">
                <p className="font-display text-8xl text-yellow-400 mb-4">
                  {bingoClaimed ? "VERIFYING BINGO" : "PAUSED"}
                </p>
                {bingoClaimed && <p className="text-3xl text-zinc-400">Please wait...</p>}
              </div>
            </div>
          )}

          {/* Footer - Recently Played */}
          <footer className="absolute bottom-0 left-0 right-0 px-10 py-6"
            style={{ zIndex: 20, background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 100%)" }}
          >
            <div className="max-w-6xl mx-auto">
              <div className="flex justify-center gap-6 flex-wrap">
                {calledSongs.slice(-10).reverse().map((song, idx) => (
                  <div key={song.number} className="text-center" style={{ opacity: 1 - idx * 0.08 }}>
                    <div className={`${idx === 0 ? "w-16 h-16 text-2xl" : "w-12 h-12 text-lg"} rounded-full bg-gradient-to-br from-fuchsia-500 to-purple-600 flex items-center justify-center text-white font-bold shadow-lg`}>
                      {song.number}
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-center text-zinc-600 mt-4 text-lg">{calledSongs.length} songs played</p>
            </div>
          </footer>
        </div>
      </div>
    );
  }

  // =====================================================
  // TRADITIONAL BINGO AUDIENCE VIEW
  // =====================================================
  return (
    <div ref={rootRef} className="fixed inset-0 bg-black overflow-hidden flex items-center justify-center" data-testid="audience-view">
      <div style={stageStyle}>
        <header className="absolute top-0 left-0 right-0 flex items-center justify-between px-10 py-6"
          style={{ zIndex: 20, background: "linear-gradient(to bottom, rgba(10,10,10,0.9) 0%, transparent 100%)" }}
        >
          <div>
            <h1 className="font-display text-5xl text-white tracking-wider">Bingo</h1>
            <p className="text-zinc-500 mt-1 text-lg">BIG Hat Entertainment</p>
          </div>
          <div className="flex items-center gap-8">
            <div className="text-right">
              <p className="text-zinc-500 text-sm">Round</p>
              <p className="font-display text-4xl text-fuchsia-400">{roundNumber}</p>
            </div>
            <div className="text-right">
              <p className="text-zinc-500 text-sm">Type</p>
              <p className="font-display text-3xl text-cyan-400">{roundType.toUpperCase()}</p>
            </div>
          </div>
        </header>

        <div className="absolute inset-0 flex flex-col items-center justify-center" style={{ zIndex: 5 }}>
          <AnimatePresence mode="wait">
            {showCelebration ? (
              <motion.div key="celebration" initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }} className="text-center">
                <motion.div animate={{ scale: [1, 1.1, 1], rotate: [0, -5, 5, 0] }} transition={{ duration: 0.5, repeat: Infinity, repeatType: "reverse" }}>
                  <Trophy size={160} className="text-yellow-400 mx-auto mb-8 fill-yellow-400" />
                </motion.div>
                <h2 className="celebration-text mb-4">BINGO!</h2>
                <p className="font-display text-5xl text-white mt-8">Congratulations, {winnerName}!</p>
              </motion.div>
            ) : currentNumber ? (
              <motion.div key={currentNumber} initial={{ scale: 0, rotate: -180 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 200, damping: 15 }} className="text-center">
                <motion.p className="big-letter mb-4" initial={{ y: -50, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }}>
                  {currentLetter}
                </motion.p>
                <div className="flex justify-center">
                  <BingoBall number={currentNumber} letter={currentLetter} size="mega" />
                </div>
              </motion.div>
            ) : isActive ? (
              <motion.div key="waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
                <div className="loading-balls justify-center mb-8">
                  {[...Array(5)].map((_, i) => <div key={i} className="loading-ball" style={{ width: 24, height: 24 }} />)}
                </div>
                <p className="font-display text-4xl text-zinc-400">Get Ready...</p>
              </motion.div>
            ) : (
              <motion.div key="not-started" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
                <h2 className="font-display text-7xl text-zinc-600 mb-4">Bingo</h2>
                <p className="text-3xl text-zinc-500">Waiting for game to start...</p>
              </motion.div>
            )}
          </AnimatePresence>

          {isPaused && !showCelebration && (
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-black/80 px-12 py-6 rounded-2xl border-2 border-yellow-500" style={{ zIndex: 30 }}>
              <p className="font-display text-5xl text-yellow-400">{bingoClaimed ? "VERIFYING BINGO..." : "PAUSED"}</p>
            </div>
          )}
        </div>

        <footer className="absolute bottom-0 left-0 right-0 px-10 py-6"
          style={{ zIndex: 20, background: "linear-gradient(to top, rgba(10,10,10,0.9) 0%, transparent 100%)" }}
        >
          <p className="text-zinc-500 text-sm mb-4 text-center">Recently Called</p>
          <div className="flex justify-center gap-5 flex-wrap">
            {calledNumbers.slice(-10).reverse().map((num, idx) => (
              <div key={num} style={{ opacity: 1 - idx * 0.08 }}>
                <BingoBall number={num} size={idx === 0 ? "default" : "small"} />
              </div>
            ))}
          </div>
          <div className="text-center mt-4">
            <p className="text-zinc-600 text-lg">{calledNumbers.length} numbers called</p>
          </div>
        </footer>
      </div>

      {/* Bingo Verifying Overlay */}
      {bingoVerifying && !winnerVideoUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.9)' }}>
          <div className="text-center">
            <div className="font-display text-6xl text-yellow-400 mb-4 animate-pulse">BINGO!</div>
            <p className="text-2xl text-white">Host is verifying...</p>
            <p className="text-lg text-zinc-400 mt-2">Please stand by</p>
          </div>
        </div>
      )}

      {/* Winner Video Loop */}
      {winnerVideoUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black">
          <video
            ref={winnerVideoRef}
            src={winnerVideoUrl}
            autoPlay
            loop
            playsInline
            className="w-full h-full object-contain"
          />
        </div>
      )}
    </div>
  );
}
