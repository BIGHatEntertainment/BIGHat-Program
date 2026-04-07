import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import axios from 'axios';
import {
  Video, ArrowLeft, Home, RefreshCw, MapPin, Calendar, User,
  Loader2, Download, Play, ChevronRight, Sparkles, Clock,
  CheckCircle2, AlertCircle, Settings
} from 'lucide-react';
import { toast } from '../../utils/toastCompat';

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

  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPres, setSelectedPres] = useState(null);
  const [preview, setPreview] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generatedVideo, setGeneratedVideo] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => { loadPresentations(); }, []);

  const loadPresentations = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/trivia-viewer/list`, { params: { userName, viewAll: true } });
      setPresentations(res.data);
    } catch { } finally { setLoading(false); }
  };

  const handleSelect = async (pres) => {
    setSelectedPres(pres);
    setGeneratedVideo(null);
    setPreview(null);
    setLoadingPreview(true);
    try {
      const [detailRes, triviaRes, previewRes] = await Promise.all([
        axios.get(`${API}/story-generator/presentation/${pres.id}`).catch(() => ({ data: {} })),
        axios.get(`${API}/trivia-viewer/${pres.id}`).catch(() => ({ data: {} })),
        axios.post(`${API}/story-generator/preview/${pres.id}`, {}, { timeout: 60000 }).catch(() => ({ data: { preview: null } }))
      ]);
      const merged = { ...pres, ...detailRes.data, ...triviaRes.data };
      setSelectedPres(merged);
      setPreview(previewRes.data.preview);
    } catch { } finally { setLoadingPreview(false); }
  };

  const handleGenerate = async () => {
    if (!selectedPres) return;
    try {
      setGenerating(true);
      toast({ title: 'Generating...', description: 'Creating your Instagram Story video. This may take ~20 seconds.' });
      
      // Start the generation job
      const startRes = await axios.post(`${API}/story-generator/generate/${selectedPres.id}`, {}, { timeout: 30000 });
      const jobId = startRes.data.jobId;
      
      if (!jobId) {
        // Direct response with filename
        if (startRes.data.filename) {
          setGeneratedVideo({ filename: startRes.data.filename, downloadUrl: `${API}/story-generator/download/${startRes.data.filename}` });
          toast({ title: 'Video Ready!' });
          setGenerating(false);
          return;
        }
        throw new Error('No job ID returned');
      }

      // Poll for job completion
      let attempts = 0;
      const maxAttempts = 60; // 60 * 2s = 2 minutes max
      const pollInterval = setInterval(async () => {
        attempts++;
        try {
          const statusRes = await axios.get(`${API}/story-generator/job-status/${jobId}`, { timeout: 10000 });
          const status = statusRes.data;
          
          if (status.status === 'completed' && status.result) {
            clearInterval(pollInterval);
            const filename = status.result.filename || status.filename;
            setGeneratedVideo({ filename, downloadUrl: `${API}/story-generator/download/${filename}` });
            toast({ title: 'Video Ready!', description: `Generated in ${status.result.duration || '~20'}s` });
            setGenerating(false);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            toast({ title: 'Error', description: status.error || 'Generation failed', variant: 'destructive' });
            setGenerating(false);
          } else if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            toast({ title: 'Timeout', description: 'Video generation is taking longer than expected. Try again.', variant: 'destructive' });
            setGenerating(false);
          }
        } catch {
          // Continue polling on transient errors
          if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            setGenerating(false);
          }
        }
      }, 2000);
      
    } catch (err) {
      toast({ title: 'Error', description: err.response?.data?.detail || 'Failed to start generation', variant: 'destructive' });
      setGenerating(false);
    }
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
            <button onClick={loadPresentations} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm" style={{ border: '1px solid rgba(251, 221, 104, 0.15)', color: '#fff' }}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        </header>

        <main className="max-w-6xl mx-auto px-6 py-10">
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
                      <div className="flex items-center gap-1.5 text-xs mb-3" style={{ color: '#8892b0' }}>
                        <MapPin size={11} /> {location}
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
            {/* Phone Preview */}
            <div className="w-[320px] rounded-3xl overflow-hidden mb-6" style={{ border: '2px solid rgba(251, 221, 104,0.3)', backgroundColor: '#000', aspectRatio: '9/16', maxHeight: '500px' }}>
              {loadingPreview ? (
                <div className="w-full h-full flex items-center justify-center">
                  <Loader2 size={32} className="animate-spin" style={{ color: '#fbdd68' }} />
                </div>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center p-8 relative" style={{ background: 'linear-gradient(180deg, #1a1a2e 0%, #000 100%)' }}>
                  <p className="text-[10px] uppercase tracking-[0.2em] mb-1" style={{ color: '#fbdd68' }}>Location</p>
                  <p className="text-xs uppercase tracking-[0.15em] mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>This Week At</p>
                  <div className="flex-1" />
                  <h2 className="text-2xl font-black uppercase tracking-wider text-center" style={{ color: '#fff', fontFamily: "'Space Grotesk', monospace" }}>
                    {location}
                  </h2>
                  {/* Corner marks */}
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
                <button onClick={() => window.open(generatedVideo.downloadUrl, '_blank')} className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold" style={{ backgroundColor: '#22c55e', color: '#000' }}>
                  <Download size={20} /> Download Story Video
                </button>
              ) : (
                <button onClick={handleGenerate} disabled={generating} className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold transition-all hover:shadow-lg disabled:opacity-50" style={{ backgroundColor: '#fbdd68', color: '#000', boxShadow: '0 0 30px rgba(251, 221, 104,0.2)' }}>
                  {generating ? <><Loader2 size={20} className="animate-spin" /> Generating...</> : <><Video size={20} /> Generate Video</>}
                </button>
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
