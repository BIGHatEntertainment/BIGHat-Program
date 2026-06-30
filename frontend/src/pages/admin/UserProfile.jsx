import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/api';
import Header from '../../components/Header';
import { toast } from 'sonner';
import { ArrowLeft, Upload, Save, MapPin, User, Image as ImageIcon, Loader2 } from 'lucide-react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

/**
 * User profile page — accessible at /admin/users/:userId.
 *
 * Master admin + admin can open any user; a non-admin host can only
 * open their own profile (the backend `/users/{id}/profile` PATCH
 * enforces this — the frontend just hides the affordance to be polite).
 *
 * Editable fields:
 *   • profile_picture — round avatar shown next to the host's name
 *     everywhere in the app. Lands in
 *     `Documents\BIG Hat Entertainment\Files\Hosts\<slug>\avatar.<ext>`.
 *   • host_image_16x9 — landscape GIF used as the host slide inside
 *     trivia presentations. Lands in `…\Hosts\<slug>\host-16x9.<ext>`.
 *   • host_image_9x16 — portrait GIF used by the Story Generator for
 *     social media stories. Lands in `…\Hosts\<slug>\host-9x16.<ext>`.
 *   • home_city — the city the host usually runs nights in. Surfaced
 *     in the user list + on the Schedule page's event-claim dialog.
 *
 * Read-only fields (changing role / email / password lives in the
 * admin user-management edit dialog):
 *   • name, email, role
 *
 * v32.0.0-alpha.28.
 */
export default function UserProfile() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();

  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [homeCity, setHomeCity] = useState('');
  const [name, setName] = useState('');

  const avatarInputRef = useRef(null);
  const host16x9InputRef = useRef(null);
  const host9x16InputRef = useRef(null);

  const canEdit =
    currentUser?.role === 'master_admin' ||
    currentUser?.role === 'admin' ||
    String(currentUser?._id) === String(userId) ||
    currentUser?.id === userId ||
    currentUser?.email === user?.email;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // The /users list endpoint already streams every user;
        // filtering client-side is simpler than adding a dedicated
        // GET /users/{id} for now and keeps the surface small.
        const res = await api.getUsers();
        const found = res.data.find(
          (u) => String(u._id) === String(userId) || u.id === userId
        );
        if (!cancelled) {
          if (found) {
            setUser(found);
            setHomeCity(found.home_city || '');
            setName(found.name || '');
          } else {
            toast.error('User not found');
            navigate('/admin');
          }
        }
      } catch (e) {
        toast.error('Failed to load user');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [userId, navigate]);

  const uploadImage = async (kind, file) => {
    if (!file) return null;
    if (!canEdit) {
      toast.error("You don't have permission to edit this profile");
      return null;
    }
    const form = new FormData();
    form.append('host_id', user.email || userId);
    form.append('kind', kind);
    form.append('file', file);
    try {
      const res = await axios.post(`${API}/api/native/files/host-image`, form);
      toast.success(`${kind} uploaded`);
      return res.data.path;
    } catch (e) {
      toast.error(e.response?.data?.detail || `${kind} upload failed`);
      return null;
    }
  };

  const handleImagePick = (kind, ref) => async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setSaving(true);
    const path = await uploadImage(kind, file);
    if (path) {
      // Persist the path onto the user doc so it survives reloads.
      const fieldMap = {
        'avatar':    'profile_picture',
        'host-16x9': 'host_image_16x9',
        'host-9x16': 'host_image_9x16',
      };
      try {
        const patch = { [fieldMap[kind]]: path };
        const res = await axios.patch(`${API}/api/users/${encodeURIComponent(userId)}/profile`, patch);
        setUser(res.data);
      } catch (err) {
        toast.error('Image uploaded but profile update failed');
      }
    }
    setSaving(false);
  };

  const handleSaveText = async () => {
    if (!canEdit) {
      toast.error("You don't have permission to edit this profile");
      return;
    }
    setSaving(true);
    try {
      const res = await axios.patch(`${API}/api/users/${encodeURIComponent(userId)}/profile`, {
        name: name.trim(),
        home_city: homeCity.trim(),
      });
      setUser(res.data);
      toast.success('Profile saved');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <Loader2 className="animate-spin" size={32} color="#fbdd68" />
      </div>
    );
  }
  if (!user) return null;

  // Build the URL we use to render any image stored under Files/Hosts/.
  const imgUrl = (path) =>
    path ? `${API}/api/native/files/raw?path=${encodeURIComponent(path)}` : null;

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }} data-testid="user-profile-page">
      <Header />
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <button
          onClick={() => navigate('/admin')}
          className="flex items-center gap-2 text-sm mb-6 text-slate-300 hover:text-yellow-300"
          data-testid="profile-back-btn"
        >
          <ArrowLeft size={16} /> Back to User Management
        </button>

        <div className="glass-card rounded-xl p-6 mb-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <div className="flex flex-col items-center gap-2">
              <div
                className="w-28 h-28 rounded-full overflow-hidden border-4"
                style={{
                  borderColor: user.role === 'master_admin' ? '#fbdd68' : user.role === 'admin' ? '#5973F7' : 'rgba(251,221,104,0.25)',
                  backgroundColor: '#141b50',
                }}
                data-testid="profile-avatar"
              >
                {user.profile_picture ? (
                  <img src={imgUrl(user.profile_picture)} alt={user.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-4xl font-bold" style={{ color: '#fbdd68' }}>
                    {user.name?.charAt(0)?.toUpperCase() || '?'}
                  </div>
                )}
              </div>
              {canEdit && (
                <>
                  <button
                    onClick={() => avatarInputRef.current?.click()}
                    className="text-xs flex items-center gap-1 px-2 py-1 rounded border border-yellow-400/30 text-yellow-300 hover:bg-yellow-400/10"
                    data-testid="profile-avatar-upload"
                    disabled={saving}
                  >
                    <Upload size={12} /> Change
                  </button>
                  <input
                    ref={avatarInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    style={{ display: 'none' }}
                    onChange={handleImagePick('avatar', avatarInputRef)}
                  />
                </>
              )}
            </div>

            {/* Identity */}
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-white" data-testid="profile-name">
                {user.name}
              </h2>
              <p className="text-sm mt-1 text-slate-400">{user.email}</p>
              <span
                className="inline-block mt-2 px-2 py-0.5 text-[10px] font-bold uppercase rounded-full"
                style={{
                  backgroundColor:
                    user.role === 'master_admin'
                      ? 'rgba(251,221,104,0.15)'
                      : user.role === 'admin'
                      ? 'rgba(89,115,247,0.15)'
                      : 'rgba(20,27,80,0.6)',
                  color:
                    user.role === 'master_admin'
                      ? '#fbdd68'
                      : user.role === 'admin'
                      ? '#5973F7'
                      : '#8892b0',
                }}
              >
                {user.role === 'master_admin' ? 'Master Admin' : user.role}
              </span>

              {/* Editable fields */}
              <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="block">
                  <span className="text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1">
                    <User size={12} /> Display Name
                  </span>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={!canEdit || saving}
                    className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-700 text-white text-sm focus:border-yellow-400 outline-none disabled:opacity-60"
                    data-testid="profile-name-input"
                  />
                </label>
                <label className="block">
                  <span className="text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1">
                    <MapPin size={12} /> Home City
                  </span>
                  <input
                    type="text"
                    placeholder="e.g. Phoenix, AZ"
                    value={homeCity}
                    onChange={(e) => setHomeCity(e.target.value)}
                    disabled={!canEdit || saving}
                    className="mt-1 w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-700 text-white text-sm focus:border-yellow-400 outline-none disabled:opacity-60"
                    data-testid="profile-home-city-input"
                  />
                </label>
              </div>

              {canEdit && (
                <button
                  onClick={handleSaveText}
                  disabled={saving}
                  className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
                  style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
                  data-testid="profile-save-btn"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  {saving ? 'Saving…' : 'Save'}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Host slide assets — these are the two GIF aspect ratios the
            Trivia Presenter (16:9) and Story Generator (9:16) pull from
            when they need to introduce this host. Stored in
            Files\Hosts\<slug>\ alongside the avatar so a backup
            captures everything in one folder. */}
        <div className="glass-card rounded-xl p-6">
          <h3 className="text-white font-semibold flex items-center gap-2 mb-1">
            <ImageIcon size={18} style={{ color: '#fbdd68' }} /> Host Slide Assets
          </h3>
          <p className="text-xs text-slate-400 mb-5">
            These are consumed by the Trivia Presenter (16:9) and the Story Generator (9:16).
            Drop the same image in different aspect ratios so each tool gets a fitting version.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <HostImageSlot
              label="16:9 — Trivia presentation host slide"
              testId="host-16x9-slot"
              aspectClass="aspect-video"
              src={imgUrl(user.host_image_16x9)}
              canEdit={canEdit}
              onPick={() => host16x9InputRef.current?.click()}
              inputRef={host16x9InputRef}
              onChange={handleImagePick('host-16x9', host16x9InputRef)}
              saving={saving}
            />
            <HostImageSlot
              label="9:16 — Social story tool"
              testId="host-9x16-slot"
              aspectClass="aspect-[9/16] max-h-72 mx-auto"
              src={imgUrl(user.host_image_9x16)}
              canEdit={canEdit}
              onPick={() => host9x16InputRef.current?.click()}
              inputRef={host9x16InputRef}
              onChange={handleImagePick('host-9x16', host9x16InputRef)}
              saving={saving}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

function HostImageSlot({ label, testId, aspectClass, src, canEdit, onPick, inputRef, onChange, saving }) {
  return (
    <div data-testid={testId}>
      <span className="block text-xs uppercase tracking-wider text-slate-400 mb-2">{label}</span>
      <div
        className={`relative ${aspectClass} rounded-lg overflow-hidden border border-slate-700 bg-slate-900/60 flex items-center justify-center`}
      >
        {src ? (
          <img src={src} alt={label} className="w-full h-full object-cover" />
        ) : (
          <span className="text-slate-500 text-xs">No image yet</span>
        )}
      </div>
      {canEdit && (
        <>
          <button
            onClick={onPick}
            disabled={saving}
            className="mt-2 w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border border-yellow-400/30 text-yellow-300 hover:bg-yellow-400/10 disabled:opacity-50"
            data-testid={`${testId}-upload`}
          >
            <Upload size={12} /> Upload {label.split(' — ')[0]}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="image/gif,image/png,image/jpeg,image/webp"
            style={{ display: 'none' }}
            onChange={onChange}
          />
        </>
      )}
    </div>
  );
}
