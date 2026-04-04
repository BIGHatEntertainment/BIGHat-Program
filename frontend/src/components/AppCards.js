import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic2, Music, HelpCircle } from 'lucide-react';

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
    id: 'karaoke',
    title: 'Karaoke',
    description: 'Manage karaoke queues, song requests, and singer rotations',
    icon: Mic2,
    color: '#22c55e',
    gradient: 'from-[#22c55e] to-[#16a34a]',
    available: false,
  },
];

export default function AppCards() {
  const navigate = useNavigate();
  return (
    <section className="mt-8 animate-slide-up stagger-2" data-testid="app-cards-section">
      <h3 className="text-lg font-semibold text-white mb-4">Event Apps</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {apps.map((app) => (
          <AppCard key={app.id} app={app} onLaunch={() => {
            if (app.id === 'trivia') {
              navigate('/trivia');
            } else if (app.id === 'bingo') {
              navigate('/schedule');
            }
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
      {/* Glow accent */}
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
