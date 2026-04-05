import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import AdminPage from './pages/AdminPage';
import SchedulingPage from './pages/schedule/SchedulingPage';
import ScheduleAdminPage from './pages/schedule/ScheduleAdminPage';
import ProfilePage from './pages/schedule/ProfilePage';
import TriviaDashboard from './pages/trivia/TriviaDashboard';
import TriviaPresenterView from './pages/trivia/TriviaPresenterView';
import TriviaEditor from './pages/trivia/Editor';
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
