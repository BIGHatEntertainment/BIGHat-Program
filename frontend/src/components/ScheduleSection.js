import React from 'react';
import { Calendar, MapPin, Clock, User } from 'lucide-react';

const eventTypeColors = {
  trivia: '#fbdd68',
  bingo: '#5973F7',
  karaoke: '#22c55e',
};

export default function ScheduleSection({ events, onRefresh }) {
  const upcomingEvents = events
    .filter(e => e.status === 'upcoming')
    .slice(0, 6);

  return (
    <section className="mt-10 animate-slide-up stagger-3" data-testid="schedule-section">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Calendar size={20} style={{ color: '#fbdd68' }} />
          Upcoming Schedule
        </h3>
        <button
          onClick={onRefresh}
          className="text-xs px-4 py-2 rounded-lg font-medium transition-all duration-200"
          style={{ color: '#fbdd68', backgroundColor: 'rgba(251, 221, 104, 0.08)', border: '1px solid rgba(251, 221, 104, 0.15)' }}
          data-testid="refresh-schedule-button"
        >
          Refresh
        </button>
      </div>

      {upcomingEvents.length === 0 ? (
        <div className="glass-card rounded-xl p-8 text-center">
          <Calendar size={40} style={{ color: '#8892b0' }} className="mx-auto mb-3 opacity-50" />
          <p style={{ color: '#8892b0' }}>No upcoming events scheduled</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {upcomingEvents.map((event) => (
            <EventCard key={event._id} event={event} />
          ))}
        </div>
      )}
    </section>
  );
}

function EventCard({ event }) {
  const typeColor = eventTypeColors[event.event_type] || '#fbdd68';

  return (
    <div className="glass-card rounded-xl p-4 group" data-testid={`event-card-${event._id}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: typeColor }} />
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: typeColor }}>
            {event.event_type}
          </span>
        </div>
        {!event.claimed && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
            Open
          </span>
        )}
        {event.claimed && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
            Claimed
          </span>
        )}
      </div>

      <h4 className="text-sm font-semibold text-white mb-2 group-hover:text-[#fbdd68] transition-colors">{event.title}</h4>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <Clock size={12} />
          <span>{event.date} at {event.time}</span>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <MapPin size={12} />
          <span>{event.venue}</span>
        </div>
        {event.host_id && (
          <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
            <User size={12} />
            <span>Assigned</span>
          </div>
        )}
      </div>
    </div>
  );
}
