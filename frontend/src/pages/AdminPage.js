import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import Header from '../components/Header';
import {
  Users, Plus, Trash2, Edit, Shield, ShieldCheck,
  Calendar, X, Save, ChevronRight, AlertTriangle, MapPin,
  Archive, Download, Loader2,
} from 'lucide-react';
import TriviaSetup from './admin/TriviaSetup';

export default function AdminPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [events, setEvents] = useState([]);
  const [showAddUser, setShowAddUser] = useState(false);
  const [showAddEvent, setShowAddEvent] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';

  useEffect(() => {
    if (!isAdmin) {
      navigate('/');
      return;
    }
    loadData();
  }, [isAdmin, navigate]);

  const loadData = async () => {
    try {
      const [usersRes, eventsRes] = await Promise.all([
        api.getUsers(),
        api.getEvents()
      ]);
      setUsers(usersRes.data);
      setEvents(eventsRes.data);
    } catch (err) {
      console.error('Failed to load admin data:', err);
    }
  };

  const clearMessages = () => { setError(''); setSuccess(''); };

  const tabs = [
    { id: 'users', label: 'User Management', icon: Users },
    { id: 'events', label: 'Event Management', icon: Calendar },
    { id: 'trivia-setup', label: 'Trivia Setup', icon: MapPin },
  ];

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }} data-testid="admin-page">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 animate-slide-up">
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Shield size={24} style={{ color: '#fbdd68' }} />
            Admin Settings
          </h2>
          <p className="text-sm mt-1" style={{ color: '#8892b0' }}>Manage users, events, and app configuration</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); clearMessages(); }}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200"
                style={{
                  backgroundColor: activeTab === tab.id ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)',
                  color: activeTab === tab.id ? '#fbdd68' : '#8892b0',
                  border: `1px solid ${activeTab === tab.id ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}`
                }}
                data-testid={`admin-tab-${tab.id}`}
              >
                <Icon size={16} /> {tab.label}
              </button>
            );
          })}
        </div>
        {error && (
          <div className="mb-4 p-3 rounded-lg text-sm flex items-center gap-2" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444' }} data-testid="admin-error">
            <AlertTriangle size={16} /> {error}
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(34, 197, 94, 0.15)', border: '1px solid rgba(34, 197, 94, 0.3)', color: '#22c55e' }} data-testid="admin-success">
            {success}
          </div>
        )}

        {activeTab === 'users' && (
          <UserManagement
            users={users}
            currentUser={user}
            showAddUser={showAddUser}
            setShowAddUser={setShowAddUser}
            editingUser={editingUser}
            setEditingUser={setEditingUser}
            onRefresh={loadData}
            setError={setError}
            setSuccess={setSuccess}
          />
        )}
        {activeTab === 'events' && (
          <EventManagement
            events={events}
            users={users}
            showAddEvent={showAddEvent}
            setShowAddEvent={setShowAddEvent}
            onRefresh={loadData}
            setError={setError}
            setSuccess={setSuccess}
          />
        )}
        {activeTab === 'trivia-setup' && (
          <TriviaSetup
            currentUser={user}
            allUsers={users}
            setError={setError}
            setSuccess={setSuccess}
          />
        )}
      </main>
    </div>
  );
}

function UserManagement({ users, currentUser, showAddUser, setShowAddUser, editingUser, setEditingUser, onRefresh, setError, setSuccess }) {
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'host' });
  const navigate = useNavigate();

  const handleAddUser = async (e) => {
    e.preventDefault();
    try {
      await api.register(form);
      setSuccess(`User ${form.email} created successfully`);
      setShowAddUser(false);
      setForm({ name: '', email: '', password: '', role: 'host' });
      onRefresh();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create user');
    }
  };

  const handleUpdateUser = async (e) => {
    e.preventDefault();
    try {
      const updateData = {};
      if (editingUser.name) updateData.name = editingUser.name;
      if (editingUser.role) updateData.role = editingUser.role;
      if (editingUser.newPassword) updateData.password = editingUser.newPassword;
      await api.updateUser(editingUser._id, updateData);
      setSuccess('User updated successfully');
      setEditingUser(null);
      onRefresh();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update user');
    }
  };

  const handleDeleteUser = async (userId, userName) => {
    if (!window.confirm(`Delete user "${userName}"? This cannot be undone.`)) return;
    try {
      await api.deleteUser(userId);
      setSuccess(`User ${userName} deleted`);
      onRefresh();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete user');
    }
  };

  const roleIcon = (role) => {
    if (role === 'master_admin') return <ShieldCheck size={14} style={{ color: '#fbdd68' }} />;
    if (role === 'admin') return <Shield size={14} style={{ color: '#5973F7' }} />;
    return null;
  };

  return (
    <div data-testid="user-management-section">
      {/* Backup my setup — master_admin only. Manual zip of the per-install
          state dir (license, master admin, MontyDB, .env, assets). Auto
          backup also runs on every startup in the background. */}
      {currentUser?.role === 'master_admin' && (
        <BackupSetupCard setError={setError} setSuccess={setSuccess} />
      )}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold">Users ({users.length})</h3>
        <button
          onClick={() => setShowAddUser(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all duration-200 hover:shadow-lg"
          style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
          data-testid="add-user-button"
        >
          <Plus size={16} /> Add User
        </button>
      </div>

      {/* Add User Form */}
      {showAddUser && (
        <div className="glass-card rounded-xl p-5 mb-4 animate-fade-in" data-testid="add-user-form">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-semibold text-white">New User</h4>
            <button onClick={() => setShowAddUser(false)} className="opacity-60 hover:opacity-100"><X size={18} color="#8892b0" /></button>
          </div>
          <form onSubmit={handleAddUser} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input type="text" placeholder="Full Name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} required className="admin-input" data-testid="new-user-name" />
            <input type="email" placeholder="Email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required className="admin-input" data-testid="new-user-email" />
            <input type="password" placeholder="Password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} required className="admin-input" data-testid="new-user-password" />
            <select value={form.role} onChange={e => setForm({...form, role: e.target.value})} className="admin-input" data-testid="new-user-role">
              <option value="host">Host</option>
              {currentUser?.role === 'master_admin' && <option value="admin">Admin</option>}
            </select>
            <div className="md:col-span-2 flex gap-2">
              <button type="submit" className="px-6 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }} data-testid="submit-new-user">Create User</button>
              <button type="button" onClick={() => setShowAddUser(false)} className="px-6 py-2 rounded-lg text-sm" style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.2)' }}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Edit User Form */}
      {editingUser && (
        <div className="glass-card rounded-xl p-5 mb-4 animate-fade-in" data-testid="edit-user-form">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-semibold text-white">Edit User: {editingUser.name}</h4>
            <button onClick={() => setEditingUser(null)} className="opacity-60 hover:opacity-100"><X size={18} color="#8892b0" /></button>
          </div>
          <form onSubmit={handleUpdateUser} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input type="text" placeholder="Name" value={editingUser.name || ''} onChange={e => setEditingUser({...editingUser, name: e.target.value})} className="admin-input" />
            <input type="password" placeholder="New Password (optional)" value={editingUser.newPassword || ''} onChange={e => setEditingUser({...editingUser, newPassword: e.target.value})} className="admin-input" />
            <select value={editingUser.role || 'host'} onChange={e => setEditingUser({...editingUser, role: e.target.value})} className="admin-input" disabled={editingUser.role === 'master_admin'}>
              <option value="host">Host</option>
              {currentUser?.role === 'master_admin' && <option value="admin">Admin</option>}
              {currentUser?.role === 'master_admin' && <option value="master_admin">Master Admin</option>}
            </select>
            <div className="flex gap-2 items-end">
              <button type="submit" className="px-6 py-2 rounded-lg text-sm font-bold flex items-center gap-2" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }} data-testid="save-user-edit"><Save size={14} /> Save</button>
              <button type="button" onClick={() => setEditingUser(null)} className="px-6 py-2 rounded-lg text-sm" style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.2)' }}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* User List — each row is a button that opens the user's
          profile page. Master admin / admin can edit anyone's; a
          regular host opening their own row can edit their profile
          fields (host images, profile picture, home city) but not
          their role. The inline edit + delete icons stay on the row
          so the admin doesn't need to navigate just to perform those
          quick actions. */}
      <div className="space-y-2">
        {users.map(u => {
          const userId = u._id || u.id;
          return (
            <div
              key={userId}
              className="glass-card rounded-xl px-4 py-3 flex items-center justify-between hover:bg-white/5 cursor-pointer transition-colors"
              data-testid={`user-row-${userId}`}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/admin/users/${encodeURIComponent(userId)}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/admin/users/${encodeURIComponent(userId)}`);
                }
              }}
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold overflow-hidden" style={{ backgroundColor: u.role === 'master_admin' ? '#fbdd68' : u.role === 'admin' ? '#5973F7' : '#141b50', color: u.role === 'master_admin' || u.role === 'admin' ? '#000e2a' : '#fbdd68' }}>
                  {u.profile_picture ? (
                    <img src={`${process.env.REACT_APP_BACKEND_URL}/api/native/files/raw?path=${encodeURIComponent(u.profile_picture)}`}
                         alt={u.name}
                         className="w-full h-full object-cover"
                         onError={(e) => { e.target.style.display = 'none'; }} />
                  ) : (
                    u.name?.charAt(0)?.toUpperCase() || '?'
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{u.name}</span>
                    {roleIcon(u.role)}
                  </div>
                  <span className="text-xs" style={{ color: '#8892b0' }}>
                    {u.email}{u.home_city ? ` · ${u.home_city}` : ''}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                <span className="text-[10px] font-bold uppercase px-2 py-1 rounded-full" style={{
                  backgroundColor: u.role === 'master_admin' ? 'rgba(251, 221, 104, 0.15)' : u.role === 'admin' ? 'rgba(89, 115, 247, 0.15)' : 'rgba(20, 27, 80, 0.6)',
                  color: u.role === 'master_admin' ? '#fbdd68' : u.role === 'admin' ? '#5973F7' : '#8892b0'
                }}>
                  {u.role === 'master_admin' ? 'Master' : u.role}
                </span>
                {u.role !== 'master_admin' && (
                  <>
                    <button onClick={() => setEditingUser(u)} className="p-1.5 rounded-lg hover:bg-white/5 transition-colors" data-testid={`edit-user-${userId}`}>
                      <Edit size={14} style={{ color: '#8892b0' }} />
                    </button>
                    <button onClick={() => handleDeleteUser(userId, u.name)} className="p-1.5 rounded-lg hover:bg-red-500/10 transition-colors" data-testid={`delete-user-${userId}`}>
                      <Trash2 size={14} style={{ color: '#ef4444' }} />
                    </button>
                  </>
                )}
                <ChevronRight size={14} style={{ color: '#8892b0' }} />
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .admin-input {
          width: 100%;
          padding: 10px 14px;
          border-radius: 8px;
          font-size: 14px;
          color: white;
          background-color: rgba(20, 27, 80, 0.6);
          border: 1px solid rgba(251, 221, 104, 0.2);
          outline: none;
          transition: border-color 0.2s;
        }
        .admin-input:focus {
          border-color: rgba(251, 221, 104, 0.5);
        }
        .admin-input option {
          background-color: #141b50;
          color: white;
        }
      `}</style>
    </div>
  );
}

function EventManagement({ events, users, showAddEvent, setShowAddEvent, onRefresh, setError, setSuccess }) {
  const [form, setForm] = useState({ title: '', event_type: 'trivia', date: '', time: '', venue: '', description: '' });

  const handleAddEvent = async (e) => {
    e.preventDefault();
    try {
      await api.createEvent(form);
      setSuccess(`Event "${form.title}" created`);
      setShowAddEvent(false);
      setForm({ title: '', event_type: 'trivia', date: '', time: '', venue: '', description: '' });
      onRefresh();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create event');
    }
  };

  const handleDeleteEvent = async (eventId, title) => {
    if (!window.confirm(`Delete event "${title}"?`)) return;
    try {
      await api.deleteEvent(eventId);
      setSuccess(`Event deleted`);
      onRefresh();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete event');
    }
  };

  const typeColors = { trivia: '#fbdd68', bingo: '#5973F7', karaoke: '#22c55e' };

  return (
    <div data-testid="event-management-section">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold">Events ({events.length})</h3>
        <button
          onClick={() => setShowAddEvent(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all duration-200 hover:shadow-lg"
          style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
          data-testid="add-event-button"
        >
          <Plus size={16} /> Add Event
        </button>
      </div>

      {showAddEvent && (
        <div className="glass-card rounded-xl p-5 mb-4 animate-fade-in" data-testid="add-event-form">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-semibold text-white">New Event</h4>
            <button onClick={() => setShowAddEvent(false)} className="opacity-60 hover:opacity-100"><X size={18} color="#8892b0" /></button>
          </div>
          <form onSubmit={handleAddEvent} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input type="text" placeholder="Event Title" value={form.title} onChange={e => setForm({...form, title: e.target.value})} required className="admin-input" data-testid="new-event-title" />
            <select value={form.event_type} onChange={e => setForm({...form, event_type: e.target.value})} className="admin-input" data-testid="new-event-type">
              <option value="trivia">Trivia</option>
              <option value="bingo">Music Bingo</option>
              <option value="karaoke">Karaoke</option>
            </select>
            <input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})} required className="admin-input" data-testid="new-event-date" />
            <input type="text" placeholder="Time (e.g. 7:00 PM)" value={form.time} onChange={e => setForm({...form, time: e.target.value})} required className="admin-input" data-testid="new-event-time" />
            <input type="text" placeholder="Venue" value={form.venue} onChange={e => setForm({...form, venue: e.target.value})} required className="admin-input" data-testid="new-event-venue" />
            <input type="text" placeholder="Description" value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="admin-input" data-testid="new-event-description" />
            <div className="md:col-span-2 flex gap-2">
              <button type="submit" className="px-6 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }} data-testid="submit-new-event">Create Event</button>
              <button type="button" onClick={() => setShowAddEvent(false)} className="px-6 py-2 rounded-lg text-sm" style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.2)' }}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="space-y-2">
        {events.map(e => (
          <div key={e._id} className="glass-card rounded-xl px-4 py-3 flex items-center justify-between" data-testid={`event-row-${e._id}`}>
            <div className="flex items-center gap-3">
              <div className="w-2 h-8 rounded-full" style={{ backgroundColor: typeColors[e.event_type] || '#fbdd68' }} />
              <div>
                <span className="text-sm font-medium text-white">{e.title}</span>
                <div className="flex items-center gap-3 text-xs" style={{ color: '#8892b0' }}>
                  <span>{e.date}</span>
                  <span>{e.time}</span>
                  <span>{e.venue}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase px-2 py-1 rounded-full" style={{
                backgroundColor: e.claimed ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                color: e.claimed ? '#22c55e' : '#ef4444'
              }}>
                {e.claimed ? 'Claimed' : 'Open'}
              </span>
              <button onClick={() => handleDeleteEvent(e._id, e.title)} className="p-1.5 rounded-lg hover:bg-red-500/10 transition-colors" data-testid={`delete-event-${e._id}`}>
                <Trash2 size={14} style={{ color: '#ef4444' }} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <style>{`
        .admin-input {
          width: 100%;
          padding: 10px 14px;
          border-radius: 8px;
          font-size: 14px;
          color: white;
          background-color: rgba(20, 27, 80, 0.6);
          border: 1px solid rgba(251, 221, 104, 0.2);
          outline: none;
          transition: border-color 0.2s;
        }
        .admin-input:focus {
          border-color: rgba(251, 221, 104, 0.5);
        }
        .admin-input option {
          background-color: #141b50;
          color: white;
        }
      `}</style>
    </div>
  );
}


// ----------------------------------------------------------------
// BackupSetupCard — master_admin-only card at the top of User
// Management. Runs a manual backup on demand AND shows what's
// already on disk (the startup auto-backup populates the list).
// ----------------------------------------------------------------
function BackupSetupCard({ setError, setSuccess }) {
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);

  const refresh = async () => {
    try {
      const r = await api.backupStatus();
      setStatus(r.data);
    } catch (e) {
      // 403 here just means we're not master_admin — the card won't render,
      // so silently swallow. Anything else surface.
      if (e.response?.status !== 403) {
        setError?.(e.response?.data?.detail || 'Failed to read backup status');
      }
    }
  };

  useEffect(() => { refresh(); }, []);

  const onRun = async () => {
    setRunning(true);
    try {
      const r = await api.runBackup();
      if (r.data.ok) {
        const mb = (r.data.size / (1024 * 1024)).toFixed(1);
        setSuccess?.(`Backup written (${r.data.files} files, ${mb} MB)`);
      } else {
        setError?.(`Backup failed: ${r.data.error || 'unknown error'}`);
      }
      await refresh();
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      if (detail === 'backup_already_running') {
        setError?.('A backup is already running — try again in a moment.');
      } else {
        setError?.(`Backup error: ${detail}`);
      }
    } finally {
      setRunning(false);
    }
  };

  const fmtBytes = (n) => {
    if (!n) return '0 B';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  };
  const fmtDate = (iso) => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  return (
    <div className="rounded-xl p-5 mb-6"
         style={{ backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.15)' }}
         data-testid="backup-card">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-start gap-3 min-w-0">
          <Archive size={22} style={{ color: '#fbdd68' }} className="flex-shrink-0 mt-0.5" />
          <div className="min-w-0">
            <h3 className="text-white font-semibold">Backup my setup</h3>
            <p className="text-xs mt-0.5" style={{ color: '#8892b0' }}>
              Snapshots your license, master admin, database, and assets into a dated
              <code className="mx-1 px-1 rounded" style={{ backgroundColor: 'rgba(0,0,0,0.3)', color: '#fbdd68' }}>.zip</code>
              under Documents/BIG Hat Entertainment/Backups. Runs automatically every time you start the app
              (last 14 days kept).
            </p>
          </div>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all duration-200 hover:shadow-lg disabled:opacity-50 flex-shrink-0"
          style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
          data-testid="run-backup-btn"
        >
          {running ? <><Loader2 size={14} className="animate-spin" /> Backing up…</>
                   : <><Download size={14} /> Back up now</>}
        </button>
      </div>

      {status && (
        <div className="text-xs space-y-1" style={{ color: '#8892b0' }} data-testid="backup-status">
          <div>
            <span style={{ color: '#fbdd68' }}>Destination:</span>{' '}
            <code className="break-all">{status.destination}</code>
          </div>
          {status.backups?.length === 0 ? (
            <div className="italic" style={{ color: '#8892b0' }}>No backups yet — click &quot;Back up now&quot; or restart the app.</div>
          ) : (
            <details className="mt-2">
              <summary className="cursor-pointer" style={{ color: '#fbdd68' }}>
                {status.backups.length} backup{status.backups.length === 1 ? '' : 's'} on disk
              </summary>
              <ul className="mt-2 space-y-1 max-h-40 overflow-auto pl-3" data-testid="backup-list">
                {status.backups.map((b) => (
                  <li key={b.name} className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-mono truncate">{b.name}</span>
                    <span className="flex-shrink-0">{fmtBytes(b.size)} · {fmtDate(b.mtime)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

