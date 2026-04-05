import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import axios from 'axios';
import {
  ArrowLeft, Play, ExternalLink, Monitor, MapPin, User, Calendar,
  Clock, Hash, FileText, ChevronRight, Maximize
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TRIVIA_PRESENTER_URL = 'https://quiz-presenter.emergent.host';

const ROUND_TYPE_COLORS = {
  MC: { bg: '#22c55e', label: 'Multiple Choice', icon: '?' },
  REG: { bg: '#ef4444', label: 'General Knowledge', icon: 'G' },
  MISC: { bg: '#3b82f6', label: 'Specific Topic', icon: 'S' },
  MYS: { bg: '#a855f7', label: 'Mystery', icon: 'M' },
  BIG: { bg: '#fbdd68', label: 'BIG Question', icon: 'B' },
};

export default function TriviaPresenterView() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const presId = searchParams.get('id');
  const [presentation, setPresentation] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (presId) loadPresentation();
  }, [presId]);

  const loadPresentation = async () => {
    try {
      const res = await axios.get(`${API}/trivia-viewer/${presId}`);
      setPresentation(res.data);
    } catch (err) {
      console.error('Failed to load presentation:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePresentLive = () => {
    // Store the presentation ID and open the editor
    localStorage.setItem('currentPresentationId', presId);
    navigate('/trivia/editor');
  };

  const handlePresentFullscreen = () => {
    localStorage.setItem('currentPresentationId', presId);
    navigate('/trivia/editor');
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-3" style={{ borderColor: '#fbdd68', borderTopColor: 'transparent' }} />
          <p className="text-sm" style={{ color: '#8892b0' }}>Loading presentation...</p>
        </div>
      </div>
    );
  }

  if (!presentation) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <div className="text-center">
          <p className="text-lg text-white mb-2">Presentation not found</p>
          <button onClick={() => navigate('/trivia')} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}>Back to Trivia</button>
        </div>
      </div>
    );
  }

  const roundTypes = presentation.roundTypes || [];
  const roundNames = presentation.roundNames || [];

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }}>
      {/* Header */}
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(0, 14, 42, 0.9)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/trivia')} className="p-2 rounded-lg hover:bg-white/5"><ArrowLeft size={20} style={{ color: '#fbdd68' }} /></button>
              <img src="/hat-logo.png" alt="BIG Hat" className="h-9 w-9 object-contain" />
              <div>
                <h1 className="text-lg font-bold text-white truncate max-w-md">{presentation.name}</h1>
                <p className="text-xs" style={{ color: '#8892b0' }}>Presentation Details</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={handlePresentLive} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold transition-all hover:shadow-lg" style={{ backgroundColor: '#fbdd68', color: '#000e2a', boxShadow: '0 0 15px rgba(251, 221, 104, 0.25)' }} data-testid="present-live-button">
                <Play size={16} />
                Present Live
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Presentation Info Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <InfoCard icon={MapPin} label="Location" value={presentation.location || 'Unknown'} color="#fbdd68" />
          <InfoCard icon={User} label="Host" value={presentation.host || presentation.createdBy} color="#5973F7" />
          <InfoCard icon={Hash} label="Rounds" value={`${presentation.numRounds || roundTypes.length}`} color="#22c55e" />
          <InfoCard icon={FileText} label="Total Slides" value={`~${presentation.totalSlides || 0}`} color="#a855f7" />
        </div>

        {/* Round Lineup */}
        <div className="mb-8">
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <ChevronRight size={20} style={{ color: '#fbdd68' }} />
            Round Lineup
          </h2>
          <div className="space-y-3">
            {roundTypes.map((type, idx) => {
              const conf = ROUND_TYPE_COLORS[type] || { bg: '#8892b0', label: type, icon: '?' };
              const name = roundNames[idx] || `Round ${idx + 1}`;
              const roundFile = presentation.roundFiles?.[idx];

              return (
                <div key={idx} className="flex items-center gap-4 p-4 rounded-xl transition-all hover:bg-white/[0.03]" style={{ background: 'linear-gradient(135deg, rgba(20, 27, 80, 0.5), rgba(10, 25, 64, 0.5))', border: `1px solid ${conf.bg}20` }}>
                  {/* Round Number */}
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: `${conf.bg}15`, border: `2px solid ${conf.bg}40` }}>
                    <span className="text-lg font-bold" style={{ color: conf.bg }}>{idx + 1}</span>
                  </div>

                  {/* Round Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full" style={{ backgroundColor: `${conf.bg}20`, color: conf.bg, border: `1px solid ${conf.bg}40` }}>
                        {conf.label}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-white truncate">{name}</h3>
                  </div>

                  {/* Slide Count */}
                  <div className="text-right shrink-0">
                    <span className="text-xs" style={{ color: '#8892b0' }}>{roundFile?.slideCount || '~12'} slides</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-4">
          <button onClick={handlePresentLive} className="flex-1 flex items-center justify-center gap-3 py-4 rounded-xl text-base font-bold transition-all hover:shadow-lg" style={{ backgroundColor: '#fbdd68', color: '#000e2a', boxShadow: '0 0 20px rgba(251, 221, 104, 0.2)' }} data-testid="present-full-button">
            <Monitor size={20} />
            Open in Trivia Presenter
          </button>
          <button onClick={() => navigate('/trivia')} className="px-8 py-4 rounded-xl text-sm font-medium transition-all" style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
            Back to Dashboard
          </button>
        </div>

        {/* Metadata */}
        <div className="mt-8 p-4 rounded-xl text-xs" style={{ backgroundColor: 'rgba(20, 27, 80, 0.3)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
          <div className="flex flex-wrap gap-6" style={{ color: '#8892b0' }}>
            <span>Created by: <strong className="text-white">{presentation.createdBy}</strong></span>
            <span>Date: <strong className="text-white">{new Date(presentation.createdAt).toLocaleDateString()}</strong></span>
            <span>ID: <strong className="text-white font-mono">{presentation.id?.slice(0, 8)}...</strong></span>
          </div>
        </div>
      </main>
    </div>
  );
}

function InfoCard({ icon: Icon, label, value, color }) {
  return (
    <div className="p-4 rounded-xl" style={{ background: 'linear-gradient(135deg, rgba(20, 27, 80, 0.5), rgba(10, 25, 64, 0.5))', border: '1px solid rgba(251, 221, 104, 0.1)' }}>
      <Icon size={18} style={{ color }} className="mb-2" />
      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: '#8892b0' }}>{label}</p>
      <p className="text-sm font-semibold text-white truncate">{value}</p>
    </div>
  );
}
