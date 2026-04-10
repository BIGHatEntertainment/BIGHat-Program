import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import '@/App.css';
import SchedulingPage from './pages/SchedulingPage';
import AdminPage from './pages/AdminPage';
import ProfilePage from './pages/ProfilePage';
import AuthCallback from './components/AuthCallback';
import { Toaster } from './components/ui/sonner';

// Router wrapper to check for OAuth callback
function AppRouter() {
  const location = useLocation();
  
  // Check for session_id in URL fragment BEFORE rendering routes
  // This prevents race conditions by detecting OAuth callback synchronously
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }
  
  return (
    <Routes>
      <Route path="/" element={<SchedulingPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <Toaster richColors position="top-center" />
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </div>
  );
}

export default App;
