/**
 * alpha.67: Bingo colour theme.
 *   blue   - main Bingo page, and Traditional Bingo (default)
 *   purple - Music Bingo (the original look, unchanged)
 *   yellow - whenever Lightning is selected (Traditional OR Music)
 * Back at the main lobby it is blue again (the lobby starts with no picks).
 */
export function pickBingoTheme(bingoType, gameType) {
  if (String(gameType || '').toLowerCase() === 'lightning') return 'yellow';
  if (String(bingoType || '').toLowerCase() === 'music') return 'purple';
  return 'blue';
}

// For the host + audience screens: read the game's saved settings.
export function themeFromGameState(gameState) {
  const s = (gameState && gameState.settings) || {};
  return pickBingoTheme(s.bingo_type, s.game_type);
}

// Confetti / canvas colours (the first one is the theme's main colour).
export const THEME_CONFETTI = {
  blue:   ['#3B82F6', '#06B6D4', '#EAB308', '#22C55E'],
  purple: ['#D946EF', '#06B6D4', '#EAB308', '#22C55E'],
  yellow: ['#FACC15', '#F59E0B', '#FDE68A', '#22C55E'],
};
