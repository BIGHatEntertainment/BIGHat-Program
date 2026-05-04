import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Settings, LogOut, Menu, X, ChevronDown } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const isAdmin = user?.role === 'admin' || user?.role === 'master_admin';

  return (
    <header className="sticky top-0 z-50 glass" style={{ borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }} data-testid="app-header">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')} data-testid="header-logo">
            <img src="/hat-logo.png" alt="BIG Hat" className="w-10 h-10 object-contain" />
            <span className="text-xl font-bold font-['Lemonada'] hidden sm:block" style={{ color: '#fbdd68' }}>
              BIG Hat
            </span>
          </div>

          {/* Nav Links - Desktop */}
          <nav className="hidden md:flex items-center gap-1">
            <NavLink active={location.pathname === '/'} onClick={() => navigate('/')}>Dashboard</NavLink>
            <NavLink active={location.pathname === '/schedule'} onClick={() => navigate('/schedule')}>Schedule</NavLink>
            {isAdmin && (
              <NavLink active={location.pathname === '/admin'} onClick={() => navigate('/admin')}>
                <Settings size={14} className="mr-1" />
                Admin
              </NavLink>
            )}
            {isAdmin && (
              <NavLink active={location.pathname === '/schedule/admin'} onClick={() => navigate('/schedule/admin')}>
                <Settings size={14} className="mr-1" />
                Schedule Admin
              </NavLink>
            )}
          </nav>

          {/* Right - Profile */}
          <div className="flex items-center gap-3">
            {/* Role Badge */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs" style={{ backgroundColor: 'rgba(20, 27, 80, 0.6)', border: '1px solid rgba(251, 221, 104, 0.1)' }}>
              <span style={{ color: '#8892b0' }}>Role:</span>
              <span className="font-semibold" style={{ color: '#fbdd68' }} data-testid="user-role-badge">
                {user?.role === 'master_admin' ? 'Master Admin' : user?.role === 'admin' ? 'Admin' : 'Host'}
              </span>
            </div>

            {/* Profile Dropdown */}
            <div className="relative">
              <button
                onClick={() => setProfileOpen(!profileOpen)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-200 hover:bg-white/5"
                data-testid="profile-dropdown-button"
              >
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}>
                  {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                </div>
                <ChevronDown size={14} className={`transition-transform ${profileOpen ? 'rotate-180' : ''}`} style={{ color: '#8892b0' }} />
              </button>
              {profileOpen && (
                <div className="absolute right-0 top-full mt-2 w-48 rounded-lg py-2 animate-fade-in" style={{ backgroundColor: '#141b50', border: '1px solid rgba(251, 221, 104, 0.2)' }}>
                  <div className="px-4 py-2 border-b" style={{ borderColor: 'rgba(251, 221, 104, 0.1)' }}>
                    <p className="text-sm font-medium text-white">{user?.name}</p>
                    <p className="text-xs" style={{ color: '#8892b0' }}>{user?.email}</p>
                  </div>
                  {isAdmin && (
                    <button
                      onClick={() => { navigate('/admin'); setProfileOpen(false); }}
                      className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center gap-2 text-white"
                      data-testid="admin-settings-link"
                    >
                      <Settings size={14} style={{ color: '#fbdd68' }} /> Settings
                    </button>
                  )}
                  <button
                    onClick={() => { logout(); setProfileOpen(false); }}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-white/5 flex items-center gap-2"
                    style={{ color: '#ef4444' }}
                    data-testid="logout-button"
                  >
                    <LogOut size={14} /> Sign Out
                  </button>
                </div>
              )}
            </div>

            {/* Mobile menu */}
            <button className="md:hidden" onClick={() => setMenuOpen(!menuOpen)} data-testid="mobile-menu-toggle">
              {menuOpen ? <X size={24} color="#fbdd68" /> : <Menu size={24} color="#fbdd68" />}
            </button>
          </div>
        </div>

        {/* Mobile Nav */}
        {menuOpen && (
          <div className="md:hidden py-3 border-t animate-fade-in" style={{ borderColor: 'rgba(251, 221, 104, 0.1)' }}>
            <NavLink mobile active={location.pathname === '/'} onClick={() => { navigate('/'); setMenuOpen(false); }}>Dashboard</NavLink>
            <NavLink mobile active={location.pathname === '/schedule'} onClick={() => { navigate('/schedule'); setMenuOpen(false); }}>Schedule</NavLink>
            {isAdmin && (
              <NavLink mobile active={location.pathname === '/admin'} onClick={() => { navigate('/admin'); setMenuOpen(false); }}>Admin Settings</NavLink>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

function NavLink({ children, active, onClick, mobile }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${mobile ? 'w-full text-left' : ''}`}
      style={{
        color: active ? '#fbdd68' : '#8892b0',
        backgroundColor: active ? 'rgba(251, 221, 104, 0.1)' : 'transparent'
      }}
    >
      {children}
    </button>
  );
}
