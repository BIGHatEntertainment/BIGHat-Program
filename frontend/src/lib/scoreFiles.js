// alpha.97: reading the score files that Trivia "Save & Exit" wrote on this PC.
// (The api helpers return the response body directly, so there is no extra ".data" here.)
import api from './scoreboardApi';

/** Look in the score folders, copy what is found into the Scoreboard, and return { files, count }. Never throws on an empty folder. */
export async function loadLocalScores() {
  const sync = await api.syncScores();                 // reads Documents\\...\\Trivia\\Scores (+ its AppData copy)
  const scores = await api.getScores();                // the synced nights, each with its teams inside `data`
  const files = (scores && scores.files) || [];
  return { files, count: (sync && sync.count) || 0 };
}

/** The venues that have at least one night saved, from a list of score files (the folder name is the venue). */
export function venuesOf(files) {
  const seen = new Map();
  for (const f of files || []) {
    const v = f && f.venue;
    if (v && !seen.has(String(v).toLowerCase())) seen.set(String(v).toLowerCase(), v);
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b));
}
