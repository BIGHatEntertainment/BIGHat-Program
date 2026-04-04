import React from 'react';

// Instagram gradient wrapper for icons
export const IGGradientIcon = ({ children, className = '' }) => {
  return (
    <span className={`ig-icon-wrapper ${className}`}>
      {children}
    </span>
  );
};

// SVG gradient definition to use in icons
export const IGGradientDef = () => (
  <svg width="0" height="0" style={{ position: 'absolute' }}>
    <defs>
      <linearGradient id="ig-gradient" x1="0%" y1="100%" x2="100%" y2="0%">
        <stop offset="0%" stopColor="#FCAF45" />
        <stop offset="20%" stopColor="#F77737" />
        <stop offset="40%" stopColor="#FD1D1D" />
        <stop offset="60%" stopColor="#E1306C" />
        <stop offset="80%" stopColor="#C13584" />
        <stop offset="100%" stopColor="#833AB4" />
      </linearGradient>
      <linearGradient id="ig-gradient-reverse" x1="100%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stopColor="#833AB4" />
        <stop offset="20%" stopColor="#C13584" />
        <stop offset="40%" stopColor="#E1306C" />
        <stop offset="60%" stopColor="#FD1D1D" />
        <stop offset="80%" stopColor="#F77737" />
        <stop offset="100%" stopColor="#FCAF45" />
      </linearGradient>
    </defs>
  </svg>
);

// Custom gradient-filled icon components
export const GradientIcon = ({ icon: Icon, className = '', size = 24, id = 'ig-grad' }) => {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className}>
      <defs>
        <linearGradient id={id} x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#FCAF45" />
          <stop offset="25%" stopColor="#F77737" />
          <stop offset="50%" stopColor="#E1306C" />
          <stop offset="75%" stopColor="#C13584" />
          <stop offset="100%" stopColor="#833AB4" />
        </linearGradient>
      </defs>
    </svg>
  );
};
