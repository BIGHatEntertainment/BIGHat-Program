import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic2, Music, HelpCircle, Trophy, Video, FileEdit, Calendar } from 'lucide-react';
import { useSubscription } from '../context/SubscriptionContext';

const apps = [
  {
    id: 'trivia',
    title: 'Trivia',
    description: 'Host live trivia events with custom rounds, scoring, and leaderboards',
    icon: HelpCircle,
    color: '#fbdd68',
    gradient: 'from-[#fbdd68] to-[#f5d050]',
    available: true,
  },
  {
    id: 'bingo',
    title: 'Music Bingo',
    description: 'Run music bingo nights with auto-generated cards and live tracking',
    icon: Music,
    color: '#5973F7',
    gradient: 'from-[#5973F7] to-[#4060e0]',
    available: true,
  },
  {
    id: 'scheduler',
    title: 'Scheduler',
    description: 'Manage events, venues, and staff schedule',
    icon: Calendar,
    color: '#ec4899',
    gradient: 'from-[#ec4899] to-[#db2777]',
    available: true,
  },
  {
    id: 'scoreboard',
    title: 'Scoreboard',
    description: 'Live leaderboard and tournament brackets for any event',
    icon: Trophy,
    color: '#a855f7',
    gradient: 'from-[#a855f7] to-[#9333ea]',
    available: true,
  },
  {
    id: 'roundmaker',
    title: 'Round Gen',
    description: 'Create professional PowerPoint rounds for trivia shows',
    icon: FileEdit,
    color: '#f97316',
    gradient: 'from-[#f97316] to-[#ea580c]',
    available: true,
  },
  {
    id: 'story',
    title: 'Story Gen',
    description: 'Create animated Instagram Story videos for your events',
    icon: Video,
    color: '#06b6d4',
    gradient: 'from-[#06b6d4] to-[#0891b2]',
    available: true,
  },
  {
    id: 'karaoke',
    title: 'Karaoke',
    description: 'Manage karaoke queues and singer rotations',
    icon: Mic2,
    color: '#22c55e',
    gradient: 'from-[#22c55e] to-[#16a34a]',
    available: true,
  },
];

export default function AppCards() {
  const navigate = useNavigate();
  const { isModuleEnabled, loading } = useSubscription();

  if (loading) return null;

  const enabledApps = apps.filter(app => app.id === 'karaoke' || isModuleEnabled(app.id));

  return (
    <section className="mt-8 animate-slide-up stagger-2" data-testid="app-cards-section">
      <h3 className="text-lg font-semibold text-white mb-4">Event Apps</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {enabledApps.map((app) => (
          <AppCard key={app.id} app={app} onLaunch={() => {
            if (app.id === 'trivia') navigate('/trivia');
            else if (app.id === 'bingo') navigate('/bingo');
            else if (app.id === 'scheduler') navigate('/schedule');
            else if (app.id === 'scoreboard') navigate('/scoreboard');
            else if (app.id === 'roundmaker') navigate('/roundmaker');
            else if (app.id === 'story') navigate('/story-generator');
          }} />
        ))}
      </div>
    </section>
  );
}

function AppCard({ app, onLaunch }) {
  const Icon = app.icon;
  return (
    <div
      className={`relative glass-card rounded-2xl p-6 cursor-pointer group overflow-hidden ${!app.available ? 'opacity-70' : ''}`}
      data-testid={`app-card-${app.id}`}
      onClick={() => app.available && onLaunch && onLaunch()}
    >
      <div
        className="absolute top-0 right-0 w-32 h-32 rounded-full opacity-10 group-hover:opacity-20 transition-opacity duration-500"
        style={{ background: `radial-gradient(circle, ${app.color} 0%, transparent 70%)`, transform: 'translate(30%, -30%)' }}
      />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${app.color}15`, border: `1px solid ${app.color}30` }}>
            <Icon size={24} style={{ color: app.color }} />
          </div>
          {!app.available && (
            <span className="text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full" style={{ backgroundColor: 'rgba(251, 221, 104, 0.1)', color: '#fbdd68', border: '1px solid rgba(251, 221, 104, 0.2)' }}>
              Coming Soon
            </span>
          )}
        </div>

        <h4 className="text-xl font-bold text-white mb-2 group-hover:text-[#fbdd68] transition-colors duration-200">{app.title}</h4>
        <p className="text-sm leading-relaxed" style={{ color: '#8892b0' }}>{app.description}</p>

        {app.available && (
          <button
            className="mt-5 w-full py-2.5 rounded-lg font-bold text-sm transition-all duration-300 hover:shadow-lg"
            style={{ backgroundColor: app.color, color: '#000e2a', boxShadow: `0 0 10px ${app.color}30` }}
            data-testid={`launch-${app.id}-button`}
            onClick={(e) => { e.stopPropagation(); onLaunch && onLaunch(); }}
          >
            Launch {app.title}
          </button>
        )}
      </div>
    </div>
  );
}
