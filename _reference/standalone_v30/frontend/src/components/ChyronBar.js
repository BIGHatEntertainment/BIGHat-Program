import React from 'react';
import { AlertCircle, MapPin, Clock } from 'lucide-react';

function EventItem({ event, onClaim }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', whiteSpace: 'nowrap', paddingRight: '32px' }}>
      <span className="text-sm font-medium text-white">{event.title}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#8892b0', fontSize: '12px' }}>
        <MapPin size={10} /> {event.venue}
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#8892b0', fontSize: '12px' }}>
        <Clock size={10} /> {event.date} {event.time}
      </span>
      <button
        onClick={(e) => { e.stopPropagation(); onClaim(event._id); }}
        className="hover:scale-105 transition-transform"
        style={{
          backgroundColor: '#fbdd68',
          color: '#000e2a',
          padding: '3px 12px',
          borderRadius: '9999px',
          fontSize: '11px',
          fontWeight: 700,
          whiteSpace: 'nowrap',
        }}
        data-testid={`claim-event-${event._id}`}
      >
        Claim
      </button>
      <span style={{ color: 'rgba(251, 221, 104, 0.3)', fontSize: '14px', paddingLeft: '4px' }}>|</span>
    </span>
  );
}

export default function ChyronBar({ events, onClaim }) {
  if (!events || events.length === 0) return null;

  // Duplicate events enough times to guarantee seamless looping
  // We render two identical sets side-by-side; when the first scrolls fully out, it wraps seamlessly
  const items = events;

  return (
    <div className="mb-6 animate-slide-up stagger-1" data-testid="chyron-bar">
      <div
        className="rounded-xl"
        style={{
          backgroundColor: 'rgba(20, 27, 80, 0.5)',
          border: '1px solid rgba(251, 221, 104, 0.15)',
          height: '48px',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
          {/* Label */}
          <div
            className="shrink-0"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '0 16px',
              height: '100%',
              backgroundColor: 'rgba(251, 221, 104, 0.15)',
              zIndex: 2,
            }}
          >
            <AlertCircle size={14} style={{ color: '#fbdd68' }} />
            <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#fbdd68', whiteSpace: 'nowrap' }}>
              Unclaimed Events
            </span>
          </div>

          {/* Scrolling ticker - seamless loop */}
          <div style={{ flex: 1, overflow: 'hidden', height: '100%', position: 'relative' }}>
            <div
              className="chyron-seamless"
              onMouseEnter={(e) => { e.currentTarget.style.animationPlayState = 'paused'; }}
              onMouseLeave={(e) => { e.currentTarget.style.animationPlayState = 'running'; }}
            >
              {/* First copy */}
              <span className="chyron-set">
                {items.map((event, idx) => (
                  <EventItem key={`a-${idx}`} event={event} onClaim={onClaim} />
                ))}
              </span>
              {/* Second copy for seamless loop */}
              <span className="chyron-set">
                {items.map((event, idx) => (
                  <EventItem key={`b-${idx}`} event={event} onClaim={onClaim} />
                ))}
              </span>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .chyron-seamless {
          display: inline-flex;
          align-items: center;
          height: 100%;
          white-space: nowrap;
          animation: chyron-loop 80s linear infinite;
        }
        .chyron-set {
          display: inline-flex;
          align-items: center;
          height: 48px;
        }
        @keyframes chyron-loop {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }
      `}</style>
    </div>
  );
}
