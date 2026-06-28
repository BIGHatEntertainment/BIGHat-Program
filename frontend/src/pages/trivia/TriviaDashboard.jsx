import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import axios from 'axios';
import BIGHatFileButtons from '../../components/BIGHatFileButtons';
import {
  HelpCircle, Play, Trash2, Calendar, MapPin, User, Clock, ExternalLink,
  ChevronDown, ChevronRight, ArrowLeft, BarChart3, Filter, Search, Shield, RefreshCw, AlertTriangle
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TRIVIA_PRESENTER_URL = 'https://quiz-presenter.emergent.host';

const ROUND_TYPE_COLORS = {
  MC: { bg: '#22c55e', label: 'Multiple Choice' },
  REG: { bg: '#ef4444', label: 'General' },
  MISC: { bg: '#3b82f6', label: 'Specific' },
  MYS: { bg: '#a855f7', label: 'Mystery' },
  BIG: { bg: '#fbdd68', label: 'BIG Question' },
};

export default function TriviaDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [presentations, setPresentations] = useState([]);
  const [roundHistory, setRoundHistory] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('presentations');
  const [locationFilter, setLocationFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedLocation, setExpandedLocation] = useState(null);

  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';
  const userName = user?.name?.split(' ')[0]?.toLowerCase() || '';
  const fullName = user?.name || '';

  // Non-admins can't view all — only see their own hosted presentations
  const [viewAll, setViewAll] = useState(false);

  // Store userName for compatibility
  useEffect(() => {
    if (userName) localStorage.setItem('userName', userName);
    // Admins default to viewAll
    if (isAdmin) setViewAll(true);
  }, [userName, isAdmin]);

  useEffect(() => {
    if (user) loadData();
  }, [viewAll, user]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [presRes, statsRes] = await Promise.all([
        axios.get(`${API}/trivia-viewer/list`, { params: { userName, viewAll: isAdmin ? viewAll : false, hostName: fullName } }),
        axios.get(`${API}/admin/stats`, { params: { userName } }),
      ]);
      setPresentations(presRes.data);
      setStats(statsRes.data);

      if (isAdmin) {
        const historyRes = await axios.get(`${API}/admin/round-usage`, { params: { userName } });
        // Group by location
        const grouped = {};
        for (const r of historyRes.data) {
          const loc = r.location || r.locationName || 'Unknown';
          if (!grouped[loc]) grouped[loc] = { _id: loc, count: 0, rounds: [] };
          grouped[loc].count++;
          grouped[loc].rounds.push(r);
        }
        setRoundHistory(Object.values(grouped));
      }
    } catch (err) {
      console.error('Failed to load trivia data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remove this presentation from the lobby? Round history will be preserved.')) return;
    try {
      await axios.post(`${API}/trivia-viewer/hide/${id}`);
      setPresentations(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error('Hide failed:', err);
    }
  };

  const handlePresent = (presId) => {
    // Navigate to the in-app presenter view with full details
    navigate(`/trivia/present?id=${presId}`);
  };

  const filteredPresentations = presentations.filter(p => {
    if (searchTerm && !p.name?.toLowerCase().includes(searchTerm.toLowerCase()) && !p.location?.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  const filteredHistory = roundHistory.filter(h => {
    if (locationFilter && !h._id?.toLowerCase().includes(locationFilter.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }} data-testid="trivia-dashboard">
      {/* Header */}
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/')} className="p-2 rounded-lg hover:bg-white/5">
                <ArrowLeft size={20} style={{ color: '#fbdd68' }} />
              </button>
              <img src="/hat-logo.png" alt="BIG Hat" className="h-10 w-10 object-contain" />
              <div>
                <h1 className="text-xl font-bold" style={{ color: '#fbdd68' }}>Trivia Presenter</h1>
                <p className="text-xs" style={{ color: '#8892b0' }}>Manage & present trivia shows</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {stats && (
                <div className="hidden sm:flex items-center gap-4">
                  <StatChip label="Shows" value={stats.totalPresentations} />
                  <StatChip label="Rounds Used" value={stats.totalRoundUsage} />
                </div>
              )}
              {/* .bighat import lives in the header so it's reachable even
                  when the user has zero presentations yet. Trivia
                  presentations are always built via Build Wizard or
                  Round Roulette — there is no direct-play path; an
                  imported round lands in the library and the host
                  picks it up from there. */}
              <BIGHatFileButtons type="presentation" onImported={() => loadData()} />
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          <TabButton active={activeTab === 'presentations'} onClick={() => setActiveTab('presentations')} icon={Play} label="Presentations" />
          {isAdmin && <TabButton active={activeTab === 'history'} onClick={() => setActiveTab('history')} icon={BarChart3} label="Round History" />}
          {isAdmin && <TabButton active={activeTab === 'admin'} onClick={() => setActiveTab('admin')} icon={Shield} label="Trivia Admin" />}
        </div>

        {/* Presentations Tab */}
        {activeTab === 'presentations' && (
          <div>
            {/* Search & Filter Bar */}
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#8892b0' }} />
                <input
                  type="text"
                  placeholder="Search presentations..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm text-white outline-none"
                  style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.15)' }}
                  data-testid="trivia-search"
                />
              </div>
              {isAdmin && (
              <label className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs cursor-pointer" style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
                <input type="checkbox" checked={viewAll} onChange={(e) => setViewAll(e.target.checked)} className="accent-yellow-400" />
                <span style={{ color: '#8892b0' }}>View All</span>
              </label>
              )}
            </div>

            {loading ? (
              <div className="text-center py-12">
                <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-3" style={{ borderColor: '#fbdd68', borderTopColor: 'transparent' }} />
                <p style={{ color: '#8892b0' }}>Loading presentations...</p>
              </div>
            ) : filteredPresentations.length === 0 ? (
              <div className="text-center py-12 glass-card rounded-xl">
                <HelpCircle size={48} className="mx-auto mb-3 opacity-40" style={{ color: '#8892b0' }} />
                <p style={{ color: '#8892b0' }}>No trivia presentations found</p>
                <p className="text-xs mt-1" style={{ color: '#8892b0', opacity: 0.6 }}>Use the Build Wizard or Round Roulette from the dashboard to create one</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredPresentations.map(pres => (
                  <PresentationCard key={pres.id} pres={pres} onDelete={handleDelete} onPresent={handlePresent} isAdmin={isAdmin} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Round History Tab (Admin Only) */}
        {activeTab === 'history' && isAdmin && (
          <div data-testid="round-history-section">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex-1 relative">
                <Filter size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#8892b0' }} />
                <input
                  type="text"
                  placeholder="Filter by location..."
                  value={locationFilter}
                  onChange={(e) => setLocationFilter(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm text-white outline-none"
                  style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.15)' }}
                  data-testid="location-filter"
                />
              </div>
            </div>

            {filteredHistory.length === 0 ? (
              <div className="text-center py-12 glass-card rounded-xl">
                <BarChart3 size={48} className="mx-auto mb-3 opacity-40" style={{ color: '#8892b0' }} />
                <p style={{ color: '#8892b0' }}>No round usage history found</p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredHistory.map((loc) => (
                  <LocationRoundHistory
                    key={loc._id}
                    location={loc._id}
                    rounds={loc.rounds}
                    count={loc.count}
                    expanded={expandedLocation === loc._id}
                    onToggle={() => setExpandedLocation(expandedLocation === loc._id ? null : loc._id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Trivia Admin Tab */}
        {activeTab === 'admin' && isAdmin && (
          <TriviaAdminPanel userName={userName} onRefresh={loadData} />
        )}
      </main>
    </div>
  );
}

function StatChip({ label, value }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs" style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.1)' }}>
      <span style={{ color: '#8892b0' }}>{label}:</span>
      <span className="font-semibold" style={{ color: '#fbdd68' }}>{value}</span>
    </div>
  );
}

function TabButton({ active, onClick, icon: Icon, label }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all"
      style={{
        backgroundColor: active ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)',
        color: active ? '#fbdd68' : '#8892b0',
        border: `1px solid ${active ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}`
      }}
    >
      <Icon size={16} /> {label}
    </button>
  );
}

function PresentationCard({ pres, onDelete, onPresent, isAdmin }) {
  const createdDate = new Date(pres.createdAt);
  const roundTypes = pres.roundTypes || pres.roundFiles?.map(r => r.type) || [];
  const roundNames = pres.roundNames || [];

  return (
    <div className="glass-card rounded-xl p-5 group" data-testid={`trivia-pres-${pres.id}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <HelpCircle size={16} style={{ color: '#fbdd68' }} />
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: '#fbdd68' }}>
            {pres.numRounds || roundTypes.length} Rounds
          </span>
        </div>
        {isAdmin && (
          <button onClick={() => onDelete(pres.id)} className="p-1 rounded-lg hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`delete-trivia-${pres.id}`}>
            <Trash2 size={14} style={{ color: '#ef4444' }} />
          </button>
        )}
      </div>

      <h4 className="text-sm font-semibold text-white mb-1 truncate">{pres.name}</h4>

      <div className="space-y-1.5 mb-3">
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <MapPin size={12} />
          <span>{pres.location || 'Unknown'}</span>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: '#fbdd68' }}>
          <User size={12} />
          <span>Host: {pres.host || pres.createdBy}</span>
        </div>
        {isAdmin && pres.createdBy && pres.host && pres.createdBy !== pres.host && (
          <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
            <span className="ml-4">Built by: {pres.createdBy}</span>
          </div>
        )}
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <Calendar size={12} />
          <span>{createdDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
        </div>
      </div>

      {/* Round Lineup */}
      {roundNames.length > 0 && (
        <div className="mb-3 space-y-1">
          {roundNames.slice(0, 6).map((name, idx) => {
            const type = roundTypes[idx] || '';
            const conf = ROUND_TYPE_COLORS[type] || { bg: '#8892b0' };
            return (
              <div key={idx} className="flex items-center gap-2 text-[11px]">
                <span className="w-4 text-center font-bold" style={{ color: conf.bg }}>{idx + 1}</span>
                <span className="font-bold uppercase w-8" style={{ color: conf.bg, fontSize: '9px' }}>{type}</span>
                <span className="text-white truncate flex-1">{name}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Round Type Badges */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {roundTypes.map((rt, idx) => {
          const conf = ROUND_TYPE_COLORS[rt] || { bg: '#8892b0', label: rt };
          return (
            <span key={idx} className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full" style={{ backgroundColor: `${conf.bg}20`, color: conf.bg, border: `1px solid ${conf.bg}40` }}>
              {rt}
            </span>
          );
        })}
      </div>

      {/* Present Button */}
      <button
        onClick={() => onPresent(pres.id)}
        className="w-full py-2.5 rounded-lg font-bold text-sm transition-all hover:shadow-lg flex items-center justify-center gap-2"
        style={{ backgroundColor: '#fbdd68', color: '#000e2a', boxShadow: '0 0 10px rgba(251, 221, 104, 0.2)' }}
        data-testid={`present-trivia-${pres.id}`}
      >
        <Play size={16} />
        Open Presentation
      </button>
    </div>
  );
}

function LocationRoundHistory({ location, rounds, count, expanded, onToggle }) {
  const roundsByType = {};
  rounds.forEach(r => {
    const type = r.roundType || 'Unknown';
    if (!roundsByType[type]) roundsByType[type] = [];
    roundsByType[type].push(r);
  });

  // Clean location name for display
  const displayName = location ? location.split('/').pop().replace(/^\d+_/, '') : 'Unknown';

  return (
    <div className="glass-card rounded-xl overflow-hidden" data-testid={`location-history-${displayName}`}>
      <button onClick={onToggle} className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 transition-colors">
        <div className="flex items-center gap-3">
          <MapPin size={18} style={{ color: '#fbdd68' }} />
          <div className="text-left">
            <h4 className="text-sm font-semibold text-white">{displayName}</h4>
            <p className="text-xs" style={{ color: '#8892b0' }}>{count} rounds used</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex gap-1.5">
            {Object.entries(roundsByType).map(([type, items]) => {
              const conf = ROUND_TYPE_COLORS[type] || { bg: '#8892b0' };
              return (
                <span key={type} className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ backgroundColor: `${conf.bg}20`, color: conf.bg }}>
                  {type}: {items.length}
                </span>
              );
            })}
          </div>
          {expanded ? <ChevronDown size={16} style={{ color: '#8892b0' }} /> : <ChevronRight size={16} style={{ color: '#8892b0' }} />}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-4 border-t" style={{ borderColor: 'rgba(251, 221, 104, 0.1)' }}>
          <div className="mt-3 space-y-4">
            {Object.entries(roundsByType).map(([type, items]) => {
              const conf = ROUND_TYPE_COLORS[type] || { bg: '#8892b0', label: type };
              return (
                <div key={type}>
                  <h5 className="text-xs font-bold uppercase mb-2 flex items-center gap-2" style={{ color: conf.bg }}>
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: conf.bg }} />
                    {conf.label} ({items.length})
                  </h5>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {items.map((r, idx) => {
                      const usedDate = r.usedDate ? new Date(r.usedDate) : null;
                      return (
                        <div key={idx} className="flex items-center justify-between px-3 py-2 rounded-lg text-xs" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)' }}>
                          <span className="text-white truncate flex-1">{r.roundFileName || r.roundFile?.split('/').pop()?.replace('.pptx', '') || 'Unknown'}</span>
                          <div className="flex items-center gap-3 shrink-0 ml-2">
                            <span style={{ color: '#8892b0' }}>{r.usedBy}</span>
                            {usedDate && !isNaN(usedDate) && <span style={{ color: '#8892b0' }}>{usedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


function TriviaAdminPanel({ userName, onRefresh }) {
  const [adminUsage, setAdminUsage] = useState([]);
  const [adminStats, setAdminStats] = useState(null);
  const [adminLoading, setAdminLoading] = useState(true);
  const [adminFilter, setAdminFilter] = useState('');
  const [scoreFiles, setScoreFiles] = useState([]);
  const [adminSubTab, setAdminSubTab] = useState('rounds');

  useEffect(() => {
    loadAdminData();
  }, []);

  const loadAdminData = async () => {
    setAdminLoading(true);
    try {
      const [usageRes, statsRes, scoresRes] = await Promise.all([
        axios.get(`${API}/admin/round-usage`, { params: { userName } }),
        axios.get(`${API}/admin/stats`, { params: { userName } }),
        axios.get(`${API}/scores/files`).catch(() => ({ data: [] })),
      ]);
      setAdminUsage(usageRes.data);
      setAdminStats(statsRes.data);
      setScoreFiles(scoresRes.data || []);
    } catch (err) {
      console.error('Admin data load failed:', err);
    } finally {
      setAdminLoading(false);
    }
  };

  const handleReleaseRound = async (usageId) => {
    if (!window.confirm('Release this round back into the selection pool?')) return;
    try {
      await axios.delete(`${API}/admin/round-usage/${usageId}`, { params: { userName } });
      loadAdminData();
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Release failed:', err);
    }
  };

  const handleReleasePresentationRounds = async (presentationId, presentationName) => {
    if (!window.confirm(`Release ALL rounds from "${presentationName}"?`)) return;
    try {
      await axios.delete(`${API}/admin/round-usage/by-presentation/${presentationId}`, { params: { userName } });
      loadAdminData();
      if (onRefresh) onRefresh();
    } catch (err) {
      console.error('Release failed:', err);
    }
  };

  const handleCleanupExpired = async () => {
    if (!window.confirm('Remove all expired round usage records?')) return;
    try {
      const res = await axios.post(`${API}/admin/cleanup-expired`, null, { params: { userName } });
      alert(`Cleaned up ${res.data.deletedCount} expired records`);
      loadAdminData();
    } catch (err) {
      console.error('Cleanup failed:', err);
    }
  };

  // Group by presentation
  const byPresentation = {};
  adminUsage.filter(u => {
    if (adminFilter && !u.location?.toLowerCase().includes(adminFilter.toLowerCase()) && !u.roundFileName?.toLowerCase().includes(adminFilter.toLowerCase())) return false;
    return true;
  }).forEach(u => {
    const key = u.presentationId || 'unknown';
    if (!byPresentation[key]) byPresentation[key] = { name: u.presentationName || 'Unknown', location: u.locationName || u.location || '', rounds: [] };
    byPresentation[key].rounds.push(u);
  });

  if (adminLoading) {
    return (
      <div className="text-center py-12">
        <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-3" style={{ borderColor: '#fbdd68', borderTopColor: 'transparent' }} />
        <p style={{ color: '#8892b0' }}>Loading admin data...</p>
      </div>
    );
  }

  const handleDeleteScoreFile = async (fileId, fileName) => {
    if (!window.confirm(`Delete score file "${fileName}"?`)) return;
    try {
      await axios.delete(`${API}/scores/files/${fileId}`);
      loadAdminData();
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  return (
    <div data-testid="trivia-admin-panel">
      {/* Admin Stats */}
      {adminStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <AdminStatCard label="Total Records" value={adminStats.totalUsageRecords} color="#fbdd68" />
          <AdminStatCard label="Active" value={adminStats.activeRecords} color="#22c55e" />
          <AdminStatCard label="Expired" value={adminStats.expiredRecords} color="#ef4444" />
          <AdminStatCard label="Score Files" value={scoreFiles.reduce((sum, f) => sum + f.fileCount, 0)} color="#5973F7" />
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-2 mb-6">
        <button onClick={() => setAdminSubTab('rounds')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all" style={{ backgroundColor: adminSubTab === 'rounds' ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)', color: adminSubTab === 'rounds' ? '#fbdd68' : '#8892b0', border: `1px solid ${adminSubTab === 'rounds' ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
          Round Usage
        </button>
        <button onClick={() => setAdminSubTab('scores')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all" style={{ backgroundColor: adminSubTab === 'scores' ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)', color: adminSubTab === 'scores' ? '#fbdd68' : '#8892b0', border: `1px solid ${adminSubTab === 'scores' ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
          Score Files ({scoreFiles.reduce((sum, f) => sum + f.fileCount, 0)})
        </button>
      </div>

      {adminSubTab === 'rounds' && (
      <>
      {/* Action Buttons */}
      <div className="flex gap-3 mb-6">
        <button onClick={handleCleanupExpired} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
          <RefreshCw size={14} /> Cleanup Expired
        </button>
        <div className="flex-1 relative">
          <Filter size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#8892b0' }} />
          <input type="text" placeholder="Filter rounds..." value={adminFilter} onChange={(e) => setAdminFilter(e.target.value)} className="w-full pl-10 pr-4 py-2 rounded-lg text-sm text-white outline-none" style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.15)' }} />
        </div>
      </div>

      {/* Rounds by Presentation */}
      <div className="space-y-3">
        {Object.entries(byPresentation).map(([presId, pres]) => (
          <div key={presId} className="glass-card rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid rgba(251, 221, 104, 0.1)' }}>
              <div>
                <h4 className="text-sm font-semibold text-white">{pres.name}</h4>
                <p className="text-xs" style={{ color: '#8892b0' }}>{pres.location} - {pres.rounds.length} rounds</p>
              </div>
              <button onClick={() => handleReleasePresentationRounds(presId, pres.name)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:bg-red-500/20" style={{ color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }} data-testid={`release-all-${presId}`}>
                <Trash2 size={12} /> Release All
              </button>
            </div>
            <div className="px-5 py-2 space-y-1">
              {pres.rounds.map((r, idx) => {
                const conf = ROUND_TYPE_COLORS[r.roundType] || { bg: '#8892b0' };
                const usedDate = r.usedDate ? new Date(r.usedDate) : null;
                return (
                  <div key={idx} className="flex items-center justify-between py-1.5 text-xs" style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <div className="flex items-center gap-3">
                      <span className="font-bold uppercase w-10" style={{ color: conf.bg }}>{r.roundType}</span>
                      <span className="text-white">{r.roundFileName || 'Unknown'}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span style={{ color: '#8892b0' }}>{r.usedBy}</span>
                      {usedDate && !isNaN(usedDate) && <span style={{ color: '#8892b0' }}>{usedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>}
                      {r.isExpired && <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ backgroundColor: 'rgba(239, 68, 68, 0.2)', color: '#ef4444' }}>Expired</span>}
                      <button onClick={() => handleReleaseRound(r.id)} className="p-1 rounded hover:bg-red-500/20 transition-colors" title="Release round" data-testid={`release-round-${r.id}`}>
                        <Trash2 size={12} style={{ color: '#ef4444' }} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      </>
      )}

      {/* Score Files Tab */}
      {adminSubTab === 'scores' && (
        <div className="space-y-4">
          {scoreFiles.length === 0 ? (
            <div className="rounded-xl p-8 text-center" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
              <p style={{ color: '#8892b0' }}>No score files found on SharePoint</p>
            </div>
          ) : (
            scoreFiles.map(loc => (
              <div key={loc.location} className="glass-card rounded-xl overflow-hidden">
                <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid rgba(251, 221, 104, 0.1)' }}>
                  <div className="flex items-center gap-2">
                    <MapPin size={16} style={{ color: '#fbdd68' }} />
                    <h4 className="text-sm font-semibold text-white">{loc.location}</h4>
                    <span className="text-xs" style={{ color: '#8892b0' }}>{loc.fileCount} files</span>
                  </div>
                </div>
                <div className="px-5 py-2 space-y-1">
                  {loc.files.map(f => (
                    <div key={f.id} className="flex items-center justify-between py-1.5 text-xs" style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                      <span className="text-white">{f.name}</span>
                      <div className="flex items-center gap-3">
                        <span style={{ color: '#8892b0' }}>{f.modified ? new Date(f.modified).toLocaleDateString() : ''}</span>
                        <button onClick={() => handleDeleteScoreFile(f.id, f.name)} className="p-1 rounded hover:bg-red-500/20">
                          <Trash2 size={12} style={{ color: '#ef4444' }} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function AdminStatCard({ label, value, color }) {
  return (
    <div className="p-4 rounded-xl" style={{ background: 'linear-gradient(135deg, rgba(20, 27, 80, 0.5), rgba(10, 25, 64, 0.5))', border: `1px solid ${color}20` }}>
      <p className="text-[10px] uppercase tracking-wider" style={{ color: '#8892b0' }}>{label}</p>
      <p className="text-2xl font-bold mt-1" style={{ color }}>{value}</p>
    </div>
  );
}
