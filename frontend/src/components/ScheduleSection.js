import React, { useState, useEffect } from 'react';
import { Calendar, MapPin, Clock, User } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const eventTypeColors = {
  Trivia: '#fbdd68',
  'Music Bingo': '#5973F7',
  Karaoke: '#22c55e',
  Special: '#a855f7',
};

export default function ScheduleSection({ events, onRefresh }) {
  const [venues, setVenues] = useState({});

  useEffect(() => {
    axios.get(`${API}/venues`).then(res => {
      const map = {};
      res.data.forEach(v => { map[v.id] = v.name; });
      setVenues(map);
    }).catch(() => {});
  }, []);

  const upcomingEvents = events
    .filter(e => e.status === 'upcoming' || e.status === 'available' || e.status === 'claimed')
    .slice(0, 6);

  return (
    <section className="mt-10 animate-slide-up stagger-3" data-testid="schedule-section">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Calendar size={20} style={{ color: '#fbdd68' }} />
          My Schedule This Week
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
          <p style={{ color: '#8892b0' }}>No events assigned to you this week</p>
          <p className="text-xs mt-1" style={{ color: '#8892b0', opacity: 0.6 }}>Check the Schedule tab to claim available events</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {upcomingEvents.map((event) => (
            <EventCard key={event.id || event._id} event={event} venues={venues} />
          ))}
        </div>
      )}
    </section>
  );
}

function EventCard({ event, venues }) {
  const typeColor = eventTypeColors[event.event_type] || '#fbdd68';
  const venueName = venues[event.venue_id] || event.venue || 'Unknown';
  
  // Parse date
  let dateStr = '';
  let timeStr = '';
  try {
    const d = new Date(event.date);
    dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    timeStr = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  } catch {
    dateStr = event.date?.slice(0, 10) || '';
  }

  return (
    <div className="glass-card rounded-xl p-4 group" data-testid={`event-card-${event.id || event._id}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: typeColor }} />
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: typeColor }}>
            {event.event_type}
          </span>
        </div>
        {!event.claimed_by && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
            Open
          </span>
        )}
        {event.claimed_by && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ backgroundColor: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
            Claimed
          </span>
        )}
      </div>

      <h4 className="text-sm font-semibold text-white mb-2 group-hover:text-[#fbdd68] transition-colors">{event.title}</h4>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <Clock size={12} />
          <span>{dateStr} {timeStr}</span>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: '#8892b0' }}>
          <MapPin size={12} />
          <span>{venueName}</span>
        </div>
      </div>
    </div>
  );
}
