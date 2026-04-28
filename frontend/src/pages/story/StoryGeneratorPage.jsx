import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import axios from 'axios';
import {
  Video, ArrowLeft, Home, RefreshCw, MapPin, Calendar, User,
  Loader2, Download, Play, ChevronRight, Sparkles, Clock,
  CheckCircle2, AlertCircle, Settings, Music, Mic
} from 'lucide-react';
import { toast } from '../../utils/toastCompat';
import { QRCodeSVG } from 'qrcode.react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROUND_DOT_COLORS = {
  MC: '#22c55e', REG: '#ef4444', MISC: '#3b82f6', MYS: '#a855f7', BIG: '#eab308',
};
const ROUND_LABELS = {
  MC: 'Multiple Choice', REG: 'General', MISC: 'Specific', MYS: 'Mystery', BIG: 'BIG Question',
};

export default function StoryGeneratorPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userName = user?.name?.split(' ')[0]?.toLowerCase() || '';
  const fullName = user?.name || '';
  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';

  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPres, setSelectedPres] = useState(null);
  const [preview, setPreview] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generatedVideo, setGeneratedVideo] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [genProgress, setGenProgress] = useState({ step: '', progress: 0 });
  const [viewAll, setViewAll] = useState(false);
  const [eventMode, setEventMode] = useState(null); // null, 'bingo', or 'karaoke'
  const [assetImages, setAssetImages] = useState(null); // {locationUrl, hostUrl} from asset-urls

  useEffect(() => {
    if (isAdmin) setViewAll(true);
  }, [isAdmin]);

  useEffect(() => {
    if (user) loadPresentations();
  }, [user, viewAll]);

  const loadPresentations = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/trivia-viewer/list`, { params: { userName, viewAll: isAdmin ? viewAll : false, hostName: fullName } });
      setPresentations(res.data);
    } catch { } finally { setLoading(false); }
  };

  const handleSelect = async (pres) => {
    setSelectedPres(pres);
    setGeneratedVideo(null);
    setPreview(null);
    setAssetImages(null);
    setLoadingPreview(true);
    try {
      const [detailRes, triviaRes, previewRes, assetRes] = await Promise.all([
        axios.get(`${API}/story-generator/presentation/${pres.id}`).catch(() => ({ data: {} })),
        axios.get(`${API}/trivia-viewer/${pres.id}`).catch(() => ({ data: {} })),
        axios.post(`${API}/story-generator/preview/${pres.id}`, {}, { timeout: 60000 }).catch(() => ({ data: { preview: null } })),
        axios.get(`${API}/story-generator/asset-urls/${pres.id}`, { timeout: 60000 }).catch(() => ({ data: { assets: null } }))
      ]);
      const merged = { ...pres, ...detailRes.data, ...triviaRes.data };
      setSelectedPres(merged);
      setPreview(previewRes.data.preview);
      if (assetRes.data?.assets) {
        setAssetImages(assetRes.data.assets);
      }
    } catch { } finally { setLoadingPreview(false); }
  };

  const handleGenerate = async () => {
    if (!selectedPres) return;
    setGenerating(true);
    setGenProgress({ step: 'Starting generation...', progress: 5 });
    setGeneratedVideo(null);
    
    let jobId = null;
    
    // Retry the initial POST up to 3 times
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const startRes = await axios.post(`${API}/story-generator/generate/${selectedPres.id}`, {}, { timeout: 30000 });
        jobId = startRes.data.jobId;
        if (jobId) break;
        if (startRes.data.filename) {
          setGeneratedVideo({ filename: startRes.data.filename, downloadUrl: `${API}/story-generator/download/${startRes.data.filename}` });
          setGenerating(false);
          return;
        }
      } catch (err) {
        if (attempt === 3) {
          toast({ title: 'Error', description: err.response?.data?.detail || `Failed after ${attempt} attempts. Please try again.`, variant: 'destructive' });
          setGenerating(false);
          return;
        }
        await new Promise(r => setTimeout(r, 2000)); // Wait 2s before retry
      }
    }

    if (!jobId) {
      toast({ title: 'Error', description: 'Could not start video generation', variant: 'destructive' });
      setGenerating(false);
      return;
    }

    setGenProgress({ step: 'Processing...', progress: 10 });

    // Poll for job completion
    let attempts = 0;
    const maxAttempts = 90;
    while (attempts < maxAttempts) {
      attempts++;
      await new Promise(r => setTimeout(r, 2000));
      try {
        const statusRes = await axios.get(`${API}/story-generator/job-status/${jobId}`, { timeout: 10000 });
        const status = statusRes.data;
        
        setGenProgress({ step: status.step || 'Processing...', progress: status.progress || 10 });
        
        if (status.status === 'completed') {
          const filename = status.result?.filename || status.filename;
          if (filename) {
            setGeneratedVideo({ filename, downloadUrl: `${API}/story-generator/download/${filename}` });
            toast({ title: 'Video Ready!', description: `Generated in ${status.result?.duration || '~20'}s` });
          } else {
            toast({ title: 'Error', description: 'Video completed but no file was produced', variant: 'destructive' });
          }
          setGenerating(false);
          return;
        } else if (status.status === 'failed') {
          toast({ title: 'Error', description: status.error || 'Generation failed', variant: 'destructive' });
          setGenerating(false);
          return;
        }
      } catch (e) {
        // Continue polling on transient network errors
      }
    }
    toast({ title: 'Timeout', description: 'Video generation timed out. Try again.', variant: 'destructive' });
    setGenerating(false);
  };

  const cleanLocation = (loc) => {
    if (!loc) return 'Unknown';
    return loc.split('/').pop().replace(/^\d+_/, '').replace(/_/g, ' ');
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  };

  // ====== EVENT STORY BUILDER (Bingo/Karaoke) ======
  if (eventMode && !selectedPres) {
    return <EventStoryBuilder eventType={eventMode} onBack={() => setEventMode(null)} />;
  }

  // ====== LOBBY VIEW ======
  if (!selectedPres) {
    return (
      <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }}>
        {/* Header */}
        <header style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104,0.15)' }}>
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button onClick={() => navigate('/')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium" style={{ backgroundColor: '#fbdd68', color: '#000' }} data-testid="back-to-dashboard">
                <Home size={14} /> Exit
              </button>
              <span style={{ color: '#8892b0' }}>—</span>
              <div className="flex items-center gap-2">
                <Video size={24} style={{ color: '#fbdd68' }} />
                <div>
                  <h1 className="text-lg font-bold tracking-wider uppercase text-white" style={{ fontFamily: "'Space Grotesk', monospace" }}>Story Generator</h1>
                  <p className="text-[10px] uppercase tracking-[0.2em]" style={{ color: '#fbdd68' }}>// Select Presentation</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {isAdmin && (
                <label className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#8892b0' }}>
                  <input type="checkbox" checked={viewAll} onChange={(e) => setViewAll(e.target.checked)} className="accent-yellow-400" />
                  View All
                </label>
              )}
              <button onClick={loadPresentations} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#fff' }}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>
          </div>
        </header>

        <main className="max-w-6xl mx-auto px-6 py-10">
          {/* Event Type Buttons */}
          <div className="flex items-center gap-4 mb-8">
            <button
              onClick={() => setEventMode('bingo')}
              className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-bold transition-all hover:scale-[1.03] hover:shadow-lg"
              style={{ backgroundColor: '#a855f7', color: '#fff', boxShadow: '0 0 20px rgba(168,85,247,0.3)' }}
              data-testid="story-bingo-btn"
            >
              <Music size={16} /> Bingo Story
            </button>
            <button
              onClick={() => setEventMode('karaoke')}
              className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-bold transition-all hover:scale-[1.03] hover:shadow-lg"
              style={{ backgroundColor: '#ef4444', color: '#fff', boxShadow: '0 0 20px rgba(239,68,68,0.3)' }}
              data-testid="story-karaoke-btn"
            >
              <Mic size={16} /> Karaoke Story
            </button>
          </div>

          {/* Section Header */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles size={14} style={{ color: '#fbdd68' }} />
              <span className="text-[11px] uppercase tracking-[0.25em] font-bold" style={{ color: '#fbdd68' }}>Your Recent Presentations</span>
              <div className="flex-1 h-px ml-3" style={{ backgroundColor: '#fbdd68' }} />
            </div>
            <h2 className="text-4xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Select a <span style={{ color: '#fbdd68' }}>Presentation</span>
            </h2>
            <p className="mt-2 text-sm" style={{ color: '#8892b0' }}>
              Click on a presentation to generate an Instagram Story. The same presentations from your home screen are shown here.
            </p>
            {/* Stats */}
            <div className="flex items-center gap-6 mt-4">
              <span className="flex items-center gap-1.5 text-xs" style={{ color: '#8892b0' }}>
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#fbdd68' }} />
                {presentations.length} Presentations
              </span>
              <span className="flex items-center gap-1.5 text-xs" style={{ color: '#8892b0' }}>
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#a855f7' }} />
                9:16 Format
              </span>
              <span className="flex items-center gap-1.5 text-xs" style={{ color: '#8892b0' }}>
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#22c55e' }} />
                ~25s Duration
              </span>
            </div>
          </div>

          {/* Cards Grid */}
          {loading ? (
            <div className="text-center py-20"><Loader2 size={32} className="animate-spin mx-auto" style={{ color: '#fbdd68' }} /></div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {presentations.map(pres => {
                const location = cleanLocation(pres.location);
                const roundTypes = pres.roundTypes || [];
                return (
                  <div key={pres.id} onClick={() => handleSelect(pres)} className="cursor-pointer group rounded-2xl overflow-hidden transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl" style={{ border: '1px solid rgba(251, 221, 104, 0.08)' }} data-testid={`story-card-${pres.id}`}>
                    {/* Card Top - Venue Name */}
                    <div className="relative h-44 flex items-center justify-center overflow-hidden" style={{ background: 'linear-gradient(135deg, #141b50, #0a1940)' }}>
                      <div className="absolute inset-0 opacity-10" style={{ background: 'radial-gradient(circle at 30% 50%, rgba(251, 221, 104,0.3), transparent 60%)' }} />
                      <h3 className="text-3xl font-black uppercase tracking-wider text-center px-4 relative z-10" style={{ color: 'rgba(251, 221, 104, 0.25)', fontFamily: "'Space Grotesk', monospace", textShadow: '0 2px 20px rgba(0,0,0,0.5)' }}>
                        {location}
                      </h3>
                      {/* TRIVIA badge */}
                      <div className="absolute top-3 right-3 px-3 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider" style={{ backgroundColor: '#fbdd68', color: '#000' }}>
                        Trivia
                      </div>
                      {/* Date */}
                      <div className="absolute bottom-3 left-4 flex items-center gap-1.5 text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                        <Calendar size={12} /> {formatDate(pres.createdAt)}
                      </div>
                    </div>

                    {/* Card Bottom - Details */}
                    <div className="p-4" style={{ backgroundColor: '#141b50' }}>
                      <h4 className="text-sm font-bold text-white mb-1 truncate">{pres.name}</h4>
                      <div className="flex items-center gap-1.5 text-xs mb-1" style={{ color: '#8892b0' }}>
                        <MapPin size={11} /> {location}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs mb-3" style={{ color: '#fbdd68' }}>
                        <User size={11} /> Host: {pres.host || pres.createdBy || 'Unknown'}
                      </div>
                      {/* Round dots */}
                      <div className="flex items-center gap-1.5 mb-3">
                        {roundTypes.map((rt, i) => (
                          <div key={i} className="w-3 h-3 rounded-full" style={{ backgroundColor: ROUND_DOT_COLORS[rt] || '#6b7280' }} title={ROUND_LABELS[rt] || rt} />
                        ))}
                      </div>
                      {/* Footer */}
                      <div className="flex items-center justify-between">
                        <span className="text-xs" style={{ color: '#8892b0' }}>{pres.totalSlides || '~50'} slides</span>
                        <span className="text-xs font-semibold flex items-center gap-1 group-hover:text-[#fbdd68] transition-colors" style={{ color: '#8892b0' }}>
                          Generate <ChevronRight size={12} />
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>
    );
  }

  // ====== BUILDER VIEW ======
  const location = cleanLocation(selectedPres.location);
  const roundTypes = selectedPres.roundTypes || [];
  const roundNames = selectedPres.roundNames || [];

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }}>
      {/* Header */}
      <header style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104,0.15)' }}>
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => { setSelectedPres(null); setPreview(null); setGeneratedVideo(null); }} className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#fff' }}>
              <ArrowLeft size={14} /> Back
            </button>
            <button onClick={() => navigate('/')} className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium" style={{ backgroundColor: '#fbdd68', color: '#000' }}>
              <Home size={14} /> Exit
            </button>
            <span style={{ color: '#8892b0' }}>—</span>
            <div>
              <h1 className="text-lg font-bold tracking-wider uppercase text-white" style={{ fontFamily: "'Space Grotesk', monospace" }}>Story Generator</h1>
              <p className="text-[10px] uppercase tracking-[0.2em]" style={{ color: '#fbdd68' }}>// Create Your Trivia Story</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#8892b0' }}>
              <Settings size={12} /> 9:16
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="grid grid-cols-12 gap-8">
          {/* LEFT SIDEBAR - Presentation Info */}
          <div className="col-span-12 lg:col-span-3 space-y-4">
            {/* Presentation Card */}
            <div className="rounded-xl p-5" style={{ border: '1px solid rgba(251, 221, 104, 0.1)', backgroundColor: '#141b50' }}>
              <h3 className="text-sm font-bold text-white mb-4">{selectedPres.name}</h3>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm" style={{ color: '#8892b0' }}>
                  <MapPin size={14} style={{ color: '#fbdd68' }} /> {location}
                </div>
                <div className="flex items-center gap-2 text-sm" style={{ color: '#8892b0' }}>
                  <Calendar size={14} style={{ color: '#fbdd68' }} /> {formatDate(selectedPres.createdAt)}
                </div>
                <div className="flex items-center gap-2 text-sm" style={{ color: '#8892b0' }}>
                  <User size={14} style={{ color: '#fbdd68' }} /> {selectedPres.host || selectedPres.createdBy}
                </div>
              </div>
            </div>

            {/* Tonight's Rounds */}
            <div className="rounded-xl p-5" style={{ border: '1px solid rgba(251, 221, 104, 0.1)', backgroundColor: '#141b50' }}>
              <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold mb-4 flex items-center gap-2" style={{ color: '#8892b0' }}>
                <Sparkles size={12} /> Tonight's Rounds ({roundTypes.length})
              </h4>
              <div className="space-y-2">
                {roundTypes.map((rt, idx) => {
                  const name = roundNames[idx] || ROUND_LABELS[rt] || rt;
                  const cleanName = name.replace(/\.pptx$/i, '').replace(/_/g, ' ');
                  return (
                    <div key={idx} className="flex items-center gap-3 px-3 py-2.5 rounded-lg" style={{ border: '1px solid rgba(251, 221, 104, 0.06)', backgroundColor: '#141b50' }}>
                      <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: ROUND_DOT_COLORS[rt] || '#6b7280' }} />
                      <span className="text-sm text-white truncate">{cleanName}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* CENTER - Phone Preview & Video Timeline */}
          <div className="col-span-12 lg:col-span-6 flex flex-col items-center">
            {/* Phone Preview — shows actual location + host images */}
            <div className="w-[320px] rounded-3xl overflow-hidden mb-6" style={{ border: '2px solid rgba(251, 221, 104,0.3)', backgroundColor: '#000', aspectRatio: '9/16', maxHeight: '500px' }}>
              {loadingPreview ? (
                <div className="w-full h-full flex items-center justify-center">
                  <Loader2 size={32} className="animate-spin" style={{ color: '#fbdd68' }} />
                </div>
              ) : assetImages?.locationUrl || assetImages?.hostUrl ? (
                <div className="w-full h-full flex flex-col">
                  {/* Location image — top half */}
                  <div className="flex-1 relative overflow-hidden">
                    {assetImages.locationUrl ? (
                      <img src={assetImages.locationUrl} alt="Location" className="absolute inset-0 w-full h-full object-cover" />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'linear-gradient(180deg, #141b50, #0a1940)' }}>
                        <span className="text-lg font-bold uppercase" style={{ color: 'rgba(251,221,104,0.3)' }}>{location}</span>
                      </div>
                    )}
                    <div className="absolute bottom-2 left-2 px-2 py-1 rounded text-[9px] font-bold uppercase" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: '#fbdd68' }}>
                      Location — {preview?.location?.duration || 3}s
                    </div>
                  </div>
                  {/* Host GIF — bottom half */}
                  <div className="flex-1 relative overflow-hidden" style={{ borderTop: '2px solid rgba(251,221,104,0.3)' }}>
                    {assetImages.hostUrl ? (
                      <img src={assetImages.hostUrl} alt="Host" className="absolute inset-0 w-full h-full object-cover" />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'linear-gradient(180deg, #0a1940, #000e2a)' }}>
                        <span className="text-sm" style={{ color: '#8892b0' }}>Host GIF not found</span>
                      </div>
                    )}
                    <div className="absolute bottom-2 left-2 px-2 py-1 rounded text-[9px] font-bold uppercase" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: '#ef4444' }}>
                      Host GIF — {preview?.host?.duration || 3}s
                    </div>
                  </div>
                </div>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center p-8 relative" style={{ background: 'linear-gradient(180deg, #1a1a2e 0%, #000 100%)' }}>
                  <p className="text-[10px] uppercase tracking-[0.2em] mb-1" style={{ color: '#fbdd68' }}>Location</p>
                  <p className="text-xs uppercase tracking-[0.15em] mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>This Week At</p>
                  <div className="flex-1" />
                  <h2 className="text-2xl font-black uppercase tracking-wider text-center" style={{ color: '#fff', fontFamily: "'Space Grotesk', monospace" }}>
                    {location}
                  </h2>
                  <div className="absolute top-8 left-8 w-6 h-6 border-t-2 border-l-2" style={{ borderColor: 'rgba(251, 221, 104,0.5)' }} />
                  <div className="absolute top-8 right-8 w-6 h-6 border-t-2 border-r-2" style={{ borderColor: 'rgba(251, 221, 104,0.5)' }} />
                  <div className="absolute bottom-8 left-8 w-6 h-6 border-b-2 border-l-2" style={{ borderColor: 'rgba(251, 221, 104,0.5)' }} />
                  <div className="absolute bottom-8 right-8 w-6 h-6 border-b-2 border-r-2" style={{ borderColor: 'rgba(251, 221, 104,0.5)' }} />
                </div>
              )}
            </div>

            {/* Video Timeline */}
            <div className="w-full max-w-md rounded-xl p-5" style={{ backgroundColor: '#141b50', border: '1px solid rgba(251, 221, 104, 0.1)' }}>
              <h4 className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2 text-white">
                <Video size={14} style={{ color: '#fbdd68' }} /> Video Timeline
              </h4>
              <div className="flex items-center gap-3 mb-4">
                <TimelineChip label="Location" duration={preview?.location?.duration || 3} color="#fbdd68" icon={MapPin} />
                <TimelineChip label="Host" duration={preview?.host?.duration || 3} color="#ef4444" icon={User} />
                <TimelineChip label="Rounds" duration={preview?.rounds?.duration || 19} color="#a855f7" icon={Sparkles} />
              </div>
              {/* Progress Bar */}
              <div className="w-full h-2 rounded-full overflow-hidden flex mb-2" style={{ backgroundColor: '#0a1940' }}>
                <div style={{ width: '12%', backgroundColor: '#fbdd68' }} />
                <div style={{ width: '12%', backgroundColor: '#ef4444' }} />
                <div style={{ width: '76%', backgroundColor: '#a855f7' }} />
              </div>
              <div className="flex justify-between text-[10px]" style={{ color: '#8892b0' }}>
                <span>0:00</span>
                <span className="font-bold" style={{ color: '#fbdd68' }}>Total: {preview?.totalDuration || 25}s</span>
              </div>
            </div>

            {/* Generate Button */}
            <div className="w-full max-w-md mt-6">
              {generatedVideo ? (
                <>
                  <button onClick={async () => {
                    try {
                      const res = await axios.get(generatedVideo.downloadUrl, { responseType: 'blob', timeout: 60000 });
                      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'video/mp4' }));
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = generatedVideo.filename || 'story.mp4';
                      document.body.appendChild(a);
                      a.click();
                      window.URL.revokeObjectURL(url);
                      a.remove();
                    } catch (e) {
                      toast({ title: 'Download failed', description: 'Try generating again', variant: 'destructive' });
                    }
                  }} className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold" style={{ backgroundColor: '#22c55e', color: '#000' }}>
                    <Download size={20} /> Download Story Video
                  </button>
                </>
              ) : (
                <>
                  <button onClick={handleGenerate} disabled={generating} className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold transition-all hover:shadow-lg disabled:opacity-50" style={{ backgroundColor: '#fbdd68', color: '#000', boxShadow: '0 0 30px rgba(251, 221, 104,0.2)' }}>
                    {generating ? <><Loader2 size={20} className="animate-spin" /> Generating...</> : <><Video size={20} /> Generate Video</>}
                  </button>
                  {/* Progress Indicator */}
                  {generating && (
                    <div className="mt-4 space-y-2">
                      <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: '#0a1940' }}>
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${genProgress.progress}%`, backgroundColor: '#fbdd68' }} />
                      </div>
                      <p className="text-center text-xs" style={{ color: '#fbdd68' }}>{genProgress.step}</p>
                      <p className="text-center text-[10px]" style={{ color: '#8892b0' }}>{genProgress.progress}% complete</p>
                    </div>
                  )}
                </>
              )}
              <p className="text-center text-[10px] mt-2" style={{ color: '#8892b0' }}>MP4 format for Instagram Stories. ~25s video.</p>
            </div>
          </div>

          {/* RIGHT - Empty for now (matches screenshot layout) */}
          <div className="col-span-12 lg:col-span-3" />
        </div>
      </main>
    </div>
  );
}

function TimelineChip({ label, duration, color, icon: Icon }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ backgroundColor: '#0a1940', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
      <Icon size={12} style={{ color }} />
      <span className="text-xs text-white">{label}</span>
      <span className="text-[10px] font-bold" style={{ color }}>{duration}s</span>
    </div>
  );
}

// ====== EVENT STORY BUILDER (Bingo & Karaoke) ======
function EventStoryBuilder({ eventType, onBack }) {
  const navigate = useNavigate();
  const [locations, setLocations] = useState([]);
  const [hosts, setHosts] = useState([]);
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [selectedHost, setSelectedHost] = useState(null);
  const [loading, setLoading] = useState(true);
  const [previewImages, setPreviewImages] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState(0);
  const [generatedVideo, setGeneratedVideo] = useState(null);
  const [qrUrl, setQrUrl] = useState(null);

  const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
  const eventLabel = eventType === 'bingo' ? 'Music Bingo' : 'Karaoke';
  const accentColor = eventType === 'bingo' ? '#a855f7' : '#ef4444';

  // Load available assets from SharePoint
  useEffect(() => {
    loadAssets();
  }, [eventType]);

  const loadAssets = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/story-generator/event-assets/${eventType}`, { timeout: 30000 });
      if (res.data.success) {
        setLocations(res.data.locations || []);
        setHosts(res.data.hosts || []);
      }
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to load assets from SharePoint', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  // Fetch preview when both selections are made
  useEffect(() => {
    if (selectedLocation && selectedHost) {
      fetchPreview();
    } else {
      setPreviewImages(null);
    }
  }, [selectedLocation, selectedHost]);

  const fetchPreview = async () => {
    if (!selectedLocation || !selectedHost) return;
    setLoadingPreview(true);
    try {
      const res = await axios.post(`${API}/story-generator/event-preview`, {
        event_type: eventType,
        location_id: selectedLocation.id,
        location_drive_id: selectedLocation.drive_id,
        host_id: selectedHost.id,
        host_drive_id: selectedHost.drive_id,
        host_is_gif: selectedHost.is_gif !== false,
      }, { timeout: 60000 });
      if (res.data.success) {
        setPreviewImages(res.data);
      }
    } catch (err) {
      toast({ title: 'Preview Error', description: 'Could not load preview images', variant: 'destructive' });
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedLocation || !selectedHost) return;
    setGenerating(true);
    setGenProgress(5);
    setGeneratedVideo(null);
    setQrUrl(null);

    try {
      // Start generation job
      const startRes = await axios.post(`${API}/story-generator/generate-event-video`, {
        event_type: eventType,
        location_id: selectedLocation.id,
        location_drive_id: selectedLocation.drive_id,
        location_name: selectedLocation.name,
        host_id: selectedHost.id,
        host_drive_id: selectedHost.drive_id,
        host_name: selectedHost.name,
        host_is_gif: selectedHost.is_gif !== false,
      }, { timeout: 30000 });

      const jobId = startRes.data.job_id;
      if (!jobId) throw new Error('No job ID returned');

      // Poll for completion
      let attempts = 0;
      while (attempts < 60) {
        attempts++;
        await new Promise(r => setTimeout(r, 2000));
        const statusRes = await axios.get(`${API}/story-generator/assemble-video/status/${jobId}`, { timeout: 10000 });
        const status = statusRes.data;

        setGenProgress(status.progress || 10);

        if (status.status === 'complete') {
          setGeneratedVideo(status.result);
          toast({ title: 'Video Ready!', description: '20s event story generated successfully.' });

          // Store for QR download
          try {
            const storeRes = await axios.post(`${API}/story-generator/store-temp`, {
              video_data: status.result.video_data,
              filename: status.result.filename?.replace('.mp4', '') || `${eventType}_story`,
            }, { timeout: 30000 });
            if (storeRes.data.success) {
              setQrUrl(`${process.env.REACT_APP_BACKEND_URL}/api/story-generator/qr-download/${storeRes.data.file_id}`);
            }
          } catch {}
          
          setGenerating(false);
          return;
        } else if (status.status === 'error') {
          throw new Error(status.error || 'Generation failed');
        }
      }
      throw new Error('Generation timed out');
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Video generation failed', variant: 'destructive' });
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (!generatedVideo?.video_data) return;
    const a = document.createElement('a');
    a.href = generatedVideo.video_data;
    a.download = generatedVideo.filename || `${eventType}_story.mp4`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }}>
      {/* Header */}
      <header style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104,0.15)' }}>
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={onBack} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#fff' }} data-testid="event-story-back">
              <ArrowLeft size={14} /> Back
            </button>
            <button onClick={() => navigate('/')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium" style={{ backgroundColor: '#fbdd68', color: '#000' }}>
              <Home size={14} /> Exit
            </button>
            <span style={{ color: '#8892b0' }}>—</span>
            <div className="flex items-center gap-2">
              {eventType === 'bingo' ? <Music size={22} style={{ color: accentColor }} /> : <Mic size={22} style={{ color: accentColor }} />}
              <div>
                <h1 className="text-lg font-bold tracking-wider uppercase text-white" style={{ fontFamily: "'Space Grotesk', monospace" }}>{eventLabel} Story</h1>
                <p className="text-[10px] uppercase tracking-[0.2em]" style={{ color: accentColor }}>// Select Location & Host</p>
              </div>
            </div>
          </div>
          <button onClick={loadAssets} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#fff' }} data-testid="event-refresh-btn">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {loading ? (
          <div className="text-center py-20">
            <Loader2 size={32} className="animate-spin mx-auto" style={{ color: accentColor }} />
            <p className="mt-4 text-sm" style={{ color: '#8892b0' }}>Loading {eventLabel} assets from SharePoint...</p>
          </div>
        ) : (
          <div className="grid grid-cols-12 gap-8">
            {/* LEFT — Dropdowns */}
            <div className="col-span-12 lg:col-span-4 space-y-6">
              {/* Location Dropdown */}
              <div className="rounded-xl p-5" style={{ border: '1px solid rgba(251, 221, 104, 0.1)', backgroundColor: '#141b50' }}>
                <label className="text-[10px] uppercase tracking-[0.2em] font-bold flex items-center gap-2 mb-3" style={{ color: accentColor }}>
                  <MapPin size={12} /> Location
                </label>
                <select
                  value={selectedLocation?.id || ''}
                  onChange={(e) => {
                    const loc = locations.find(l => l.id === e.target.value);
                    setSelectedLocation(loc || null);
                  }}
                  className="w-full px-4 py-3 rounded-lg text-sm font-medium focus:outline-none"
                  style={{ backgroundColor: '#0a1940', color: '#fff', border: '1px solid rgba(251, 221, 104, 0.15)' }}
                  data-testid="event-location-select"
                >
                  <option value="">Select a location...</option>
                  {locations.map(loc => (
                    <option key={loc.id} value={loc.id}>{loc.name}</option>
                  ))}
                </select>
                <p className="mt-2 text-[10px]" style={{ color: '#8892b0' }}>{locations.length} locations available</p>
              </div>

              {/* Host Dropdown */}
              <div className="rounded-xl p-5" style={{ border: '1px solid rgba(251, 221, 104, 0.1)', backgroundColor: '#141b50' }}>
                <label className="text-[10px] uppercase tracking-[0.2em] font-bold flex items-center gap-2 mb-3" style={{ color: accentColor }}>
                  <User size={12} /> Host
                </label>
                <select
                  value={selectedHost?.id || ''}
                  onChange={(e) => {
                    const host = hosts.find(h => h.id === e.target.value);
                    setSelectedHost(host || null);
                  }}
                  className="w-full px-4 py-3 rounded-lg text-sm font-medium focus:outline-none"
                  style={{ backgroundColor: '#0a1940', color: '#fff', border: '1px solid rgba(251, 221, 104, 0.15)' }}
                  data-testid="event-host-select"
                >
                  <option value="">Select a host...</option>
                  {hosts.map(h => (
                    <option key={h.id} value={h.id}>{h.name}</option>
                  ))}
                </select>
                <p className="mt-2 text-[10px]" style={{ color: '#8892b0' }}>{hosts.length} hosts available</p>
              </div>

              {/* Timeline Info */}
              <div className="rounded-xl p-5" style={{ border: '1px solid rgba(251, 221, 104, 0.1)', backgroundColor: '#141b50' }}>
                <h4 className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2 text-white">
                  <Video size={14} style={{ color: '#fbdd68' }} /> Video Timeline
                </h4>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2" style={{ color: '#8892b0' }}>
                      <MapPin size={11} style={{ color: '#fbdd68' }} /> Location
                    </span>
                    <span style={{ color: '#fbdd68' }}>10s</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2" style={{ color: '#8892b0' }}>
                      <User size={11} style={{ color: accentColor }} /> Host GIF
                    </span>
                    <span style={{ color: accentColor }}>10s</span>
                  </div>
                  <div className="w-full h-2 rounded-full overflow-hidden flex mt-2" style={{ backgroundColor: '#0a1940' }}>
                    <div style={{ width: '50%', backgroundColor: '#fbdd68' }} />
                    <div style={{ width: '50%', backgroundColor: accentColor }} />
                  </div>
                  <div className="flex justify-between text-[10px]" style={{ color: '#8892b0' }}>
                    <span>0:00</span>
                    <span className="font-bold" style={{ color: '#fbdd68' }}>Total: 20s</span>
                  </div>
                </div>
              </div>
            </div>

            {/* CENTER — Preview + Generate */}
            <div className="col-span-12 lg:col-span-8 flex flex-col items-center">
              {/* Phone Preview */}
              <div className="w-[300px] rounded-3xl overflow-hidden mb-6" style={{ border: `2px solid ${accentColor}40`, backgroundColor: '#000', aspectRatio: '9/16', maxHeight: '480px' }}>
                {loadingPreview ? (
                  <div className="w-full h-full flex items-center justify-center">
                    <Loader2 size={32} className="animate-spin" style={{ color: accentColor }} />
                  </div>
                ) : previewImages?.locationImage ? (
                  <div className="w-full h-full flex flex-col">
                    <div className="flex-1 relative overflow-hidden">
                      <img src={previewImages.locationImage} alt="Location" className="absolute inset-0 w-full h-full object-cover" />
                      <div className="absolute bottom-2 left-2 px-2 py-1 rounded text-[9px] font-bold uppercase" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: '#fbdd68' }}>
                        Location — 10s
                      </div>
                    </div>
                    <div className="flex-1 relative overflow-hidden" style={{ borderTop: `2px solid ${accentColor}` }}>
                      <img src={previewImages.hostImage} alt="Host" className="absolute inset-0 w-full h-full object-cover" />
                      <div className="absolute bottom-2 left-2 px-2 py-1 rounded text-[9px] font-bold uppercase" style={{ backgroundColor: 'rgba(0,0,0,0.7)', color: accentColor }}>
                        Host GIF — 10s
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center p-6" style={{ background: 'linear-gradient(180deg, #1a1a2e, #000)' }}>
                    <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: `${accentColor}20` }}>
                      {eventType === 'bingo' ? <Music size={28} style={{ color: accentColor }} /> : <Mic size={28} style={{ color: accentColor }} />}
                    </div>
                    <p className="text-xs text-center" style={{ color: '#8892b0' }}>
                      {selectedLocation && selectedHost
                        ? 'Loading preview...'
                        : 'Select a location and host to see preview'}
                    </p>
                  </div>
                )}
              </div>

              {/* Generate/Download Area */}
              <div className="w-full max-w-md">
                {generatedVideo ? (
                  <div className="space-y-4">
                    <button
                      onClick={handleDownload}
                      className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold"
                      style={{ backgroundColor: '#22c55e', color: '#000' }}
                      data-testid="event-download-btn"
                    >
                      <Download size={20} /> Download {eventLabel} Story
                    </button>
                    {/* QR Code */}
                    {qrUrl && (
                      <div className="flex flex-col items-center gap-3 p-4 rounded-xl" style={{ backgroundColor: '#141b50', border: '1px solid rgba(251, 221, 104, 0.1)' }}>
                        <p className="text-[10px] uppercase tracking-[0.2em] font-bold" style={{ color: '#8892b0' }}>Scan to Download on Phone</p>
                        <div className="p-3 bg-white rounded-xl">
                          <QRCodeSVG value={qrUrl} size={140} />
                        </div>
                        <p className="text-[10px]" style={{ color: '#8892b0' }}>Expires in 1 hour</p>
                      </div>
                    )}
                    <button
                      onClick={() => { setGeneratedVideo(null); setQrUrl(null); }}
                      className="w-full text-center text-xs py-2 rounded-lg"
                      style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.1)' }}
                    >
                      Generate Another
                    </button>
                  </div>
                ) : (
                  <div>
                    <button
                      onClick={handleGenerate}
                      disabled={generating || !selectedLocation || !selectedHost}
                      className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold transition-all hover:shadow-lg disabled:opacity-50"
                      style={{ backgroundColor: accentColor, color: '#fff', boxShadow: `0 0 30px ${accentColor}40` }}
                      data-testid="event-generate-btn"
                    >
                      {generating ? <><Loader2 size={20} className="animate-spin" /> Generating...</> : <><Video size={20} /> Generate {eventLabel} Story</>}
                    </button>
                    {generating && (
                      <div className="mt-4 space-y-2">
                        <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: '#0a1940' }}>
                          <div className="h-full rounded-full transition-all duration-500" style={{ width: `${genProgress}%`, backgroundColor: accentColor }} />
                        </div>
                        <p className="text-center text-xs" style={{ color: accentColor }}>{genProgress}% complete</p>
                      </div>
                    )}
                    {(!selectedLocation || !selectedHost) && (
                      <p className="text-center text-[10px] mt-3" style={{ color: '#8892b0' }}>Select both a location and host to generate</p>
                    )}
                    <p className="text-center text-[10px] mt-2" style={{ color: '#8892b0' }}>MP4 format for Instagram Stories. 20s video.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
