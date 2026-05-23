import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Play, 
  Settings, 
  Music, 
  Timer, 
  Zap,
  Circle,
  Hash,
  Square,
  Grid3X3,
  ArrowRight,
  ArrowLeft,
  Disc3,
  CircleDot
} from "lucide-react";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { RadioGroup, RadioGroupItem } from "../../components/ui/radio-group";
import { Label } from "../../components/ui/label";
import { toast } from "sonner";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// v31.0.6 — Music Bingo is on ice until we rebuild the music-video pipeline
// as a paid add-on. While false: lobby only offers traditional bingo, the
// "Bingo Type" / "Music Decade" steps are skipped, the "Quick Play" preset
// (loads a 30-min music video) is hidden, and the page title says "Bingo".
// Flip this to `true` to bring the music flow back without touching anything
// else in the file.
const ENABLE_MUSIC_BINGO = false;

export default function Lobby() {
  const navigate = useNavigate();
  // When music bingo is disabled, jump straight into the custom wizard —
  // the "Quick Play" preset-video mode is meaningless without songs.
  const [mode, setMode] = useState(ENABLE_MUSIC_BINGO ? null : 'custom');
  // Start the wizard at step 1 (Game Type) when music is disabled — step 0
  // is the Bingo Type picker which has only one option in that build.
  const [step, setStep] = useState(ENABLE_MUSIC_BINGO ? 0 : 1);
  const [isLoading, setIsLoading] = useState(false);
  
  // Game settings
  const [settings, setSettings] = useState({
    bingoType: ENABLE_MUSIC_BINGO ? "music" : "traditional",
    gameType: "regular",
    roundType: "traditional",
    callInterval: 30,
    musicDecade: "1980s"
  });

  // Bingo Types - filtered to the traditional-only set when the music flow
  // is disabled. The "type selection" step is also short-circuited below.
  const allBingoTypes = [
    { 
      id: "music", 
      name: "Music Bingo", 
      icon: Disc3, 
      description: "Play songs from your video library",
      color: "text-fuchsia-500"
    },
    { 
      id: "traditional", 
      name: "Traditional Bingo", 
      icon: CircleDot, 
      description: "Classic numbered ball bingo",
      color: "text-cyan-500"
    }
  ];
  const bingoTypes = ENABLE_MUSIC_BINGO
    ? allBingoTypes
    : allBingoTypes.filter(t => t.id === "traditional");

  const roundTypes = [
    { id: "traditional", name: "Traditional", icon: Grid3X3, description: "5 in a row (any direction)" },
    { id: "4-corners", name: "4 Corners", icon: Square, description: "All 4 corner squares" },
    { id: "7", name: "Lucky 7", icon: Hash, description: "Form the number 7" },
    { id: "blackout", name: "Blackout", icon: Circle, description: "Cover all squares" }
  ];

  const [decades, setDecades] = useState([
    { id: "1970s", name: "1970s", emoji: "Disco Era" },
    { id: "1980s", name: "1980s", emoji: "Synth Pop" },
    { id: "1990s", name: "1990s", emoji: "Grunge & Pop" },
    { id: "2000s", name: "2000s", emoji: "Y2K Hits" },
    { id: "Emo", name: "Emo", emoji: "Emo & Pop Punk" }
  ]);
  const [decadesLoading, setDecadesLoading] = useState(false);

  // Fetch available decades from SharePoint
  useEffect(() => {
    const fetchDecades = async () => {
      setDecadesLoading(true);
      try {
        const res = await axios.get(`${API}/bingo/available-decades`);
        if (res.data.success && res.data.decades.length > 0) {
          setDecades(res.data.decades.map(d => ({ id: d.id, name: d.name, emoji: d.subtitle })));
        }
      } catch (err) {
        console.error('Failed to fetch decades from SharePoint:', err);
      } finally {
        setDecadesLoading(false);
      }
    };
    fetchDecades();
  }, []);

  // Timer intervals depend on game type
  const getLightningIntervals = () => [
    { value: 10, label: "10 sec", description: "Blazing fast" },
    { value: 15, label: "15 sec", description: "Speed round" }
  ];

  const getStandardIntervals = () => [
    { value: 30, label: "30 sec", description: "Standard pace" },
    { value: 45, label: "45 sec", description: "Comfortable" },
    { value: 60, label: "60 sec", description: "Relaxed" }
  ];

  const intervals = settings.gameType === "lightning" ? getLightningIntervals() : getStandardIntervals();

  const createGame = async (presetMode = false) => {
    setIsLoading(true);
    try {
      const response = await axios.post(`${API}/bingo/game/create`, {
        bingo_type: settings.bingoType,
        game_type: settings.gameType,
        round_type: settings.roundType,
        call_interval: settings.callInterval,
        music_decade: settings.musicDecade,
        preset_mode: presetMode
      });
      
      if (response.data.success) {
        toast.success("Game created! Let's play BINGO!");
        navigate("/bingo/host");
      }
    } catch (error) {
      console.error("Error creating game:", error);
      toast.error("Failed to create game");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePresetStart = () => {
    createGame(true);
  };

  const handleCustomStart = () => {
    createGame(false);
  };

  // Determine total steps based on bingo type. Note: with music disabled
  // we skip step 0 (bingo-type select), so the visible wizard runs from
  // step 1 → step 3 (Game Type → Round Type → Call Interval).
  const getTotalSteps = () => {
    if (!ENABLE_MUSIC_BINGO) {
      return 4; // total slots, indices 0..3 — step 0 is just skipped
    }
    if (settings.bingoType === "music") {
      return 5; // Bingo Type -> Music Decade -> Game Speed -> Round Type -> Interval
    }
    return 4; // Bingo Type -> Game Type -> Round Type -> Interval
  };

  // The first visible step when music is disabled is step 1, not step 0.
  const firstStep = ENABLE_MUSIC_BINGO ? 0 : 1;

  const nextStep = () => setStep(s => Math.min(s + 1, getTotalSteps() - 1));
  const prevStep = () => setStep(s => Math.max(s - 1, firstStep));

  return (
    <div className="min-h-screen bg-gradient-radial flex flex-col items-center justify-center p-8 relative">
      {/* Back to Dashboard */}
      <button onClick={() => navigate('/')} className="absolute top-4 left-4 flex items-center gap-2 px-3 py-2 rounded-lg text-sm z-50 opacity-60 hover:opacity-100 transition-opacity" style={{ color: '#D946EF' }} data-testid="back-to-dashboard">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Dashboard
      </button>
      {/* Header */}
      <motion.div 
        initial={{ y: -50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="text-center mb-12"
      >
        <h1 className="font-display text-6xl md:text-8xl neon-text mb-4">
          {ENABLE_MUSIC_BINGO ? "Music Bingo" : "Bingo"}
        </h1>
        <p className="text-zinc-400 text-lg md:text-xl font-medium tracking-wide">
          BIG Hat Entertainment
        </p>
      </motion.div>

      <AnimatePresence mode="wait">
        {!mode ? (
          /* Mode Selection (only shown when music bingo is enabled — the
             "Quick Play" card loads a pre-edited 30-min music video, which
             doesn't apply to traditional bingo). */
          <motion.div
            key="mode-select"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="grid md:grid-cols-2 gap-8 max-w-4xl w-full"
          >
            {/* Preset Mode */}
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="preset-card"
              onClick={() => setMode('preset')}
              data-testid="preset-mode-card"
            >
              <div className="flex items-center gap-4 mb-4">
                <div className="p-4 rounded-xl bg-fuchsia-500/20">
                  <Play size={40} className="text-fuchsia-500 fill-fuchsia-500" />
                </div>
                <div>
                  <h2 className="font-display text-2xl text-white">Quick Play</h2>
                  <p className="text-zinc-400">Use preset video playlist</p>
                </div>
              </div>
              <p className="text-zinc-500 text-sm">
                Perfect for pre-edited 30-minute music video compilations. 
                Just load your video and start playing!
              </p>
            </motion.div>

            {/* Custom Mode */}
            <motion.div
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="preset-card"
              onClick={() => setMode('custom')}
              data-testid="custom-mode-card"
            >
              <div className="flex items-center gap-4 mb-4">
                <div className="p-4 rounded-xl bg-cyan-500/20">
                  <Settings size={40} className="text-cyan-500" />
                </div>
                <div>
                  <h2 className="font-display text-2xl text-white">Custom Setup</h2>
                  <p className="text-zinc-400">Configure your game</p>
                </div>
              </div>
              <p className="text-zinc-500 text-sm">
                Choose bingo type (Music or Traditional), round style, timing, and music decade.
                Full control over your bingo experience!
              </p>
            </motion.div>
          </motion.div>
        ) : mode === 'preset' ? (
          /* Preset Mode Confirmation */
          <motion.div
            key="preset-confirm"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="max-w-xl w-full"
          >
            <Card className="card-dark">
              <CardHeader>
                <CardTitle className="font-display text-3xl text-center">
                  Quick Play Mode
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="text-center text-zinc-400">
                  <p className="mb-4">
                    In Quick Play mode, you'll load a pre-edited video and the 
                    host will manually call numbers as songs play.
                  </p>
                  <div className="bg-zinc-800/50 rounded-xl p-4 text-left space-y-2">
                    <p className="flex items-center gap-2">
                      <Music className="text-fuchsia-500" size={20} />
                      <span>Load your video file</span>
                    </p>
                    <p className="flex items-center gap-2">
                      <Timer className="text-cyan-500" size={20} />
                      <span>Manual number calling</span>
                    </p>
                    <p className="flex items-center gap-2">
                      <Play className="text-green-500" size={20} />
                      <span>Play for time (video length)</span>
                    </p>
                  </div>
                </div>
                
                <div className="flex gap-4">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setMode(null)}
                    data-testid="back-to-modes-btn"
                  >
                    <ArrowLeft className="mr-2" size={20} />
                    Back
                  </Button>
                  <Button
                    className="flex-1 btn-primary"
                    onClick={handlePresetStart}
                    disabled={isLoading}
                    data-testid="start-preset-btn"
                  >
                    {isLoading ? "Creating..." : "Start Game"}
                    <ArrowRight className="ml-2" size={20} />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : (
          /* Custom Setup Wizard */
          <motion.div
            key="custom-wizard"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="max-w-3xl w-full"
          >
            <Card className="card-dark">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="font-display text-2xl">
                    Game Setup
                  </CardTitle>
                  <div className="flex gap-2">
                    {Array.from({ length: getTotalSteps() }, (_, s) => s)
                      .filter(s => s >= firstStep)
                      .map((s) => (
                        <div
                          key={s}
                          className={`w-3 h-3 rounded-full transition-colors duration-300 ${
                            s === step ? "bg-fuchsia-500" : s < step ? "bg-fuchsia-500/50" : "bg-zinc-700"
                          }`}
                        />
                      ))}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <AnimatePresence mode="wait">
                  {/* Step 1: Bingo Type (NEW) */}
                  {step === 0 && (
                    <motion.div
                      key="step-0"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      <h3 className="text-xl font-semibold text-zinc-200">Select Bingo Type</h3>
                      <RadioGroup
                        value={settings.bingoType}
                        onValueChange={(v) => setSettings(s => ({ ...s, bingoType: v }))}
                        className="grid grid-cols-2 gap-4"
                      >
                        {bingoTypes.map((type) => {
                          const Icon = type.icon;
                          return (
                            <Label
                              key={type.id}
                              htmlFor={`type-${type.id}`}
                              className={`round-type-card ${settings.bingoType === type.id ? 'selected' : ''}`}
                            >
                              <RadioGroupItem value={type.id} id={`type-${type.id}`} className="sr-only" />
                              <div className="flex items-center gap-3">
                                <Icon size={32} className={type.color} />
                                <div>
                                  <p className="font-bold text-lg">{type.name}</p>
                                  <p className="text-zinc-500 text-sm">{type.description}</p>
                                </div>
                              </div>
                            </Label>
                          );
                        })}
                      </RadioGroup>
                      
                      {settings.bingoType === "music" && (
                        <div className="bg-fuchsia-500/10 border border-fuchsia-500/30 rounded-xl p-4 mt-4">
                          <p className="text-fuchsia-300 text-sm">
                            <strong>Music Bingo:</strong> Players mark song names on their cards. 
                            Videos play from your local drive based on the song list.
                          </p>
                        </div>
                      )}
                      
                      {settings.bingoType === "traditional" && (
                        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-4 mt-4">
                          <p className="text-cyan-300 text-sm">
                            <strong>Traditional Bingo:</strong> Classic numbered balls (B1-15, I16-30, etc.). 
                            Music plays in the background while numbers are called.
                          </p>
                        </div>
                      )}
                    </motion.div>
                  )}

                  {/* Step 2: Music Decade (for Music Bingo) OR Game Type (for Traditional) */}
                  {step === 1 && (
                    <motion.div
                      key="step-1"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      {settings.bingoType === "music" ? (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Select Music Decade</h3>
                          <p className="text-zinc-500 text-sm">
                            {decadesLoading ? 'Fetching available decades from SharePoint...' : 'This will load the song list from SharePoint for the selected era.'}
                          </p>
                          {decadesLoading ? (
                            <div className="flex items-center justify-center py-8">
                              <div className="loading-balls">
                                <div className="loading-ball" /><div className="loading-ball" /><div className="loading-ball" /><div className="loading-ball" /><div className="loading-ball" />
                              </div>
                            </div>
                          ) : (
                          <RadioGroup
                            value={settings.musicDecade}
                            onValueChange={(v) => setSettings(s => ({ ...s, musicDecade: v }))}
                            className="grid grid-cols-2 gap-4"
                          >
                            {decades.map((decade) => (
                              <Label
                                key={decade.id}
                                htmlFor={`decade-${decade.id}`}
                                className={`round-type-card text-center py-6 ${settings.musicDecade === decade.id ? 'selected' : ''}`}
                              >
                                <RadioGroupItem 
                                  value={decade.id} 
                                  id={`decade-${decade.id}`} 
                                  className="sr-only" 
                                />
                                <p className="font-display text-4xl text-fuchsia-400">{decade.name}</p>
                                <p className="text-zinc-500 text-sm mt-2">{decade.emoji}</p>
                              </Label>
                            ))}
                          </RadioGroup>
                          )}
                        </>
                      ) : (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Select Game Type</h3>
                          <RadioGroup
                            value={settings.gameType}
                            onValueChange={(v) => setSettings(s => ({ ...s, gameType: v, callInterval: v === "lightning" ? 10 : 30 }))}
                            className="grid grid-cols-2 gap-4"
                          >
                            <Label
                              htmlFor="regular"
                              className={`round-type-card ${settings.gameType === 'regular' ? 'selected' : ''}`}
                            >
                              <RadioGroupItem value="regular" id="regular" className="sr-only" />
                              <div className="flex items-center gap-3">
                                <Music size={32} className="text-fuchsia-500" />
                                <div>
                                  <p className="font-bold text-lg">Regular Bingo</p>
                                  <p className="text-zinc-500 text-sm">Standard gameplay</p>
                                </div>
                              </div>
                            </Label>
                            <Label
                              htmlFor="lightning"
                              className={`round-type-card ${settings.gameType === 'lightning' ? 'selected' : ''}`}
                            >
                              <RadioGroupItem value="lightning" id="lightning" className="sr-only" />
                              <div className="flex items-center gap-3">
                                <Zap size={32} className="text-yellow-500" />
                                <div>
                                  <p className="font-bold text-lg">Lightning Bingo</p>
                                  <p className="text-zinc-500 text-sm">Fast-paced action</p>
                                </div>
                              </div>
                            </Label>
                          </RadioGroup>
                        </>
                      )}
                    </motion.div>
                  )}

                  {/* Step 3 (Music Bingo): Game Speed / Step 3 (Traditional): Round Type */}
                  {step === 2 && (
                    <motion.div
                      key="step-2"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      {settings.bingoType === "music" ? (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Select Game Speed</h3>
                          <RadioGroup
                            value={settings.gameType}
                            onValueChange={(v) => setSettings(s => ({ ...s, gameType: v, callInterval: v === "lightning" ? 10 : 30 }))}
                            className="grid grid-cols-2 gap-4"
                          >
                            <Label
                              htmlFor="music-regular"
                              className={`round-type-card ${settings.gameType === 'regular' ? 'selected' : ''}`}
                            >
                              <RadioGroupItem value="regular" id="music-regular" className="sr-only" />
                              <div className="flex items-center gap-3">
                                <Music size={32} className="text-fuchsia-500" />
                                <div>
                                  <p className="font-bold text-lg">Regular</p>
                                  <p className="text-zinc-500 text-sm">Standard pace (30-60s)</p>
                                </div>
                              </div>
                            </Label>
                            <Label
                              htmlFor="music-lightning"
                              className={`round-type-card ${settings.gameType === 'lightning' ? 'selected' : ''}`}
                            >
                              <RadioGroupItem value="lightning" id="music-lightning" className="sr-only" />
                              <div className="flex items-center gap-3">
                                <Zap size={32} className="text-yellow-500" />
                                <div>
                                  <p className="font-bold text-lg">Lightning</p>
                                  <p className="text-zinc-500 text-sm">Speed round (10-15s)</p>
                                </div>
                              </div>
                            </Label>
                          </RadioGroup>
                        </>
                      ) : (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Select Round Type</h3>
                          <RadioGroup
                            value={settings.roundType}
                            onValueChange={(v) => setSettings(s => ({ ...s, roundType: v }))}
                            className="grid grid-cols-2 gap-4"
                          >
                            {roundTypes.map((type) => {
                              const Icon = type.icon;
                              return (
                                <Label
                                  key={type.id}
                                  htmlFor={`trad-${type.id}`}
                                  className={`round-type-card ${settings.roundType === type.id ? 'selected' : ''}`}
                                >
                                  <RadioGroupItem value={type.id} id={`trad-${type.id}`} className="sr-only" />
                                  <div className="flex items-center gap-3">
                                    <Icon size={32} className="text-cyan-500" />
                                    <div>
                                      <p className="font-bold text-lg">{type.name}</p>
                                      <p className="text-zinc-500 text-sm">{type.description}</p>
                                    </div>
                                  </div>
                                </Label>
                              );
                            })}
                          </RadioGroup>
                        </>
                      )}
                    </motion.div>
                  )}

                  {/* Step 4 (Music Bingo): Round Type / Step 4 (Traditional): Interval */}
                  {step === 3 && (
                    <motion.div
                      key="step-3"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      {settings.bingoType === "music" ? (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Select Round Type</h3>
                          <RadioGroup
                            value={settings.roundType}
                            onValueChange={(v) => setSettings(s => ({ ...s, roundType: v }))}
                            className="grid grid-cols-2 gap-4"
                          >
                            {roundTypes.map((type) => {
                              const Icon = type.icon;
                              return (
                                <Label
                                  key={type.id}
                                  htmlFor={`music-round-${type.id}`}
                                  className={`round-type-card ${settings.roundType === type.id ? 'selected' : ''}`}
                                >
                                  <RadioGroupItem value={type.id} id={`music-round-${type.id}`} className="sr-only" />
                                  <div className="flex items-center gap-3">
                                    <Icon size={32} className="text-cyan-500" />
                                    <div>
                                      <p className="font-bold text-lg">{type.name}</p>
                                      <p className="text-zinc-500 text-sm">{type.description}</p>
                                    </div>
                                  </div>
                                </Label>
                              );
                            })}
                          </RadioGroup>
                        </>
                      ) : (
                        <>
                          <h3 className="text-xl font-semibold text-zinc-200">Number Call Interval</h3>
                          <p className="text-zinc-500 text-sm">Time between each number being called</p>
                          <RadioGroup
                            value={settings.callInterval.toString()}
                            onValueChange={(v) => setSettings(s => ({ ...s, callInterval: parseInt(v) }))}
                            className={`grid ${intervals.length === 2 ? 'grid-cols-2' : 'grid-cols-3'} gap-4`}
                          >
                            {intervals.map((interval) => (
                              <Label
                                key={interval.value}
                                htmlFor={`trad-interval-${interval.value}`}
                                className={`round-type-card text-center ${settings.callInterval === interval.value ? 'selected' : ''}`}
                              >
                                <RadioGroupItem
                                  value={interval.value.toString()}
                                  id={`trad-interval-${interval.value}`}
                                  className="sr-only"
                                />
                                <div>
                                  <p className="font-display text-3xl text-cyan-400">{interval.label}</p>
                                  <p className="text-zinc-500 text-sm mt-1">{interval.description}</p>
                                </div>
                              </Label>
                            ))}
                          </RadioGroup>
                        </>
                      )}
                    </motion.div>
                  )}

                  {/* Step 5 (Music Bingo only): Interval */}
                  {step === 4 && settings.bingoType === "music" && (
                    <motion.div
                      key="step-4"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      className="space-y-6"
                    >
                      <h3 className="text-xl font-semibold text-zinc-200">Song Duration</h3>
                      <p className="text-zinc-500 text-sm">How long each song clip plays before the next number appears</p>
                      <RadioGroup
                        value={settings.callInterval.toString()}
                        onValueChange={(v) => setSettings(s => ({ ...s, callInterval: parseInt(v) }))}
                        className={`grid ${intervals.length === 2 ? 'grid-cols-2' : 'grid-cols-3'} gap-4`}
                      >
                        {intervals.map((interval) => (
                          <Label
                            key={interval.value}
                            htmlFor={`music-interval-${interval.value}`}
                            className={`round-type-card text-center ${settings.callInterval === interval.value ? 'selected' : ''}`}
                          >
                            <RadioGroupItem
                              value={interval.value.toString()}
                              id={`music-interval-${interval.value}`}
                              className="sr-only"
                            />
                            <div>
                              <p className="font-display text-3xl text-cyan-400">{interval.label}</p>
                              <p className="text-zinc-500 text-sm mt-1">{interval.description}</p>
                            </div>
                          </Label>
                        ))}
                      </RadioGroup>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Navigation */}
                <div className="flex gap-4 mt-8">
                  <Button
                    variant="outline"
                    onClick={step === firstStep
                      ? (ENABLE_MUSIC_BINGO ? () => setMode(null) : () => navigate('/'))
                      : prevStep}
                    data-testid="wizard-back-btn"
                  >
                    <ArrowLeft className="mr-2" size={20} />
                    Back
                  </Button>
                  <div className="flex-1" />
                  {step < getTotalSteps() - 1 ? (
                    <Button
                      className="btn-primary"
                      onClick={nextStep}
                      data-testid="wizard-next-btn"
                    >
                      Next
                      <ArrowRight className="ml-2" size={20} />
                    </Button>
                  ) : (
                    <Button
                      className="btn-success"
                      onClick={handleCustomStart}
                      disabled={isLoading}
                      data-testid="start-custom-btn"
                    >
                      {isLoading ? "Creating..." : "Start Game"}
                      <Play className="ml-2" size={20} />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Footer */}
      <motion.p 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-12 text-zinc-600 text-sm"
      >
        Press ESC to return to mode selection
      </motion.p>
    </div>
  );
}
