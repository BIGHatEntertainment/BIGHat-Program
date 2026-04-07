import React, { useState } from 'react';
import './App.css';
import { BrowserRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { DataProvider } from './context/DataContext';

// Layout Components
import Header from './components/layout/Header';
import Footer from './components/layout/Footer';

// Public Pages
import Home from './pages/Home';
import Packages from './pages/Packages';
import HowItWorks from './pages/HowItWorks';
import FAQ from './pages/FAQ';
import Login from './pages/Login';
import Signup from './pages/Signup';
import AuthCallback from './pages/AuthCallback';
import TermsOfService from './pages/TermsOfService';
import PrivacyPolicy from './pages/PrivacyPolicy';
import ConfirmDeletion from './pages/ConfirmDeletion';

// Dashboard Pages
import DashboardLayout from './pages/DashboardLayout';
import DashboardOverview from './pages/dashboard/DashboardOverview';
import UploadMedia from './pages/dashboard/UploadMedia';
import MyAssets from './pages/dashboard/MyAssets';
import Placements from './pages/dashboard/Placements';
import Statistics from './pages/dashboard/Statistics';
import Profile from './pages/dashboard/Profile';
import Subscribe from './pages/dashboard/Subscribe';

// Admin Pages
import AdminLayout from './pages/AdminLayout';
import AdminOverview from './pages/admin/AdminOverview';
import PendingApprovals from './pages/admin/PendingApprovals';
import LocationsManagement from './pages/admin/LocationsManagement';
import SponsorsManagement from './pages/admin/SponsorsManagement';
import AllAssets from './pages/admin/AllAssets';
import AdminSettings from './pages/admin/AdminSettings';

// Protected Route Component
const ProtectedRoute = ({ user, children }) => {
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// App Router with auth callback detection
function AppRouter({ user, setUser }) {
  const location = useLocation();

  // Handle auth callback synchronously
  if (location.hash?.includes('session_id=')) {
    return <AuthCallback onLogin={setUser} />;
  }

  const handleLogout = () => {
    setUser(null);
    // Clear localStorage
    localStorage.removeItem('bh_user');
    // Clear cookies if needed
    document.cookie = 'session_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
  };

  // Determine if we should show header/footer
  const isDashboard = location.pathname.startsWith('/dashboard');
  const isAdmin = location.pathname.startsWith('/admin');
  const showHeaderFooter = !isDashboard && !isAdmin;

  return (
    <>
      {showHeaderFooter && <Header user={user} onLogout={handleLogout} />}
      
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<Home />} />
        <Route path="/packages" element={<Packages />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/faq" element={<FAQ />} />
        <Route path="/terms" element={<TermsOfService />} />
        <Route path="/privacy" element={<PrivacyPolicy />} />
        <Route path="/confirm-deletion" element={<ConfirmDeletion />} />
        <Route path="/login" element={<Login onLogin={setUser} />} />
        <Route path="/signup" element={<Signup onLogin={setUser} />} />

        {/* Dashboard Routes (Protected) */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute user={user}>
              <DashboardLayout user={user} onLogout={handleLogout} />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardOverview user={user} />} />
          <Route path="upload" element={<UploadMedia />} />
          <Route path="assets" element={<MyAssets />} />
          <Route path="placements" element={<Placements />} />
          <Route path="stats" element={<Statistics />} />
          <Route path="profile" element={<Profile user={user} onUpdateUser={setUser} />} />
          <Route path="subscribe" element={<Subscribe user={user} />} />
        </Route>

        {/* Admin Routes (Protected) */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute user={user}>
              <AdminLayout user={user} onLogout={handleLogout} />
            </ProtectedRoute>
          }
        >
          <Route index element={<AdminOverview />} />
          <Route path="approvals" element={<PendingApprovals />} />
          <Route path="locations" element={<LocationsManagement />} />
          <Route path="sponsors" element={<SponsorsManagement />} />
          <Route path="assets" element={<AllAssets />} />
          <Route path="settings" element={<AdminSettings />} />
        </Route>
      </Routes>

      {showHeaderFooter && <Footer />}
      
      <Toaster 
        position="top-right" 
        theme="dark"
        toastOptions={{
          style: {
            background: '#1a1a2e',
            border: '1px solid rgba(244, 208, 63, 0.2)',
            color: '#fff',
          },
        }}
      />
    </>
  );
}

function App() {
  // Initialize user from localStorage if available
  const [user, setUser] = useState(() => {
    try {
      const savedUser = localStorage.getItem('bh_user');
      if (savedUser) {
        let userData = JSON.parse(savedUser);
        let needsSave = false;
        
        // Fix any stale "Top Tier" references to "Star Tier"
        if (userData.sponsorPackage && userData.sponsorPackage.toLowerCase().includes('top tier')) {
          userData.sponsorPackage = userData.sponsorPackage.replace(/top tier/gi, 'Star Tier');
          needsSave = true;
        }
        
        // CRITICAL FIX: Clean stale isVenueSponsor flags
        // If isVenueSponsor is true but there's no sponsorTier/sponsorId to back it up,
        // this is likely corrupted data from a previous session. Reset it.
        if (userData.isVenueSponsor === true && !userData.sponsorId && !userData.sponsorTier) {
          userData.isVenueSponsor = false;
          needsSave = true;
        }
        
        if (needsSave) {
          localStorage.setItem('bh_user', JSON.stringify(userData));
        }
        
        return userData;
      }
      return null;
    } catch (e) {
      return null;
    }
  });

  // Persist user to localStorage when it changes
  const handleSetUser = (newUser) => {
    if (newUser) {
      // Fix any "Top Tier" references before saving
      if (newUser.sponsorPackage && newUser.sponsorPackage.toLowerCase().includes('top tier')) {
        newUser.sponsorPackage = newUser.sponsorPackage.replace(/top tier/gi, 'Star Tier');
      }
      localStorage.setItem('bh_user', JSON.stringify(newUser));
    } else {
      localStorage.removeItem('bh_user');
    }
    setUser(newUser);
  };

  return (
    <DataProvider>
      <div className="App min-h-screen bg-[#0f0f1a]">
        <BrowserRouter>
          <AppRouter user={user} setUser={handleSetUser} />
        </BrowserRouter>
      </div>
    </DataProvider>
  );
}

export default App;