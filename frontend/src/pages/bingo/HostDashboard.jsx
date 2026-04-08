import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
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

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function HostDashboard() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const audienceWindowRef = useRef(null);
  const wsRef = useRef(null);

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
  const [volume, setVolume] = useState(0.75);
  const [isDragging, setIsDragging] = useState(false);

  // Timer State
  const [timerRunning, setTimerRunning] = useState(false);
  const [timerValue, setTimerValue] = useState(20);
  const timerIntervalRef = useRef(null);

  // Bingo Verification Dialog
  const [showBingoDialog, setShowBingoDialog] = useState(false);
  const [winnerName, setWinnerName] = useState("");

  // Audience song info toggle
  const [showSongInfoAudience, setShowSongInfoAudience] = useState(true);

  const isMusicBingo = gameState?.settings?.bingo_type === "music";

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
        setSongList(response.data.songs);
        setSongListSource(response.data.source || "sample");
        const numbers = response.data.songs.map(s => s.number);
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
      // Pre-buffer the video file if available
      const file = videoFiles[nextNum];
      if (file) {
        const tempUrl = URL.createObjectURL(file);
        const tempVid = document.createElement("video");
        tempVid.preload = "auto";
        tempVid.src = tempUrl;
        tempVid.addEventListener("canplaythrough", () => {
          URL.revokeObjectURL(tempUrl);
        }, { once: true });
        setTimeout(() => URL.revokeObjectURL(tempUrl), 15000);
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
      broadcastVideoState({ isPlaying: newPlaying });
    }
  };

  const handleVolumeChange = (value) => {
    const vol = value[0] / 100;
    setVolume(vol);
    if (videoRef.current) {
      videoRef.current.volume = vol;
    }
  };

  // Game controls
  const startGame = async () => {
    try {
      await axios.post(`${API}/bingo/game/start`);
      toast.success("Game started!");
      playBallsRolling();
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
    if (availableSongNumbers.length === 0) {
      toast.error("All songs have been called!");
      return;
    }

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
        const url = URL.createObjectURL(videoFile);
        setVideoUrl(url);
        broadcastVideoState({ videoUrl: url, isPlaying: true, currentSong: song });
        setTimeout(() => {
          if (videoRef.current) {
            videoRef.current.play();
            setIsPlaying(true);
            broadcastVideoState({ videoUrl: url, isPlaying: true, currentSong: song });
          }
        }, 100);
      } else {
        // No video file for this song — still broadcast the song info
        broadcastVideoState({ currentSong: song });
      }

      // Pre-select the NEXT song so the host can see what's coming
      pickNextSong(newAvailable);

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
        broadcastVideoState({ isPlaying: false });
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
        broadcastVideoState({ isPlaying: true });
      }
    } catch (error) {
      toast.error("Failed to resume game");
    }
  };

  const claimBingo = async () => {
    try {
      await axios.post(`${API}/bingo/game/bingo`);
      stopTimer();
      if (videoRef.current) {
        videoRef.current.pause();
        setIsPlaying(false);
      }
    } catch (error) {
      toast.error("Failed to claim bingo");
    }
  };

  const verifyBingo = async (confirmed) => {
    try {
      await axios.post(`${API}/bingo/game/verify-bingo`, {
        winner_name: winnerName || "Winner",
        confirmed
      });
      setShowBingoDialog(false);
      setWinnerName("");
      
      if (confirmed) {
        toast.success(`BINGO confirmed for ${winnerName || "Winner"}!`);
      } else {
        toast.info("Bingo rejected - game continues");
        if (videoRef.current && videoUrl) {
          videoRef.current.play();
          setIsPlaying(true);
        }
      }
    } catch (error) {
      toast.error("Failed to verify bingo");
    }
  };

  const endRound = async () => {
    try {
      await axios.post(`${API}/bingo/game/end-round`);
      stopTimer();
      toast.info("Round ended");
    } catch (error) {
      toast.error("Failed to end round");
    }
  };

  const newRound = async () => {
    try {
      await axios.post(`${API}/bingo/game/new-round`);
      setCurrentSong(null);
      setNextSong(null);
      setCalledSongs([]);
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
    return () => channelRef.current?.close();
  }, []);

  // Broadcast video state whenever it changes — includes song data so audience doesn't depend on polling
  const broadcastVideoState = useCallback((overrides = {}) => {
    if (!channelRef.current) return;
    channelRef.current.postMessage({
      type: "video-state",
      videoUrl: overrides.videoUrl !== undefined ? overrides.videoUrl : videoUrl,
      isPlaying: overrides.isPlaying !== undefined ? overrides.isPlaying : isPlaying,
      currentTime: videoRef.current?.currentTime || 0,
      volume: volume,
      showSongInfo: overrides.showSongInfo !== undefined ? overrides.showSongInfo : showSongInfoAudience,
      currentSong: overrides.currentSong !== undefined ? overrides.currentSong : currentSong,
    });
  }, [videoUrl, isPlaying, volume, showSongInfoAudience, currentSong]);

  // Periodically sync playback position
  useEffect(() => {
    if (!isMusicBingo || !videoUrl || !isPlaying) return;
    const syncInterval = setInterval(() => broadcastVideoState(), 2000);
    return () => clearInterval(syncInterval);
  }, [isMusicBingo, videoUrl, isPlaying, broadcastVideoState]);

  // Open Audience View - this window will mirror the video
  const openAudienceView = () => {
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      audienceWindowRef.current.focus();
      return;
    }
    const audienceUrl = `${window.location.origin}/audience`;
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
      confetti({ particleCount: 7, angle: 60, spread: 55, origin: { x: 0 }, colors: ["#D946EF", "#06B6D4", "#EAB308", "#22C55E"] });
      confetti({ particleCount: 7, angle: 120, spread: 55, origin: { x: 1 }, colors: ["#D946EF", "#06B6D4", "#EAB308", "#22C55E"] });
      if (Date.now() < end) requestAnimationFrame(frame);
    };
    frame();
  };

  const VolumeIcon = volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="loading-balls">
          {[...Array(5)].map((_, i) => <div key={i} className="loading-ball" />)}
        </div>
      </div>
    );
  }

  // =====================================================
  // MUSIC BINGO LAYOUT - Video on LEFT, Controls on RIGHT (Original layout)
  // =====================================================
  if (isMusicBingo) {
    return (
      <div className="min-h-screen bg-background p-4" data-testid="host-dashboard">
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
            <span className={`px-2 py-1 rounded text-xs ${songListSource === "sharepoint" ? "bg-green-500/20 text-green-400" : "bg-yellow-500/20 text-yellow-400"}`}>
              {songListSource === "sharepoint" ? "SharePoint" : "Sample Data"}
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
                  <div className={`drop-zone h-full flex flex-col items-center justify-center ${isDragging ? "dragging" : ""}`}>
                    <FolderOpen size={64} className="text-zinc-600 mb-4" />
                    <p className="text-zinc-400 text-lg mb-2">
                      {Object.keys(videoFiles).length > 0 ? `${Object.keys(videoFiles).length} videos loaded` : "Load your video files"}
                    </p>
                    <p className="text-zinc-600 text-sm mb-4">Files should start with numbers: 01_Song.mp4, 02_Song.mp4...</p>
                    <div className="flex gap-3">
                      <label className="cursor-pointer">
                        <input type="file" accept="video/*,.mp4,.webm,.mov" multiple webkitdirectory="" directory="" onChange={handleFolderSelect} className="hidden" />
                        <span className="btn-primary px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                          <FolderOpen size={18} />
                          Select Folder
                        </span>
                      </label>
                      <label className="cursor-pointer">
                        <input type="file" accept="video/*,.mp4,.webm,.mov" multiple onChange={handleMultiFileSelect} className="hidden" />
                        <span className="btn-accent px-4 py-2 rounded-lg flex items-center gap-2 text-sm">
                          <Video size={18} />
                          Select Files
                        </span>
                      </label>
                    </div>
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

                {Object.keys(videoFiles).length === 0 && (
                  <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 mb-2">
                    <p className="text-yellow-400 text-sm flex items-center gap-2">
                      <AlertCircle size={16} />
                      Load video files to play songs
                    </p>
                  </div>
                )}

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
                      disabled={gameState?.is_paused || Object.keys(videoFiles).length === 0}
                      data-testid="next-song-btn"
                    >
                      <Music size={24} className="mr-2" />
                      Next Song
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
        <Dialog open={showBingoDialog} onOpenChange={setShowBingoDialog}>
          <DialogContent className="bg-zinc-900 border-zinc-700">
            <DialogHeader>
              <DialogTitle className="font-display text-3xl text-center text-yellow-400">BINGO Claimed!</DialogTitle>
            </DialogHeader>
            <div className="py-6 space-y-4">
              <p className="text-center text-zinc-400">Verify the player's card and enter their name</p>
              <Input placeholder="Winner's name" value={winnerName} onChange={(e) => setWinnerName(e.target.value)} className="bg-zinc-800 border-zinc-700 text-center text-lg" />
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
      </div>
    );
  }

  // =====================================================
  // TRADITIONAL BINGO LAYOUT
  // =====================================================
  return (
    <div className="min-h-screen bg-background p-4" data-testid="host-dashboard">
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
                  <video ref={videoRef} src={videoUrl} className="w-full h-full object-contain bg-black" onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} />
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

      <Dialog open={showBingoDialog} onOpenChange={setShowBingoDialog}>
        <DialogContent className="bg-zinc-900 border-zinc-700">
          <DialogHeader>
            <DialogTitle className="font-display text-3xl text-center text-yellow-400">BINGO Claimed!</DialogTitle>
          </DialogHeader>
          <div className="py-6 space-y-4">
            <p className="text-center text-zinc-400">Verify the player's card and enter their name</p>
            <Input placeholder="Winner's name" value={winnerName} onChange={(e) => setWinnerName(e.target.value)} className="bg-zinc-800 border-zinc-700 text-center text-lg" />
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
    </div>
  );
}
