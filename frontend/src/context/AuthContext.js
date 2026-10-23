import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const API = process.env.REACT_APP_BACKEND_URL;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/auth/me`, { withCredentials: true });
      setUser(data);
    } catch {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const { data } = await axios.get(`${API}/api/auth/me`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          setUser(data);
        } catch {
          localStorage.removeItem('token');
          setUser(false);
        }
      } else {
        setUser(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // CRITICAL: If returning from OAuth callback, skip the /me check.
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    // AuthCallback will exchange the session_id and establish the session first.
    if (window.location.hash?.includes('session_id=')) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const login = async (email, password, copyAccount = false) => {
    const { data } = await axios.post(`${API}/api/auth/login`, { email, password, copy_account: copyAccount }, { withCredentials: true });
    if (data.token) {
      localStorage.setItem('token', data.token);
    }
    // v32.4.0: a Cloud sign-in of a person with no account here answers offer_copy. The app is NOT opened yet: the login page asks
    // "Copy my account to this computer?" first, then calls login again (or finishUnsaved) so the answer is honoured.
    if (data.offer_copy) {
      return data;
    }
    setUser(data);
    return data;
  };

  const finishCloudSignIn = (data) => { setUser(data); return data; };

  const loginWithGoogle = async (sessionId) => {
    const { data } = await axios.post(`${API}/api/auth/google-callback`, { session_id: sessionId }, { withCredentials: true });
    if (data.token) {
      localStorage.setItem('token', data.token);
    }
    setUser(data);
    return data;
  };

  const logout = async () => {
    try {
      await axios.post(`${API}/api/auth/logout`, {}, { withCredentials: true });
    } catch { /* ignore */ }
    localStorage.removeItem('token');
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, finishCloudSignIn, loginWithGoogle, logout, checkAuth, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
