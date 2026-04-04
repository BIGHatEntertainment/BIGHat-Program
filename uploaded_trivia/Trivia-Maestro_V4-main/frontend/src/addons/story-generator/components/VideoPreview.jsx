import React, { useRef, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Pause, RotateCcw } from 'lucide-react';
import { Button } from '../../../components/ui/button';

// Video dimensions for 9:16 aspect ratio
export const VIDEO_WIDTH = 1080;
export const VIDEO_HEIGHT = 1920;

// Section durations in seconds (25s total video)
export const SECTION_DURATIONS = {
  location: 3,    // 3s location image
  host: 3,        // 3s host image
  rounds: 19      // 19s background with round names
};

export const VideoPreview = ({ 
  event, 
  currentSection, 
  onSectionChange,
  isPlaying,
  onPlayPause,
  previewRef
}) => {
  const [currentTime, setCurrentTime] = useState(0);
  const intervalRef = useRef(null);

  const totalDuration = SECTION_DURATIONS.location + SECTION_DURATIONS.host + SECTION_DURATIONS.rounds;

  // Playback timer
  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        setCurrentTime(prev => {
          const next = prev + 0.1;
          if (next >= totalDuration) {
            onPlayPause(false);
            return 0;
          }
          return next;
        });
      }, 100);
    } else {
      clearInterval(intervalRef.current);
    }

    return () => clearInterval(intervalRef.current);
  }, [isPlaying, totalDuration, onPlayPause]);

  // Update current section based on time
  useEffect(() => {
    let section = 'location';
    if (currentTime >= SECTION_DURATIONS.location) {
      section = 'host';
    }
    if (currentTime >= SECTION_DURATIONS.location + SECTION_DURATIONS.host) {
      section = 'rounds';
    }
    if (currentSection !== section) {
      onSectionChange(section);
    }
  }, [currentTime, currentSection, onSectionChange]);

  const handleReset = () => {
    setCurrentTime(0);
    onPlayPause(false);
    onSectionChange('location');
  };

  const getSectionProgress = () => {
    if (currentSection === 'location') {
      return (currentTime / SECTION_DURATIONS.location) * 100;
    }
    if (currentSection === 'host') {
      return ((currentTime - SECTION_DURATIONS.location) / SECTION_DURATIONS.host) * 100;
    }
    return ((currentTime - SECTION_DURATIONS.location - SECTION_DURATIONS.host) / SECTION_DURATIONS.rounds) * 100;
  };

  if (!event) {
    return (
      <div className="rounded-2xl flex items-center justify-center max-h-[600px] border border-dashed border-border/50 bg-muted/20" style={{ aspectRatio: '9/16', width: '270px' }}>
        <motion.p 
          className="text-muted-foreground font-mono text-sm"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          // SELECT_EVENT
        </motion.p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Preview Container */}
      <motion.div 
        ref={previewRef}
        className="w-[270px] bg-black rounded-2xl overflow-hidden relative"
        style={{ aspectRatio: '9/16', maxHeight: '480px', boxShadow: '0 0 30px rgba(250, 204, 21, 0.2)' }}
        data-testid="video-preview-container"
        whileHover={{ scale: 1.02 }}
        transition={{ duration: 0.3 }}
      >
        {/* Scan line effect */}
        <div className="absolute inset-0 pointer-events-none z-20 overflow-hidden">
          <motion.div
            className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-yellow-400/30 to-transparent"
            animate={{ top: ['0%', '100%'] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
          />
        </div>

        {/* Corner brackets */}
        <div className="absolute top-2 left-2 w-4 h-4 border-l-2 border-t-2 border-yellow-500/40 z-10" />
        <div className="absolute top-2 right-2 w-4 h-4 border-r-2 border-t-2 border-yellow-500/40 z-10" />
        <div className="absolute bottom-2 left-2 w-4 h-4 border-l-2 border-b-2 border-yellow-500/40 z-10" />
        <div className="absolute bottom-2 right-2 w-4 h-4 border-r-2 border-b-2 border-yellow-500/40 z-10" />

        <AnimatePresence mode="wait">
          {/* Location Section */}
          {currentSection === 'location' && (
            <motion.div
              key="location"
              initial={{ opacity: 0, scale: 1.3 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
              transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
              className="absolute inset-0"
              data-testid="section-location"
            >
              {/* Use img tag for better base64 compatibility */}
              <img 
                src={event.location.imageUrl}
                alt="Location"
                className="w-full h-full object-cover"
                onError={(e) => console.error('[VideoPreview] Location image error:', e)}
                onLoad={() => console.log('[VideoPreview] Location image loaded')}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-black/50" />
              <div className="absolute bottom-0 left-0 right-0 p-4 text-center">
                <motion.h2 
                  className="font-display text-2xl text-white tracking-wider uppercase"
                  style={{ textShadow: '0 0 20px rgba(255,255,255,0.5)' }}
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  {event.venue}
                </motion.h2>
                <motion.p 
                  className="text-white/70 text-xs font-mono mt-2"
                  initial={{ y: 10, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.3 }}
                >
                  {event.location.address}
                </motion.p>
              </div>
              <motion.div 
                className="absolute top-4 left-0 right-0 text-center"
                initial={{ y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ delay: 0.1 }}
              >
                <span className="font-display text-sm text-white/80 tracking-[0.3em] uppercase">
                  This Week At
                </span>
              </motion.div>
            </motion.div>
          )}

          {/* Host Section */}
          {currentSection === 'host' && (
            <motion.div
              key="host"
              initial={{ opacity: 0, scale: 1.3 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, y: '-100%' }}
              transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
              className="absolute inset-0"
              data-testid="section-host"
            >
              <img 
                src={event.host.gifUrl}
                alt={event.host.name}
                className="w-full h-full object-cover"
                onError={(e) => console.error('[VideoPreview] Host image error:', e)}
                onLoad={() => console.log('[VideoPreview] Host image loaded')}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent" />
              <div className="absolute bottom-0 left-0 right-0 p-4 text-center">
                <motion.span 
                  className="font-mono text-xs text-amber-400 uppercase tracking-[0.2em]"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  Your Host
                </motion.span>
                <motion.h2 
                  className="font-display text-xl text-white tracking-wider uppercase mt-2"
                  style={{ textShadow: '0 0 20px rgba(251, 191, 36, 0.5)' }}
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.3 }}
                >
                  {event.host.name}
                </motion.h2>
              </div>
            </motion.div>
          )}

          {/* Rounds Section */}
          {currentSection === 'rounds' && (
            <motion.div
              key="rounds"
              initial={{ opacity: 0, y: '100%' }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 1.05 }}
              transition={{ duration: 0.5, ease: [0.34, 1.56, 0.64, 1] }}
              className="absolute inset-0"
              data-testid="section-rounds"
            >
              {/* Use img tag for better base64 compatibility */}
              <img 
                src={event.background.imageUrl}
                alt="Background"
                className="w-full h-full object-cover"
                onError={(e) => console.error('[VideoPreview] Background image error:', e)}
                onLoad={() => console.log('[VideoPreview] Background image loaded')}
              />
              <div className="absolute inset-0 bg-black/70" />
              <div className="absolute inset-0 flex flex-col items-center justify-center p-4">
                {/* Move content down 50px using transform */}
                <div className="flex flex-col items-center" style={{ transform: 'translateY(25px)' }}>
                  <motion.span 
                    className="font-display text-lg text-white tracking-[0.2em] uppercase mb-4"
                    initial={{ y: -20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                  >
                    Tonight&apos;s Rounds
                  </motion.span>
                  <div className="flex flex-col gap-2 w-full max-w-[200px]">
                    {event.rounds.map((round, index) => (
                      <motion.div
                        key={round.name}
                        initial={{ x: -30, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        transition={{ delay: 0.1 + index * 0.1 }}
                        className="rounded-lg px-3 py-2 text-center transform hover:scale-105 transition-transform"
                        style={{ 
                          backgroundColor: round.color,
                          boxShadow: `0 0 20px ${round.color}40`
                        }}
                      >
                        <span 
                          className="text-sm tracking-wider uppercase"
                          style={{ fontFamily: "'Lemonada', cursive", fontWeight: 700, color: 'black' }}
                        >
                          {round.name}
                        </span>
                      </motion.div>
                    ))}
                  </div>
                </div>
                <motion.p 
                  className="absolute bottom-4 font-display text-base text-amber-400 tracking-wider"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                >
                  {event.time}
                </motion.p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Section Progress Bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-black/50 z-10">
          <motion.div 
            className="h-full bg-gradient-to-r from-yellow-500 via-orange-500 to-yellow-500"
            style={{ 
              width: `${getSectionProgress()}%`,
              boxShadow: '0 0 10px rgba(250, 204, 21, 0.6)'
            }}
          />
        </div>
      </motion.div>
    </div>
  );
};
