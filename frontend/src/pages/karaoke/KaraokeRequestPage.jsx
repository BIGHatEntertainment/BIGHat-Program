import React, { useState, useEffect, useRef } from 'react';
import { Mic, Send, CheckCircle, XCircle } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const accent = '#22c55e';

export default function KaraokeRequestPage() {
  const [name, setName] = useState('');
  const [song, setSong] = useState('');
  const [artist, setArtist] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [status, setStatus] = useState(null); // null, 'pending', 'accepted', 'rejected'
  const [queuePosition, setQueuePosition] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [requestId, setRequestId] = useState(null);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  // stop checking when the page is closed
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const handleSubmit = async () => {
    if (!name.trim() || !song.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const res = await axios.post(`${API}/karaoke/request-song`, {
        singer_name: name.trim(),
        song_title: song.trim(),
        song_artist: artist.trim(),
      });
      if (res.data.success) {
        setSubmitted(true);
        setStatus('pending');
        setRequestId(res.data.request_id);
        // Poll for status updates
        pollStatus(res.data.request_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not send your request. Check your connection and try again.');
    } finally { setSubmitting(false); }
  };

  const pollStatus = (id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${API}/karaoke/request-status/${id}`);
        const s = res.data.status;
        if (s === 'accepted') {
          setStatus('accepted');
          setQueuePosition(res.data.position || 0);
          clearInterval(interval);
        } else if (s === 'rejected') {
          setStatus('rejected');
          clearInterval(interval);
        }
      } catch { clearInterval(interval); }
    }, 3000);
    pollRef.current = interval;
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ backgroundColor: '#000e2a' }}>
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center" style={{ backgroundColor: 'rgba(34,197,94,0.15)', border: `2px solid ${accent}` }}>
            <Mic size={32} style={{ color: accent }} />
          </div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Karaoke Request</h1>
          <p className="text-sm mt-1" style={{ color: '#8892b0' }}>Enter your name and the song you want to sing</p>
        </div>

        {!submitted ? (
          /* Request Form */
          <div className="space-y-4">
            <div>
              <label className="text-xs uppercase tracking-wider font-bold block mb-2" style={{ color: accent }}>Your Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter your name..."
                className="w-full px-4 py-3 rounded-xl text-base"
                style={{ backgroundColor: '#141b50', color: '#fff', border: `1.5px solid rgba(34,197,94,0.3)` }}
                data-testid="karaoke-request-name" autoFocus />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider font-bold block mb-2" style={{ color: accent }}>Song Request</label>
              <input value={song} onChange={(e) => setSong(e.target.value)} placeholder="Song title..."
                className="w-full px-4 py-3 rounded-xl text-base"
                style={{ backgroundColor: '#141b50', color: '#fff', border: `1.5px solid rgba(34,197,94,0.3)` }}
                data-testid="karaoke-request-song" />
            </div>
            <div>
              <label className="text-xs uppercase tracking-wider font-bold block mb-2" style={{ color: accent }}>Artist</label>
              <input value={artist} onChange={(e) => setArtist(e.target.value)} placeholder="Artist name..."
                className="w-full px-4 py-3 rounded-xl text-base"
                style={{ backgroundColor: '#141b50', color: '#fff', border: `1.5px solid rgba(34,197,94,0.3)` }}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                data-testid="karaoke-request-artist" />
            </div>
            <button onClick={handleSubmit} disabled={!name.trim() || !song.trim() || submitting} data-testid="karaoke-request-submit"
              className="w-full py-4 rounded-xl text-lg font-bold flex items-center justify-center gap-2 disabled:opacity-40"
              style={{ backgroundColor: accent, color: '#000' }}>
              <Send size={20} /> {submitting ? 'Submitting...' : 'Submit Request'}
            </button>
            {error && <p className="text-sm text-center" style={{ color: '#fbdd68' }} data-testid="karaoke-request-error">{error}</p>}
          </div>
        ) : (
          /* Status Display */
          <div className="text-center">
            {status === 'pending' && (
              <div data-testid="karaoke-request-pending" className="p-6 rounded-2xl" style={{ backgroundColor: 'rgba(251,221,104,0.1)', border: '1.5px solid rgba(251,221,104,0.3)' }}>
                <div className="w-12 h-12 mx-auto mb-3 rounded-full flex items-center justify-center animate-pulse" style={{ backgroundColor: 'rgba(251,221,104,0.2)' }}>
                  <Mic size={24} style={{ color: '#fbdd68' }} />
                </div>
                <h2 className="text-xl font-bold text-white mb-2">Request Submitted!</h2>
                <p className="text-sm" style={{ color: '#fbdd68' }}>Waiting for the host to review...</p>
                <p className="text-xs mt-3" style={{ color: '#8892b0' }}>
                  <span className="font-bold text-white">{name}</span> — {song}{artist ? ` by ${artist}` : ''}
                </p>
              </div>
            )}
            {status === 'accepted' && (
              <div data-testid="karaoke-request-accepted" className="p-6 rounded-2xl" style={{ backgroundColor: 'rgba(34,197,94,0.1)', border: '1.5px solid rgba(34,197,94,0.3)' }}>
                <CheckCircle size={48} style={{ color: accent }} className="mx-auto mb-3" />
                <h2 className="text-xl font-bold text-white mb-2">You're In!</h2>
                <p className="text-sm" style={{ color: accent }}>Your request has been accepted</p>
                {queuePosition > 0 && (
                  <p className="text-lg font-bold mt-3 text-white">{queuePosition} {queuePosition === 1 ? 'person' : 'people'} ahead of you</p>
                )}
                <p className="text-xs mt-3" style={{ color: '#8892b0' }}>Get ready to sing!</p>
              </div>
            )}
            {status === 'rejected' && (
              <div data-testid="karaoke-request-rejected" className="p-6 rounded-2xl" style={{ backgroundColor: 'rgba(239,68,68,0.1)', border: '1.5px solid rgba(239,68,68,0.3)' }}>
                <XCircle size={48} style={{ color: '#ef4444' }} className="mx-auto mb-3" />
                <h2 className="text-xl font-bold text-white mb-2">Request Not Available</h2>
                <p className="text-sm" style={{ color: '#ef4444' }}>Unfortunately that song isn't available right now</p>
                <p className="text-xs mt-3" style={{ color: '#8892b0' }}>Try requesting a different song!</p>
              </div>
            )}

            {/* Submit another */}
            {(status === 'accepted' || status === 'rejected') && (
              <button onClick={() => { setSubmitted(false); setStatus(null); setSong(''); setArtist(''); }}
                data-testid="karaoke-request-another" className="mt-6 px-6 py-3 rounded-xl text-sm font-bold"
                style={{ border: `1.5px solid ${accent}`, color: accent }}>
                Request Another Song
              </button>
            )}
          </div>
        )}

        <p className="text-center text-[10px] mt-8" style={{ color: '#555' }}>BIG Hat Entertainment</p>
      </div>
    </div>
  );
}
