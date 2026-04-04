import React from 'react';
import { AlertCircle, MapPin, Clock } from 'lucide-react';

export default function ChyronBar({ events, onClaim }) {
  if (!events || events.length === 0) return null;

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
            }}
          >
            <AlertCircle size={14} style={{ color: '#fbdd68' }} />
            <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#fbdd68', whiteSpace: 'nowrap' }}>
              Unclaimed Events
            </span>
          </div>

          {/* Scrolling ticker */}
          <div style={{ flex: 1, overflow: 'hidden', height: '100%', position: 'relative' }}>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                height: '100%',
                whiteSpace: 'nowrap',
                animation: 'chyron-scroll 40s linear infinite',
                gap: '32px',
                paddingLeft: '20px',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.animationPlayState = 'paused'; }}
              onMouseLeave={(e) => { e.currentTarget.style.animationPlayState = 'running'; }}
            >
              {events.concat(events).map((event, idx) => (
                <span key={idx} style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', whiteSpace: 'nowrap' }}>
                  <span className="text-sm font-medium text-white">{event.title}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#8892b0', fontSize: '12px' }}>
                    <MapPin size={10} /> {event.venue}
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#8892b0', fontSize: '12px' }}>
                    <Clock size={10} /> {event.date} {event.time}
                  </span>
                  <button
                    onClick={() => onClaim(event._id)}
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
                  <span style={{ color: 'rgba(251, 221, 104, 0.3)', fontSize: '12px' }}>|</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
