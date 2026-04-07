import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { useData } from '../../context/SponsorContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AuthCallback = ({ onLogin }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { initializeUserProfile } = useData();
  const hasProcessed = useRef(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('Completing sign in...');

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processAuth = async () => {
      try {
        // Extract session_id from URL hash
        const hash = location.hash;
        const sessionIdMatch = hash.match(/session_id=([^&]+)/);
        
        if (!sessionIdMatch) {
          throw new Error('No session ID found in redirect');
        }

        const sessionId = sessionIdMatch[1];
        setStatus('Verifying your account...');

        // Exchange session_id for user data via backend
        const response = await fetch(`${BACKEND_URL}/api/auth/session`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Session-ID': sessionId,
          },
          credentials: 'include',
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to authenticate');
        }

        const userData = await response.json();
        setStatus('Welcome back!');
        
        // Check for stored package selection (from signup flow)
        const selectedPackage = localStorage.getItem('selectedPackage');
        if (selectedPackage) {
          localStorage.removeItem('selectedPackage');
        }

        // Store user and redirect
        // CRITICAL: Initialize DataContext's userProfile for subscription logic
        initializeUserProfile(userData);
        
        onLogin(userData);
        toast.success(`Welcome, ${userData.name}!`);
        
        // Redirect based on role
        const redirectPath = userData.role === 'admin' ? '/admin' : '/dashboard';
        navigate(redirectPath, { replace: true });
        
      } catch (err) {
        console.error('Auth error:', err);
        setError(err.message);
        toast.error('Sign in failed: ' + err.message);
        // Redirect to login after error
        setTimeout(() => navigate('/login'), 3000);
      }
    };

    processAuth();
  }, [location, navigate, onLogin, initializeUserProfile]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0f0f1a]">
        <div className="text-center card-dark rounded-2xl p-8 max-w-md">
          <div className="w-16 h-16 rounded-full bg-red-500/20 flex items-center justify-center mx-auto mb-4">
            <span className="text-red-400 text-2xl">!</span>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Authentication Failed</h2>
          <p className="text-red-400 mb-4">{error}</p>
          <p className="text-white/60 text-sm">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0f0f1a]">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-[#f4d03f] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-white text-lg">{status}</p>
      </div>
    </div>
  );
};

export default AuthCallback;
