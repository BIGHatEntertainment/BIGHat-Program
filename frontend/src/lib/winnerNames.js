// alpha.87: where the team name goes on each winners VIDEO (1920x1080 stage).
// Measured on the 1280x720 videos and scaled by 1.5. The name + points sit in
// the video's blank top area, and the name shrinks to fit on ONE line.
export const WINNER_AREA = {
  '1st': { x: 120, y: 20, w: 1680, h: 150, base: 84, color: '#4A2A00',
           shadow: '0 0 10px rgba(255,236,170,0.95), 0 0 4px rgba(255,255,255,0.9)' },
  '2nd': { x: 60,  y: 30, w: 1800, h: 150, base: 84, color: '#0E2A5A',
           shadow: '0 0 8px rgba(255,255,255,0.9)' },
  '3rd': { x: 130, y: 40, w: 1660, h: 200, base: 84, color: '#FFF3DC',
           shadow: '3px 3px 8px rgba(60,25,0,0.95), -2px -2px 6px rgba(60,25,0,0.8)' },
};

// Font size so the name fits on one line inside the area (width and height).
export const fitWinnerName = (name, area) => {
  const text = String(name || '');
  const perChar = 0.62; // average character width / font size (Lemonada is wide)
  const widthLimit = (area.w * 0.94) / Math.max(1, text.length * perChar);
  return Math.max(28, Math.floor(Math.min(area.base, area.h * 0.62, widthLimit)));
};
