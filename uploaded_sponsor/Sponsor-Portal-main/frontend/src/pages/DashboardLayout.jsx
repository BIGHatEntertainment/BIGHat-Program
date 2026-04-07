import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { 
  LayoutDashboard, Upload, Image, Calendar, BarChart3, User, LogOut, Menu, X, ChevronRight, ShoppingCart, CreditCard 
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useData } from '../context/DataContext';

const DashboardLayout = ({ user, onLogout }) => {
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { getActiveSubscription, userProfile } = useData();
  
  const activeSubscription = getActiveSubscription();
  
  // Check if user is a venue sponsor
  const isVenueSponsor = userProfile?.isVenueSponsor || activeSubscription?.isVenueSponsor;

  // Base navigation items
  const allNavItems = [
    { path: '/dashboard', label: 'Overview', icon: LayoutDashboard, end: true },
    { path: '/dashboard/upload', label: 'Upload Media', icon: Upload },
    { path: '/dashboard/assets', label: 'My Assets', icon: Image },
    { path: '/dashboard/placements', label: 'Placements', icon: Calendar, hideForVenueSponsor: true },
    { path: '/dashboard/stats', label: 'Statistics', icon: BarChart3 },
    { path: '/dashboard/profile', label: 'Profile', icon: User },
  ];
  
  // Filter out Placements for venue sponsors
  const navItems = isVenueSponsor 
    ? allNavItems.filter(item => !item.hideForVenueSponsor)
    : allNavItems;

  const handleLogout = () => {
    onLogout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-[#0f0f1a] pt-20">
      {/* Mobile Sidebar Toggle */}
      <button
        className="lg:hidden fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-[#f4d03f] text-[#1a1a2e] flex items-center justify-center shadow-lg"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      <div className="flex">
        {/* Sidebar */}
        <aside
          className={`fixed lg:sticky top-20 left-0 z-40 h-[calc(100vh-5rem)] w-64 bg-[#1a1a2e]/80 backdrop-blur-lg border-r border-[#f4d03f]/10 transform transition-transform duration-300 lg:translate-x-0 ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex flex-col h-full p-4">
            {/* User Info */}
            <div className="mb-6 p-4 bg-white/5 rounded-xl">
              <div className="flex items-center gap-3">
                <img
                  src={user?.picture || 'https://api.dicebear.com/7.x/initials/svg?seed=U'}
                  alt={user?.name}
                  className="w-10 h-10 rounded-full border-2 border-[#f4d03f]/30"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{user?.name || 'Sponsor'}</p>
                  <p className="text-white/50 text-xs truncate">{user?.businessName || user?.email}</p>
                </div>
              </div>
              {activeSubscription ? (
                <div className="mt-3 pt-3 border-t border-white/10">
                  {activeSubscription.isVenueSponsor ? (
                    <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-xs">
                      🏠 Venue Sponsor
                    </Badge>
                  ) : (
                    <Badge className="bg-[#f4d03f]/20 text-[#f4d03f] border-[#f4d03f]/30 text-xs">
                      {activeSubscription.packageName}
                    </Badge>
                  )}
                </div>
              ) : (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30 text-xs">
                    No Active Plan
                  </Badge>
                </div>
              )}
            </div>

            {/* Subscribe/Upgrade CTA */}
            {!activeSubscription && (
              <NavLink
                to="/dashboard/subscribe"
                onClick={() => setSidebarOpen(false)}
                className="mb-4 p-3 bg-gradient-to-r from-[#f4d03f]/20 to-[#d4ac0d]/20 rounded-xl border border-[#f4d03f]/30 hover:border-[#f4d03f]/50 transition-colors"
              >
                <div className="flex items-center gap-2 text-[#f4d03f]">
                  <ShoppingCart size={16} />
                  <span className="font-medium text-sm">Get Started</span>
                </div>
                <p className="text-white/50 text-xs mt-1">Choose a sponsorship package</p>
              </NavLink>
            )}

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
                        ? 'bg-[#f4d03f]/10 text-[#f4d03f]'
                        : 'text-white/60 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  <item.icon size={18} />
                  {item.label}
                  <ChevronRight size={14} className="ml-auto opacity-50" />
                </NavLink>
              ))}

              {/* Subscription Management */}
              <NavLink
                to="/dashboard/subscribe"
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[#f4d03f]/10 text-[#f4d03f]'
                      : 'text-white/60 hover:text-white hover:bg-white/5'
                  }`
                }
              >
                <CreditCard size={18} />
                {activeSubscription ? 'Manage Plan' : 'Subscribe'}
                <ChevronRight size={14} className="ml-auto opacity-50" />
              </NavLink>
            </nav>

            {/* Logout */}
            <Button
              variant="ghost"
              onClick={handleLogout}
              className="w-full justify-start text-red-400 hover:bg-red-500/10 hover:text-red-400 mt-4"
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

export default DashboardLayout;
