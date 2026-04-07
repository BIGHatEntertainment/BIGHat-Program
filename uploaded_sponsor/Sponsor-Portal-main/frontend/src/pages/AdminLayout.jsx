import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, Users, Image, CheckSquare, Settings, LogOut, Menu, X, ChevronRight, Shield, MapPin, Building2 
} from 'lucide-react';
import { Button } from '../components/ui/button';

const AdminLayout = ({ user, onLogout }) => {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const navItems = [
    { path: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
    { path: '/admin/approvals', label: 'Pending Approvals', icon: CheckSquare },
    { path: '/admin/locations', label: 'Locations', icon: MapPin },
    { path: '/admin/sponsors', label: 'Sponsors', icon: Building2 },
    { path: '/admin/assets', label: 'All Assets', icon: Image },
    { path: '/admin/settings', label: 'Settings', icon: Settings },
  ];

  const handleLogout = () => {
    onLogout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-[#0f0f1a] pt-20">
      {/* Mobile Sidebar Toggle */}
      <button
        className="lg:hidden fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-[#e94560] text-white flex items-center justify-center shadow-lg"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      <div className="flex">
        {/* Sidebar */}
        <aside
          className={`fixed lg:sticky top-20 left-0 z-40 h-[calc(100vh-5rem)] w-64 bg-[#1a1a2e]/80 backdrop-blur-lg border-r border-[#e94560]/20 transform transition-transform duration-300 lg:translate-x-0 ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex flex-col h-full p-4">
            {/* Admin Badge */}
            <div className="mb-6 p-4 bg-[#e94560]/10 rounded-xl border border-[#e94560]/20">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-[#f4d03f] flex items-center justify-center">
                  <span className="text-[#1a1a2e] font-bold text-sm">NS</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium">{user?.name || 'Nicholas Sellards'}</p>
                  <p className="text-[#e94560] text-xs">Admin • BIG Hat Trivia</p>
                </div>
              </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.end}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-[#e94560]/10 text-[#e94560]'
                        : 'text-white/60 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  <item.icon size={18} />
                  {item.label}
                  <ChevronRight size={14} className="ml-auto opacity-50" />
                </NavLink>
              ))}
            </nav>

            {/* Back to Sponsor View */}
            <Button
              variant="ghost"
              onClick={() => navigate('/dashboard')}
              className="w-full justify-start text-white/60 hover:text-white hover:bg-white/5 mb-2"
            >
              Switch to Sponsor View
            </Button>

            {/* Logout */}
            <Button
              variant="ghost"
              onClick={handleLogout}
              className="w-full justify-start text-red-400 hover:bg-red-500/10 hover:text-red-400"
            >
              <LogOut size={18} className="mr-3" />
              Logout
            </Button>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 min-h-[calc(100vh-5rem)] p-4 lg:p-8">
          <div className="max-w-6xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default AdminLayout;