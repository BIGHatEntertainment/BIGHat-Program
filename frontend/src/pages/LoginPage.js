import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
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
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState(location.state?.error || '');
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

  const handleGoogleSignIn = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + '/';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
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
          <h2 className="text-lg font-semibold text-white mb-6 text-center">Sign in to manage your events</h2>

          {/* Google Sign In Button */}
          <button
            onClick={handleGoogleSignIn}
            className="w-full flex items-center justify-center gap-3 py-3 rounded-xl font-semibold text-sm transition-all duration-300 hover:shadow-lg mb-4"
            style={{ backgroundColor: '#ffffff', color: '#333333', border: '1px solid #e0e0e0' }}
            data-testid="google-signin-button"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4"/>
              <path d="M9.003 18c2.43 0 4.467-.806 5.956-2.18l-2.909-2.26c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9.003 18z" fill="#34A853"/>
              <path d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
              <path d="M9.003 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.464.891 11.428 0 9.002 0 5.48 0 2.438 2.017.956 4.958L3.964 7.29c.708-2.127 2.692-3.71 5.036-3.71z" fill="#EA4335"/>
            </svg>
            Sign in with Google
          </button>

          <p className="text-center text-xs mb-4" style={{ color: '#8892b0' }}>
            Secure login using your Google account
          </p>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px" style={{ backgroundColor: 'rgba(251, 221, 104, 0.15)' }} />
            <span className="text-xs uppercase tracking-wider" style={{ color: '#8892b0' }}>or use password</span>
            <div className="flex-1 h-px" style={{ backgroundColor: 'rgba(251, 221, 104, 0.15)' }} />
          </div>

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
                className="w-full px-4 py-3 rounded-lg text-sm text-white outline-none transition-all duration-300"
                style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.2)' }}
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
                  style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.2)' }}
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
              className="w-full py-3 rounded-lg font-bold text-sm transition-all duration-300 hover:shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
              style={{ backgroundColor: '#fbdd68', color: '#000e2a', boxShadow: '0 0 15px rgba(251, 221, 104, 0.2)' }}
              data-testid="login-submit-button"
            >
              <LogIn size={16} />
              {loading ? 'Signing in...' : 'Sign In with Password'}
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
