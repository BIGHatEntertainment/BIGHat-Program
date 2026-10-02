/**
 * alpha.66: the BIG tiebreaker is an IF event.
 * It only plays when two or more teams share a place of 5 or better
 * (standard competition ranking: 1, 2, 2, 4 ...).
 */
export const TIEBREAKER_TOP_PLACES = 5;

// teams: [{ name, total }]  (any order). Returns true if the tiebreaker is needed.
export function needsTiebreaker(teams, topPlaces = TIEBREAKER_TOP_PLACES) {
  const list = (Array.isArray(teams) ? teams : [])
    .filter((t) => t && t.name && String(t.name).trim() !== '')
    .map((t) => Number(t.total) || 0)
    .sort((a, b) => b - a);
  if (list.length < 2) return false;
  // place of each team = 1 + number of teams with a strictly higher total
  for (let i = 0; i < list.length; i++) {
    const place = list.findIndex((v) => v === list[i]) + 1;
    if (place > topPlaces) break;
    const sharing = list.filter((v) => v === list[i]).length;
    if (sharing > 1) return true;
  }
  return false;
}
