import React from 'react';

/**
 * Synthwave/Retrowave backdrop for leaderboard mode.
 * Navy blue sky, thin gold horizon line, grid that scrolls up and fades out.
 */
const SynthwaveBackdrop = ({ className = '' }) => {
  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} data-testid="synthwave-backdrop">
      {/* Deep navy sky — matches hub theme */}
      <div 
        className="absolute inset-0"
        style={{ 
          background: 'linear-gradient(180deg, #000e2a 0%, #0a1940 30%, #141b50 55%, #0a1940 75%, #000e2a 100%)',
        }}
      />

      {/* Star particles */}
      <div className="absolute inset-0" style={{ top: 0, height: '70%' }}>
        {Array.from({ length: 40 }).map((_, i) => (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              width: `${1 + Math.random() * 2}px`,
              height: `${1 + Math.random() * 2}px`,
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              background: ['#5973F7', '#fbdd68', '#8892b0', '#ffffff', '#5973F7'][Math.floor(Math.random() * 5)],
              opacity: 0.3 + Math.random() * 0.5,
              animation: `pulse ${2 + Math.random() * 3}s ease-in-out infinite`,
              animationDelay: `${Math.random() * 3}s`,
            }}
          />
        ))}
      </div>

      {/* Subtle horizon glow — no large yellow gradient */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          bottom: '30%',
          height: '60px',
          background: 'linear-gradient(180deg, transparent 0%, rgba(255,215,0,0.06) 40%, rgba(255,215,0,0.12) 60%, transparent 100%)',
          filter: 'blur(15px)',
        }}
      />

      {/* Thin gold horizon line */}
      <div 
        className="absolute left-0 right-0"
        style={{ 
          bottom: '30%',
          height: '2px',
          background: 'linear-gradient(90deg, transparent 5%, rgba(255,215,0,0.5) 20%, #FFD700 40%, #ffffff 50%, #FFD700 60%, rgba(255,215,0,0.5) 80%, transparent 95%)',
          boxShadow: '0 0 20px rgba(255,215,0,0.3), 0 0 40px rgba(255,215,0,0.15)',
        }}
      />

      {/* Perspective grid — scrolls upward and fades out near horizon */}
      <div 
        className="absolute bottom-0 left-0 w-full"
        style={{ 
          height: '30%',
          maskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.3) 20%, rgba(0,0,0,0.8) 60%, rgba(0,0,0,1) 100%)',
          WebkitMaskImage: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.3) 20%, rgba(0,0,0,0.8) 60%, rgba(0,0,0,1) 100%)',
        }}
      >
        <svg
          className="absolute bottom-0 left-0 w-full h-full"
          viewBox="0 0 1080 600"
          preserveAspectRatio="xMidYMax slice"
          style={{
            animation: 'gridScrollUp 8s linear infinite',
          }}
        >
          {/* Horizontal grid lines */}
          {Array.from({ length: 20 }).map((_, i) => {
            const y = 10 + (i / 20) * 580;
            const opacity = 0.15 + (i / 20) * 0.4;
            return (
              <line
                key={`h-${i}`}
                x1="0" y1={y} x2="1080" y2={y}
                stroke="#fbdd68"
                strokeWidth={i < 5 ? "0.5" : "1"}
                opacity={opacity}
              />
            );
          })}
          
          {/* Vertical grid lines — converging */}
          {Array.from({ length: 25 }).map((_, i) => {
            const xBottom = (i / 24) * 1080;
            const xTop = 540 + (xBottom - 540) * 0.15;
            return (
              <line
                key={`v-${i}`}
                x1={xBottom} y1="600" x2={xTop} y2="0"
                stroke="#5973F7"
                strokeWidth="1"
                opacity={0.15 + Math.abs(i - 12) * 0.01}
              />
            );
          })}
        </svg>
      </div>

      {/* Grid scroll animation */}
      <style>{`
        @keyframes gridScrollUp {
          0% { transform: translateY(0); }
          100% { transform: translateY(-30px); }
        }
      `}</style>

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
        style={{ background: 'radial-gradient(ellipse at 50% 40%, transparent 30%, rgba(0,14,42,0.6) 100%)' }}
      />
    </div>
  );
};

export { SynthwaveBackdrop };
export default SynthwaveBackdrop;
