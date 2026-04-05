import React from 'react';
import { Shuffle, Wand2, Zap, Grid3X3, Calendar, Instagram, Trophy, GraduationCap, Handshake } from 'lucide-react';

const resourceCategories = [
  {
    title: 'Trivia Tools',
    color: '#fbdd68',
    tools: [
      { id: 'round-generator', name: 'Round Generator', description: 'Auto-generate trivia rounds by category', icon: Zap },
      { id: 'round-roulette', name: 'Round Roulette', description: 'Randomize round types for variety', icon: Shuffle },
      { id: 'build-wizard', name: 'Build Wizard', description: 'Step-by-step trivia show builder', icon: Wand2 },
    ]
  },
  {
    title: 'Bingo Tools',
    color: '#5973F7',
    tools: [
      { id: 'bingo-card-generator', name: 'Bingo Card Generator', description: 'Create custom bingo cards for any theme', icon: Grid3X3 },
    ]
  },
  {
    title: 'Socials',
    color: '#22c55e',
    tools: [
      { id: 'schedule', name: 'Schedule', description: 'View and manage event schedules', icon: Calendar },
      { id: 'story-generator', name: 'Story Generator', description: 'Create social media stories', icon: Instagram },
      { id: 'scoreboard-tool', name: 'Scoreboard Tool', description: 'Live scoreboard for events', icon: Trophy },
      { id: 'training', name: 'Training', description: 'Host training materials and guides', icon: GraduationCap },
    ]
  },
  {
    title: 'Business',
    color: '#FFC107',
    tools: [
      { id: 'sponsor-portal', name: 'Sponsor Portal', description: 'Manage sponsors and partnerships', icon: Handshake },
    ]
  }
];

export default function ResourcesSection({ onToolClick }) {
  return (
    <section className="mt-10 animate-slide-up stagger-4" data-testid="resources-section">
      <h3 className="text-lg font-semibold text-white mb-6">Resources & Tools</h3>
      <div className="space-y-8">
        {resourceCategories.map((cat) => (
          <div key={cat.title}>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-1.5 h-5 rounded-full" style={{ backgroundColor: cat.color }} />
              <h4 className="text-sm font-semibold" style={{ color: cat.color }}>{cat.title}</h4>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {cat.tools.map((tool) => (
                <ResourceCard key={tool.id} tool={tool} accentColor={cat.color} onClick={() => onToolClick && onToolClick(tool.id)} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResourceCard({ tool, accentColor, onClick }) {
  const Icon = tool.icon;
  return (
    <div
      className="glass-card rounded-xl p-4 cursor-pointer group"
      data-testid={`resource-card-${tool.id}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${accentColor}12`, border: `1px solid ${accentColor}20` }}>
          <Icon size={16} style={{ color: accentColor }} />
        </div>
        <div className="min-w-0">
          <h5 className="text-sm font-semibold text-white group-hover:text-[#fbdd68] transition-colors truncate">{tool.name}</h5>
          <p className="text-xs mt-0.5 leading-relaxed" style={{ color: '#8892b0' }}>{tool.description}</p>
        </div>
      </div>
    </div>
  );
}
