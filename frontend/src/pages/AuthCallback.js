import React, { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function AuthCallback() {
  const navigate = useNavigate();
  const { loginWithGoogle } = useAuth();
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = window.location.hash;
    const sessionIdMatch = hash.match(/session_id=([^&]+)/);
    
    if (!sessionIdMatch) {
      navigate('/login', { replace: true });
      return;
    }

    const sessionId = sessionIdMatch[1];

    const processAuth = async () => {
      // Retry up to 3 times with delays
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          await loginWithGoogle(sessionId);
          window.history.replaceState({}, document.title, '/');
          navigate('/', { replace: true });
          return;
        } catch (err) {
          console.warn(`Google auth attempt ${attempt} failed:`, err.message);
          if (attempt < 3) {
            await new Promise(r => setTimeout(r, 1500)); // Wait 1.5s before retry
          } else {
            navigate('/login', { replace: true, state: { error: 'Authentication failed. Please try again.' } });
          }
        }
      }
    };

    processAuth();
  }, [loginWithGoogle, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
      <div className="text-center">
        <img src="/hat-logo.png" alt="Loading" className="w-16 h-16 mx-auto mb-4 animate-pulse" />
        <p className="text-sm" style={{ color: '#8892b0' }}>Signing you in...</p>
      </div>
    </div>
  );
}
