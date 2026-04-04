import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, Users, MapPin, Calendar, FileText, Plus, Pencil, Trash2, Lock, DollarSign, ShieldCheck } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { toast } from 'sonner';
import { useAuth } from '../../context/AuthContext';
import EmployeeManager from '../../components/schedule/EmployeeManager';
import VenueManager from '../../components/schedule/VenueManager';
import EventManager from '../../components/schedule/EventManager';
import WeeklyReport from '../../components/schedule/WeeklyReport';
import MonthlyReports from '../../components/schedule/MonthlyReports';
import LocationPricing from '../../components/schedule/LocationPricing';
import VenueRoleManager from '../../components/schedule/VenueRoleManager';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AdminPage = () => {
  const navigate = useNavigate();
  const { user: hubUser } = useAuth();
  const [activeTab, setActiveTab] = useState('employees');

  // Auto-authenticate: hub admin/master_admin users are automatically authorized
  const isAuthenticated = hubUser?.role === 'admin' || hubUser?.role === 'master_admin';

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>
        <div className="text-center">
          <p className="text-lg font-semibold" style={{ color: '#ef4444' }}>Access Denied</p>
          <p className="text-sm mt-2" style={{ color: '#8892b0' }}>Admin privileges required</p>
          <button onClick={() => navigate('/')} className="mt-4 px-6 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}>Back to Dashboard</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#000e2a', color: '#fff' }}>
      {/* Header - matches hub design */}
      <header className="sticky top-0 z-50" style={{ backgroundColor: 'rgba(0, 14, 42, 0.8)', backdropFilter: 'blur(24px)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <button onClick={() => navigate('/')} className="p-2 rounded-lg transition-colors hover:bg-white/5">
                <ArrowLeft className="h-5 w-5" style={{ color: '#fbdd68' }} />
              </button>
              <img src="/hat-logo.png" alt="BIG Hat" className="h-10 w-10 object-contain" />
              <div>
                <h1 className="text-xl font-bold" style={{ color: '#fbdd68' }}>Schedule Admin</h1>
                <p className="text-xs" style={{ color: '#8892b0' }}>Manage employees, venues, and events</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4" style={{ color: '#22c55e' }} />
              <span className="text-sm font-medium" style={{ color: '#22c55e' }}>Authenticated</span>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Tabs - styled to match hub */}
        <div className="flex flex-wrap gap-2 mb-6">
          {[
            { id: 'employees', label: 'Employees', icon: Users },
            { id: 'venues', label: 'Venues', icon: MapPin },
            { id: 'pricing', label: 'Pricing', icon: DollarSign },
            { id: 'roles', label: 'Roles', icon: ShieldCheck },
            { id: 'events', label: 'Events', icon: Calendar },
            { id: 'reports', label: 'Weekly', icon: FileText },
            { id: 'monthly', label: 'Monthly', icon: Calendar },
          ].map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                style={{
                  backgroundColor: activeTab === tab.id ? 'rgba(251, 221, 104, 0.15)' : 'rgba(20, 27, 80, 0.4)',
                  color: activeTab === tab.id ? '#fbdd68' : '#8892b0',
                  border: `1px solid ${activeTab === tab.id ? 'rgba(251, 221, 104, 0.3)' : 'rgba(251, 221, 104, 0.08)'}`
                }}
              >
                <Icon size={16} /> {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="dark">
          {activeTab === 'employees' && <EmployeeManager />}
          {activeTab === 'venues' && <VenueManager />}
          {activeTab === 'pricing' && <LocationPricing />}
          {activeTab === 'roles' && <VenueRoleManager />}
          {activeTab === 'events' && <EventManager />}
          {activeTab === 'reports' && <WeeklyReport />}
          {activeTab === 'monthly' && <MonthlyReports />}
        </div>
      </div>
    </div>
  );
};

export default AdminPage;
