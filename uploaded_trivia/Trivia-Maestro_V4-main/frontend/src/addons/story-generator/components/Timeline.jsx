import React from 'react';
import { motion } from 'framer-motion';
import { MapPin, User, ListChecks } from 'lucide-react';
import { SECTION_DURATIONS } from './VideoPreview';

const sections = [
  { 
    id: 'location', 
    label: 'Location', 
    duration: SECTION_DURATIONS.location,
    icon: MapPin,
    color: 'from-yellow-500 to-orange-500',
    bgColor: 'bg-gradient-to-r from-yellow-500 to-orange-500'
  },
  { 
    id: 'host', 
    label: 'Host', 
    duration: SECTION_DURATIONS.host,
    icon: User,
    color: 'from-pink-500 to-red-500',
    bgColor: 'bg-gradient-to-r from-pink-500 to-red-500'
  },
  { 
    id: 'rounds', 
    label: 'Rounds', 
    duration: SECTION_DURATIONS.rounds,
    icon: ListChecks,
    color: 'from-purple-500 to-violet-500',
    bgColor: 'bg-gradient-to-r from-purple-500 to-violet-600'
  }
];

const totalDuration = sections.reduce((acc, s) => acc + s.duration, 0);

export const Timeline = ({ currentSection, onSelect }) => {
  return (
    <div className="w-full space-y-4" data-testid="video-timeline">
      {/* Section Labels */}
      <div className="flex gap-2">
        {sections.map((section) => {
          const Icon = section.icon;
          const isActive = currentSection === section.id;
          
          return (
            <motion.button
              key={section.id}
              onClick={() => onSelect(section.id)}
              className={`
                relative flex items-center justify-center gap-2 py-3 px-4 rounded-xl flex-1
                transition-all duration-300 cursor-pointer overflow-hidden
                ${isActive 
                  ? 'bg-[#1a1a1f] border border-yellow-500/50 text-white shadow-lg' 
                  : 'bg-[#141418] border border-white/10 text-white/70 hover:bg-[#1a1a1f] hover:border-yellow-500/30'
                }
              `}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              data-testid={`timeline-section-${section.id}`}
            >
              {/* Active glow */}
              {isActive && (
                <motion.div
                  className="absolute inset-0 bg-gradient-to-r from-yellow-500/15 via-transparent to-transparent"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                />
              )}
              
              {/* Shimmer effect on hover */}
              <motion.div
                className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent"
                initial={{ x: '-100%' }}
                whileHover={{ x: '100%' }}
                transition={{ duration: 0.6 }}
              />
              
              <Icon className={`h-4 w-4 relative z-10 flex-shrink-0 ${isActive ? 'text-yellow-400' : 'text-white/80'}`} />
              <span className={`font-sans text-sm font-medium relative z-10 ${isActive ? 'text-white' : 'text-white/80'}`}>
                {section.label}
              </span>
              <span className={`font-mono text-xs relative z-10 ${isActive ? 'text-yellow-400' : 'text-white/60'}`}>
                {section.duration}s
              </span>
            </motion.button>
          );
        })}
      </div>

      {/* Visual Timeline Bar */}
      <div className="relative">
        {/* Background track */}
        <div className="flex h-3 rounded-full overflow-hidden bg-[#141418] border border-white/5">
          {sections.map((section) => {
            const widthPercent = (section.duration / totalDuration) * 100;
            const isActive = currentSection === section.id;
            
            return (
              <motion.div
                key={section.id}
                className={`relative ${section.bgColor} cursor-pointer`}
                style={{ width: `${widthPercent}%` }}
                animate={{ 
                  opacity: isActive ? 1 : 0.4,
                  filter: isActive ? 'brightness(1.2)' : 'brightness(1)'
                }}
                onClick={() => onSelect(section.id)}
                whileHover={{ opacity: 0.8 }}
              >
                {/* Active pulse effect */}
                {isActive && (
                  <motion.div
                    className="absolute inset-0 bg-white/30"
                    animate={{ opacity: [0.3, 0, 0.3] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}
              </motion.div>
            );
          })}
        </div>

        {/* Glowing indicator for active section */}
        <motion.div
          className="absolute -bottom-1 h-1 bg-gradient-to-r from-yellow-500 via-orange-500 to-yellow-500 rounded-full"
          style={{
            width: `${(sections.find(s => s.id === currentSection)?.duration || 0) / totalDuration * 100}%`,
            boxShadow: '0 0 10px rgba(250, 204, 21, 0.6), 0 0 20px rgba(250, 204, 21, 0.3)'
          }}
          animate={{
            left: `${
              sections.slice(0, sections.findIndex(s => s.id === currentSection))
                .reduce((acc, s) => acc + (s.duration / totalDuration * 100), 0)
            }%`
          }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      {/* Duration Info */}
      <div className="flex justify-between items-center text-xs font-mono">
        <span className="text-white/60">0:00</span>
        <div className="flex items-center gap-2">
          <motion.div 
            className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-green-400 to-emerald-500"
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
          <span className="text-white/60">TOTAL: <span className="text-white font-semibold">{totalDuration}s</span></span>
        </div>
      </div>
    </div>
  );
};
