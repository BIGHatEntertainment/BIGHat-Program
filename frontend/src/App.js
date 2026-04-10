import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
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
import { Toaster } from './components/ui/sonner';
import './index.css';

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <div className="text-center">
          <img src="/hat-logo.png" alt="Loading" className="w-16 h-16 mx-auto mb-4 animate-pulse" />
          <p className="text-sm" style={{ color: '#8892b0' }}>Loading...</p>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <div className="text-center">
          <img src="/hat-logo.png" alt="Loading" className="w-16 h-16 mx-auto mb-4 animate-pulse" />
          <p className="text-sm" style={{ color: '#8892b0' }}>Loading...</p>
        </div>
      </div>
    );
  }
  if (user) return <Navigate to="/" replace />;
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
    <Routes>
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
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster richColors position="top-center" />
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
