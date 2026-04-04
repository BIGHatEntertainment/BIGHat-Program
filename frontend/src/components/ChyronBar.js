import React from 'react';
import { AlertCircle, MapPin, Clock } from 'lucide-react';

export default function ChyronBar({ events, onClaim }) {
  if (!events || events.length === 0) return null;

  return (
    <div className="mb-6 animate-slide-up stagger-1" data-testid="chyron-bar">
      <div className="rounded-xl overflow-hidden" style={{ backgroundColor: 'rgba(20, 27, 80, 0.5)', border: '1px solid rgba(251, 221, 104, 0.15)', maxHeight: '150px' }}>
        {/* Label */}
        <div className="flex items-center">
          <div className="flex items-center gap-2 px-4 py-2 shrink-0" style={{ backgroundColor: 'rgba(251, 221, 104, 0.15)' }}>
            <AlertCircle size={14} style={{ color: '#fbdd68' }} />
            <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#fbdd68' }}>Unclaimed Events</span>
          </div>

          {/* Scrolling content */}
          <div className="chyron-container flex-1 py-2 px-4">
            <div className="chyron-content flex items-center gap-8">
              {events.concat(events).map((event, idx) => (
                <div key={idx} className="flex items-center gap-3 shrink-0">
                  <span className="text-sm font-medium text-white">{event.title}</span>
                  <span className="flex items-center gap-1 text-xs" style={{ color: '#8892b0' }}>
                    <MapPin size={10} /> {event.venue}
                  </span>
                  <span className="flex items-center gap-1 text-xs" style={{ color: '#8892b0' }}>
                    <Clock size={10} /> {event.date} {event.time}
                  </span>
                  <button
                    onClick={() => onClaim(event._id)}
                    className="px-3 py-1 rounded-full text-xs font-bold transition-all duration-200 hover:scale-105"
                    style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
                    data-testid={`claim-event-${event._id}`}
                  >
                    Claim
                  </button>
                  <span className="text-xs" style={{ color: 'rgba(251, 221, 104, 0.3)' }}>|</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
