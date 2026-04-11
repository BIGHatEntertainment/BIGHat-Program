import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Grid2X2, HelpCircle, Target, Search, Crown, Trash2, Download, FileText, Upload, CheckCircle, Loader2, Copy, Shield, Check, X } from "lucide-react";
import { Button } from "../../components/ui/button";
import { toast } from "sonner";
import { useAuth } from "../../context/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROUND_TYPES = [
  {
    id: "MC",
    name: "Multiple Choice",
    description: "Classic 4-option trivia. 10 Questions.",
    icon: Grid2X2,
    cardClass: "round-card-mc",
    badgeClass: "badge-mc",
    color: "#22c55e",
  },
  {
    id: "REG",
    name: "General Round",
    description: "Standard Q&A format. 10 Questions.",
    icon: HelpCircle,
    cardClass: "round-card-reg",
    badgeClass: "badge-reg",
    color: "#ef4444",
  },
  {
    id: "MISC",
    name: "Specific / Misc",
    description: "Theme-based rapid fire. 10 Questions.",
    icon: Target,
    cardClass: "round-card-misc",
    badgeClass: "badge-misc",
    color: "#3b82f6",
  },
  {
    id: "MYS",
    name: "Mystery Round",
    description: "9 Clues + 1 Theme Question.",
    icon: Search,
    cardClass: "round-card-mys",
    badgeClass: "badge-mys",
    color: "#a855f7",
  },
  {
    id: "BIG",
    name: "The BIG Question",
    description: "One question, many answers. High stakes.",
    icon: Crown,
    cardClass: "round-card-big",
    badgeClass: "badge-big",
    color: "#facc15",
  },
];

const getRoundConfig = (id) => ROUND_TYPES.find((r) => r.id === id);

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';
  const [rounds, setRounds] = useState([]);
  const [activeTab, setActiveTab] = useState('create');
  const [loading, setLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState(null);
  const [sharepointReady, setSharepointReady] = useState(false);

  useEffect(() => {
    fetchRounds();
    checkSharepoint();
  }, []);

  const checkSharepoint = async () => {
    try {
      const res = await axios.get(`${API}/roundmaker/sharepoint-status`);
      setSharepointReady(res.data.configured && res.data.token_valid);
    } catch (e) {
      setSharepointReady(false);
    }
  };

  const handleUploadSharepoint = async (round, e) => {
    if (e) e.stopPropagation();
    setUploadingId(round.id);
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await axios.post(`${API}/roundmaker/rounds/${round.id}/upload-sharepoint`, null, { headers });
      toast.success(res.data.message || "Uploaded to SharePoint!");
      fetchRounds();
    } catch (e) {
      const msg = e.response?.data?.detail || "SharePoint upload failed";
      if (e.response?.status === 403) {
        toast.success("Round submitted for admin approval!");
      } else {
        toast.error(msg);
      }
      fetchRounds();
    } finally {
      setUploadingId(null);
    }
  };

  const fetchRounds = async () => {
    try {
      const res = await axios.get(`${API}/roundmaker/rounds`);
      setRounds(res.data);
    } catch (e) {
      console.error("Failed to fetch rounds", e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API}/roundmaker/rounds/${id}`);
      setRounds((prev) => prev.filter((r) => r.id !== id));
      toast.success("Round deleted");
    } catch (e) {
      toast.error("Failed to delete round");
    }
  };

  const handleDownload = async (round) => {
    try {
      const res = await axios.post(`${API}/roundmaker/rounds/${round.id}/generate`, null, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${round.name}.pptx`;
      link.click();
      window.URL.revokeObjectURL(url);
      toast.success("PowerPoint downloaded!");
    } catch (e) {
      toast.error("Failed to generate PowerPoint");
    }
  };

  const handleDuplicate = async (round) => {
    try {
      const res = await axios.post(`${API}/roundmaker/rounds/${round.id}/duplicate`);
      toast.success(`Duplicated as "${res.data.name}"`);
      navigate(`/roundmaker/create/${res.data.round_type}?edit=${res.data.id}`);
    } catch (e) {
      toast.error("Failed to duplicate round");
    }
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }}>
      {/* Header */}
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/')} className="p-2 rounded-lg hover:bg-white/5" data-testid="back-to-dashboard">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fbdd68" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <img src="/hat-logo.png" alt="BIG Hat" className="h-9 w-9 object-contain" />
          <div>
            <h1 className="text-xl font-bold" style={{ color: '#fbdd68' }}>Round Generator</h1>
            <p className="text-xs" style={{ color: '#8892b0' }}>Trivia Round Creator</p>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Tabs */}
        {isAdmin && (
          <div className="flex gap-2 mb-8">
            <button onClick={() => setActiveTab('create')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all" style={{ backgroundColor: activeTab === 'create' ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)', color: activeTab === 'create' ? '#fbdd68' : '#8892b0', border: `1px solid ${activeTab === 'create' ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
              <FileText size={16} /> Create Rounds
            </button>
            <button onClick={() => setActiveTab('admin')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all relative" style={{ backgroundColor: activeTab === 'admin' ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)', color: activeTab === 'admin' ? '#fbdd68' : '#8892b0', border: `1px solid ${activeTab === 'admin' ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}` }}>
              <Shield size={16} /> Admin
              {rounds.filter(r => r.approval_status === 'pending' || r.status === 'pending_approval').length > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold" style={{ backgroundColor: '#ef4444', color: 'white' }}>
                  {rounds.filter(r => r.approval_status === 'pending' || r.status === 'pending_approval').length}
                </span>
              )}
            </button>
          </div>
        )}

        {activeTab === 'create' && (
        <>
        {/* Round Type Selection */}
        <section className="mb-16">
          <h2 className="text-2xl font-medium text-teal-400 mb-8" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
            Choose Round Type
          </h2>
          <div data-testid="round-type-grid" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 stagger-children">
            {ROUND_TYPES.map((rt) => {
              const Icon = rt.icon;
              return (
                <button
                  key={rt.id}
                  data-testid={`round-card-${rt.id.toLowerCase()}`}
                  onClick={() => navigate(`/roundmaker/create/${rt.id}`)}
                  className={`${rt.cardClass} bg-slate-800/40 border border-slate-700/50 rounded-xl p-6 text-left
                    hover:shadow-xl hover:-translate-y-1 cursor-pointer group
                    backdrop-blur-sm transition-transform transition-shadow duration-300`}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: `${rt.color}20` }}
                    >
                      <Icon size={20} style={{ color: rt.color }} />
                    </div>
                    <h3 className="text-xl font-semibold text-white group-hover:text-teal-300 transition-colors duration-200" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                      {rt.name}
                    </h3>
                  </div>
                  <p className="text-slate-400 text-sm leading-relaxed">{rt.description}</p>
                  <div className="mt-4">
                    <span
                      className="inline-block text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded-full"
                      style={{ backgroundColor: `${rt.color}20`, color: rt.color }}
                    >
                      {rt.id}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* Recent Rounds */}
        <section>
          <div className="flex items-center gap-3 mb-8">
            <div className="w-1 h-8 bg-yellow-400 rounded-full" />
            <h2 className="text-2xl font-medium text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
              Recent Rounds
            </h2>
          </div>

          {loading ? (
            <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-12 text-center">
              <div className="animate-pulse text-slate-500">Loading...</div>
            </div>
          ) : rounds.length === 0 ? (
            <div data-testid="no-rounds-message" className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-12 text-center">
              <FileText size={48} className="mx-auto text-slate-600 mb-4" />
              <p className="text-slate-500 text-lg">No rounds yet</p>
              <p className="text-slate-600 text-sm mt-1">Create your first trivia round to get started</p>
            </div>
          ) : (
            <div data-testid="rounds-list" className="space-y-3 stagger-children">
              {rounds.map((round) => {
                const config = getRoundConfig(round.round_type);
                return (
                  <div
                    key={round.id}
                    data-testid={`round-item-${round.id}`}
                    className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 flex items-center justify-between
                      hover:border-slate-600 transition-colors duration-200 cursor-pointer"
                    onClick={() => navigate(`/roundmaker/create/${round.round_type}?edit=${round.id}`)}
                  >
                    <div className="flex items-center gap-4">
                      <span
                        className="inline-block text-xs font-bold uppercase tracking-wider px-3 py-1 rounded-full"
                        style={{
                          backgroundColor: config ? `${config.color}20` : "#33415520",
                          color: config?.color || "#94a3b8",
                        }}
                      >
                        {round.round_type}
                      </span>
                      <div>
                        <p className="text-white font-medium">{round.name}</p>
                        <p className="text-slate-500 text-xs mt-0.5">
                          {round.questions?.length || 0} questions &middot;{" "}
                          {new Date(round.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {round.status === "uploaded" ? (
                        <span className="flex items-center gap-1 text-xs text-green-400 bg-green-400/10 px-2 py-1 rounded-full">
                          <CheckCircle size={12} />
                          On SharePoint
                        </span>
                      ) : round.status === "pending_approval" || round.approval_status === "pending" ? (
                        <span className="flex items-center gap-1 text-xs text-yellow-400 bg-yellow-400/10 px-2 py-1 rounded-full">
                          Pending Approval
                        </span>
                      ) : round.approval_status === "rejected" ? (
                        <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 px-2 py-1 rounded-full">
                          Rejected
                        </span>
                      ) : (
                        <Button
                          data-testid={`upload-sp-btn-${round.id}`}
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleUploadSharepoint(round, e)}
                          disabled={uploadingId === round.id || !sharepointReady}
                          className="text-yellow-400 hover:text-yellow-300 hover:bg-yellow-400/10 disabled:opacity-40"
                        >
                          {uploadingId === round.id ? (
                            <Loader2 size={16} className="mr-1 animate-spin" />
                          ) : (
                            <Upload size={16} className="mr-1" />
                          )}
                          {uploadingId === round.id ? "Uploading..." : "SharePoint"}
                        </Button>
                      )}
                      <Button
                        data-testid={`duplicate-btn-${round.id}`}
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDuplicate(round)}
                        className="text-slate-400 hover:text-teal-400 hover:bg-teal-400/10"
                        title="Clone as template"
                      >
                        <Copy size={16} className="mr-1" />
                        Clone
                      </Button>
                      <Button
                        data-testid={`download-btn-${round.id}`}
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDownload(round)}
                        className="text-teal-400 hover:text-teal-300 hover:bg-slate-700/50"
                      >
                        <Download size={16} className="mr-1" />
                        PPTX
                      </Button>
                      <Button
                        data-testid={`delete-btn-${round.id}`}
                        variant="ghost"
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); handleDelete(round.id); }}
                        className="text-slate-500 hover:text-red-400 hover:bg-red-400/10"
                      >
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
        </>
        )}

        {/* Admin Tab */}
        {activeTab === 'admin' && isAdmin && (
          <AdminPanel rounds={rounds} onRefresh={fetchRounds} />
        )}
      </main>
    </div>
  );
}


function AdminPanel({ rounds, onRefresh }) {
  const [approving, setApproving] = useState(null);

  const pendingRounds = rounds.filter(r => r.approval_status === 'pending' || r.status === 'pending_approval');
  const approvedRounds = rounds.filter(r => r.approval_status === 'approved' || r.status === 'uploaded');
  const allRounds = rounds;

  const handleApprove = async (roundId) => {
    setApproving(roundId);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/roundmaker/rounds/${roundId}/approve`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Round approved! It can now be uploaded to SharePoint.");
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Approval failed");
    } finally {
      setApproving(null);
    }
  };

  const handleReject = async (roundId) => {
    if (!window.confirm("Reject this round?")) return;
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/roundmaker/rounds/${roundId}/reject`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Round rejected.");
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Rejection failed");
    }
  };

  const handleUploadApproved = async (round) => {
    setApproving(round.id);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/roundmaker/rounds/${round.id}/upload-sharepoint`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Uploaded to SharePoint!");
      onRefresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed");
    } finally {
      setApproving(null);
    }
  };

  const getRoundConfig = (type) => {
    const colors = { MC: '#22c55e', REG: '#ef4444', MISC: '#3b82f6', MYS: '#a855f7', BIG: '#eab308' };
    return { color: colors[type] || '#8892b0' };
  };

  return (
    <div>
      <h2 className="text-2xl font-medium mb-6" style={{ color: '#fbdd68', fontFamily: "'Space Grotesk', sans-serif" }}>
        Admin Panel
      </h2>

      {/* Pending Approval */}
      <section className="mb-10">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-yellow-400" />
          Pending Approval ({pendingRounds.length})
        </h3>
        {pendingRounds.length === 0 ? (
          <div className="rounded-xl p-8 text-center" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
            <p style={{ color: '#8892b0' }}>No rounds pending approval</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pendingRounds.map(round => {
              const config = getRoundConfig(round.round_type);
              return (
                <div key={round.id} className="rounded-xl p-5 flex items-center justify-between" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
                  <div className="flex items-center gap-4">
                    <span className="text-xs font-bold uppercase px-3 py-1 rounded-full" style={{ backgroundColor: `${config.color}20`, color: config.color }}>{round.round_type}</span>
                    <div>
                      <p className="text-white font-medium">{round.name}</p>
                      <p className="text-xs mt-0.5" style={{ color: '#8892b0' }}>{round.questions?.length || 0} questions &middot; {new Date(round.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button onClick={() => handleApprove(round.id)} disabled={approving === round.id} className="bg-green-600 hover:bg-green-700 text-white text-sm px-4 py-2" size="sm">
                      {approving === round.id ? <Loader2 size={14} className="animate-spin mr-1" /> : <Check size={14} className="mr-1" />}
                      Approve
                    </Button>
                    <Button onClick={() => handleReject(round.id)} variant="ghost" size="sm" className="text-red-400 hover:bg-red-400/10">
                      <X size={14} className="mr-1" /> Reject
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Approved - Ready to Upload */}
      <section className="mb-10">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400" />
          Approved — Ready to Upload ({approvedRounds.filter(r => r.status !== 'uploaded').length})
        </h3>
        <div className="space-y-3">
          {approvedRounds.filter(r => r.status !== 'uploaded').map(round => {
            const config = getRoundConfig(round.round_type);
            return (
              <div key={round.id} className="rounded-xl p-5 flex items-center justify-between" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
                <div className="flex items-center gap-4">
                  <span className="text-xs font-bold uppercase px-3 py-1 rounded-full" style={{ backgroundColor: `${config.color}20`, color: config.color }}>{round.round_type}</span>
                  <div>
                    <p className="text-white font-medium">{round.name}</p>
                    <p className="text-xs mt-0.5" style={{ color: '#8892b0' }}>{round.questions?.length || 0} questions</p>
                  </div>
                </div>
                <Button onClick={() => handleUploadApproved(round)} disabled={approving === round.id} className="bg-yellow-400 hover:bg-yellow-300 text-black font-bold text-sm" size="sm">
                  {approving === round.id ? <Loader2 size={14} className="animate-spin mr-1" /> : <Upload size={14} className="mr-1" />}
                  Upload to SharePoint
                </Button>
              </div>
            );
          })}
          {approvedRounds.filter(r => r.status !== 'uploaded').length === 0 && (
            <div className="rounded-xl p-6 text-center" style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
              <p style={{ color: '#8892b0' }}>No approved rounds waiting for upload</p>
            </div>
          )}
        </div>
      </section>

      {/* All Rounds */}
      <section>
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: '#5973F7' }} />
          All Rounds ({allRounds.length})
        </h3>
        <div className="space-y-2">
          {allRounds.map(round => {
            const config = getRoundConfig(round.round_type);
            const statusColor = round.status === 'uploaded' ? '#22c55e' : round.approval_status === 'pending' ? '#eab308' : round.approval_status === 'rejected' ? '#ef4444' : '#8892b0';
            const statusLabel = round.status === 'uploaded' ? 'On SharePoint' : round.approval_status === 'pending' ? 'Pending' : round.approval_status === 'rejected' ? 'Rejected' : round.approval_status === 'approved' ? 'Approved' : 'Draft';
            return (
              <div key={round.id} className="rounded-lg px-4 py-3 flex items-center justify-between" style={{ backgroundColor: 'rgba(20, 27, 80, 0.3)', border: '1px solid rgba(251, 221, 104, 0.05)' }}>
                <div className="flex items-center gap-3">
                  <span className="text-[10px] font-bold uppercase w-10" style={{ color: config.color }}>{round.round_type}</span>
                  <span className="text-sm text-white">{round.name}</span>
                </div>
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full" style={{ backgroundColor: `${statusColor}15`, color: statusColor }}>{statusLabel}</span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
