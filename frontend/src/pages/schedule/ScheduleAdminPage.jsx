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
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-white border-b border-border shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Button
                onClick={() => navigate('/')}
                variant="ghost"
                size="icon"
                className="hover:bg-muted"
              >
                <ArrowLeft className="h-5 w-5" />
              </Button>
              <div className="p-1">
                <img 
                  src="/assets/hat-logo.png" 
                  alt="BIG Hat Entertainment" 
                  className="h-10 w-10 object-contain"
                />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Admin Panel</h1>
                <p className="text-sm text-muted-foreground">Manage employees, venues, and events</p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Lock className="h-4 w-4 text-green-600" />
              <span className="text-sm text-green-600 font-medium">Authenticated</span>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-7 lg:w-auto lg:inline-grid bg-muted/50 p-1">
            <TabsTrigger value="employees" className="flex items-center space-x-2">
              <Users className="h-4 w-4" />
              <span className="hidden sm:inline">Employees</span>
            </TabsTrigger>
            <TabsTrigger value="venues" className="flex items-center space-x-2">
              <MapPin className="h-4 w-4" />
              <span className="hidden sm:inline">Venues</span>
            </TabsTrigger>
            <TabsTrigger value="pricing" className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4" />
              <span className="hidden sm:inline">Pricing</span>
            </TabsTrigger>
            <TabsTrigger value="roles" className="flex items-center space-x-2">
              <ShieldCheck className="h-4 w-4" />
              <span className="hidden sm:inline">Roles</span>
            </TabsTrigger>
            <TabsTrigger value="events" className="flex items-center space-x-2">
              <Calendar className="h-4 w-4" />
              <span className="hidden sm:inline">Events</span>
            </TabsTrigger>
            <TabsTrigger value="reports" className="flex items-center space-x-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Weekly</span>
            </TabsTrigger>
            <TabsTrigger value="monthly" className="flex items-center space-x-2">
              <Calendar className="h-4 w-4" />
              <span className="hidden sm:inline">Monthly</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="employees" className="space-y-4">
            <EmployeeManager />
          </TabsContent>

          <TabsContent value="venues" className="space-y-4">
            <VenueManager />
          </TabsContent>

          <TabsContent value="pricing" className="space-y-4">
            <LocationPricing />
          </TabsContent>

          <TabsContent value="roles" className="space-y-4">
            <VenueRoleManager />
          </TabsContent>

          <TabsContent value="events" className="space-y-4">
            <EventManager />
          </TabsContent>

          <TabsContent value="reports" className="space-y-4">
            <WeeklyReport />
          </TabsContent>

          <TabsContent value="monthly" className="space-y-4">
            <MonthlyReports />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default AdminPage;
