import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import api from '../lib/api';
import Header from '../components/Header';
import AppCards from '../components/AppCards';
import ScheduleSection from '../components/ScheduleSection';
import ChyronBar from '../components/ChyronBar';
import ResourcesSection from '../components/ResourcesSection';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function Dashboard() {
  const { user } = useAuth();
  const [myEvents, setMyEvents] = useState([]);
  const [unclaimedEvents, setUnclaimedEvents] = useState([]);
  const [employeeId, setEmployeeId] = useState(null);

  // Find the schedule employee ID matching the hub user's email
  useEffect(() => {
    if (!user?.email) return;
    axios.get(`${API_URL}/api/employees`).then(res => {
      const match = res.data.find(e => e.email.toLowerCase() === user.email.toLowerCase());
      if (match) setEmployeeId(match.id);
    }).catch(() => {});
  }, [user]);

  useEffect(() => {
    loadData();
  }, [employeeId]);

  const loadData = async () => {
    try {
      const [eventsRes, unclaimedRes] = await Promise.all([
        axios.get(`${API_URL}/api/events`),
        api.getUnclaimedEvents()
      ]);

      // Filter to only show events claimed by THIS user for the current week
      const now = new Date();
      const dayOfWeek = now.getDay(); // 0=Sun
      const startOfWeek = new Date(now);
      startOfWeek.setDate(now.getDate() - dayOfWeek);
      startOfWeek.setHours(0, 0, 0, 0);
      const endOfWeek = new Date(startOfWeek);
      endOfWeek.setDate(startOfWeek.getDate() + 7);

      const userEvents = eventsRes.data.filter(e => {
        if (!employeeId || e.claimed_by !== employeeId) return false;
        const eventDate = new Date(e.date);
        return eventDate >= startOfWeek && eventDate < endOfWeek;
      });

      setMyEvents(userEvents);
      setUnclaimedEvents(unclaimedRes.data);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    }
  };

  const handleClaimEvent = async (eventId) => {
    try {
      await api.claimEvent(eventId);
      loadData();
    } catch (err) {
      console.error('Failed to claim event:', err);
    }
  };

  return (
    <div className="min-h-screen relative" style={{ backgroundColor: '#000e2a' }} data-testid="dashboard">
      {/* Background glow orbs */}
      <div className="fixed top-20 left-10 w-[500px] h-[500px] rounded-full opacity-10 animate-pulse-glow pointer-events-none" style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }} />
      <div className="fixed bottom-20 right-10 w-[400px] h-[400px] rounded-full opacity-10 animate-pulse-glow pointer-events-none" style={{ background: 'radial-gradient(circle, #151c51 0%, transparent 70%)', animationDelay: '2s' }} />

      <Header />

      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
        {/* Welcome */}
        <div className="pt-6 pb-4 animate-slide-up">
          <h2 className="text-2xl font-bold text-white">
            Welcome back, <span style={{ color: '#fbdd68' }}>{user?.name || 'Host'}</span>
          </h2>
          <p className="text-sm mt-1" style={{ color: '#8892b0' }}>
            Your event command center is ready
          </p>
        </div>

        {/* Chyron - Unclaimed Events Ticker */}
        {unclaimedEvents.length > 0 && (
          <ChyronBar events={unclaimedEvents} onClaim={handleClaimEvent} />
        )}

        {/* Main App Cards */}
        <AppCards />

        {/* My Schedule This Week - only shows events claimed by logged-in user */}
        <ScheduleSection events={myEvents} onRefresh={loadData} />

        {/* Resources & Tools */}
        <ResourcesSection />
      </main>
    </div>
  );
}
