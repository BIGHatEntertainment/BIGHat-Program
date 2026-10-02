import { useState, useEffect, useRef, useCallback } from "react";
import { isTauri, openNativeAudience } from '../../lib/audienceWindow';
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { QRCodeSVG } from 'qrcode.react';
import {
  Play,
  Pause,
  Square,
  Volume2,
  VolumeX,
  Volume1,
  Maximize,
  Users,
  Timer,
  Trophy,
  CheckCircle,
  XCircle,
  RotateCcw,
  Upload,
  FolderOpen,
  Video,
  SkipForward,
  Music,
  Disc3,
  AlertCircle,
  ArrowLeft
} from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Slider } from "../../components/ui/slider";
import { Input } from "../../components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from "../../components/ui/dialog";
import { toast } from "sonner";
import axios from "axios";
import confetti from "canvas-confetti";
import { BingoBall, BingoBoard, MusicBingoBall } from "../../components/bingo/BingoComponents";
import { themeFromGameState, THEME_CONFETTI } from "../../lib/bingoTheme";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// alpha.67: a video entry is either a stream link (string, from Bingo Setup's folder)
// or a File the host picked by hand. Both become something <video> can play.
const toPlayableUrl = (entry) => (typeof entry === "string" ? entry : URL.createObjectURL(entry));

export default function HostDashboard() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const audienceWindowRef = useRef(null);
  const wsRef = useRef(null);
  const introAudioRef = useRef(null);

  // Game State
  const [gameState, setGameState] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [songListSource, setSongListSource] = useState("sample");

  // Music Bingo State
  const [songList, setSongList] = useState([]);
  const [videoFiles, setVideoFiles] = useState({});
  const [currentSong, setCurrentSong] = useState(null);
  const [nextSong, setNextSong] = useState(null);
  const [calledSongs, setCalledSongs] = useState([]);
  const [availableSongNumbers, setAvailableSongNumbers] = useState([]);

  // Video State
  const [videoFile, setVideoFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [songCooldown, setSongCooldown] = useState(false);
  const preloadedUrlsRef = useRef({}); // { songNumber: { url, ready: bool } }
  const audienceStartedRef = useRef(false);        // true once the audience window reports it is playing
  const pendingPreviewRef = useRef(null);          // starts the host preview (called when the audience starts)
  const pendingStartRef = useRef(null);            // { url, song } waiting for the <video> to exist
  const [playRequest, setPlayRequest] = useState(0); // bumps every time a new song must start
  const [volume, setVolume] = useState(0.5);
  const [isDragging, setIsDragging] = useState(false);

  // Rewards QR
  const [bingoGameCode, setBingoGameCode] = useState('');
  const [showRewardsSplash, setShowRewardsSplash] = useState(false);
  const rewardsSplashTimerRef = useRef(null);
  const bingoEventsRef = useRef([]);  // Track bingo hits: [{songs_played, winner_name}]

  // Timer State
  const [timerRunning, setTimerRunning] = useState(false);
  const [timerValue, setTimerValue] = useState(20);
  const timerIntervalRef = useRef(null);

  // Bingo Verification Dialog
  const [showBingoDialog, setShowBingoDialog] = useState(false);

  // alpha.68: "Round over" pop-up -> next round (fresh theme) or end the whole Bingo night
  const [showRoundOver, setShowRoundOver] = useState(false);
  const [roundOverStep, setRoundOverStep] = useState("choose");   // "choose" | "confirm-end"
  const [nextTheme, setNextTheme] = useState("");
  const [nextSpeed, setNextSpeed] = useState("regular");
  const [themeChoices, setThemeChoices] = useState([]);
  const [roundBusy, setRoundBusy] = useState(false);
  const [winnerName, setWinnerName] = useState("");
  const [showWinnerVideo, setShowWinnerVideo] = useState(false);
  const winnerVideoRef = useRef(null);

  // Audience song info toggle
  const [showSongInfoAudience, setShowSongInfoAudience] = useState(true);

  const isMusicBingo = gameState?.settings?.bingo_type === "music";
  const bingoTheme = themeFromGameState(gameState);

  // Fetch initial game state
  useEffect(() => {
    const fetchGameState = async () => {
      try {
        const response = await axios.get(`${API}/bingo/game/state`);
        if (response.data.game) {
          setGameState(response.data.game);
          setTimerValue(response.data.game.settings?.call_interval || 20);
          
          if (response.data.game.settings?.bingo_type === "music") {
            fetchSongList(response.data.game.settings?.music_decade || "1980s");
          }
        } else {
          toast.error("No active game found");
          navigate("/bingo");
        }
      } catch (error) {
        console.error("Error fetching game state:", error);
        toast.error("Failed to load game");
        navigate("/bingo");
      } finally {
        setIsLoading(false);
      }
    };
    fetchGameState();
  }, [navigate]);

  // Fetch song list from API (SharePoint or sample)
  const fetchSongList = async (decade) => {
    try {
      const response = await axios.get(`${API}/bingo/songlist/${decade}`);
      if (response.data.songs) {
        const all = response.data.songs;
        if (response.data.source === "local-folder") {
          // Songs come from the Bingo Setup folder and play by streaming from it.
          // Only songs that really have a video are ever called.
          const playable = all.filter(s => s.has_video !== false);
          const links = {};
          playable.forEach(s => { links[s.number] = `${API}/bingo/media/${encodeURIComponent(decade)}/${s.number}`; });
          setVideoFiles(links);
          setSongList(playable);
          setSongListSource("local-folder");
          setAvailableSongNumbers(shuffleArray(playable.map(s => s.number)));
          if (all.length !== playable.length) {
            toast.warning(`${all.length - playable.length} song(s) have no video and will be skipped`);
          }
          return;
        }
        setSongList(all);
        setSongListSource(response.data.source || "sample");
        const numbers = all.map(s => s.number);
        setAvailableSongNumbers(shuffleArray([...numbers]));
        
        if (response.data.source === "sharepoint") {
          toast.success(`Loaded ${response.data.songs.length} songs from SharePoint`);
        }
      }
    } catch (error) {
      console.error("Error fetching song list:", error);
      toast.error("Failed to load song list");
    }
  };

  const shuffleArray = (array) => {
    const shuffled = [...array];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  };

  // Pre-select and pre-buffer the next song from the available pool
  const pickNextSong = useCallback((available) => {
    if (!available || available.length === 0) {
      setNextSong(null);
      return;
    }
    const nextNum = available[0];
    const song = songList.find(s => s.number === nextNum);
    if (song) {
      setNextSong(song);
      // Pre-buffer the next 2 songs as blob URLs
      for (let i = 0; i < Math.min(2, available.length); i++) {
        const num = available[i];
        if (preloadedUrlsRef.current[num]) continue; // already preloaded
        const file = videoFiles[num];
        if (file) {
          const url = toPlayableUrl(file);
          preloadedUrlsRef.current[num] = { url, ready: false };
          const tempVid = document.createElement("video");
          tempVid.preload = "auto";
          tempVid.src = url;
          tempVid.addEventListener("canplaythrough", () => {
            preloadedUrlsRef.current[num] = { url, ready: true };
          }, { once: true });
        }
      }
    } else {
      setNextSong(null);
    }
  }, [songList, videoFiles]);

  // Auto-pick the first "up next" once song list + available numbers are ready
  useEffect(() => {
    if (availableSongNumbers.length > 0 && !nextSong && !currentSong && songList.length > 0) {
      pickNextSong(availableSongNumbers);
    }
  }, [availableSongNumbers, nextSong, currentSong, songList, pickNextSong]);

  // WebSocket connection with polling fallback
  useEffect(() => {
    let pollInterval = null;
    
    const fetchLatestState = async () => {
      try {
        const response = await axios.get(`${API}/bingo/game/state`);
        if (response.data.game) {
          setGameState(response.data.game);
        }
      } catch (error) {
        console.error("Error polling game state:", error);
      }
    };

    try {
      const wsUrl = BACKEND_URL.replace("https://", "wss://").replace("http://", "ws://");
      const ws = new WebSocket(`${wsUrl}/api/bingo/ws/game`);

      ws.onopen = () => {
        setIsConnected(true);
        if (pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWsMessage(message);
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (!pollInterval) {
          pollInterval = setInterval(fetchLatestState, 2000);
        }
      };

      ws.onerror = () => {
        setIsConnected(false);
        if (!pollInterval) {
          pollInterval = setInterval(fetchLatestState, 2000);
        }
      };

      wsRef.current = ws;
    } catch (e) {
      pollInterval = setInterval(fetchLatestState, 2000);
    }

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  const handleWsMessage = (message) => {
    switch (message.type) {
      case "state_update":
      case "game_started":
      case "game_paused":
      case "game_resumed":
      case "new_round":
        setGameState((prev) => ({ ...prev, ...message.data }));
        break;
      case "number_called":
        setGameState((prev) => ({ ...prev, ...message.data }));
        playCallSound();
        break;
      case "song_called":
        setGameState((prev) => ({ ...prev, ...message.data }));
        if (message.data.current_song) {
          setCurrentSong(message.data.current_song);
          setCalledSongs(prev => [...prev, message.data.current_song]);
        }
        break;
      case "bingo_claimed":
        setGameState((prev) => ({ ...prev, ...message.data }));
        setShowBingoDialog(true);
        break;
      case "bingo_confirmed":
        setGameState((prev) => ({ ...prev, ...message.data }));
        triggerCelebration();
        break;
      case "bingo_rejected":
        setGameState((prev) => ({ ...prev, ...message.data }));
        break;
      default:
        break;
    }
  };

  // File handling
  const handleFolderSelect = async (event) => {
    const files = Array.from(event.target.files || []);
    const videoFilesMap = {};
    
    files.forEach(file => {
      if (file.type.startsWith("video/") || file.name.toLowerCase().match(/\.(mp4|webm|mov|avi|mkv)$/)) {
        const match = file.name.match(/^(\d+)/);
        if (match) {
          const num = parseInt(match[1]);
          videoFilesMap[num] = file;
        }
      }
    });
    
    setVideoFiles(videoFilesMap);
    if (Object.keys(videoFilesMap).length > 0) {
      toast.success(`Loaded ${Object.keys(videoFilesMap).length} video files`);
    } else {
      toast.error("No video files found. Ensure files start with numbers (e.g., 01_Song.mp4)");
    }
  };

  const handleMultiFileSelect = async (event) => {
    const files = Array.from(event.target.files || []);
    const videoFilesMap = { ...videoFiles };
    
    files.forEach(file => {
      if (file.type.startsWith("video/") || file.name.toLowerCase().match(/\.(mp4|webm|mov|avi|mkv)$/)) {
        const match = file.name.match(/^(\d+)/);
        if (match) {
          const num = parseInt(match[1]);
          videoFilesMap[num] = file;
        }
      }
    });
    
    setVideoFiles(videoFilesMap);
    if (Object.keys(videoFilesMap).length > 0) {
      toast.success(`Loaded ${Object.keys(videoFilesMap).length} video files`);
    }
  };

  const handleFileSelect = useCallback((event) => {
    const file = event.target.files?.[0];
    if (file) {
      const isVideo = file.type.startsWith("video/") || file.name.toLowerCase().match(/\.(mp4|webm|mov|avi|mkv)$/);
      if (isVideo) {
        setVideoFile(file);
        const url = URL.createObjectURL(file);
        setVideoUrl(url);
        toast.success(`Loaded: ${file.name}`);
      }
    }
  }, []);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    setIsDragging(false);
    
    const files = Array.from(event.dataTransfer.files || []);
    const isVideoFile = (file) => file.type.startsWith("video/") || file.name.toLowerCase().match(/\.(mp4|webm|mov|avi|mkv)$/);
    
    if (isMusicBingo) {
      const videoFilesMap = { ...videoFiles };
      let loadedCount = 0;
      
      files.forEach(file => {
        if (isVideoFile(file)) {
          const match = file.name.match(/^(\d+)/);
          if (match) {
            const num = parseInt(match[1]);
            videoFilesMap[num] = file;
            loadedCount++;
          }
        }
      });
      
      if (loadedCount > 0) {
        setVideoFiles(videoFilesMap);
        toast.success(`Loaded ${loadedCount} video files`);
      }
    } else {
      const videoFile = files.find(f => isVideoFile(f));
      if (videoFile) {
        setVideoFile(videoFile);
        const url = URL.createObjectURL(videoFile);
        setVideoUrl(url);
        toast.success(`Loaded: ${videoFile.name}`);
      }
    }
  }, [isMusicBingo, videoFiles]);

  const handleDragOver = (event) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      const newPlaying = !isPlaying;
      setIsPlaying(newPlaying);
      broadcastVideoState({ isPlaying: newPlaying, command: newPlaying ? "play" : "pause" });
    }
  };

  const handleVolumeChange = (value) => {
    const vol = value[0] / 100;
    setVolume(vol);
    // Host video stays muted — volume controls the audience view
    broadcastVideoState({ volume: vol });
  };

  // Game controls
  const playIntroSound = () => {
    try {
      const audio = new Audio('/bingo-intro.mp3');
      audio.volume = 0.36;
      introAudioRef.current = audio;
      audio.play().catch(() => {});
      
      // Get the audio duration and fade out over the last 3 seconds
      audio.addEventListener('loadedmetadata', () => {
        const duration = audio.duration;
        const fadeStart = Math.max(0, duration - 3);
        
        const fadeInterval = setInterval(() => {
          if (!introAudioRef.current) { clearInterval(fadeInterval); return; }
          const timeLeft = duration - audio.currentTime;
          if (timeLeft <= 3 && timeLeft > 0) {
            audio.volume = Math.max(0, (timeLeft / 3) * 0.36);
          } else if (timeLeft <= 0) {
            clearInterval(fadeInterval);
          }
        }, 100);
      });
      
      audio.addEventListener('ended', () => { introAudioRef.current = null; });
    } catch (e) {
      console.warn('Intro sound failed:', e);
    }
  };

  const startGame = async () => {
    try {
      await axios.post(`${API}/bingo/game/start`);
      toast.success("Game started!");
      playIntroSound();
      playBallsRolling();
      
      // Generate game code for rewards and show splash
      if (!bingoGameCode) {
        try {
          const codeRes = await axios.post(`${API}/player/game/create`, {
            event_type: "bingo",
            location: gameState?.settings?.venue || "Music Bingo",
            host_name: "",
          });
          if (codeRes.data.code) {
            setBingoGameCode(codeRes.data.code);
            setShowRewardsSplash(true);
            // Auto-dismiss after 15 seconds
            rewardsSplashTimerRef.current = setTimeout(() => setShowRewardsSplash(false), 15000);
          }
        } catch (e) {
          console.log("Game code creation failed:", e);
        }
      } else {
        // Show splash with existing code
        setShowRewardsSplash(true);
        rewardsSplashTimerRef.current = setTimeout(() => setShowRewardsSplash(false), 15000);
      }
    } catch (error) {
      toast.error("Failed to start game");
    }
  };

  const callNumber = async () => {
    try {
      const response = await axios.post(`${API}/bingo/game/call-number`);
      if (response.data.success && gameState?.settings?.call_interval) {
        startTimer();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to call number");
    }
  };

  const callNextSong = async () => {
    if (songCooldown) return; // 5-second cooldown active
    if (availableSongNumbers.length === 0) {
      toast.error("All songs have been called!");
      return;
    }

    // Start 5-second cooldown
    setSongCooldown(true);
    setTimeout(() => setSongCooldown(false), 5000);

    const nextNumber = availableSongNumbers[0];
    const newAvailable = availableSongNumbers.slice(1);
    setAvailableSongNumbers(newAvailable);

    const song = songList.find(s => s.number === nextNumber);
    if (song) {
      setCurrentSong(song);
      setCalledSongs(prev => [...prev, song]);

      // Load and play the video for this song
      const videoFile = videoFiles[nextNumber];
      if (videoFile) {
        // Use preloaded URL if available, otherwise create new
        let url;
        var preloaded = preloadedUrlsRef.current[nextNumber];
        if (preloaded?.url) {
          url = preloaded.url;
          delete preloadedUrlsRef.current[nextNumber]; // consumed
        } else {
          if (videoUrl) URL.revokeObjectURL(videoUrl);
          url = toPlayableUrl(videoFile);
        }
        // The <video> element may not exist yet (the first song). Setting these two
        // is enough: the "start the song" effect below runs once the element is on screen.
        pendingStartRef.current = { url, song, ready: !!preloaded?.ready };
        setVideoUrl(url);
        setPlayRequest((n) => n + 1);

      } else {
        // No video file for this song — still broadcast the song info
        broadcastVideoState({ currentSong: song });
      }

      // Pre-select and pre-buffer the NEXT song(s)
      pickNextSong(newAvailable);

      // Broadcast preload URL for the NEXT song so audience can buffer it
      if (newAvailable.length > 0) {
        const nextPreloadNum = newAvailable[0];
        const nextPreloadFile = videoFiles[nextPreloadNum];
        if (nextPreloadFile) {
          let preUrl = preloadedUrlsRef.current[nextPreloadNum]?.url;
          if (!preUrl) {
            preUrl = toPlayableUrl(nextPreloadFile);
            preloadedUrlsRef.current[nextPreloadNum] = { url: preUrl, ready: false };
          }
          // Send preload hint to audience after a short delay (let current song broadcast first)
          setTimeout(() => {
            channelRef.current?.postMessage({ type: "preload-next", videoUrl: preUrl });
          }, 1000);
        }
      }

      // Sync to backend for Audience View
      try {
        await axios.post(`${API}/bingo/game/call-song`, {
          number: nextNumber,
          title: song.title,
          artist: song.artist
        });
      } catch (error) {
        console.log("Backend sync error:", error);
      }

      if (gameState?.settings?.call_interval) {
        startTimer();
      }
    }
  };

  const pauseGame = async () => {
    try {
      await axios.post(`${API}/bingo/game/pause`);
      stopTimer();
      if (videoRef.current) {
        videoRef.current.pause();
        setIsPlaying(false);
        broadcastVideoState({ isPlaying: false, command: "pause" });
      }
    } catch (error) {
      toast.error("Failed to pause game");
    }
  };

  const resumeGame = async () => {
    try {
      await axios.post(`${API}/bingo/game/resume`);
      if (videoRef.current && videoUrl) {
        videoRef.current.play();
        setIsPlaying(true);
        broadcastVideoState({ isPlaying: true, command: "play" });
      }
    } catch (error) {
      toast.error("Failed to resume game");
    }
  };

  const claimBingo = async () => {
    try {
      await axios.post(`${API}/bingo/game/bingo`);
      setShowBingoDialog(true);
      stopTimer();
      if (videoRef.current) {
        videoRef.current.pause();
        setIsPlaying(false);
      }
      // Tell audience "Host is verifying Bingo" and stop the song there too
      broadcastVideoState({ bingoVerifying: true, isPlaying: false, command: "pause" });
    } catch (error) {
      toast.error("Failed to claim bingo");
    }
  };

  // alpha.69: winner videos are served by the backend from the app-data "winner_videos" folder
  // (full URL, so the separate audience window can play it). No theme match -> the Generic video.
  const getWinnerVideoUrl = () => {
    const theme = isMusicBingo ? (gameState?.settings?.music_decade || "") : "";
    return `${API}/bingo/winner-video/${encodeURIComponent(theme || "generic")}`;
  };

  const verifyBingo = async (confirmed) => {
    try {
      await axios.post(`${API}/bingo/game/verify-bingo`, {
        winner_name: "Winner",
        confirmed
      });
      setShowBingoDialog(false);
      
      if (confirmed) {
        // Record bingo event for rewards scoring
        bingoEventsRef.current.push({
          songs_played: calledSongs.length,
          winner_name: "",  // Name set later via submitWinnerName
        });
        // Start winner video on host + audience (no name yet)
        setShowWinnerVideo(true);
        broadcastVideoState({ bingoWinner: true, winnerVideo: getWinnerVideoUrl(), winnerName: "" });
        toast.success("BINGO confirmed! Enter winner's name.");
      } else {
        // Rejected - resume the current song
        setWinnerName("");
        toast.info("Bingo rejected - game continues");
        broadcastVideoState({ bingoVerifying: false, isPlaying: true, command: "play" });
        if (videoRef.current && videoUrl) {
          videoRef.current.play();
          setIsPlaying(true);
        }
      }
    } catch (error) {
      toast.error("Failed to verify bingo");
    }
  };

  const submitWinnerName = () => {
    if (!winnerName.trim()) return;
    // Update the last bingo event with the winner name
    if (bingoEventsRef.current.length > 0) {
      bingoEventsRef.current[bingoEventsRef.current.length - 1].winner_name = winnerName.trim();
    }
    broadcastVideoState({ bingoWinner: true, winnerVideo: getWinnerVideoUrl(), winnerName: winnerName.trim() });
    toast.success(`Winner: ${winnerName.trim()}`);
  };

  const handleWinnerContinue = () => {
    // Continue the current round - stop winner video, resume song
    setShowWinnerVideo(false);
    setWinnerName("");
    broadcastVideoState({ bingoWinner: false, bingoVerifying: false, isPlaying: true, command: "play" });
    if (videoRef.current && videoUrl) {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleWinnerEndRound = async () => {
    // alpha.68: ending the round after a Bingo opens the same "Round over" pop-up
    // (next round with a fresh theme, or end the whole Bingo night).
    setShowWinnerVideo(false);
    setWinnerName("");
    try { videoRef.current?.pause(); } catch {}
    setIsPlaying(false);
    broadcastVideoState({ bingoWinner: false, bingoVerifying: false, isPlaying: false, command: "pause" });

    // Auto-award bingo player rewards with song-based formula
    if (bingoGameCode) {
      try {
        await axios.post(`${API}/player/award-bingo-direct`, {
          game_code: bingoGameCode,
          total_songs: songList.length || 75,
          bingo_events: bingoEventsRef.current,
        });
      } catch (e) {
        console.log('[Rewards] Bingo award failed (non-critical):', e.message);
      }
    }
    bingoEventsRef.current = [];

    try {
      await axios.post(`${API}/bingo/game/end-round`);
    } catch { /* the pop-up still opens so the host is never stuck */ }
    stopTimer();
    openRoundOver();
  };

  const endRound = async () => {
    try {
      await axios.post(`${API}/bingo/game/end-round`);
      stopTimer();
      // Stop the song on both screens, then ask the host what happens next.
      try { videoRef.current?.pause(); } catch {}
      setIsPlaying(false);
      broadcastVideoState({ isPlaying: false, command: "pause" });
      openRoundOver();
      
      // Auto-award bingo player rewards with song-based formula
      if (bingoGameCode) {
        try {
          await axios.post(`${API}/player/award-bingo-direct`, {
            game_code: bingoGameCode,
            total_songs: songList.length || 75,
            bingo_events: bingoEventsRef.current,
          });
          console.log(`[Rewards] Bingo points awarded: ${bingoEventsRef.current.length} bingos, ${songList.length} total songs`);
        } catch (e) {
          console.log('[Rewards] Bingo award failed (non-critical):', e.message);
        }
      }
      // Reset bingo events for next round
      bingoEventsRef.current = [];
    } catch (error) {
      toast.error("Failed to end round");
    }
  };

  // ----- Round over pop-up -----
  const openRoundOver = async () => {
    setRoundOverStep("choose");
    setNextSpeed(gameState?.settings?.game_type === "lightning" ? "lightning" : "regular");
    setNextTheme(gameState?.settings?.music_decade || "");
    setShowRoundOver(true);
    if (isMusicBingo) {
      try {
        const res = await axios.get(`${API}/bingo/available-themes`);
        const list = res.data.themes || [];
        setThemeChoices(list);
        // keep the current theme if it is still on, otherwise the first one available
        setNextTheme((cur) => (list.some(t => t.id === cur) ? cur : (list[0]?.id || "")));
      } catch { setThemeChoices([]); }
    }
  };

  const startNextRound = async () => {
    if (roundBusy) return;
    setRoundBusy(true);
    try {
      const body = isMusicBingo ? { music_decade: nextTheme, game_type: nextSpeed } : { game_type: nextSpeed };
      await axios.post(`${API}/bingo/game/new-round`, body);
      setCurrentSong(null);
      setNextSong(null);
      setCalledSongs([]);
      bingoEventsRef.current = [];
      preloadedUrlsRef.current = {};
      setVideoUrl(null);
      setShowWinnerVideo(false);
      broadcastVideoState({ videoUrl: null, isPlaying: false, currentSong: null, calledSongs: [], roundEnded: true, bingoWinner: false, bingoVerifying: false });
      if (isMusicBingo && nextTheme) await fetchSongList(nextTheme);   // fresh songs + stream links
      setShowRoundOver(false);
      toast.success("Next round ready");
    } catch (e) {
      toast.error("Could not start the next round");
    } finally {
      setRoundBusy(false);
    }
  };

  const finalizeNight = async () => {
    if (roundBusy) return;
    setRoundBusy(true);
    try {
      await axios.post(`${API}/bingo/game/finalize`);
      broadcastVideoState({ videoUrl: null, isPlaying: false, currentSong: null, calledSongs: [], roundEnded: true });
      setShowRoundOver(false);
      toast.success("Bingo night ended. Thanks for playing!");
      navigate("/bingo");
    } catch (e) {
      toast.error("Could not end the Bingo night");
      setRoundBusy(false);
    }
  };

  const newRound = async () => {
    try {
      await axios.post(`${API}/bingo/game/new-round`);
      setCurrentSong(null);
      setNextSong(null);
      setCalledSongs([]);
      bingoEventsRef.current = [];  // Reset bingo events for new round
      const numbers = songList.map(s => s.number);
      const shuffled = shuffleArray([...numbers]);
      setAvailableSongNumbers(shuffled);
      if (videoUrl) URL.revokeObjectURL(videoUrl);
      setVideoUrl(null);
      // Pre-pick first "up next" for the new round
      pickNextSong(shuffled);
      toast.success("New round started!");
    } catch (error) {
      toast.error("Failed to start new round");
    }
  };

  const startTimer = () => {
    const interval = gameState?.settings?.call_interval || 20;
    setTimerValue(interval);
    setTimerRunning(true);

    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);

    timerIntervalRef.current = setInterval(() => {
      setTimerValue((prev) => {
        if (prev <= 1) {
          clearInterval(timerIntervalRef.current);
          setTimerRunning(false);
          return interval;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const stopTimer = () => {
    setTimerRunning(false);
    if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
  };

  // BroadcastChannel for video mirroring to Audience View
  const channelRef = useRef(null);

  useEffect(() => {
    channelRef.current = new BroadcastChannel("music-bingo-video");
    // The AUDIENCE is the master clock: the host's silent preview follows it, never the reverse.
    channelRef.current.onmessage = (event) => {
      const data = event.data || {};
      const el = videoRef.current;
      if (data.type === "audience-playing") {
        audienceStartedRef.current = true;
        if (el && el.paused && pendingPreviewRef.current) { pendingPreviewRef.current(); }
      } else if (data.type === "audience-time" && el && !el.paused && data.videoUrl === el.getAttribute("src")) {
        if (Math.abs(el.currentTime - data.time) > 1.5) el.currentTime = data.time;   // preview catches up to the audience
      }
    };
    return () => channelRef.current?.close();
  }, []);

  // Start the requested song. Runs after the render, so the <video> element exists
  // even for the very first song. The host's own video is silent and only a
  // preview: the AUDIENCE view is the one that matters in Bingo.
  useEffect(() => {
    const pending = pendingStartRef.current;
    if (!pending) return;
    const el = videoRef.current;
    if (!el) return;                       // not on screen yet; the next render re-runs this
    pendingStartRef.current = null;
    el.src = pending.url;
    el.preload = "auto";
    el.muted = true;
    el.volume = 0;

    // 1) Tell the AUDIENCE first. It is the master: it buffers and starts the song.
    audienceStartedRef.current = false;
    broadcastVideoState({ videoUrl: pending.url, isPlaying: true, currentSong: pending.song });

    // 2) The host's silent preview starts when the audience says it is playing.
    //    If no audience window is open (or it never answers), start anyway after 4 s.
    let done = false;
    const startPreview = () => {
      if (done) return;
      done = true;
      pendingPreviewRef.current = null;
      clearTimeout(fallback);
      const go = () => el.play().then(() => setIsPlaying(true)).catch(() => setTimeout(() => videoRef.current?.play(), 500));
      if (pending.ready || el.readyState >= 3) go();
      else el.addEventListener("canplay", go, { once: true });
    };
    pendingPreviewRef.current = startPreview;
    const fallback = setTimeout(startPreview, 4000);
    setIsPlaying(true);
  }, [playRequest, videoUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  // Broadcast video state whenever it changes — includes song data so audience doesn't depend on polling
  const broadcastVideoState = useCallback((overrides = {}) => {
    if (!channelRef.current) return;
    channelRef.current.postMessage({
      type: "video-state",
      videoUrl: overrides.videoUrl !== undefined ? overrides.videoUrl : videoUrl,
      isPlaying: overrides.isPlaying !== undefined ? overrides.isPlaying : isPlaying,
      currentTime: videoRef.current?.currentTime || 0,
      volume: overrides.volume !== undefined ? overrides.volume : volume,
      showSongInfo: overrides.showSongInfo !== undefined ? overrides.showSongInfo : showSongInfoAudience,
      currentSong: overrides.currentSong !== undefined ? overrides.currentSong : currentSong,
      calledSongs: overrides.calledSongs !== undefined ? overrides.calledSongs : calledSongs,
      ...(overrides.command ? { command: overrides.command } : {}),
      ...(overrides.bingoVerifying !== undefined ? { bingoVerifying: overrides.bingoVerifying } : {}),
      ...(overrides.bingoWinner !== undefined ? { bingoWinner: overrides.bingoWinner } : {}),
      ...(overrides.winnerVideo !== undefined ? { winnerVideo: overrides.winnerVideo } : {}),
      ...(overrides.winnerName !== undefined ? { winnerName: overrides.winnerName } : {}),
      ...(overrides.roundEnded !== undefined ? { roundEnded: overrides.roundEnded } : {}),
    });
  }, [videoUrl, isPlaying, volume, showSongInfoAudience, currentSong, calledSongs]);

  // Periodically sync playback position
  useEffect(() => {
    if (!isMusicBingo || !videoUrl || !isPlaying) return;
    const syncInterval = setInterval(() => broadcastVideoState(), 2000);
    return () => clearInterval(syncInterval);
  }, [isMusicBingo, videoUrl, isPlaying, broadcastVideoState]);

  // Open Audience View - this window will mirror the video
  const openAudienceView = async () => {
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      audienceWindowRef.current.focus();
      return;
    }
    // Desktop app: native window (no pop-ups). Browser: window.open.
    if (isTauri()) {
      try {
        const { win } = await openNativeAudience({
          label: 'bingo-audience',
          path: '/bingo/audience',
          title: 'BIG Hat - Bingo Audience',
          onClosed: () => { audienceWindowRef.current = null; },
        });
        audienceWindowRef.current = {
          closed: false,
          focus: () => { try { win.setFocus(); } catch (_e) { /* best-effort */ } },
          close: () => { try { win.close(); } catch (_e) { /* gone */ } },
        };
      } catch (err) {
        console.error('[bingo audience] native window failed:', err);
        alert(`Audience view failed to open: ${err?.message || err}`);
      }
      return;
    }
    const audienceUrl = `${window.location.origin}/bingo/audience`;
    audienceWindowRef.current = window.open(
      audienceUrl,
      "MusicBingoAudience",
      "width=1920,height=1080,menubar=no,toolbar=no,location=no,status=no"
    );
  };

  const playCallSound = () => {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      oscillator.frequency.value = 880;
      oscillator.type = 'sine';
      gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.3);
    } catch (e) {}
  };

  const playBallsRolling = () => {
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      for (let i = 0; i < 5; i++) {
        setTimeout(() => {
          const oscillator = audioContext.createOscillator();
          const gainNode = audioContext.createGain();
          oscillator.connect(gainNode);
          gainNode.connect(audioContext.destination);
          oscillator.frequency.value = 200 + Math.random() * 300;
          oscillator.type = 'sine';
          gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
          gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
          oscillator.start(audioContext.currentTime);
          oscillator.stop(audioContext.currentTime + 0.2);
        }, i * 100);
      }
    } catch (e) {}
  };

  const triggerCelebration = () => {
    const duration = 3000;
    const end = Date.now() + duration;
    const frame = () => {
      confetti({ particleCount: 7, angle: 60, spread: 55, origin: { x: 0 }, colors: THEME_CONFETTI[bingoTheme] });
      confetti({ particleCount: 7, angle: 120, spread: 55, origin: { x: 1 }, colors: THEME_CONFETTI[bingoTheme] });
      if (Date.now() < end) requestAnimationFrame(frame);
    };
    frame();
  };

  const VolumeIcon = volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;

  if (isLoading) {
    return (
      <div className="bingo-theme min-h-screen flex items-center justify-center" data-theme={bingoTheme} style={{backgroundColor:"#0A0A0A",color:"white"}}>
        <div className="loading-balls">
          {[...Array(5)].map((_, i) => <div key={i} className="loading-ball" />)}
        </div>
      </div>
    );
  }

  // =====================================================
  // MUSIC BINGO LAYOUT - Video on LEFT, Controls on RIGHT (Original layout)
  // =====================================================
  // Winner screen (video + name box + Continue / End Round). Used by BOTH layouts:
  // it used to exist only in the Traditional one, so a Music game never showed it.
  const winnerOverlay = showWinnerVideo ? (
        <div className="fixed inset-0 z-[200] flex flex-col items-center justify-center" style={{ backgroundColor: '#000' }} data-testid="winner-overlay">
          <video
            ref={winnerVideoRef}
            src={getWinnerVideoUrl()}
            autoPlay
            muted
            loop
            playsInline
            className="w-full h-full object-contain"
            style={{ maxHeight: '70vh' }}
          />
          {/* Winner name input + submit */}
          <div className="absolute bottom-28 flex items-center gap-3 px-4 w-full max-w-md">
            <Input
              placeholder="Enter winner's name..."
              value={winnerName}
              onChange={(e) => setWinnerName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitWinnerName()}
              className="bg-zinc-800/90 border-yellow-500/50 text-center text-lg text-white placeholder:text-zinc-500 flex-1"
              data-testid="winner-name-input"
            />
            <button onClick={submitWinnerName} className="px-6 py-3 rounded-xl text-base font-bold" style={{ backgroundColor: '#fbdd68', color: '#000' }}>
              Submit
            </button>
          </div>
          {/* Continue / End Round buttons */}
          <div className="absolute bottom-8 flex gap-4">
            <button onClick={handleWinnerContinue} className="px-8 py-4 rounded-xl text-lg font-bold transition-all hover:scale-105" style={{ backgroundColor: '#22c55e', color: '#000' }} data-testid="winner-continue-btn">
              Continue Round
            </button>
            <button onClick={handleWinnerEndRound} className="px-8 py-4 rounded-xl text-lg font-bold transition-all hover:scale-105" style={{ backgroundColor: '#ef4444', color: '#fff' }} data-testid="winner-end-btn">
              End Round
            </button>
          </div>
        </div>
      ) : null;

  if (isMusicBingo) {
    return (
      <div className="bingo-theme min-h-screen p-4" data-theme={bingoTheme} style={{backgroundColor:"#0A0A0A",color:"white"}} data-testid="host-dashboard">
        {/* Header */}
        <header className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="icon" onClick={() => navigate("/bingo")} className="text-zinc-400 hover:text-white hover:bg-zinc-800" data-testid="back-to-lobby-btn">
              <ArrowLeft size={24} />
            </Button>
            <h1 className="font-display text-2xl text-white">Music Bingo</h1>
            <span className="px-3 py-1 rounded-full text-sm bg-fuchsia-500/20 text-fuchsia-400">
              <Disc3 size={14} className="inline mr-1" />{gameState?.settings?.music_decade || "Music"}
            </span>
            <span className={`px-2 py-1 rounded text-xs ${songListSource === "local-folder" ? "bg-green-500/20 text-green-400" : "bg-yellow-500/20 text-yellow-400"}`}>
              {songListSource === "local-folder" ? "Bingo folder" : "Sample Data"}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-zinc-400 text-sm">Round {gameState?.round_number || 1}</p>
              <p className="text-fuchsia-400 font-semibold">{gameState?.settings?.round_type?.toUpperCase() || "TRADITIONAL"}</p>
            </div>
            <Button variant="outline" onClick={openAudienceView} className="gap-2" data-testid="audience-view-btn">
              <Users size={20} />
              Audience View
            </Button>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* LEFT COLUMN - Video Player (Large - This is what Audience sees) */}
          <div className="lg:col-span-2 space-y-4">
            <Card className="card-dark overflow-hidden">
              <div
                className={`video-frame aspect-video relative ${isDragging ? "border-cyan-500" : ""}`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                {videoUrl ? (
                  <>
                    <video
                      ref={videoRef}
                      src={videoUrl}
                      className="w-full h-full object-contain bg-black"
                      onPlay={() => setIsPlaying(true)}
                      onPause={() => setIsPlaying(false)}
                      onError={() => toast.error("Error playing video")}
                    />
                    <div className="video-controls flex items-center gap-4">
                      <Button size="icon" variant="ghost" onClick={togglePlay} className="text-white hover:bg-white/20">
                        {isPlaying ? <Pause size={24} /> : <Play size={24} className="fill-white" />}
                      </Button>
                      <div className="flex items-center gap-2 flex-1 max-w-xs">
                        <VolumeIcon size={20} className="text-white" />
                        <Slider value={[volume * 100]} onValueChange={handleVolumeChange} max={100} step={1} className="flex-1" />
                      </div>
                      <Button size="icon" variant="ghost" onClick={() => videoRef.current?.requestFullscreen()} className="text-white hover:bg-white/20">
                        <Maximize size={20} />
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center" data-testid="video-idle-panel">
                    <Video size={64} className="text-zinc-600 mb-4" />
                    {Object.keys(videoFiles).length > 0 ? (
                      <>
                        <p className="text-zinc-300 text-lg mb-2" data-testid="videos-ready-text">
                          {Object.keys(videoFiles).length} songs ready
                        </p>
                        <p className="text-zinc-600 text-sm">
                          {gameState?.is_active ? "Press Next Song to start." : "Press Start Round, then Next Song."}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-yellow-400 text-lg mb-2" data-testid="videos-missing-text">No videos found for this theme</p>
                        <p className="text-zinc-500 text-sm mb-4">Check the theme in Bingo Setup.</p>
                        <Button className="btn-primary" onClick={() => navigate("/bingo/setup")} data-testid="host-open-setup">Open Bingo Setup</Button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* Song List */}
            <Card className="card-dark">
              <CardHeader className="py-3">
                <CardTitle className="text-lg flex items-center justify-between">
                  <span>Song List ({gameState?.settings?.music_decade})</span>
                  <span className="text-zinc-400 text-sm font-normal">{calledSongs.length} / {songList.length} songs played</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 md:grid-cols-5 gap-2 max-h-[150px] overflow-y-auto">
                  {songList.map((song) => {
                    const isCalled = calledSongs.some(s => s.number === song.number);
                    return (
                      <div
                        key={song.number}
                        className={`p-2 rounded-lg text-xs ${isCalled ? "bg-fuchsia-500/30 border border-fuchsia-500" : "bg-zinc-800/50 border border-zinc-700"}`}
                      >
                        <span className="font-mono text-fuchsia-400">#{song.number}</span>
                        <p className="truncate text-white mt-1">{song.title}</p>
                        <p className="truncate text-zinc-500">{song.artist}</p>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* RIGHT COLUMN - Controls */}
          <div className="space-y-4">
            {/* Up Next — shows the next song so host can prepare */}
            <Card className="card-dark neon-border">
              <CardContent className="py-6">
                <div className="text-center">
                  <p className="text-cyan-400 text-sm font-semibold mb-2">Up Next</p>
                  {nextSong ? (
                    <motion.div key={nextSong.number} initial={{ scale: 0 }} animate={{ scale: 1 }}>
                      <MusicBingoBall number={nextSong.number} title={nextSong.title} artist={nextSong.artist} size="large" animate />
                    </motion.div>
                  ) : availableSongNumbers.length === 0 && calledSongs.length > 0 ? (
                    <div className="h-[160px] flex items-center justify-center text-zinc-600">
                      <p>All songs played!</p>
                    </div>
                  ) : (
                    <div className="h-[160px] flex items-center justify-center text-zinc-600">
                      <p>Waiting for round to start</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Timer */}
            <Card className="card-dark">
              <CardContent className="py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Timer size={24} className="text-cyan-400" />
                    <span className="text-zinc-400">Timer</span>
                  </div>
                  <span className={`timer-display ${timerValue <= 5 ? "danger" : timerValue <= 10 ? "warning" : ""}`}>
                    {timerValue}s
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Recent Songs */}
            <Card className="card-dark">
              <CardHeader className="py-3">
                <CardTitle className="text-sm text-zinc-400">Recent Songs</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {calledSongs.slice(-5).reverse().map((song) => (
                    <div key={song.number} className="text-center">
                      <div className="w-10 h-10 rounded-full bg-fuchsia-500 flex items-center justify-center text-white font-bold text-sm">
                        {song.number}
                      </div>
                      <p className="text-xs text-zinc-500 mt-1 truncate w-12">{song.title.split(' ')[0]}</p>
                    </div>
                  ))}
                  {calledSongs.length === 0 && <p className="text-zinc-600 text-sm">Nothing played yet</p>}
                </div>
              </CardContent>
            </Card>

            {/* Controls */}
            <Card className="card-dark">
              <CardHeader className="py-3">
                <CardTitle className="text-lg">Controls</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Audience Song Info Toggle */}
                <div
                  className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/60 border border-zinc-700 cursor-pointer select-none"
                  onClick={() => {
                    const next = !showSongInfoAudience;
                    setShowSongInfoAudience(next);
                    broadcastVideoState({ showSongInfo: next });
                  }}
                  data-testid="toggle-song-info-audience"
                >
                  <div className="flex items-center gap-2">
                    <Music size={16} className="text-fuchsia-400" />
                    <span className="text-sm text-zinc-300">Song Info on TV</span>
                  </div>
                  <div className={`w-10 h-5 rounded-full relative transition-colors duration-200 ${showSongInfoAudience ? "bg-fuchsia-500" : "bg-zinc-600"}`}>
                    <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200 ${showSongInfoAudience ? "translate-x-5" : "translate-x-0.5"}`} />
                  </div>
                </div>

                {!gameState?.is_active ? (
                  <Button className="w-full btn-success control-btn" onClick={startGame} data-testid="start-game-btn">
                    <Play size={24} className="mr-2 fill-white" />
                    Start Round
                  </Button>
                ) : (
                  <>
                    <Button
                      className="w-full btn-primary control-btn animate-pulse-glow"
                      onClick={callNextSong}
                      disabled={gameState?.is_paused || Object.keys(videoFiles).length === 0 || songCooldown}
                      data-testid="next-song-btn"
                    >
                      <Music size={24} className="mr-2" />
                      {songCooldown ? 'Loading...' : 'Next Song'}
                    </Button>

                    {!gameState?.is_paused ? (
                      <Button variant="outline" className="w-full control-btn" onClick={pauseGame} data-testid="pause-btn">
                        <Pause size={24} className="mr-2" />
                        Pause
                      </Button>
                    ) : (
                      <Button variant="outline" className="w-full control-btn" onClick={resumeGame} data-testid="resume-btn">
                        <Play size={24} className="mr-2" />
                        Resume
                      </Button>
                    )}
                  </>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <Button className="btn-gold control-btn" onClick={claimBingo} disabled={!gameState?.is_active} data-testid="bingo-btn">
                    <Trophy size={20} className="mr-1" />
                    BINGO!
                  </Button>
                  <Button variant="outline" className="control-btn" onClick={newRound} data-testid="new-round-btn">
                    <RotateCcw size={20} className="mr-1" />
                    New Round
                  </Button>
                </div>

                <Button variant="destructive" className="w-full control-btn" onClick={endRound} disabled={!gameState?.is_active} data-testid="end-round-btn">
                  <Square size={20} className="mr-2 fill-white" />
                  End Round
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Bingo Verification Dialog */}
              <Dialog open={showRoundOver} onOpenChange={(o) => { if (!roundBusy) setShowRoundOver(o); }}>
        <DialogContent className="bg-zinc-900 border-zinc-700" data-testid="round-over-dialog">
          {roundOverStep === "choose" ? (
            <>
              <DialogHeader>
                <DialogTitle className="font-display text-3xl text-center text-yellow-400" data-testid="round-over-title">
                  Round {gameState?.round_number || 1} complete
                </DialogTitle>
              </DialogHeader>
              <div className="py-4 space-y-5">
                <p className="text-center text-zinc-400">Keep the night going or wrap it up.</p>
                {isMusicBingo && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-2">Theme for round {(gameState?.round_number || 1) + 1}</p>
                    {themeChoices.length === 0 ? (
                      <p className="text-yellow-400 text-sm" data-testid="round-over-no-themes">No themes are switched on. Open Bingo Setup to add one.</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2" data-testid="round-over-themes">
                        {themeChoices.map(t => (
                          <button key={t.id} type="button" onClick={() => setNextTheme(t.id)} data-testid={`next-theme-${t.id}`}
                            className={`px-3 py-3 rounded-lg border text-left transition-colors ${nextTheme === t.id ? "border-fuchsia-500 bg-fuchsia-500/20 text-white" : "border-zinc-700 text-zinc-300 hover:border-fuchsia-500/50"}`}>
                            <span className="font-semibold">{t.name}</span>
                            <span className="block text-xs text-zinc-500">{t.videos} songs</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div>
                  <p className="text-sm text-zinc-500 mb-2">Game speed</p>
                  <div className="grid grid-cols-2 gap-2">
                    {["regular", "lightning"].map(v => (
                      <button key={v} type="button" onClick={() => setNextSpeed(v)} data-testid={`next-speed-${v}`}
                        className={`px-3 py-2 rounded-lg border capitalize transition-colors ${nextSpeed === v ? "border-fuchsia-500 bg-fuchsia-500/20 text-white" : "border-zinc-700 text-zinc-300"}`}>{v}</button>
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter className="flex flex-col gap-3 sm:flex-col">
                <Button className="w-full btn-success" onClick={startNextRound} disabled={roundBusy || (isMusicBingo && !nextTheme)} data-testid="start-next-round-btn">
                  Start Round {(gameState?.round_number || 1) + 1}
                </Button>
                <Button variant="outline" className="w-full" onClick={() => setRoundOverStep("confirm-end")} disabled={roundBusy} data-testid="end-night-btn">
                  End Bingo Night
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="font-display text-3xl text-center text-red-400">End the Bingo night?</DialogTitle>
              </DialogHeader>
              <p className="py-4 text-center text-zinc-400">This finishes the whole night after {gameState?.round_number || 1} round{(gameState?.round_number || 1) === 1 ? "" : "s"}. It can't be undone.</p>
              <DialogFooter className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => setRoundOverStep("choose")} disabled={roundBusy} data-testid="end-night-cancel-btn">Go back</Button>
                <Button variant="destructive" className="flex-1" onClick={finalizeNight} disabled={roundBusy} data-testid="end-night-confirm-btn">Yes, end the night</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={showBingoDialog} onOpenChange={setShowBingoDialog}>
          <DialogContent className="bg-zinc-900 border-zinc-700">
            <DialogHeader>
              <DialogTitle className="font-display text-3xl text-center text-yellow-400">BINGO Claimed!</DialogTitle>
            </DialogHeader>
            <div className="py-6 space-y-4">
              <p className="text-center text-zinc-400">Verify the player's bingo card</p>
            </div>
            <DialogFooter className="flex gap-4">
              <Button variant="destructive" className="flex-1" onClick={() => verifyBingo(false)}>
                <XCircle size={20} className="mr-2" />
                False Bingo
              </Button>
              <Button className="flex-1 btn-success" onClick={() => verifyBingo(true)}>
                <CheckCircle size={20} className="mr-2" />
                Confirm Bingo
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        {winnerOverlay}
      </div>
    );
  }

  // =====================================================
  // TRADITIONAL BINGO LAYOUT
  // =====================================================
  return (
    <div className="bingo-theme min-h-screen p-4" data-theme={bingoTheme} style={{backgroundColor:"#0A0A0A",color:"white"}} data-testid="host-dashboard">
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/bingo")} className="text-zinc-400 hover:text-white hover:bg-zinc-800" data-testid="back-to-lobby-btn">
            <ArrowLeft size={24} />
          </Button>
          <h1 className="font-display text-2xl text-white">Traditional Bingo</h1>
          <span className="px-3 py-1 rounded-full text-sm bg-cyan-500/20 text-cyan-400">Numbers</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-zinc-400 text-sm">Round {gameState?.round_number || 1}</p>
            <p className="text-fuchsia-400 font-semibold">{gameState?.settings?.round_type?.toUpperCase() || "TRADITIONAL"}</p>
          </div>
          <Button variant="outline" onClick={openAudienceView} className="gap-2" data-testid="audience-view-btn">
            <Users size={20} />
            Audience View
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card className="card-dark overflow-hidden">
            <div className={`video-frame aspect-video relative ${isDragging ? "border-cyan-500" : ""}`} onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}>
              {videoUrl ? (
                <>
                  <video ref={videoRef} src={videoUrl} preload="auto" muted className="w-full h-full object-contain bg-black" onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} />
                  <div className="video-controls flex items-center gap-4">
                    <Button size="icon" variant="ghost" onClick={togglePlay} className="text-white hover:bg-white/20">
                      {isPlaying ? <Pause size={24} /> : <Play size={24} className="fill-white" />}
                    </Button>
                    <div className="flex items-center gap-2 flex-1 max-w-xs">
                      <VolumeIcon size={20} className="text-white" />
                      <Slider value={[volume * 100]} onValueChange={handleVolumeChange} max={100} step={1} className="flex-1" />
                    </div>
                    <Button size="icon" variant="ghost" onClick={() => videoRef.current?.requestFullscreen()} className="text-white hover:bg-white/20">
                      <Maximize size={20} />
                    </Button>
                  </div>
                </>
              ) : (
                <div className={`drop-zone h-full flex flex-col items-center justify-center ${isDragging ? "dragging" : ""}`}>
                  <Video size={64} className="text-zinc-600 mb-4" />
                  <p className="text-zinc-400 text-lg mb-2">Drag & drop a video file</p>
                  <p className="text-zinc-600 text-sm mb-4">Background music for your bingo game</p>
                  <label className="cursor-pointer">
                    <input type="file" accept="video/*,.mp4,.webm,.mov" onChange={handleFileSelect} className="hidden" />
                    <span className="btn-primary px-6 py-3 rounded-lg flex items-center gap-2">
                      <Upload size={20} />
                      Browse Files
                    </span>
                  </label>
                </div>
              )}
            </div>
          </Card>

          <Card className="card-dark">
            <CardHeader className="py-3">
              <CardTitle className="text-lg flex items-center justify-between">
                <span>Bingo Board</span>
                <span className="text-zinc-400 text-sm font-normal">{gameState?.called_numbers?.length || 0} / 75 called</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <BingoBoard calledNumbers={gameState?.called_numbers || []} size="small" />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="card-dark neon-border">
            <CardContent className="py-6">
              <div className="text-center">
                <p className="text-zinc-400 text-sm mb-2">Current Number</p>
                {gameState?.current_number ? (
                  <motion.div key={gameState.current_number} initial={{ scale: 0 }} animate={{ scale: 1 }} className="flex justify-center">
                    <BingoBall number={gameState.current_number} letter={gameState.current_letter} size="large" animate />
                  </motion.div>
                ) : (
                  <div className="h-[160px] flex items-center justify-center text-zinc-600">
                    <p>No number called yet</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="card-dark">
            <CardContent className="py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Timer size={24} className="text-cyan-400" />
                  <span className="text-zinc-400">Timer</span>
                </div>
                <span className={`timer-display ${timerValue <= 5 ? "danger" : timerValue <= 10 ? "warning" : ""}`}>{timerValue}s</span>
              </div>
            </CardContent>
          </Card>

          <Card className="card-dark">
            <CardHeader className="py-3">
              <CardTitle className="text-sm text-zinc-400">Recently Called</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="recent-numbers">
                {(gameState?.called_numbers || []).slice(-5).reverse().map((num) => (
                  <BingoBall key={num} number={num} size="small" />
                ))}
                {(!gameState?.called_numbers || gameState.called_numbers.length === 0) && <p className="text-zinc-600 text-sm">No numbers called</p>}
              </div>
            </CardContent>
          </Card>

          <Card className="card-dark">
            <CardHeader className="py-3">
              <CardTitle className="text-lg">Controls</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {!gameState?.is_active ? (
                <Button className="w-full btn-success control-btn" onClick={startGame} data-testid="start-game-btn">
                  <Play size={24} className="mr-2 fill-white" />
                  Start Round
                </Button>
              ) : (
                <>
                  <Button className="w-full btn-primary control-btn animate-pulse-glow" onClick={callNumber} disabled={gameState?.is_paused} data-testid="call-number-btn">
                    <SkipForward size={24} className="mr-2" />
                    Call Number
                  </Button>
                  {!gameState?.is_paused ? (
                    <Button variant="outline" className="w-full control-btn" onClick={pauseGame} data-testid="pause-btn">
                      <Pause size={24} className="mr-2" />
                      Pause
                    </Button>
                  ) : (
                    <Button variant="outline" className="w-full control-btn" onClick={resumeGame} data-testid="resume-btn">
                      <Play size={24} className="mr-2" />
                      Resume
                    </Button>
                  )}
                </>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Button className="btn-gold control-btn" onClick={claimBingo} disabled={!gameState?.is_active} data-testid="bingo-btn">
                  <Trophy size={20} className="mr-1" />
                  BINGO!
                </Button>
                <Button variant="outline" className="control-btn" onClick={newRound} data-testid="new-round-btn">
                  <RotateCcw size={20} className="mr-1" />
                  New Round
                </Button>
              </div>
              <Button variant="destructive" className="w-full control-btn" onClick={endRound} disabled={!gameState?.is_active} data-testid="end-round-btn">
                <Square size={20} className="mr-2 fill-white" />
                End Round
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

            <Dialog open={showRoundOver} onOpenChange={(o) => { if (!roundBusy) setShowRoundOver(o); }}>
        <DialogContent className="bg-zinc-900 border-zinc-700" data-testid="round-over-dialog">
          {roundOverStep === "choose" ? (
            <>
              <DialogHeader>
                <DialogTitle className="font-display text-3xl text-center text-yellow-400" data-testid="round-over-title">
                  Round {gameState?.round_number || 1} complete
                </DialogTitle>
              </DialogHeader>
              <div className="py-4 space-y-5">
                <p className="text-center text-zinc-400">Keep the night going or wrap it up.</p>
                {isMusicBingo && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-2">Theme for round {(gameState?.round_number || 1) + 1}</p>
                    {themeChoices.length === 0 ? (
                      <p className="text-yellow-400 text-sm" data-testid="round-over-no-themes">No themes are switched on. Open Bingo Setup to add one.</p>
                    ) : (
                      <div className="grid grid-cols-2 gap-2" data-testid="round-over-themes">
                        {themeChoices.map(t => (
                          <button key={t.id} type="button" onClick={() => setNextTheme(t.id)} data-testid={`next-theme-${t.id}`}
                            className={`px-3 py-3 rounded-lg border text-left transition-colors ${nextTheme === t.id ? "border-fuchsia-500 bg-fuchsia-500/20 text-white" : "border-zinc-700 text-zinc-300 hover:border-fuchsia-500/50"}`}>
                            <span className="font-semibold">{t.name}</span>
                            <span className="block text-xs text-zinc-500">{t.videos} songs</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div>
                  <p className="text-sm text-zinc-500 mb-2">Game speed</p>
                  <div className="grid grid-cols-2 gap-2">
                    {["regular", "lightning"].map(v => (
                      <button key={v} type="button" onClick={() => setNextSpeed(v)} data-testid={`next-speed-${v}`}
                        className={`px-3 py-2 rounded-lg border capitalize transition-colors ${nextSpeed === v ? "border-fuchsia-500 bg-fuchsia-500/20 text-white" : "border-zinc-700 text-zinc-300"}`}>{v}</button>
                    ))}
                  </div>
                </div>
              </div>
              <DialogFooter className="flex flex-col gap-3 sm:flex-col">
                <Button className="w-full btn-success" onClick={startNextRound} disabled={roundBusy || (isMusicBingo && !nextTheme)} data-testid="start-next-round-btn">
                  Start Round {(gameState?.round_number || 1) + 1}
                </Button>
                <Button variant="outline" className="w-full" onClick={() => setRoundOverStep("confirm-end")} disabled={roundBusy} data-testid="end-night-btn">
                  End Bingo Night
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="font-display text-3xl text-center text-red-400">End the Bingo night?</DialogTitle>
              </DialogHeader>
              <p className="py-4 text-center text-zinc-400">This finishes the whole night after {gameState?.round_number || 1} round{(gameState?.round_number || 1) === 1 ? "" : "s"}. It can't be undone.</p>
              <DialogFooter className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => setRoundOverStep("choose")} disabled={roundBusy} data-testid="end-night-cancel-btn">Go back</Button>
                <Button variant="destructive" className="flex-1" onClick={finalizeNight} disabled={roundBusy} data-testid="end-night-confirm-btn">Yes, end the night</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog open={showBingoDialog} onOpenChange={setShowBingoDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-700">
          <DialogHeader>
            <DialogTitle className="font-display text-3xl text-center text-yellow-400">BINGO Claimed!</DialogTitle>
          </DialogHeader>
          <div className="py-6 space-y-4">
            <p className="text-center text-zinc-400">Verify the player's bingo card</p>
          </div>
          <DialogFooter className="flex gap-4">
            <Button variant="destructive" className="flex-1" onClick={() => verifyBingo(false)}>
              <XCircle size={20} className="mr-2" />
              False Bingo
            </Button>
            <Button className="flex-1 btn-success" onClick={() => verifyBingo(true)}>
              <CheckCircle size={20} className="mr-2" />
              Confirm Bingo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {winnerOverlay}
      {/* Rewards Splash Overlay — shown at game start */}
      {showRewardsSplash && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 cursor-pointer"
          onClick={() => { setShowRewardsSplash(false); clearTimeout(rewardsSplashTimerRef.current); }}
          data-testid="rewards-splash">
          <div className="relative" style={{ width: '80vw', maxWidth: 800, aspectRatio: '16/9' }}>
            <img src="/rewards-promo.jpg" alt="BIG Hat Rewards" className="w-full h-full object-contain rounded-2xl" />
            {/* Dynamic QR overlay */}
            <div className="absolute flex items-center justify-center" style={{ left: '37%', top: '20%', width: '26%', height: '50%' }}>
              <div className="bg-white rounded-2xl p-3 shadow-2xl">
                <QRCodeSVG value={`${window.location.origin}/player?code=${bingoGameCode}`} size={180} />
              </div>
            </div>
            {/* Game code */}
            <div className="absolute text-center" style={{ left: '30%', bottom: '12%', width: '40%' }}>
              <p className="text-4xl font-black tracking-wider" style={{ color: '#fbdd68', fontFamily: "'Space Grotesk', sans-serif", textShadow: '0 2px 8px rgba(0,0,0,0.9)' }}>
                {bingoGameCode}
              </p>
            </div>
          </div>
          <p className="absolute bottom-8 text-zinc-500 text-sm">Click anywhere to dismiss</p>
        </div>
      )}
    </div>
  );
}
