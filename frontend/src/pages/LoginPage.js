import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Eye, EyeOff, LogIn } from 'lucide-react';

function formatApiError(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  return String(detail);
}

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden" style={{ backgroundColor: '#000e2a' }}>
      {/* Background glow orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-20 animate-pulse-glow" style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }} />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full opacity-15 animate-pulse-glow" style={{ background: 'radial-gradient(circle, #5973F7 0%, transparent 70%)', animationDelay: '2s' }} />

      <div className="relative z-10 w-full max-w-md mx-4 animate-slide-up" data-testid="login-page">
        {/* Logo */}
        <div className="text-center mb-8">
          <img src="/hat-logo.png" alt="BIG Hat" className="w-24 h-24 mx-auto mb-4 object-contain" data-testid="login-logo" />
          <h1 className="text-4xl font-bold font-['Lemonada']" style={{ color: '#fbdd68' }}>
            BIG Hat
          </h1>
          <p className="mt-2 text-sm" style={{ color: '#8892b0' }}>Host Command Center</p>
        </div>

        {/* Login Card */}
        <div className="glass-card rounded-2xl p-8" data-testid="login-form">
          <h2 className="text-lg font-semibold text-white mb-6 flex items-center gap-2">
            <LogIn size={20} style={{ color: '#fbdd68' }} />
            Sign In
          </h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444' }} data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8892b0' }}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-lg text-sm text-white outline-none transition-all duration-300 focus:ring-2"
                style={{
                  backgroundColor: 'rgba(20, 27, 80, 0.6)',
                  border: '1px solid rgba(251, 221, 104, 0.2)',
                  focusRingColor: '#fbdd68'
                }}
                placeholder="your@email.com"
                required
                data-testid="login-email-input"
              />
            </div>

            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: '#8892b0' }}>Password</label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 rounded-lg text-sm text-white outline-none transition-all duration-300 pr-12"
                  style={{
                    backgroundColor: 'rgba(20, 27, 80, 0.6)',
                    border: '1px solid rgba(251, 221, 104, 0.2)'
                  }}
                  placeholder="Enter password"
                  required
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 opacity-60 hover:opacity-100 transition-opacity"
                  data-testid="toggle-password-visibility"
                >
                  {showPass ? <EyeOff size={18} color="#8892b0" /> : <Eye size={18} color="#8892b0" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg font-bold text-sm transition-all duration-300 hover:shadow-lg disabled:opacity-50"
              style={{
                backgroundColor: '#fbdd68',
                color: '#000e2a',
                boxShadow: '0 0 15px rgba(251, 221, 104, 0.2)'
              }}
              data-testid="login-submit-button"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: '#8892b0' }}>
          Contact your admin for account access
        </p>
      </div>
    </div>
  );
}
