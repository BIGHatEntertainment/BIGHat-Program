import React, { useMemo } from 'react';

/**
 * Synthwave backdrop — uniform parallel grid scrolling upward,
 * with a fixed 10-step opacity mask fading to 0% at the gold horizon line.
 */
const SynthwaveBackdrop = ({ className = '' }) => {
  // Pre-compute star positions so they don't re-randomize on every render
  const stars = useMemo(() =>
    Array.from({ length: 50 }, (_, i) => ({
      size: 1 + Math.random() * 2.5,
      left: Math.random() * 100,
      top: Math.random() * 100,
      color: ['#5973F7', '#fbdd68', '#8892b0', '#fff', '#5973F7'][Math.floor(Math.random() * 5)],
      opacity: 0.3 + Math.random() * 0.6,
      duration: 2 + Math.random() * 4,
      delay: Math.random() * 3,
    })), []);

  // 10-step CSS mask: transparent at top (horizon) → opaque at bottom
  // Steps: 0%, 10%, 20%, ... 90%, 100% with opacities 0.0 → 1.0
  const maskStops = [
    'rgba(0,0,0,0.0) 0%',
    'rgba(0,0,0,0.08) 10%',
    'rgba(0,0,0,0.16) 20%',
    'rgba(0,0,0,0.28) 30%',
    'rgba(0,0,0,0.4) 40%',
    'rgba(0,0,0,0.55) 50%',
    'rgba(0,0,0,0.7) 60%',
    'rgba(0,0,0,0.8) 70%',
    'rgba(0,0,0,0.9) 80%',
    'rgba(0,0,0,1.0) 90%',
  ].join(', ');

  const VERT_COUNT = 24;   // number of vertical lines
  const HORIZ_SPACING = 60; // px between horizontal lines
  const GRID_HEIGHT = HORIZ_SPACING * 20; // enough height for seamless scroll (2x visible area)

  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} data-testid="synthwave-backdrop">
      {/* Deep navy sky */}
      <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #000e2a 0%, #0a1940 25%, #141b50 45%, #0a1940 50%, #000e2a 100%)' }} />

      {/* Stars — only in top 50% */}
      <div className="absolute inset-0" style={{ height: '50%' }}>
        {stars.map((s, i) => (
          <div key={i} className="absolute rounded-full" style={{
            width: `${s.size}px`, height: `${s.size}px`,
            left: `${s.left}%`, top: `${s.top}%`,
            background: s.color, opacity: s.opacity,
            animation: `twinkle ${s.duration}s ease-in-out infinite`,
            animationDelay: `${s.delay}s`,
          }} />
        ))}
      </div>

      {/* Horizon glow */}
      <div className="absolute left-0 right-0" style={{
        top: '47%', height: '100px',
        background: 'linear-gradient(180deg, transparent 0%, rgba(251,221,104,0.08) 30%, rgba(251,221,104,0.2) 50%, rgba(251,221,104,0.08) 70%, transparent 100%)',
        filter: 'blur(20px)',
      }} />

      {/* Bold gold horizon line at 50% */}
      <div className="absolute left-0 right-0" style={{
        top: '50%', height: '3px',
        background: 'linear-gradient(90deg, transparent 2%, rgba(251,221,104,0.6) 15%, #fbdd68 35%, #fff 50%, #fbdd68 65%, rgba(251,221,104,0.6) 85%, transparent 98%)',
        boxShadow: '0 0 30px rgba(251,221,104,0.5), 0 0 60px rgba(251,221,104,0.25)',
        zIndex: 2,
      }} />

      {/* Scrolling uniform grid — bottom 50%, with fixed opacity mask */}
      <div className="absolute left-0 right-0" style={{
        top: '50%', height: '50%', overflow: 'hidden',
        WebkitMaskImage: `linear-gradient(to bottom, ${maskStops})`,
        maskImage: `linear-gradient(to bottom, ${maskStops})`,
      }}>
        {/* SVG grid that scrolls upward — two copies for seamless loop */}
        <div style={{
          position: 'relative',
          height: `${GRID_HEIGHT}px`,
          animation: 'gridScrollUp 6s linear infinite',
        }}>
          <svg
            width="100%" height={GRID_HEIGHT}
            xmlns="http://www.w3.org/2000/svg"
            style={{ position: 'absolute', top: 0, left: 0 }}
            preserveAspectRatio="none"
          >
            {/* Vertical lines — PARALLEL, evenly spaced */}
            {Array.from({ length: VERT_COUNT }).map((_, i) => {
              const x = ((i + 0.5) / VERT_COUNT) * 100;
              return (
                <line key={`v${i}`}
                  x1={`${x}%`} y1="0" x2={`${x}%`} y2={GRID_HEIGHT}
                  stroke="#5973F7" strokeWidth="1.2" opacity="0.45"
                />
              );
            })}
            {/* Horizontal lines — evenly spaced */}
            {Array.from({ length: Math.ceil(GRID_HEIGHT / HORIZ_SPACING) }).map((_, i) => {
              const y = i * HORIZ_SPACING;
              return (
                <line key={`h${i}`}
                  x1="0" y1={y} x2="100%" y2={y}
                  stroke="#fbdd68" strokeWidth="1.5" opacity="0.45"
                />
              );
            })}
          </svg>
        </div>
      </div>

      <style>{`
        @keyframes gridScrollUp {
          0% { transform: translateY(0); }
          100% { transform: translateY(-50%); }
        }
        @keyframes twinkle {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.8; }
        }
      `}</style>

      {/* Noise */}
      <div className="absolute inset-0 pointer-events-none" style={{
        backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E\")",
        mixBlendMode: 'overlay', opacity: 0.04,
      }} />

      {/* Vignette */}
      <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse at 50% 40%, transparent 30%, rgba(0,14,42,0.5) 100%)' }} />
    </div>
  );
};

export { SynthwaveBackdrop };
export default SynthwaveBackdrop;
