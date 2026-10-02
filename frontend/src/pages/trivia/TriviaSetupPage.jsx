import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, MapPin } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/api';
import TriviaSetup from '../admin/TriviaSetup';

/**
 * Trivia Setup (alpha.69) - moved here from the Admin page so it lives inside the Trivia player,
 * the same way Bingo Setup lives inside the Bingo player.
 * Everything in <TriviaSetup> is unchanged: locations, branding, overlays, slide style, global slides,
 * admin assignments. Admins and master admins only (same rule the Admin page used).
 */
export default function TriviaSetupPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';
  const isMaster = user?.role === 'master_admin';

  useEffect(() => {
    if (user && !isAdmin) navigate('/trivia');
  }, [user, isAdmin, navigate]);

  // The user list is only used by the master admin's "assign admins" panel.
  useEffect(() => {
    if (!isMaster) return;
    api.getUsers().then((r) => setUsers(r.data)).catch(() => {});
  }, [isMaster]);

  // auto-hide messages
  useEffect(() => {
    if (!success) return undefined;
    const t = setTimeout(() => setSuccess(''), 4000);
    return () => clearTimeout(t);
  }, [success]);

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a' }} data-testid="trivia-setup-page">
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/trivia')} className="p-2 rounded-lg hover:bg-white/5" data-testid="trivia-setup-back-btn">
            <ArrowLeft size={20} style={{ color: '#fbdd68' }} />
          </button>
          <MapPin size={22} style={{ color: '#fbdd68' }} />
          <div>
            <h1 className="text-xl font-bold" style={{ color: '#fbdd68' }}>Trivia Setup</h1>
            <p className="text-xs" style={{ color: '#8892b0' }}>Locations, branding, overlays and slide style</p>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {error && (
          <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(239,68,68,0.12)', color: '#fca5a5', border: '1px solid rgba(239,68,68,0.3)' }} data-testid="trivia-setup-error">
            {error} <button className="ml-2 underline" onClick={() => setError('')}>dismiss</button>
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(34,197,94,0.12)', color: '#86efac', border: '1px solid rgba(34,197,94,0.3)' }} data-testid="trivia-setup-success">
            {success}
          </div>
        )}
        <TriviaSetup currentUser={user} allUsers={users} setError={setError} setSuccess={setSuccess} />
      </main>
    </div>
  );
}
