import React, { useState, useCallback, useRef } from 'react';
import { toast } from 'sonner';
import { Download, Film, Maximize2, Save, FolderSync, RefreshCw, Play, Pause, Settings2, Zap, Sparkles, Video, QrCode, X } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Separator } from '../../components/ui/separator';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../components/ui/dialog';
import { Input } from '../../components/ui/input';
import { Slider } from '../../components/ui/slider';
import { Badge } from '../../components/ui/badge';
import { ScrollArea } from '../../components/ui/scroll-area';
import RenderStage from '../../components/scoreboard/render/RenderStage';
import LeaderboardRender from '../../components/scoreboard/render/LeaderboardRender';
import BracketRender from '../../components/scoreboard/render/BracketRender';
import { generateBracket, advanceRound } from '../../lib/bracketLogic';
import api from '../../lib/scoreboardApi';

const Dashboard = () => {
  const [mode, setMode] = useState('leaderboard');
  const [aspectRatio, setAspectRatio] = useState('landscape');
  const [animationSpeed, setAnimationSpeed] = useState(1);
  const [isAnimating, setIsAnimating] = useState(true);
  
  const [scoreFiles, setScoreFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  
  const [tournamentName, setTournamentName] = useState('THE BIG TRIVIA TOURNAMENT');
  const [tournamentYear, setTournamentYear] = useState(new Date().getFullYear().toString());
  const [totalTeams, setTotalTeams] = useState(12);
  const [byeCount, setByeCount] = useState(4);
  const [tournamentTeams, setTournamentTeams] = useState([]);
  const [bracket, setBracket] = useState(null);
  const [editingTeams, setEditingTeams] = useState(false);
  const [teamInputs, setTeamInputs] = useState('');
  
  // Accumulated scores for tournament
  const [selectedVenue, setSelectedVenue] = useState('');
  const [accumulatedTeams, setAccumulatedTeams] = useState([]); // {name, totalScore, weekScores[], appearances}
  const [teamRenames, setTeamRenames] = useState({}); // {originalName: newName} for merging
  const [showRenameEditor, setShowRenameEditor] = useState(false);
  const [renameFrom, setRenameFrom] = useState('');
  const [renameTo, setRenameTo] = useState('');
  
  const [presets, setPresets] = useState([]);
  const [presetName, setPresetName] = useState('');
  const [showSavePreset, setShowSavePreset] = useState(false);
  
  // QR code state
  const [qrUrl, setQrUrl] = useState(null);
  const [showQr, setShowQr] = useState(false);
  
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState('');
  
  const stageRef = useRef(null);

  // Get unique venues from score files - use SharePoint folder name as primary key
  const venues = React.useMemo(() => {
    const venueMap = {};
    scoreFiles.forEach(f => {
      // Use the SharePoint folder name (f.venue) as the canonical venue identifier
      // Strip numeric prefixes like "01_", "03_", "06_" to normalize
      let venue = f.venue || f.data?.location || 'Unknown';
      venue = venue.replace(/^\d+_/, ''); // strip leading "01_", "03_", etc.
      if (!venueMap[venue]) venueMap[venue] = [];
      venueMap[venue].push(f);
    });
    return venueMap;
  }, [scoreFiles]);

  // Accumulate scores when venue is selected
  React.useEffect(() => {
    if (!selectedVenue || !venues[selectedVenue]) return;
    const files = venues[selectedVenue];
    const teamScores = {}; // {name: {totalScore, weekScores[], appearances}}
    
    files.forEach(f => {
      const teams = f.data?.teams || [];
      const date = f.data?.date || f.file_name;
      teams.forEach(t => {
        // Apply renames
        const name = teamRenames[t.name] || t.name;
        if (!teamScores[name]) {
          teamScores[name] = { name, totalScore: 0, weekScores: [], appearances: 0 };
        }
        teamScores[name].totalScore += (t.total || 0);
        teamScores[name].weekScores.push({ date, score: t.total || 0 });
        teamScores[name].appearances += 1;
      });
    });
    
    // Sort by total accumulated score descending
    const sorted = Object.values(teamScores).sort((a, b) => b.totalScore - a.totalScore);
    setAccumulatedTeams(sorted);
  }, [selectedVenue, venues, teamRenames]);

  // ===== SharePoint sync =====
  const handleSync = async () => {
    setSyncing(true);
    try {
      toast.info('Syncing with SharePoint...');
      const syncRes = await api.syncSharePoint();
      toast.success(`Synced ${syncRes.data.count} files`);
      const scoresRes = await api.getScores();
      setScoreFiles(scoresRes.data.files || []);
      setLastSync(new Date().toLocaleTimeString());
    } catch (err) {
      console.error('Sync error:', err);
      toast.error('SharePoint sync failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSyncing(false);
    }
  };

  const handleFetchDirect = async () => {
    setSyncing(true);
    try {
      toast.info('Fetching from SharePoint...');
      const res = await api.getSharePointFiles();
      const files = res.files || [];
      setScoreFiles(files);
      setLastSync(new Date().toLocaleTimeString());
      toast.success(`Found ${files.length} score files`);
    } catch (err) {
      console.error('Fetch error:', err);
      toast.error('Failed to fetch: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSyncing(false);
    }
  };

  // ===== Auto-populate tournament from selected file OR accumulated standings =====
  const DEFAULT_BRACKET_SIZE = 12;
  const DEFAULT_BYES = 4;

  const populateTeamsFromFile = useCallback((fileData) => {
    if (!fileData?.teams || fileData.teams.length === 0) return;
    const allTeams = fileData.teams
      .slice()
      .sort((a, b) => (a.rank || 999) - (b.rank || 999));
    const bracketSize = Math.min(allTeams.length, totalTeams || DEFAULT_BRACKET_SIZE);
    const topTeams = allTeams.slice(0, bracketSize).map((t, i) => ({
      seed: i + 1,
      name: t.name,
      score: t.total,
    }));
    setTournamentTeams(topTeams);
    setTotalTeams(bracketSize);
    setTeamInputs(topTeams.map(t => t.name).join('\n'));
    setByeCount(DEFAULT_BYES);
    const b = generateBracket(topTeams, DEFAULT_BYES);
    setBracket(b);
  }, [totalTeams]);

  // Populate bracket from accumulated venue standings
  const populateFromAccumulated = useCallback(() => {
    if (accumulatedTeams.length === 0) {
      toast.error('No accumulated standings. Select a venue first.');
      return;
    }
    const bracketSize = Math.min(accumulatedTeams.length, totalTeams || DEFAULT_BRACKET_SIZE);
    const topTeams = accumulatedTeams.slice(0, bracketSize).map((t, i) => ({
      seed: i + 1,
      name: t.name,
      score: t.totalScore,
    }));
    setTournamentTeams(topTeams);
    setTotalTeams(bracketSize);
    setTeamInputs(topTeams.map(t => t.name).join('\n'));
    setByeCount(DEFAULT_BYES);
    const b = generateBracket(topTeams, DEFAULT_BYES);
    setBracket(b);
    toast.success(`Bracket built from ${accumulatedTeams.length} accumulated teams (top ${bracketSize})`);
  }, [accumulatedTeams, totalTeams]);

  // Handle team rename/merge
  const handleAddRename = () => {
    if (!renameFrom.trim() || !renameTo.trim()) return;
    setTeamRenames(prev => ({ ...prev, [renameFrom.trim()]: renameTo.trim() }));
    setRenameFrom('');
    setRenameTo('');
    toast.success(`"${renameFrom.trim()}" will be merged into "${renameTo.trim()}"`);
  };

  const handleRemoveRename = (from) => {
    setTeamRenames(prev => {
      const next = { ...prev };
      delete next[from];
      return next;
    });
  };

  // When selected file changes, auto-populate tournament teams
  React.useEffect(() => {
    const fileData = selectedFile?.data || selectedFile;
    if (fileData?.teams && fileData.teams.length > 0) {
      populateTeamsFromFile(fileData);
    }
  }, [selectedFile, populateTeamsFromFile]);

  // ===== Tournament =====
  const handleGenerateBracket = () => {
    if (tournamentTeams.length < 2) {
      toast.error('Need at least 2 teams to generate a bracket');
      return;
    }
    const b = generateBracket(tournamentTeams, byeCount);
    setBracket(b);
    toast.success('Bracket generated!');
  };

  const handleSetTeams = () => {
    const lines = teamInputs.split('\n').filter(l => l.trim());
    const teams = lines.map((name, i) => ({ seed: i + 1, name: name.trim() }));
    setTournamentTeams(teams);
    setTotalTeams(teams.length);
    setEditingTeams(false);
    toast.success(`Set ${teams.length} teams`);
  };

  const handleRecordResult = (matchId, winnerSeed, scoreA, scoreB) => {
    if (!bracket) return;
    const updated = { ...bracket };
    const match = updated.matches[matchId];
    if (match) {
      match.winner_seed = winnerSeed;
      match.score_a = scoreA;
      match.score_b = scoreB;
      match.completed = true;
    }
    const advanced = advanceRound(updated, tournamentTeams);
    setBracket({ ...advanced });
  };

  // ===== Presets =====
  const handleLoadPresets = async () => {
    try {
      const res = await api.getPresets();
      setPresets(res.data.presets || []);
    } catch (err) {
      console.error('Failed to load presets:', err);
    }
  };

  const handleSavePreset = async () => {
    if (!presetName.trim()) { toast.error('Enter a preset name'); return; }
    try {
      await api.createPreset({
        name: presetName, mode, aspect_ratio: aspectRatio, animation_speed: animationSpeed,
        config: { selectedFile: selectedFile?.file_name, tournamentName, totalTeams, byeCount },
      });
      toast.success('Preset saved!');
      setShowSavePreset(false);
      setPresetName('');
      handleLoadPresets();
    } catch (err) { toast.error('Failed to save preset'); }
  };

  const handleLoadPreset = (preset) => {
    setMode(preset.mode);
    setAspectRatio(preset.aspect_ratio);
    setAnimationSpeed(preset.animation_speed || 1);
    if (preset.config?.tournamentName) setTournamentName(preset.config.tournamentName);
    if (preset.config?.totalTeams) setTotalTeams(preset.config.totalTeams);
    if (preset.config?.byeCount) setByeCount(preset.config.byeCount);
    if (preset.config?.selectedFile) {
      const match = scoreFiles.find(f => f.file_name === preset.config.selectedFile);
      if (match) setSelectedFile(match);
    }
    toast.success(`Loaded preset: ${preset.name}`);
  };

  const handleDeletePreset = async (presetId) => {
    try { await api.deletePreset(presetId); toast.success('Preset deleted'); handleLoadPresets(); }
    catch (err) { toast.error('Failed to delete preset'); }
  };

  // ===== Export =====
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

  const uploadForQr = async (blob, filename) => {
    try {
      const formData = new FormData();
      formData.append('file', blob, filename);
      const res = await api.uploadExport(formData);
      // Build the full public URL for the QR code
      const publicUrl = `${BACKEND_URL}${res.data.url}`;
      setQrUrl(publicUrl);
      return publicUrl;
    } catch (err) {
      console.error('Upload for QR failed:', err);
      return null;
    }
  };

  const handleExportPng = async () => {
    setExporting(true);
    setExportStatus('Generating full-res PNG...');
    try {
      // Disable animations so all content is fully visible (no fade-in opacity issues)
      const wasAnimating = isAnimating;
      setIsAnimating(false);
      await new Promise(r => setTimeout(r, 200)); // wait for state to apply

      if (window.__renderStage?.exportAsPng) {
        const dataUrl = await window.__renderStage.exportAsPng();
        if (dataUrl) {
          const res = await fetch(dataUrl);
          const blob = await res.blob();
          const blobUrl = URL.createObjectURL(blob);
          
          const link = document.createElement('a');
          link.download = `bighat-${mode}-${aspectRatio}-${Date.now()}.png`;
          link.href = blobUrl;
          link.click();

          setExportStatus('Uploading for QR sharing...');
          await uploadForQr(blob, `bighat-${mode}-${aspectRatio}-${Date.now()}.png`);
          
          setExportStatus('PNG exported! QR ready for phone download.');
          toast.success('PNG exported! QR ready.');
        }
      }
      // Restore animation state
      if (wasAnimating) setIsAnimating(true);
    } catch (err) {
      console.error('PNG export failed:', err);
      setExportStatus('Export failed');
      toast.error('PNG export failed');
    } finally { setExporting(false); }
  };

  const handleExportVideo = async () => {
    setExporting(true);
    setExportStatus('Capturing high-res frame...');
    toast.info('Creating smooth 15s video at 30fps...');
    try {
      // Disable animations so we capture the final complete state
      const wasAnimating = isAnimating;
      setIsAnimating(false);
      await new Promise(r => setTimeout(r, 300));

      // Capture a single high-quality PNG frame
      if (window.__renderStage?.exportAsPng) {
        const dataUrl = await window.__renderStage.exportAsPng();
        if (dataUrl) {
          setExportStatus('Uploading to server for video creation...');
          
          // Convert to blob
          const res = await fetch(dataUrl);
          const blob = await res.blob();
          
          // Upload PNG to server and convert to smooth 30fps MP4
          setExportStatus('Creating 15s MP4 at 30fps (450 frames)...');
          const formData = new FormData();
          formData.append('file', blob, `bighat-${mode}-${aspectRatio}-${Date.now()}.png`);
          const videoRes = await api.imageToVideo(formData, 15);
          
          // Download the MP4
          const mp4Url = `${BACKEND_URL}${videoRes.data.url}`;
          const link = document.createElement('a');
          link.download = videoRes.data.file_id || `bighat-${mode}-${aspectRatio}.mp4`;
          link.href = mp4Url;
          link.click();

          setQrUrl(mp4Url);
          setExportStatus(`MP4 exported! ${videoRes.data.total_frames} frames @ ${videoRes.data.fps}fps. QR ready.`);
          toast.success('Smooth MP4 video exported!');
        }
      }
      // Restore animation state
      if (wasAnimating) setIsAnimating(true);
    } catch (err) {
      console.error('Video export failed:', err);
      setExportStatus('Video export failed: ' + (err.response?.data?.detail || err.message));
      toast.error('Video export failed');
    } finally { setExporting(false); }
  };

  const handleShowQr = () => {
    if (!qrUrl) {
      toast.error('Export a PNG or Video first');
      return;
    }
    setShowQr(true);
  };

  const handleOpenLiveView = () => {
    const liveData = { data: currentData, bracket, teams: tournamentTeams, tournamentName };
    localStorage.setItem('liveRenderData', JSON.stringify(liveData));
    const url = `/scoreboard/live?mode=${mode}&aspect=${aspectRatio}`;
    window.open(url, '_blank', 'fullscreen=yes');
  };

  const currentData = selectedFile?.data || selectedFile;

  // Card and section styling for dark theme
  const cardClass = "bg-[#111118]/80 backdrop-blur-sm border-[rgba(225,48,108,0.15)] hover:border-[rgba(225,48,108,0.3)] transition-colors";
  const labelClass = "text-xs font-semibold text-[#fbdd68] uppercase tracking-[0.15em] flex items-center gap-2";

  return (
    <div className="min-h-screen cyber-grid" style={{ background: '#000e2a' }}>
      {/* Ambient glow blobs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-40 -left-40 w-80 h-80 bg-gradient-to-br from-blue-900/20 via-blue-800/10 to-transparent rounded-full blur-[100px] animate-pulse" />
        <div className="absolute -bottom-40 -right-40 w-80 h-80 bg-gradient-to-br from-blue-900/20 via-indigo-900/10 to-transparent rounded-full blur-[100px] animate-pulse" style={{ animationDelay: '2s' }} />
      </div>

      {/* Header */}
      <header className="border-b border-[rgba(251,221,104,0.15)] bg-[#141b50] backdrop-blur-xl sticky top-0 z-50">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => { window.location.href = '/'; }} className="p-2 rounded-lg hover:bg-[#fbdd68]/5" data-testid="back-to-dashboard">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fbdd68" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div className="h-10 w-10 rounded-xl bg-[#fbdd68] flex items-center justify-center pulse-ring">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-['Inter'] text-xl font-bold text-white">
                BIG HAT LEADERBOARDS
              </h1>
              <p className="text-[10px] text-[#fbdd68] font-mono tracking-wider">
                // TRIVIA_LEADERBOARD
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {lastSync && (
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[rgba(225,48,108,0.1)] border border-[rgba(251,221,104,0.15)]">
                <div className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                <span className="text-[10px] text-green-400 font-mono">SYNCED {lastSync}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-12 gap-6 p-6 relative z-10">
        {/* Left Rail - Controls */}
        <div className="col-span-12 lg:col-span-4 xl:col-span-3 space-y-4">
          
          {/* Mode Selection */}
          <Card className={cardClass}>
            <CardHeader className="pb-3">
              <CardTitle className={labelClass}>
                <Sparkles className="h-3 w-3" /> Mode
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs value={mode} onValueChange={setMode} data-testid="mode-tabs">
                <TabsList className="w-full bg-[#141b50]">
                  <TabsTrigger value="leaderboard" className="flex-1 text-[#8892b0] data-[state=active]:bg-[rgba(251,221,104,0.15)] data-[state=active]:text-[#fbdd68]" data-testid="mode-leaderboard">
                    Leaderboard
                  </TabsTrigger>
                  <TabsTrigger value="tournament" className="flex-1 text-[#8892b0] data-[state=active]:bg-[rgba(251,221,104,0.15)] data-[state=active]:text-[#fbdd68]" data-testid="mode-tournament">
                    Tournament
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </CardContent>
          </Card>

          {/* Data Source */}
          <Card className={cardClass}>
            <CardHeader className="pb-3">
              <CardTitle className={labelClass}>
                <FolderSync className="h-3 w-3" /> Data Source
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Button 
                  onClick={handleFetchDirect}
                  disabled={syncing}
                  size="sm"
                  className="flex-1 text-white hover:bg-[#f5d050] border-[#fbdd68]"
                  data-testid="sharepoint-sync-button"
                >
                  <FolderSync className="w-4 h-4 mr-1" />
                  {syncing ? 'Syncing...' : 'Fetch'}
                </Button>
                <Button 
                  onClick={handleSync}
                  disabled={syncing}
                  size="sm"
                  className="flex-1 btn-futuristic"
                  data-testid="sharepoint-save-button"
                >
                  <RefreshCw className={`w-4 h-4 mr-1 ${syncing ? 'animate-spin' : ''}`} />
                  Sync & Save
                </Button>
              </div>
              
              {syncing && (
                <div className="flex items-center gap-2 text-xs text-[#8892b0]">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  <span className="font-mono">Fetching from SharePoint...</span>
                </div>
              )}

              {scoreFiles.length > 0 && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono text-[#8892b0]" data-testid="file-count">
                      {scoreFiles.length} files available
                    </span>
                  </div>
                  <Select 
                    onValueChange={(val) => {
                      const file = scoreFiles.find(f => f.file_name === val);
                      setSelectedFile(file);
                    }}
                  >
                    <SelectTrigger className="bg-[#141b50] border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/40 text-white" data-testid="sharepoint-file-picker">
                      <SelectValue placeholder="Select a score file" />
                    </SelectTrigger>
                    <SelectContent className="bg-[#15151f] border-[rgba(251,221,104,0.15)]">
                      {scoreFiles.map((f) => (
                        <SelectItem key={f.file_name} value={f.file_name} data-testid={`file-option-${f.file_name}`}>
                          {f.data?.presentationName || f.file_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </>
              )}

              {selectedFile && (
                <div className="text-xs space-y-1 p-3 rounded-lg holographic border border-[#fbdd68]/10">
                  <p className="text-white"><strong>Venue:</strong> <span className="text-white/70">{selectedFile.data?.location || selectedFile.venue}</span></p>
                  <p className="text-white"><strong>Date:</strong> <span className="text-white/70">{selectedFile.data?.date}</span></p>
                  <p className="text-white"><strong>Teams:</strong> <span className="text-white/70">{selectedFile.data?.teams?.length}</span></p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tournament: Venue & Accumulated Standings */}
          {mode === 'tournament' && scoreFiles.length > 0 && (
            <Card className={cardClass}>
              <CardHeader className="pb-3">
                <CardTitle className={labelClass}>
                  <Sparkles className="h-3 w-3" /> Venue Standings
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-[10px] font-mono text-white/50 mb-1 block">SELECT VENUE TO ACCUMULATE SCORES</label>
                  <Select value={selectedVenue} onValueChange={setSelectedVenue}>
                    <SelectTrigger className="bg-[#141b50] border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/40 text-white" data-testid="venue-selector">
                      <SelectValue placeholder="Choose a venue..." />
                    </SelectTrigger>
                    <SelectContent className="bg-[#15151f] border-[rgba(251,221,104,0.15)]">
                      {Object.entries(venues).map(([venue, files]) => (
                        <SelectItem key={venue} value={venue}>
                          {venue} ({files.length} week{files.length > 1 ? 's' : ''})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedVenue && venues[selectedVenue] && (
                  <div className="text-[10px] font-mono text-white/40 p-2 rounded-lg" style={{ background: 'rgba(225,48,108,0.05)' }}>
                    <p className="text-white mb-1 font-semibold">Weeks included:</p>
                    {venues[selectedVenue].map((f, i) => (
                      <p key={i}>{f.data?.date || f.file_name}</p>
                    ))}
                  </div>
                )}

                {/* Team Rename / Merge */}
                <div>
                  <Button  size="sm" className="w-full border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-purple-500/10 text-purple-300"
                    onClick={() => setShowRenameEditor(!showRenameEditor)} data-testid="rename-teams-button">
                    <Settings2 className="w-4 h-4 mr-1" />
                    Rename / Merge Teams ({Object.keys(teamRenames).length})
                  </Button>
                  {showRenameEditor && (
                    <div className="mt-2 space-y-2 p-3 rounded-lg border border-[rgba(251,221,104,0.15)] bg-[#141b50]">
                      <p className="text-[10px] font-mono text-purple-400/60">Merge teams that changed names between weeks:</p>
                      <div className="flex gap-2">
                        <Input value={renameFrom} onChange={(e) => setRenameFrom(e.target.value)} placeholder="Old name..." 
                          className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white text-xs flex-1" />
                        <span className="text-purple-400/40 text-xs self-center">&rarr;</span>
                        <Input value={renameTo} onChange={(e) => setRenameTo(e.target.value)} placeholder="New name..."
                          className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white text-xs flex-1" />
                      </div>
                      <Button size="sm" className="w-full btn-futuristic text-xs" onClick={handleAddRename} disabled={!renameFrom.trim() || !renameTo.trim()}>
                        Merge
                      </Button>
                      {Object.entries(teamRenames).length > 0 && (
                        <div className="space-y-1 mt-2">
                          {Object.entries(teamRenames).map(([from, to]) => (
                            <div key={from} className="flex items-center gap-2 text-[10px] font-mono">
                              <span className="text-red-400/60 line-through flex-1 truncate">{from}</span>
                              <span className="text-purple-400/40">&rarr;</span>
                              <span className="text-green-400/60 flex-1 truncate">{to}</span>
                              <button onClick={() => handleRemoveRename(from)} className="text-white/30 hover:text-red-400 text-xs">x</button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Accumulated Standings */}
                {accumulatedTeams.length > 0 && (
                  <>
                    <Separator className="bg-[#141b50]" />
                    <p className={labelClass}>Accumulated Standings ({accumulatedTeams.length} teams)</p>
                    <ScrollArea className="max-h-52">
                      <div className="space-y-1">
                        {accumulatedTeams.map((t, i) => (
                          <div key={t.name} className="flex items-center gap-2 px-2 py-1 rounded text-xs"
                            style={{ background: i < (totalTeams || 12) ? 'rgba(252,175,69,0.08)' : 'transparent', border: i < (totalTeams || 12) ? '1px solid rgba(252,175,69,0.15)' : '1px solid transparent' }}>
                            <span className="font-mono-score w-5 text-center" style={{ color: i < (totalTeams || 12) ? '#FCAF45' : 'rgba(244,242,255,0.3)' }}>{i + 1}</span>
                            <span className="flex-1 truncate font-medium" style={{ color: i < (totalTeams || 12) ? '#F4F2FF' : 'rgba(244,242,255,0.4)' }}>{t.name}</span>
                            <span className="font-mono-score text-[10px]" style={{ color: 'rgba(244,242,255,0.3)' }}>{t.appearances}wk</span>
                            <span className="font-mono-score font-bold" style={{ color: '#FCAF45', minWidth: '35px', textAlign: 'right' }}>{t.totalScore}</span>
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                    <Button onClick={populateFromAccumulated} className="w-full btn-futuristic font-['Inter'] tracking-wider text-sm" data-testid="use-accumulated-button">
                      <Zap className="w-4 h-4 mr-1" />
                      Build Bracket from Standings
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          )}

          {/* Tournament Controls */}
          {mode === 'tournament' && (
            <Card className={cardClass}>
              <CardHeader className="pb-3">
                <CardTitle className={labelClass}>
                  <Zap className="h-3 w-3" /> Tournament Setup
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Input
                  value={tournamentName}
                  onChange={(e) => setTournamentName(e.target.value)}
                  placeholder="Tournament Name"
                  className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white font-['Inter'] tracking-wider"
                  data-testid="tournament-name-input"
                />
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="text-[10px] font-mono text-white/50 mb-1 block">YEAR</label>
                    <Input
                      value={tournamentYear}
                      onChange={(e) => setTournamentYear(e.target.value)}
                      placeholder="2026"
                      className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white font-['Inter'] tracking-wider text-center"
                      data-testid="tournament-year-input"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-white/50 mb-1 block">TEAMS</label>
                    <Input
                      type="number" value={totalTeams}
                      onChange={(e) => setTotalTeams(parseInt(e.target.value) || 2)}
                      min={2} max={32}
                      className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white"
                      data-testid="tournament-teams-input"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-white/50 mb-1 block">BYES</label>
                    <Input
                      type="number" value={byeCount}
                      onChange={(e) => setByeCount(parseInt(e.target.value) || 0)}
                      min={0} max={totalTeams - 2}
                      className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white"
                      data-testid="tournament-byes-input"
                    />
                  </div>
                </div>

                <Dialog open={editingTeams} onOpenChange={setEditingTeams}>
                  <DialogTrigger asChild>
                    <Button  size="sm" className="w-full border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-[#f5d050] bg-[#fbdd68] text-[#000e2a] font-bold" data-testid="edit-teams-button">
                      <Settings2 className="w-4 h-4 mr-1" />
                      Edit Teams ({tournamentTeams.length})
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="bg-[#111118] border-[rgba(251,221,104,0.15)] text-white">
                    <DialogHeader>
                      <DialogTitle className="font-['Inter'] tracking-wider">Enter Team Names</DialogTitle>
                    </DialogHeader>
                    <p className="text-sm text-white/60 font-mono">One team per line, in seed order (1st line = #1 seed).</p>
                    <textarea
                      className="w-full h-64 p-3 rounded-lg text-sm font-medium resize-none focus:outline-none focus:ring-2 focus:ring-yellow-500/50 bg-[#141b50] border border-[rgba(251,221,104,0.15)] text-white"
                      value={teamInputs}
                      onChange={(e) => setTeamInputs(e.target.value)}
                      placeholder={"Team Alpha\nTeam Beta\nTeam Gamma\n..."}
                      data-testid="team-names-textarea"
                    />
                    <Button onClick={handleSetTeams} className="w-full btn-futuristic font-['Inter'] tracking-wider" data-testid="save-teams-button">
                      Set {teamInputs.split('\n').filter(l => l.trim()).length} Teams
                    </Button>
                  </DialogContent>
                </Dialog>

                <Button 
                  onClick={handleGenerateBracket}
                  className="w-full btn-futuristic font-['Inter'] tracking-wider"
                  disabled={tournamentTeams.length < 2}
                  data-testid="generate-bracket-button"
                >
                  <Zap className="w-4 h-4 mr-1" />
                  Generate Bracket
                </Button>

                {bracket && (
                  <div className="space-y-2">
                    <Separator className="bg-[#141b50]" />
                    <p className={labelClass}>Record Results</p>
                    <ScrollArea className="max-h-48">
                      {bracket.rounds.map((round) =>
                        round.matchIds.map((matchId) => {
                          const match = bracket.matches[matchId];
                          if (!match || !match.teamA || !match.teamB || match.completed) return null;
                          return (
                            <div key={matchId} className="p-2 rounded-lg mb-2 border border-[#fbdd68]/10 bg-[rgba(225,48,108,0.05)]">
                              <p className="text-[10px] font-mono text-white/50 mb-1">{round.label}</p>
                              <div className="flex items-center gap-2">
                                <Button 
                                  size="sm"  className="flex-1 text-xs truncate border-[rgba(251,221,104,0.15)] hover:bg-[#f5d050] text-white"
                                  onClick={() => handleRecordResult(matchId, match.teamA.seed, 1, 0)}
                                  data-testid={`win-${matchId}-a`}
                                >
                                  {match.teamA.name}
                                </Button>
                                <span className="text-[10px] font-mono text-white/30">vs</span>
                                <Button 
                                  size="sm"  className="flex-1 text-xs truncate border-[rgba(251,221,104,0.15)] hover:bg-purple-500/10 text-purple-200"
                                  onClick={() => handleRecordResult(matchId, match.teamB.seed, 0, 1)}
                                  data-testid={`win-${matchId}-b`}
                                >
                                  {match.teamB.name}
                                </Button>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </ScrollArea>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Display Settings */}
          <Card className={cardClass}>
            <CardHeader className="pb-3">
              <CardTitle className={labelClass}>
                <Video className="h-3 w-3" /> Display
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="text-[10px] font-mono text-white/50 mb-1.5 block">ASPECT RATIO</label>
                <Tabs value={aspectRatio} onValueChange={setAspectRatio} data-testid="aspect-ratio-select">
                  <TabsList className="w-full bg-[#141b50]">
                    <TabsTrigger value="landscape" className="flex-1 text-xs data-[state=active]:bg-gradient-to-r data-[state=active]:from-orange-500/20 data-[state=active]:to-yellow-500/20 data-[state=active]:text-white" data-testid="aspect-landscape-option">
                      16:9 Live
                    </TabsTrigger>
                    <TabsTrigger value="portrait" className="flex-1 text-xs data-[state=active]:bg-[rgba(251,221,104,0.15)] data-[state=active]:text-white" data-testid="aspect-portrait-option">
                      9:16 Story
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              <div>
                <label className="text-[10px] font-mono text-white/50 mb-1.5 block">
                  ANIMATION SPEED: <span className="text-white">{animationSpeed}x</span>
                </label>
                <Slider
                  value={[animationSpeed]}
                  onValueChange={([v]) => setAnimationSpeed(v)}
                  min={0.5} max={3} step={0.25}
                  data-testid="animation-speed-slider"
                />
              </div>

              <div className="flex gap-2">
                <Button 
                  onClick={() => { setIsAnimating(false); setTimeout(() => setIsAnimating(true), 50); }}
                   size="sm" className="flex-1 border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-[#f5d050] text-white"
                  data-testid="replay-animation-button"
                >
                  <Play className="w-4 h-4 mr-1" /> Replay
                </Button>
                <Button 
                  onClick={() => setIsAnimating(!isAnimating)}
                   size="sm" className="flex-1 border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-purple-500/10 text-purple-300"
                  data-testid="pause-animation-button"
                >
                  {isAnimating ? <Pause className="w-4 h-4 mr-1" /> : <Play className="w-4 h-4 mr-1" />}
                  {isAnimating ? 'Pause' : 'Play'}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Export & Presets */}
          <Card className={cardClass}>
            <CardHeader className="pb-3">
              <CardTitle className={labelClass}>
                <Download className="h-3 w-3" /> Export & Presets
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Button 
                  onClick={handleExportPng}
                   size="sm" className="flex-1 border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-[#f5d050] text-white"
                  disabled={exporting}
                  data-testid="export-png-button"
                >
                  <Download className="w-4 h-4 mr-1" /> PNG
                </Button>
                <Button 
                  onClick={handleExportVideo}
                  size="sm" className="flex-1 btn-futuristic"
                  disabled={exporting}
                  data-testid="export-webm-button"
                >
                  <Film className="w-4 h-4 mr-1" /> MP4 Video
                </Button>
              </div>

              {/* QR Download */}
              <Button 
                onClick={handleShowQr}
                 size="sm" 
                className={`w-full ${qrUrl ? 'border-green-500/30 hover:border-green-500/50 hover:bg-green-500/10 text-green-300' : 'border-gray-500/20 text-gray-500'}`}
                disabled={!qrUrl}
                data-testid="qr-download-button"
              >
                <QrCode className="w-4 h-4 mr-1" /> {qrUrl ? 'Show QR for Phone Download' : 'Export first to get QR'}
              </Button>

              <Button 
                onClick={handleOpenLiveView}
                 size="sm" className="w-full border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-[#f5d050] text-white"
                data-testid="open-live-view-button"
              >
                <Maximize2 className="w-4 h-4 mr-1" /> Open Live View
              </Button>

              <Separator className="bg-[#141b50]" />

              <div className="flex gap-2">
                <Dialog open={showSavePreset} onOpenChange={setShowSavePreset}>
                  <DialogTrigger asChild>
                    <Button  size="sm" className="flex-1 border-[rgba(251,221,104,0.15)] hover:border-[#fbdd68]/50 hover:bg-purple-500/10 text-purple-300" data-testid="preset-save-button">
                      <Save className="w-4 h-4 mr-1" /> Save Preset
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="bg-[#111118] border-[rgba(251,221,104,0.15)] text-white">
                    <DialogHeader>
                      <DialogTitle className="font-['Inter'] tracking-wider">Save Animation Preset</DialogTitle>
                    </DialogHeader>
                    <Input
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      placeholder="Preset name..."
                      className="bg-[#141b50] border-[rgba(251,221,104,0.15)] text-white"
                      data-testid="preset-name-input"
                    />
                    <div className="text-xs space-y-1 font-mono text-white/50">
                      <p>Mode: <span className="text-white/70">{mode}</span></p>
                      <p>Aspect: <span className="text-white/70">{aspectRatio}</span></p>
                      <p>Speed: <span className="text-white/70">{animationSpeed}x</span></p>
                    </div>
                    <Button onClick={handleSavePreset} className="btn-futuristic font-['Inter'] tracking-wider" data-testid="confirm-save-preset">
                      Save
                    </Button>
                  </DialogContent>
                </Dialog>

                <Button 
                   size="sm" className="flex-1 border-orange-500/20 hover:border-orange-500/50 hover:bg-orange-500/10 text-orange-300"
                  onClick={handleLoadPresets}
                  data-testid="preset-load-button"
                >
                  Load Preset
                </Button>
              </div>

              {presets.length > 0 && (
                <ScrollArea className="max-h-32">
                  <div className="space-y-1">
                    {presets.map((p) => (
                      <div key={p.id} className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-[#141b50] transition-colors">
                        <button 
                          onClick={() => handleLoadPreset(p)}
                          className="flex-1 text-left text-xs font-medium truncate text-white/70 hover:text-white"
                        >
                          {p.name}
                        </button>
                        <Badge className="text-[10px] bg-[#141b50] text-white border-[rgba(251,221,104,0.15)]">{p.mode}</Badge>
                        <button 
                          onClick={() => handleDeletePreset(p.id)}
                          className="text-xs px-1 text-white/30 hover:text-red-400 transition-colors"
                        >
                          x
                        </button>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}

              {exportStatus && (
                <p className="text-xs text-center font-mono text-white/50" data-testid="export-status">
                  {exportStatus}
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Main Preview Area */}
        <div className="col-span-12 lg:col-span-8 xl:col-span-9">
          <div className="sticky top-16">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="h-px w-4 bg-[#fbdd68]" />
                <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white">
                  Preview — {mode === 'leaderboard' ? 'Leaderboard' : 'Tournament'} — {aspectRatio === 'landscape' ? '16:9' : '9:16'}
                </h2>
              </div>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[rgba(225,48,108,0.1)] border border-[rgba(251,221,104,0.15)]">
                <div className={`h-1.5 w-1.5 rounded-full ${isAnimating ? 'bg-green-400 animate-pulse' : 'bg-[#fbdd68]'}`} />
                <span className={`text-[10px] font-mono ${isAnimating ? 'text-green-400' : 'text-white'}`}>
                  {isAnimating ? 'ANIMATING' : 'STATIC'}
                </span>
              </div>
            </div>
            
            {/* Preview with glow */}
            <div className="relative">
              <div className="absolute -inset-4 bg-[rgba(251,221,104,0.03)] rounded-3xl blur-xl" />
              <div className="relative video-preview-glow rounded-xl overflow-hidden">
                <RenderStage aspectRatio={aspectRatio} ref={stageRef}>
                  {mode === 'leaderboard' ? (
                    <LeaderboardRender 
                      data={currentData}
                      aspectRatio={aspectRatio}
                      animationSpeed={animationSpeed}
                      isAnimating={isAnimating}
                    />
                  ) : (
                    <BracketRender 
                      bracket={bracket}
                      teams={tournamentTeams}
                      tournamentName={tournamentName}
                      tournamentYear={tournamentYear}
                      aspectRatio={aspectRatio}
                      animationSpeed={animationSpeed}
                      isAnimating={isAnimating}
                    />
                  )}
                </RenderStage>
              </div>
            </div>

            {!currentData && mode === 'leaderboard' && (
              <div className="mt-6 p-8 rounded-xl text-center border border-dashed border-[rgba(251,221,104,0.15)] bg-[rgba(225,48,108,0.03)]">
                <div className="h-16 w-16 rounded-2xl bg-[rgba(225,48,108,0.1)] flex items-center justify-center mx-auto mb-4 shadow-yellow-500/20 float">
                  <FolderSync className="w-8 h-8 text-white/40" />
                </div>
                <p className="font-['Inter'] tracking-wider text-white/80">No Data Loaded</p>
                <p className="text-sm mt-2 font-mono text-white/40">
                  // CLICK_FETCH_TO_PULL_SCORES
                </p>
              </div>
            )}

            {mode === 'tournament' && !bracket && (
              <div className="mt-6 p-8 rounded-xl text-center border border-dashed border-[rgba(251,221,104,0.15)] bg-[rgba(131,58,180,0.03)]">
                <div className="h-16 w-16 rounded-2xl bg-[rgba(131,58,180,0.1)] flex items-center justify-center mx-auto mb-4 shadow-yellow-500/20 float">
                  <Settings2 className="w-8 h-8 text-purple-500/40" />
                </div>
                <p className="font-['Inter'] tracking-wider text-white/80">No Bracket Generated</p>
                <p className="text-sm mt-2 font-mono text-purple-400/40">
                  // ENTER_TEAMS_AND_GENERATE
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-[#fbdd68]/10 relative z-10">
        <div className="px-6 py-4 flex items-center justify-between">
          <p className="text-[10px] text-white/20 font-mono">// BIG_HAT_ENTERTAINMENT • PHOENIX_AZ</p>
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
            <span className="text-[10px] text-green-400/60 font-mono">SYSTEM ONLINE</span>
          </div>
        </div>
      </footer>

      {/* QR Code Modal */}
      {showQr && qrUrl && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center" style={{ background: 'rgba(10, 10, 18, 0.92)' }}>
          <div className="relative glass-panel rounded-2xl p-8 max-w-sm w-full mx-4 text-center shadow-yellow-500/20">
            <button 
              onClick={() => setShowQr(false)}
              className="absolute top-4 right-4 text-white/50 hover:text-white transition-colors"
              data-testid="close-qr-modal"
            >
              <X className="w-5 h-5" />
            </button>
            <QrCode className="w-8 h-8 mx-auto mb-3" style={{ color: '#FCAF45' }} />
            <h3 className="font-['Inter'] tracking-wider text-lg mb-1" style={{ color: '#F4F2FF' }}>
              SCAN TO DOWNLOAD
            </h3>
            <p className="text-xs font-mono mb-6" style={{ color: 'rgba(225, 48, 108, 0.6)' }}>
              // OPEN_ON_PHONE_TO_SAVE
            </p>
            <div className="bg-[#fbdd68] rounded-xl p-4 inline-block mx-auto">
              <QRCodeSVG 
                value={qrUrl || ''}
                size={220}
                bgColor="#FFFFFF"
                fgColor="#000e2a"
                level="M"
              />
            </div>
            <p className="text-xs font-mono mt-4" style={{ color: 'rgba(244,242,255,0.4)' }}>
              Scan with your phone camera to download the file
            </p>
            <p className="text-[10px] font-mono mt-1 break-all px-4" style={{ color: 'rgba(244,242,255,0.2)' }}>
              {qrUrl}
            </p>
            <Button 
              onClick={() => setShowQr(false)}
              className="mt-4 btn-futuristic font-['Inter'] tracking-wider"
            >
              Done
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
