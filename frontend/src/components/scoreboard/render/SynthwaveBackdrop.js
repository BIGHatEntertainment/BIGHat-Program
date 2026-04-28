import React from 'react';

/**
 * Synthwave/Retrowave backdrop for leaderboard mode.
 * Navy blue sky, prominent gold horizon line at center, large scrolling grid below.
 */
const SynthwaveBackdrop = ({ className = '' }) => {
  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} data-testid="synthwave-backdrop">
      {/* Deep navy sky */}
      <div 
        className="absolute inset-0"
        style={{ 
          background: 'linear-gradient(180deg, #000e2a 0%, #0a1940 25%, #141b50 45%, #0a1940 50%, #000e2a 100%)',
        }}
      />

      {/* Star particles */}
      <div className="absolute inset-0" style={{ top: 0, height: '50%' }}>
        {Array.from({ length: 50 }).map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              width: `${1 + Math.random() * 2.5}px`,
              height: `${1 + Math.random() * 2.5}px`,
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              background: ['#5973F7', '#fbdd68', '#8892b0', '#ffffff', '#5973F7'][Math.floor(Math.random() * 5)],
              opacity: 0.3 + Math.random() * 0.6,
              animation: `twinkle ${2 + Math.random() * 4}s ease-in-out infinite`,
              animationDelay: `${Math.random() * 3}s`,
            }}
          />
        ))}
      </div>

      {/* Horizon glow — centered at 50% */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          top: '47%',
          height: '100px',
          background: 'linear-gradient(180deg, transparent 0%, rgba(251,221,104,0.08) 30%, rgba(251,221,104,0.2) 50%, rgba(251,221,104,0.08) 70%, transparent 100%)',
          filter: 'blur(20px)',
        }}
      />

      {/* Bold gold horizon line — at 50% vertical center */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          top: '50%',
          height: '3px',
          background: 'linear-gradient(90deg, transparent 2%, rgba(251,221,104,0.6) 15%, #fbdd68 35%, #ffffff 50%, #fbdd68 65%, rgba(251,221,104,0.6) 85%, transparent 98%)',
          boxShadow: '0 0 30px rgba(251,221,104,0.5), 0 0 60px rgba(251,221,104,0.25), 0 -5px 20px rgba(251,221,104,0.15)',
        }}
      />

      {/* Perspective grid — bottom 50%, scrolls upward continuously, fades at horizon */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          top: '50%',
          height: '50%',
          overflow: 'hidden',
          maskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.6) 5%, rgba(0,0,0,0.9) 20%, rgba(0,0,0,1) 40%, rgba(0,0,0,1) 100%)',
          WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.6) 5%, rgba(0,0,0,0.9) 20%, rgba(0,0,0,1) 40%, rgba(0,0,0,1) 100%)',
        }}
      >
        {/* Scrolling grid SVG — doubled height for continuous scroll */}
        <div style={{ animation: 'gridScroll 6s linear infinite', height: '200%', position: 'relative' }}>
          <svg
            className="absolute left-0 w-full"
            style={{ height: '50%', top: 0 }}
            viewBox="0 0 1080 900"
            preserveAspectRatio="xMidYMin slice"
          >
            {/* Horizontal grid lines — thick and visible */}
            {Array.from({ length: 25 }).map((_, i) => {
              const y = (i / 24) * 900;
              const opacity = 0.15 + (i / 24) * 0.5;
              const width = 0.8 + (i / 24) * 1.5;
              return (
                <line key={`h1-${i}`} x1="0" y1={y} x2="1080" y2={y}
                  stroke="#fbdd68" strokeWidth={width} opacity={opacity} />
              );
            })}
            {/* Vertical grid lines — converging to center */}
            {Array.from({ length: 30 }).map((_, i) => {
              const xBottom = (i / 29) * 1080;
              const xTop = 540 + (xBottom - 540) * 0.08;
              return (
                <line key={`v1-${i}`} x1={xBottom} y1="900" x2={xTop} y2="0"
                  stroke="#5973F7" strokeWidth="1.2" opacity={0.2 + Math.abs(i - 14.5) * 0.008} />
              );
            })}
          </svg>
          {/* Duplicate for seamless scroll */}
          <svg
            className="absolute left-0 w-full"
            style={{ height: '50%', top: '50%' }}
            viewBox="0 0 1080 900"
            preserveAspectRatio="xMidYMin slice"
          >
            {Array.from({ length: 25 }).map((_, i) => {
              const y = (i / 24) * 900;
              const opacity = 0.15 + (i / 24) * 0.5;
              const width = 0.8 + (i / 24) * 1.5;
              return (
                <line key={`h2-${i}`} x1="0" y1={y} x2="1080" y2={y}
                  stroke="#fbdd68" strokeWidth={width} opacity={opacity} />
              );
            })}
            {Array.from({ length: 30 }).map((_, i) => {
              const xBottom = (i / 29) * 1080;
              const xTop = 540 + (xBottom - 540) * 0.08;
              return (
                <line key={`v2-${i}`} x1={xBottom} y1="900" x2={xTop} y2="0"
                  stroke="#5973F7" strokeWidth="1.2" opacity={0.2 + Math.abs(i - 14.5) * 0.008} />
              );
            })}
          </svg>
        </div>
      </div>

      {/* Grid scroll animation */}
      <style>{`
        @keyframes gridScroll {
          0% { transform: translateY(0); }
          100% { transform: translateY(-50%); }
        }
        @keyframes twinkle {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.8; }
        }
      `}</style>

      {/* Noise overlay */}
      <div 
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E\")",
          mixBlendMode: 'overlay',
          opacity: 0.04,
        }}
      />

      {/* Vignette */}
      <div 
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse at 50% 40%, transparent 30%, rgba(0,14,42,0.5) 100%)' }}
      />
    </div>
  );
};

export { SynthwaveBackdrop };
export default SynthwaveBackdrop;
