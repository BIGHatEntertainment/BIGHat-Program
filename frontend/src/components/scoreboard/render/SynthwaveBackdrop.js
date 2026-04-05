import React from 'react';

/**
 * Synthwave/Retrowave backdrop for leaderboard mode.
 * Neon grid receding into perspective, cosmic sky, luminous horizon.
 * Inspired by 80s retro-futuristic aesthetic.
 */
const SynthwaveBackdrop = ({ className = '' }) => {
  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} data-testid="synthwave-backdrop">
      {/* Deep cosmic sky */}
      <div 
        className="absolute inset-0"
        style={{ 
          background: 'linear-gradient(180deg, #050012 0%, #0a0025 20%, #120035 40%, #1a0040 55%, #2d0060 70%, #1a0a3a 85%, #FFD700 98%, #FFD700 100%)',
        }}
      />

      {/* Star particles */}
      <div className="absolute inset-0" style={{ top: 0, height: '65%' }}>
        {Array.from({ length: 40 }).map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              width: `${1 + Math.random() * 2}px`,
              height: `${1 + Math.random() * 2}px`,
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              background: ['#00d4ff', '#ff00ff', '#FFD700', '#ffffff', '#8b00ff'][Math.floor(Math.random() * 5)],
              opacity: 0.3 + Math.random() * 0.5,
              animation: `pulse ${2 + Math.random() * 3}s ease-in-out infinite`,
              animationDelay: `${Math.random() * 3}s`,
            }}
          />
        ))}
      </div>

      {/* Horizon glow band */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          bottom: '30%',
          height: '120px',
          background: 'linear-gradient(180deg, transparent 0%, rgba(255,215,0,0.08) 30%, rgba(255,215,0,0.25) 50%, rgba(255,150,0,0.15) 70%, transparent 100%)',
          filter: 'blur(20px)',
        }}
      />

      {/* Bright horizon line */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          bottom: '30%',
          height: '3px',
          background: 'linear-gradient(90deg, transparent 5%, rgba(255,215,0,0.6) 20%, #FFD700 40%, #ffffff 50%, #FFD700 60%, rgba(255,215,0,0.6) 80%, transparent 95%)',
          boxShadow: '0 0 30px rgba(255,215,0,0.5), 0 0 60px rgba(255,215,0,0.3)',
        }}
      />

      {/* Perspective grid - bottom section */}
      <svg
        className="absolute bottom-0 left-0 w-full"
        viewBox="0 0 1080 600"
        preserveAspectRatio="xMidYMax slice"
        style={{ height: '30%' }}
      >
        {/* Horizontal grid lines - perspective receding */}
        {Array.from({ length: 20 }).map((_, i) => {
          const y = 10 + (i / 20) * 580;
          const opacity = 0.1 + (i / 20) * 0.5;
          return (
            <line
              key={`h-${i}`}
              x1="0" y1={y} x2="1080" y2={y}
              stroke="#8b00ff"
              strokeWidth={i < 5 ? "0.5" : "1"}
              opacity={opacity}
            />
          );
        })}
        
        {/* Vertical grid lines - converging to vanishing point */}
        {Array.from({ length: 25 }).map((_, i) => {
          const xBottom = (i / 24) * 1080;
          const xTop = 540 + (xBottom - 540) * 0.15; // converge toward center
          return (
            <line
              key={`v-${i}`}
              x1={xBottom} y1="600" x2={xTop} y2="0"
              stroke="#00d4ff"
              strokeWidth="1"
              opacity={0.2 + Math.abs(i - 12) * 0.015}
            />
          );
        })}

        {/* Center glow on grid */}
        <ellipse cx="540" cy="20" rx="300" ry="80" fill="rgba(255,215,0,0.06)" />
      </svg>

      {/* Noise overlay */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E\")",
          mixBlendMode: 'overlay',
          opacity: 0.05,
        }}
      />

      {/* Subtle vignette */}
      <div 
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at 50% 40%, transparent 30%, rgba(5,0,18,0.6) 100%)' }}
      />
    </div>
  );
};

export { SynthwaveBackdrop };
export default SynthwaveBackdrop;
