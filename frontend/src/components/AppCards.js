import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic2, Music, HelpCircle, Lock, ShoppingCart, KeyRound } from 'lucide-react';
import { useNative } from '../context/NativeContext';
import LicenseActivationDialog from './LicenseActivationDialog';

const STORE_BASE = 'https://bighat.live/shop';

const apps = [
  {
    id: 'trivia',
    title: 'Trivia',
    description:
      'Host live trivia events with custom rounds, scoring, and leaderboards.',
    icon: HelpCircle,
    color: '#fbdd68',
    feature: 'story_generator_enabled', // owns_standalone
    route: '/trivia',
    storePath: '',                       // base package — never sold separately
    storePrice: null,
    ownershipLabel: 'Included with BIG Hat Entertainment',
  },
  {
    id: 'bingo',
    title: 'Bingo',
    description:
      'Run traditional number bingo nights with auto-generated cards and live tracking.',
    icon: Music,
    color: '#5973F7',
    // v31.0.6: while the music-video bingo flow is on ice, Bingo is offered
    // to anyone who owns the standalone package. When music bingo ships as
    // a paid add-on again, flip this back to 'music_bingo_enabled' and
    // restore the upsell on the lobby's "Music Bingo" option.
    feature: 'story_generator_enabled',
    route: '/bingo',
    storePath: '',                       // bundled with standalone for now
    storePrice: null,
    ownershipLabel: 'Included with BIG Hat Entertainment',
  },
  {
    id: 'karaoke',
    title: 'Karaoke',
    description:
      'Manage karaoke queues, song requests, and singer rotations.',
    icon: Mic2,
    color: '#22c55e',
    feature: 'karaoke_enabled',
    route: '/karaoke',
    storePath: '/karaoke',
    storePrice: '$24.99',
    ownershipLabel: 'Add-on',
  },
];

export default function AppCards() {
  const navigate = useNavigate();
  const { isPremiumActive, subscription } = useNative();
  const ownsStandalone = Boolean(subscription?.owns_standalone);
  const [activateOpen, setActivateOpen] = useState(false);

  return (
    <section
      className="mt-8 animate-slide-up stagger-2"
      data-testid="app-cards-section"
    >
      <h3 className="text-lg font-semibold text-white mb-4">Event Apps</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {apps.map((app) => {
          // Trivia is included with the base package.
          const owned =
            app.id === 'trivia' ? ownsStandalone : isPremiumActive(app.feature);
          return (
            <AppCard
              key={app.id}
              app={app}
              owned={owned}
              ownsStandalone={ownsStandalone}
              onLaunch={() => owned && navigate(app.route)}
              onActivate={() => setActivateOpen(true)}
              onBuy={() => {
                window.open(`${STORE_BASE}${app.storePath}`, '_blank', 'noopener,noreferrer');
              }}
            />
          );
        })}
      </div>

      {/* In-place license activation modal — opened by the locked Trivia
          card "Enter License Key" button and the user-dropdown menu item.
          Calls /api/native/license/cloud/activate then re-runs the native
          info fetch so cards unlock without an app restart. */}
      <LicenseActivationDialog open={activateOpen} onClose={() => setActivateOpen(false)} />
    </section>
  );
}

function AppCard({ app, owned, ownsStandalone, onLaunch, onBuy, onActivate }) {
  const Icon = app.icon;
  const isAddon = app.id !== 'trivia';
  // Add-ons require the standalone base; if base is missing, prompt for that
  // first (the customer can't use any add-on without the main app installed).
  const blockedByMissingBase = isAddon && !ownsStandalone;

  return (
    <div
      className={`relative glass-card rounded-2xl p-6 group overflow-hidden transition-opacity duration-300 ${
        owned ? 'cursor-pointer' : 'opacity-80'
      }`}
      data-testid={`app-card-${app.id}`}
      data-owned={owned ? 'true' : 'false'}
      onClick={() => owned && onLaunch && onLaunch()}
    >
      <div
        className="absolute top-0 right-0 w-32 h-32 rounded-full opacity-10 group-hover:opacity-20 transition-opacity duration-500"
        style={{
          background: `radial-gradient(circle, ${app.color} 0%, transparent 70%)`,
          transform: 'translate(30%, -30%)',
        }}
      />

      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center"
            style={{
              backgroundColor: `${app.color}15`,
              border: `1px solid ${app.color}${owned ? '30' : '20'}`,
            }}
          >
            <Icon
              size={24}
              style={{ color: owned ? app.color : `${app.color}80` }}
            />
          </div>
          {!owned && (
            <span
              className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full"
              style={{
                backgroundColor: 'rgba(251, 221, 104, 0.1)',
                color: '#fbdd68',
                border: '1px solid rgba(251, 221, 104, 0.2)',
              }}
              data-testid={`app-card-${app.id}-locked-badge`}
            >
              <Lock className="w-3 h-3" />
              Locked
            </span>
          )}
          {owned && isAddon && (
            <span
              className="text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full"
              style={{
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                color: '#22c55e',
                border: '1px solid rgba(34, 197, 94, 0.2)',
              }}
              data-testid={`app-card-${app.id}-owned-badge`}
            >
              Owned
            </span>
          )}
        </div>

        <h4
          className={`text-xl font-bold mb-2 transition-colors duration-200 ${
            owned
              ? 'text-white group-hover:text-[#fbdd68]'
              : 'text-white/80'
          }`}
        >
          {app.title}
        </h4>
        <p className="text-sm leading-relaxed" style={{ color: '#8892b0' }}>
          {app.description}
        </p>

        {/* Owned: Launch button */}
        {owned && (
          <button
            className="mt-5 w-full py-2.5 rounded-lg font-bold text-sm transition-all duration-300 hover:shadow-lg"
            style={{
              backgroundColor: app.color,
              color: '#000e2a',
              boxShadow: `0 0 10px ${app.color}30`,
            }}
            data-testid={`launch-${app.id}-button`}
            onClick={(e) => {
              e.stopPropagation();
              onLaunch && onLaunch();
            }}
          >
            Launch {app.title}
          </button>
        )}

        {/* Not owned, base missing: prompt to buy main app first */}
        {!owned && blockedByMissingBase && (
          <div
            className="mt-5 px-3 py-2.5 rounded-lg text-xs text-amber-200/90 bg-amber-500/10 border border-amber-500/20"
            data-testid={`app-card-${app.id}-needs-base`}
          >
            Activate BIG Hat Entertainment first to use add-ons.
          </div>
        )}

        {/* Not owned, base present: show "Add for $X.XX" upsell button */}
        {!owned && !blockedByMissingBase && app.storePrice && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onBuy && onBuy();
            }}
            data-testid={`buy-${app.id}-button`}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold border transition-all duration-200"
            style={{
              borderColor: `${app.color}55`,
              color: app.color,
              backgroundColor: `${app.color}10`,
            }}
          >
            <ShoppingCart className="w-4 h-4" />
            Add {app.title} for {app.storePrice}
          </button>
        )}

        {/* Trivia (base) when owns_standalone is false — shouldn't normally
            happen since the wizard gates this, but render gracefully.
            Surfaces the in-place activation button so a customer who
            skipped Setup can recover without uninstalling. */}
        {!owned && app.id === 'trivia' && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onActivate && onActivate(); }}
            data-testid={`app-card-${app.id}-activate-btn`}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold border transition-all duration-200"
            style={{
              borderColor: 'rgba(251, 221, 104, 0.55)',
              color: '#fbdd68',
              backgroundColor: 'rgba(251, 221, 104, 0.08)',
            }}
          >
            <KeyRound className="w-4 h-4" />
            Enter License Key
          </button>
        )}
      </div>
    </div>
  );
}
