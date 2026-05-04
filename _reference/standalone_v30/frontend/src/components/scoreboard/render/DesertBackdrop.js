import React from 'react';

/**
 * Cyber backdrop with IG gradient sky and geometric patterns.
 * Replaces desert backdrop with playful futuristic look.
 */
const DesertBackdrop = ({ className = '' }) => {
  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} data-testid="desert-backdrop">
      {/* Base gradient - IG-inspired sunset */}
      <div 
        className="absolute inset-0 animate-gradient-drift"
        style={{ 
          background: 'linear-gradient(180deg, #0A0718 0%, #1a0a2e 15%, #2d1045 30%, #5a1a5e 50%, #833AB4 65%, #C13584 78%, #E1306C 88%, #F77737 95%, #FCAF45 100%)',
          backgroundSize: '100% 300%',
        }}
      />

      {/* Noise texture overlay */}
      <div className="noise-overlay" />

      {/* Cyber grid overlay */}
      <div 
        className="absolute inset-0"
        style={{
          backgroundImage: 'linear-gradient(rgba(225, 48, 108, 0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(225, 48, 108, 0.06) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      {/* Radial glow center */}
      <div 
        className="absolute inset-0"
        style={{ 
          background: 'radial-gradient(ellipse at 50% 40%, rgba(225, 48, 108, 0.15) 0%, transparent 60%)',
        }}
      />

      {/* Vignette */}
      <div 
        className="absolute inset-0"
        style={{ 
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(8,6,18,0.5) 100%)',
        }}
      />

      {/* Abstract city silhouette */}
      <svg
        className="absolute bottom-0 left-0 w-full"
        viewBox="0 0 1920 350"
        preserveAspectRatio="xMidYMax slice"
        style={{ height: '30%' }}
      >
        {/* Far skyline - softer */}
        <path
          d="M0 350 L0 260 Q80 200 200 240 Q350 170 480 210 Q550 160 650 190 Q720 130 820 180 Q900 110 1000 160 Q1100 90 1200 150 Q1300 80 1400 140 Q1500 90 1600 160 Q1700 100 1800 170 Q1850 150 1920 190 L1920 350 Z"
          fill="rgba(131, 58, 180, 0.25)"
        />

        {/* Mid skyline */}
        <path
          d="M0 350 L0 290 Q100 230 220 270 Q350 200 500 250 Q600 190 700 240 Q800 170 920 220 Q1020 160 1120 210 Q1200 150 1320 200 Q1420 140 1520 190 Q1620 150 1720 200 Q1820 170 1920 220 L1920 350 Z"
          fill="rgba(225, 48, 108, 0.2)"
        />

        {/* Near city silhouette */}
        <path
          d="M0 350 L0 310 L50 310 L50 290 L70 290 L70 280 L90 280 L90 290 L120 290 L120 305 L200 305 L200 300 L210 280 L220 280 L220 265 L230 265 L230 280 L240 280 L240 295 L280 295 L280 300 L350 300 L350 270 L360 260 L370 260 L370 270 L380 270 L380 290 L450 290 L450 305 L600 305 L600 295 L620 280 L640 280 L640 265 L660 265 L660 255 L670 245 L680 245 L680 255 L700 255 L700 265 L720 265 L720 280 L750 280 L750 290 L800 290 L800 310 L850 310 L870 300 L890 310 L920 310 L920 305 L950 305 L980 310 L1050 310 L1050 300 L1080 300 L1100 295 L1120 300 L1150 300 L1150 310 L1250 310 L1300 305 L1350 310 L1400 310 L1400 295 L1420 285 L1430 275 L1440 275 L1440 260 L1450 255 L1460 255 L1460 275 L1470 285 L1480 295 L1500 300 L1550 300 L1550 310 L1650 310 L1680 305 L1720 310 L1920 310 L1920 350 Z"
          fill="rgba(10, 10, 18, 0.92)"
        />

        {/* Glowing windows effect - small dots on buildings */}
        <g fill="#FCAF45" opacity="0.4">
          <rect x="215" y="270" width="3" height="3" rx="1" />
          <rect x="225" y="275" width="3" height="3" rx="1" />
          <rect x="355" y="265" width="3" height="3" rx="1" />
          <rect x="365" y="275" width="3" height="3" rx="1" />
          <rect x="645" y="270" width="3" height="3" rx="1" />
          <rect x="665" y="260" width="3" height="3" rx="1" />
          <rect x="675" y="250" width="3" height="3" rx="1" />
          <rect x="1435" y="265" width="3" height="3" rx="1" />
          <rect x="1445" y="260" width="3" height="3" rx="1" />
          <rect x="1455" y="270" width="3" height="3" rx="1" />
        </g>
        <g fill="#E1306C" opacity="0.3">
          <rect x="230" y="280" width="2" height="2" rx="1" />
          <rect x="670" y="255" width="2" height="2" rx="1" />
          <rect x="1440" y="270" width="2" height="2" rx="1" />
        </g>
      </svg>
    </div>
  );
};

export { DesertBackdrop };
export default DesertBackdrop;
