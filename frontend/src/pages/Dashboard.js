import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import api from '../lib/api';
import Header from '../components/Header';
import AppCards from '../components/AppCards';
import ScheduleSection from '../components/ScheduleSection';
import ChyronBar from '../components/ChyronBar';
import ResourcesSection from '../components/ResourcesSection';
import SlotMachineRandomizer from '../components/trivia/SlotMachineRandomizer';
import TriviaBuilderWizard from '../components/trivia/TriviaBuilderWizard';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [myEvents, setMyEvents] = useState([]);
  const [unclaimedEvents, setUnclaimedEvents] = useState([]);
  const [employeeId, setEmployeeId] = useState(null);
  const [showRoulette, setShowRoulette] = useState(false);
  const [showBuildWizard, setShowBuildWizard] = useState(false);
  const [locations, setLocations] = useState([]);

  // Find the schedule employee ID matching the hub user's email
  useEffect(() => {
    if (!user?.email) return;
    axios.get(`${API_URL}/api/employees`).then(res => {
      const match = res.data.find(e => e.email.toLowerCase() === user.email.toLowerCase());
      if (match) setEmployeeId(match.id);
    }).catch(() => {});
  }, [user]);

  // Store userName for SlotMachineRandomizer
  useEffect(() => {
    if (user?.name) {
      localStorage.setItem('userName', user.name.split(' ')[0].toLowerCase());
    }
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

      const now = new Date();
      const dayOfWeek = now.getDay();
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

      // Load locations for Round Roulette
      try {
        const locRes = await axios.get(`${API_URL}/api/trivia/locations`);
        setLocations(locRes.data.map(l => l.display_name || l.name));
      } catch { /* ignore */ }
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    }
  };

  const handleClaimEvent = async (eventId) => {
    if (!employeeId) return;
    try {
      await axios.post(`${API_URL}/api/events/${eventId}/claim`, { employee_id: employeeId });
      loadData();
    } catch (err) {
      console.error('Failed to claim event:', err);
    }
  };

  const handleToolClick = (toolId) => {
    switch (toolId) {
      case 'round-roulette':
        setShowRoulette(true);
        break;
      case 'build-wizard':
        setShowBuildWizard(true);
        break;
      case 'round-generator':
        navigate('/roundmaker');
        break;
      case 'scoreboard-tool':
        navigate('/scoreboard');
        break;
      case 'schedule':
        navigate('/schedule');
        break;
      default:
        break;
    }
  };

  return (
    <div className="min-h-screen relative" style={{ backgroundColor: '#000e2a' }} data-testid="dashboard">
      <div className="fixed top-20 left-10 w-[500px] h-[500px] rounded-full opacity-10 animate-pulse-glow pointer-events-none" style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }} />
      <div className="fixed bottom-20 right-10 w-[400px] h-[400px] rounded-full opacity-10 animate-pulse-glow pointer-events-none" style={{ background: 'radial-gradient(circle, #151c51 0%, transparent 70%)', animationDelay: '2s' }} />

      <Header />

      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
        <div className="pt-6 pb-4 animate-slide-up">
          <h2 className="text-2xl font-bold text-white">
            Welcome back, <span style={{ color: '#fbdd68' }}>{user?.name || 'Host'}</span>
          </h2>
          <p className="text-sm mt-1" style={{ color: '#8892b0' }}>
            Your event command center is ready
          </p>
        </div>

        {unclaimedEvents.length > 0 && (
          <ChyronBar events={unclaimedEvents} onClaim={handleClaimEvent} />
        )}

        <AppCards />
        <ScheduleSection events={myEvents} onRefresh={loadData} />
        <ResourcesSection onToolClick={handleToolClick} />
      </main>

      {/* Round Roulette Popup - opens from main dashboard */}
      <SlotMachineRandomizer
        open={showRoulette}
        onClose={() => setShowRoulette(false)}
        onComplete={(selectedRounds, location, paths, builtPresentation) => {
          setShowRoulette(false);
        }}
        locations={locations}
      />

      {/* Build Wizard Popup */}
      <TriviaBuilderWizard
        open={showBuildWizard}
        onOpenChange={setShowBuildWizard}
        onComplete={async (triviaData) => {
          try {
            const normalizedData = { ...triviaData, userName: (triviaData.userName || '').toLowerCase() };
            await axios.post(`${API_URL}/api/presentations/import-trivia`, normalizedData);
            await axios.post(`${API_URL}/api/story-builds/save`, {
              host: triviaData.hostName || '',
              location: triviaData.locationName || '',
              locationFolder: triviaData.locationFolder || '',
              numRounds: triviaData.numRounds,
              roundNames: triviaData.roundNames || [],
              roundTypes: triviaData.roundTypes || [],
              presentationName: triviaData.presentationName || '',
              createdBy: (triviaData.userName || '').toLowerCase()
            }).catch(() => {});
          } catch (err) {
            console.error('Build failed:', err);
          }
        }}
        userName={user?.name?.split(' ')[0]?.toLowerCase() || ''}
      />
    </div>
  );
}
