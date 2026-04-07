import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import axios from 'axios';
import {
  Video, ArrowLeft, Play, Download, Image as ImageIcon, Upload,
  Loader2, CheckCircle2, AlertCircle, Trash2, RefreshCw, MapPin,
  User, Calendar, ChevronRight, Sparkles, Film, Clock
} from 'lucide-react';
import { toast } from '../../utils/toastCompat';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROUND_COLORS = {
  MC: { bg: '#22c55e', label: 'Multiple Choice' },
  REG: { bg: '#ef4444', label: 'General' },
  MISC: { bg: '#3b82f6', label: 'Specific' },
  MYS: { bg: '#a855f7', label: 'Mystery' },
  BIG: { bg: '#eab308', label: 'BIG Question' },
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

  // Assets
  const [showAssets, setShowAssets] = useState(false);
  const [assets, setAssets] = useState({ locations: [], hosts: [], backgrounds: [] });
  const [uploadingAsset, setUploadingAsset] = useState(false);
  const [refreshingAssets, setRefreshingAssets] = useState(false);

  useEffect(() => {
    loadPresentations();
  }, []);

  const loadPresentations = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/trivia-viewer/list`, { params: { userName, viewAll: true } });
      setPresentations(res.data);
    } catch (err) {
      console.error('Failed to load:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadAssets = async (refresh = false) => {
    try {
      if (refresh) setRefreshingAssets(true);
      const res = await axios.get(`${API}/story-generator/assets`, { params: { refresh } });
      setAssets(res.data);
    } catch (err) {
      console.error('Assets load failed:', err);
    } finally {
      setRefreshingAssets(false);
    }
  };

  const handleSelectPresentation = async (pres) => {
    setSelectedPres(pres);
    setGeneratedVideo(null);
    setPreview(null);
    setLoadingPreview(true);
    try {
      const [detailRes, previewRes] = await Promise.all([
        axios.get(`${API}/story-generator/presentation/${pres.id}`),
        axios.post(`${API}/story-generator/preview/${pres.id}`, {}, { timeout: 60000 })
      ]);
      setSelectedPres(detailRes.data);
      setPreview(previewRes.data.preview);
    } catch (err) {
      console.error('Preview failed:', err);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedPres) return;
    try {
      setGenerating(true);
      toast({ title: 'Generating...', description: 'Creating your Instagram story. This may take a minute.' });
      const res = await axios.post(`${API}/story-generator/generate/${selectedPres.id}`, {}, { timeout: 300000 });
      if (res.data.success) {
        setGeneratedVideo({
          filename: res.data.filename,
          downloadUrl: `${API}/story-generator/download/${res.data.filename}`
        });
        toast({ title: 'Video Ready!', description: 'Your Instagram story has been generated.' });
      }
    } catch (err) {
      toast({ title: 'Error', description: err.response?.data?.detail || 'Failed to generate video', variant: 'destructive' });
    } finally {
      setGenerating(false);
    }
  };

  const handleUploadAsset = async (event, assetType) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      setUploadingAsset(true);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('asset_type', assetType);
      await axios.post(`${API}/story-generator/upload-asset`, formData, { timeout: 60000 });
      toast({ title: 'Uploaded', description: `${assetType} asset uploaded` });
      loadAssets();
    } catch {
      toast({ title: 'Error', description: 'Upload failed', variant: 'destructive' });
    } finally {
      setUploadingAsset(false);
      event.target.value = '';
    }
  };

  const handleDeleteAsset = async (assetType, assetId) => {
    if (!window.confirm('Delete this asset?')) return;
    try {
      await axios.delete(`${API}/story-generator/assets/${assetType}/${assetId}`);
      loadAssets();
    } catch {
      toast({ title: 'Error', description: 'Delete failed', variant: 'destructive' });
    }
  };

  // ====== LOBBY VIEW (no presentation selected) ======
  if (!selectedPres) {
    return (
      <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)' }}>
        {/* Header */}
        <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(26, 26, 46, 0.9)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(255, 193, 7, 0.2)' }}>
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/')} className="p-2 rounded-lg hover:bg-white/5" data-testid="back-to-dashboard">
                <ArrowLeft size={20} style={{ color: '#FFC107' }} />
              </button>
              <Video size={28} style={{ color: '#FFC107' }} />
              <div>
                <h1 className="text-xl font-bold" style={{ color: '#FFC107' }}>Instagram Story Generator</h1>
                <p className="text-xs" style={{ color: '#94a3b8' }}>Create 25-second stories from trivia presentations</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => { setShowAssets(!showAssets); if (!showAssets) loadAssets(); }} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all" style={{ color: showAssets ? '#FFC107' : '#94a3b8', backgroundColor: showAssets ? 'rgba(255, 193, 7, 0.15)' : 'rgba(255,255,255,0.05)', border: `1px solid ${showAssets ? 'rgba(255, 193, 7, 0.3)' : 'rgba(255,255,255,0.1)'}` }}>
                <ImageIcon size={16} /> Manage Assets
              </button>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Assets Panel (toggled) */}
          {showAssets && (
            <div className="mb-8 p-6 rounded-2xl animate-fade-in" style={{ background: 'linear-gradient(135deg, rgba(42, 42, 42, 0.8), rgba(26, 26, 46, 0.8))', border: '1px solid rgba(255, 193, 7, 0.2)' }}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold" style={{ color: '#FFC107' }}>Assets Manager</h3>
                <button onClick={() => { setRefreshingAssets(true); loadAssets(true); }} className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs" style={{ color: '#FFC107', border: '1px solid rgba(255, 193, 7, 0.3)' }}>
                  <RefreshCw size={12} className={refreshingAssets ? 'animate-spin' : ''} /> Refresh from SharePoint
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {['location', 'host', 'background'].map(type => (
                  <AssetList key={type} type={type} assets={assets[`${type}s`] || []} onUpload={handleUploadAsset} onDelete={handleDeleteAsset} uploading={uploadingAsset} />
                ))}
              </div>
            </div>
          )}

          {/* Presentation Cards Grid */}
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Film size={20} style={{ color: '#FFC107' }} />
            Select a Presentation
          </h2>

          {loading ? (
            <div className="text-center py-16">
              <Loader2 size={32} className="animate-spin mx-auto mb-3" style={{ color: '#FFC107' }} />
              <p style={{ color: '#94a3b8' }}>Loading presentations...</p>
            </div>
          ) : presentations.length === 0 ? (
            <div className="text-center py-16 rounded-2xl" style={{ background: 'rgba(42, 42, 42, 0.5)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <Video size={48} className="mx-auto mb-3 opacity-30" style={{ color: '#94a3b8' }} />
              <p style={{ color: '#94a3b8' }}>No presentations found</p>
              <p className="text-xs mt-1" style={{ color: '#64748b' }}>Build a trivia show first using the Build Wizard or Round Roulette</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {presentations.map(pres => (
                <PresentationCard key={pres.id} pres={pres} onSelect={() => handleSelectPresentation(pres)} />
              ))}
            </div>
          )}
        </main>
      </div>
    );
  }

  // ====== STORY BUILDER VIEW (presentation selected) ======
  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)' }}>
      {/* Header */}
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(26, 26, 46, 0.9)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(255, 193, 7, 0.2)' }}>
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => { setSelectedPres(null); setPreview(null); setGeneratedVideo(null); }} className="p-2 rounded-lg hover:bg-white/5">
              <ArrowLeft size={20} style={{ color: '#FFC107' }} />
            </button>
            <Sparkles size={24} style={{ color: '#FFC107' }} />
            <div>
              <h1 className="text-lg font-bold text-white truncate max-w-md">{selectedPres.name}</h1>
              <p className="text-xs" style={{ color: '#94a3b8' }}>Story Builder</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left: Presentation Info */}
          <div>
            <div className="p-5 rounded-2xl mb-6" style={{ background: 'rgba(42, 42, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)' }}>
              <h3 className="text-sm font-bold uppercase tracking-wider mb-4" style={{ color: '#FFC107' }}>Presentation Details</h3>
              <div className="space-y-2 mb-4">
                <div className="flex items-center gap-2 text-sm" style={{ color: '#94a3b8' }}><MapPin size={14} style={{ color: '#FFC107' }} /> {selectedPres.location || 'Unknown'}</div>
                <div className="flex items-center gap-2 text-sm" style={{ color: '#94a3b8' }}><User size={14} style={{ color: '#FFC107' }} /> {selectedPres.host || selectedPres.createdBy}</div>
                <div className="flex items-center gap-2 text-sm" style={{ color: '#94a3b8' }}><Calendar size={14} style={{ color: '#FFC107' }} /> {selectedPres.createdAt ? new Date(selectedPres.createdAt).toLocaleDateString() : ''}</div>
              </div>
              {/* Rounds */}
              <h4 className="text-xs font-bold uppercase mb-2" style={{ color: '#94a3b8' }}>Rounds ({selectedPres.numRounds || selectedPres.roundTypes?.length || 0})</h4>
              <div className="space-y-2">
                {(selectedPres.roundTypes || []).map((type, idx) => {
                  const conf = ROUND_COLORS[type] || { bg: '#6b7280', label: type };
                  const name = (selectedPres.roundNames || [])[idx] || `Round ${idx + 1}`;
                  return (
                    <div key={idx} className="flex items-center justify-between px-4 py-2.5 rounded-lg" style={{ backgroundColor: conf.bg }}>
                      <span className="text-white text-sm font-semibold">{conf.label}</span>
                      <span className="text-white text-sm truncate ml-4">{name}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right: Preview & Generate */}
          <div>
            {/* Preview Timeline */}
            {loadingPreview ? (
              <div className="text-center py-12 rounded-2xl" style={{ background: 'rgba(42, 42, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)' }}>
                <Loader2 size={28} className="animate-spin mx-auto mb-3" style={{ color: '#FFC107' }} />
                <p style={{ color: '#94a3b8' }}>Generating preview...</p>
              </div>
            ) : preview ? (
              <div className="p-5 rounded-2xl mb-6" style={{ background: 'rgba(42, 42, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)' }}>
                <h3 className="font-bold mb-4 flex items-center gap-2" style={{ color: '#FFC107' }}>
                  <Video size={18} />
                  Story Timeline ({preview.totalDuration}s)
                </h3>
                <div className="space-y-3">
                  <TimelineSegment label={`Location: ${preview.location?.name || ''}`} duration={preview.location?.duration} hasAsset={preview.location?.hasAsset} color="#1657E8" icon="location" />
                  <TimelineSegment label={`Host: ${preview.host?.name || ''}`} duration={preview.host?.duration} hasAsset={preview.host?.hasAsset} color="#16213e" icon="host" />
                  <TimelineSegment label={`Rounds (${preview.rounds?.items?.length || 0})`} duration={preview.rounds?.duration} hasAsset={preview.rounds?.hasBackground} color="#0a0a1a" icon="rounds" />
                </div>
                {(!preview.location?.hasAsset || !preview.host?.hasAsset || !preview.rounds?.hasBackground) && (
                  <div className="mt-3 p-3 rounded-lg" style={{ backgroundColor: 'rgba(255, 193, 7, 0.1)', border: '1px solid rgba(255, 193, 7, 0.2)' }}>
                    <p className="text-xs flex items-center gap-2" style={{ color: '#FFC107' }}>
                      <AlertCircle size={14} /> Some assets are missing. Placeholder images will be used.
                    </p>
                  </div>
                )}
              </div>
            ) : null}

            {/* Generated Video */}
            {generatedVideo && (
              <div className="p-5 rounded-2xl mb-6" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                <h3 className="font-bold mb-3 flex items-center gap-2" style={{ color: '#22c55e' }}>
                  <CheckCircle2 size={18} /> Video Ready!
                </h3>
                <button onClick={() => window.open(generatedVideo.downloadUrl, '_blank')} className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold" style={{ backgroundColor: '#22c55e', color: '#000' }}>
                  <Download size={16} /> Download Story Video
                </button>
              </div>
            )}

            {/* Generate Button */}
            <button onClick={handleGenerate} disabled={generating || !preview} className="w-full flex items-center justify-center gap-3 py-4 rounded-2xl text-base font-bold transition-all hover:shadow-lg disabled:opacity-50" style={{ backgroundColor: '#FFC107', color: '#000', boxShadow: '0 0 25px rgba(255, 193, 7, 0.3)' }}>
              {generating ? (
                <><Loader2 size={20} className="animate-spin" /> Generating Story...</>
              ) : (
                <><Sparkles size={20} /> Generate Instagram Story</>
              )}
            </button>

            <div className="mt-3 text-center">
              <p className="text-xs" style={{ color: '#64748b' }}>
                <Clock size={10} className="inline mr-1" /> Takes about 30-60 seconds to generate
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function PresentationCard({ pres, onSelect }) {
  const roundTypes = pres.roundTypes || [];
  const createdDate = pres.createdAt ? new Date(pres.createdAt) : null;

  return (
    <div onClick={onSelect} className="group cursor-pointer rounded-2xl p-5 transition-all duration-300 hover:scale-[1.02]" style={{ background: 'linear-gradient(135deg, rgba(42, 42, 42, 0.8), rgba(26, 26, 46, 0.8))', border: '1px solid rgba(255, 193, 7, 0.15)' }} data-testid={`story-pres-${pres.id}`}>
      {/* Top row */}
      <div className="flex items-start justify-between mb-3">
        <Video size={20} style={{ color: '#FFC107' }} />
        <ChevronRight size={16} className="opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: '#FFC107' }} />
      </div>

      <h4 className="text-sm font-bold text-white mb-2 truncate group-hover:text-[#FFC107] transition-colors">{pres.name}</h4>

      <div className="space-y-1.5 mb-3">
        <div className="flex items-center gap-2 text-xs" style={{ color: '#94a3b8' }}>
          <MapPin size={11} /> <span>{pres.location || 'Unknown'}</span>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: '#94a3b8' }}>
          <User size={11} /> <span>{pres.host || pres.createdBy}</span>
        </div>
        {createdDate && (
          <div className="flex items-center gap-2 text-xs" style={{ color: '#94a3b8' }}>
            <Calendar size={11} /> <span>{createdDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
          </div>
        )}
      </div>

      {/* Round badges */}
      <div className="flex flex-wrap gap-1.5">
        {roundTypes.map((rt, idx) => {
          const conf = ROUND_COLORS[rt] || { bg: '#6b7280' };
          return <span key={idx} className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full text-white" style={{ backgroundColor: conf.bg }}>{rt}</span>;
        })}
      </div>

      {/* CTA */}
      <div className="mt-4 flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-bold transition-all opacity-80 group-hover:opacity-100" style={{ backgroundColor: 'rgba(255, 193, 7, 0.15)', color: '#FFC107', border: '1px solid rgba(255, 193, 7, 0.3)' }}>
        <Sparkles size={14} /> Create Story
      </div>
    </div>
  );
}

function TimelineSegment({ label, duration, hasAsset, color, icon }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-14 text-right text-xs" style={{ color: '#64748b' }}>{duration}s</div>
      <div className="flex-1 rounded-lg p-3 flex items-center justify-between" style={{ backgroundColor: color }}>
        <span className="text-white text-sm">{label}</span>
        {hasAsset ? <CheckCircle2 size={16} style={{ color: '#22c55e' }} /> : <AlertCircle size={16} style={{ color: '#FFC107' }} />}
      </div>
    </div>
  );
}

function AssetList({ type, assets, onUpload, onDelete, uploading }) {
  const label = type.charAt(0).toUpperCase() + type.slice(1);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold capitalize" style={{ color: '#94a3b8' }}>{label}s ({assets.length})</span>
        <label className="cursor-pointer">
          <input type="file" accept="image/*,.gif" className="hidden" onChange={(e) => onUpload(e, type)} disabled={uploading} />
          <span className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs cursor-pointer" style={{ color: '#FFC107', border: '1px solid rgba(255, 193, 7, 0.3)' }}>
            {uploading ? <Loader2 size={10} className="animate-spin" /> : <Upload size={10} />} Upload
          </span>
        </label>
      </div>
      <div className="max-h-40 overflow-y-auto space-y-1">
        {assets.length === 0 ? (
          <p className="text-xs" style={{ color: '#64748b' }}>No {type} assets</p>
        ) : assets.map(asset => (
          <div key={asset.id} className="flex items-center justify-between px-3 py-1.5 rounded-lg" style={{ backgroundColor: 'rgba(255,255,255,0.05)' }}>
            <div className="flex items-center gap-2">
              <ImageIcon size={12} style={{ color: '#94a3b8' }} />
              <span className="text-xs text-white truncate max-w-[120px]">{asset.name}</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: asset.source === 'sharepoint' ? 'rgba(22, 87, 232, 0.3)' : 'rgba(100,100,100,0.3)', color: asset.source === 'sharepoint' ? '#60a5fa' : '#94a3b8' }}>{asset.source || 'local'}</span>
            </div>
            <button onClick={() => onDelete(type, asset.id)} className="p-1 rounded hover:bg-red-500/20"><Trash2 size={10} style={{ color: '#ef4444' }} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
