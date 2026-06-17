import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { NativeProvider, useNative } from './context/NativeContext';
import LoginPage from './pages/LoginPage';
import AuthCallback from './pages/AuthCallback';
import Dashboard from './pages/Dashboard';
import AdminPage from './pages/AdminPage';
import SchedulingPage from './pages/schedule/SchedulingPage';
import ScheduleAdminPage from './pages/schedule/ScheduleAdminPage';
import ProfilePage from './pages/schedule/ProfilePage';
import TriviaDashboard from './pages/trivia/TriviaDashboard';
import TriviaPresenterView from './pages/trivia/TriviaPresenterView';
import TriviaEditor from './pages/trivia/Editor';
import RoundMakerDashboard from './pages/roundmaker/RoundMakerDashboard';
import RoundCreator from './pages/roundmaker/RoundCreator';
import BingoLobby from './pages/bingo/Lobby';
import BingoHostDashboard from './pages/bingo/HostDashboard';
import BingoAudienceView from './pages/bingo/AudienceView';
import ScoreboardDashboard from './pages/scoreboard/ScoreboardDashboard';
import ScoreboardLiveRender from './pages/scoreboard/LiveRender';
import StoryGeneratorPage from './pages/story/StoryGeneratorPage';
import SetupWizard from './pages/SetupWizard';
import LicenseApiLanding from './pages/LicenseApiLanding';
import { Toaster } from './components/ui/sonner';
import './index.css';

/**
 * True when this React bundle is being served from the cloud license API
 * deployment (e.g. `api.bighat.live`). The cloud server hosts the same
 * backend as the desktop app but should NEVER expose the host UI to humans.
 * We detect by hostname so no extra build step / env var is needed.
 */
function isLicenseApiHost() {
  if (typeof window === 'undefined') return false;
  const h = window.location.hostname || '';
  // Exact prefix match: api.bighat.live, api.staging.bighat.live, etc.
  // Local dev (127.0.0.1, localhost, *.preview.emergentagent.com) never matches.
  return h.startsWith('api.');
}

function LoadingScreen({ label = 'Loading...' }) {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
      <div className="text-center">
        <img src="/hat-logo.png" alt="Loading" className="w-16 h-16 mx-auto mb-4 animate-pulse" />
        <p className="text-sm" style={{ color: '#8892b0' }}>{label}</p>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (user) return <Navigate to="/" replace />;
  return children;
}

/**
 * Native-mode gate. When BIGHAT_NATIVE_MODE=1 on the backend AND setup is incomplete,
 * every route except /setup is redirected to /setup. When setup is complete OR
 * native mode is off, behaviour is identical to the original webapp.
 */
function NativeGate({ children }) {
  const { loading, error, isNativeBuild, nativeMode, setupComplete, refresh } = useNative();
  const location = useLocation();

  // v31.0.10 hardening: a native install whose backend isn't reachable must
  // NEVER fall through to /login (where the user would face cryptic auth
  // errors). Show a clear "can't reach backend" screen with a retry.
  if (loading && isNativeBuild && error) {
    return (
      <div data-testid="backend-unreachable"
           style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', background: '#0a1428', color: '#e5edff',
                    fontFamily: 'system-ui, -apple-system, sans-serif', padding: 24 }}>
        <div style={{ maxWidth: 480, textAlign: 'center' }}>
          <h1 style={{ color: '#fbdd68', margin: 0, fontSize: 28 }}>BIG Hat</h1>
          <p style={{ color: '#8892b0', marginTop: 8, fontSize: 14 }}>can't reach its background service</p>
          <p style={{ marginTop: 32, fontSize: 15, lineHeight: 1.5 }}>
            The app's backend isn't responding yet. This usually clears up
            in a few seconds. If it persists, close BIG Hat completely and
            relaunch it from your Start Menu / Applications folder.
          </p>
          <button onClick={() => refresh()} data-testid="backend-retry-btn"
                  style={{ marginTop: 24, padding: '12px 24px', borderRadius: 10,
                           background: '#fbdd68', color: '#1a1a1a', border: 0,
                           fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
            Try again
          </button>
          <p style={{ marginTop: 24, fontSize: 12, color: '#8892b0' }}>
            Still stuck? Email support@bighat.live with this code:
            <code style={{ marginLeft: 6, padding: '2px 8px', background: '#0f1d3a',
                            borderRadius: 4, fontSize: 11 }}>NET-{error?.slice(0, 24) || 'UNKNOWN'}</code>
          </p>
        </div>
      </div>
    );
  }

  if (loading) return <LoadingScreen label="Initializing..." />;

  if (nativeMode && !setupComplete && location.pathname !== '/setup') {
    return <Navigate to="/setup" replace />;
  }
  if (nativeMode && setupComplete && location.pathname === '/setup') {
    return <Navigate to="/login" replace />;
  }
  // Non-native: /setup is still reachable for manual configuration but not forced.
  return children;
}

function AppRoutes() {
  const location = useLocation();
  // Check URL fragment for session_id from Google OAuth callback
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  return (
    <NativeGate>
      <Routes>
        <Route path="/setup" element={<SetupWizard />} />
        <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
        <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
        <Route path="/schedule" element={<ProtectedRoute><SchedulingPage /></ProtectedRoute>} />
        <Route path="/schedule/admin" element={<ProtectedRoute><ScheduleAdminPage /></ProtectedRoute>} />
        <Route path="/schedule/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
        <Route path="/trivia" element={<ProtectedRoute><TriviaDashboard /></ProtectedRoute>} />
        <Route path="/trivia/present" element={<ProtectedRoute><TriviaPresenterView /></ProtectedRoute>} />
        <Route path="/trivia/editor" element={<ProtectedRoute><TriviaEditor /></ProtectedRoute>} />
        <Route path="/roundmaker" element={<ProtectedRoute><RoundMakerDashboard /></ProtectedRoute>} />
        <Route path="/roundmaker/create/:roundType" element={<ProtectedRoute><RoundCreator /></ProtectedRoute>} />
        <Route path="/bingo" element={<ProtectedRoute><BingoLobby /></ProtectedRoute>} />
        <Route path="/bingo/host" element={<ProtectedRoute><BingoHostDashboard /></ProtectedRoute>} />
        <Route path="/bingo/audience" element={<BingoAudienceView />} />
        <Route path="/scoreboard" element={<ProtectedRoute><ScoreboardDashboard /></ProtectedRoute>} />
        <Route path="/scoreboard/live" element={<ProtectedRoute><ScoreboardLiveRender /></ProtectedRoute>} />
        <Route path="/story-generator" element={<ProtectedRoute><StoryGeneratorPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </NativeGate>
  );
}

function App() {
  // Cloud license API server: never expose the desktop host UI publicly.
  // Bypasses Auth + Native providers (no /api/native/* calls — the cloud
  // deploy runs with BIGHAT_CLOUD_MODE=1 where those routes are absent).
  if (isLicenseApiHost()) {
    return (
      <>
        <Toaster richColors position="top-center" />
        <LicenseApiLanding />
      </>
    );
  }
  return (
    <BrowserRouter>
      <NativeProvider>
        <AuthProvider>
          <Toaster richColors position="top-center" />
          <AppRoutes />
        </AuthProvider>
      </NativeProvider>
    </BrowserRouter>
  );
}

export default App;
