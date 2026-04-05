/**
 * Tournament bracket logic with reseeding
 * Single elimination, highest vs lowest seed each round
 */

/**
 * Generate initial bracket for a single elimination tournament with reseeding.
 * @param {Array} teams - Array of {seed, name, ...} sorted by seed ascending
 * @param {number} byeCount - Number of top seeds that get a bye
 * @returns {Object} bracket state with rounds and matches
 */
export function generateBracket(teams, byeCount = 4) {
  const totalTeams = teams.length;
  if (totalTeams < 2) return { rounds: [], matches: {} };

  // Sort by seed (ascending)
  const sorted = [...teams].sort((a, b) => a.seed - b.seed);

  // Teams with byes (top seeds)
  const byeTeams = sorted.slice(0, byeCount);
  // Teams that play in round 1
  const playInTeams = sorted.slice(byeCount);

  const rounds = [];
  const matches = {};

  // Round 1: play-in round
  // Pair highest remaining seed vs lowest remaining seed
  const round1Matches = [];
  const numPlayInMatches = Math.floor(playInTeams.length / 2);

  for (let i = 0; i < numPlayInMatches; i++) {
    const high = playInTeams[i]; // lower seed number = higher seed
    const low = playInTeams[playInTeams.length - 1 - i];
    const matchId = `r1-m${i}`;
    const match = {
      id: matchId,
      round: 1,
      index: i,
      teamA: high,
      teamB: low,
      score_a: null,
      score_b: null,
      winner_seed: null,
      completed: false,
    };
    matches[matchId] = match;
    round1Matches.push(matchId);
  }

  rounds.push({ round: 1, label: 'Round 1', matchIds: round1Matches });

  // Calculate total rounds needed
  const teamsAfterR1 = byeCount + numPlayInMatches;
  let roundsNeeded = Math.ceil(Math.log2(teamsAfterR1)) + 1;

  // Round 2 (Quarterfinals): Pre-populate bye teams into their slots
  // Each bye team is paired against a TBD opponent (winner from Round 1)
  // Seeding: highest bye vs slot for lowest R1 winner, etc.
  const qfMatchCount = Math.floor(teamsAfterR1 / 2);
  const round2Matches = [];
  let roundLabel2 = 'Round 2';
  if (qfMatchCount === 4) roundLabel2 = 'Quarterfinals';
  else if (qfMatchCount === 2) roundLabel2 = 'Semifinals';
  else if (qfMatchCount === 1) roundLabel2 = 'Championship';

  // Pre-populate QF: bye teams get placed, opponents are TBD (from Round 1)
  // With reseeding: after R1, we'd reseed. But at generation time, we know
  // the bye teams and can place them. Their opponents depend on R1 results.
  // Layout: bye team #1 (seed 1) in match 0, bye team #2 (seed 2) in match 1, etc.
  // The opponent slot stays TBD until Round 1 completes.
  for (let m = 0; m < qfMatchCount; m++) {
    const matchId = `r2-m${m}`;
    let teamA = null;
    let teamB = null;

    // Place bye teams in QF slots
    // Bye teams occupy one side of each QF match
    if (m < byeCount) {
      // Bye team takes teamA slot, opponent (from R1) is teamB (TBD)
      teamA = byeTeams[m];
    }

    matches[matchId] = {
      id: matchId,
      round: 2,
      index: m,
      teamA: teamA,
      teamB: teamB,
      score_a: null,
      score_b: null,
      winner_seed: null,
      completed: false,
      hasBye: m < byeCount, // mark that this match has a bye team
    };
    round2Matches.push(matchId);
  }
  rounds.push({ round: 2, label: roundLabel2, matchIds: round2Matches });

  // Generate remaining rounds (Semifinals, Championship, etc.)
  let prevTeamCount = qfMatchCount;
  for (let r = 3; r <= roundsNeeded; r++) {
    const matchCount = Math.floor(prevTeamCount / 2);
    const roundMatches = [];
    let roundLabel = `Round ${r}`;
    if (matchCount === 1) roundLabel = 'Championship';
    else if (matchCount === 2) roundLabel = 'Semifinals';

    for (let m = 0; m < matchCount; m++) {
      const matchId = `r${r}-m${m}`;
      matches[matchId] = {
        id: matchId,
        round: r,
        index: m,
        teamA: null,
        teamB: null,
        score_a: null,
        score_b: null,
        winner_seed: null,
        completed: false,
      };
      roundMatches.push(matchId);
    }
    rounds.push({ round: r, label: roundLabel, matchIds: roundMatches });
    prevTeamCount = matchCount;
  }

  return {
    rounds,
    matches,
    byeTeams: byeTeams.map(t => t.seed),
    totalTeams,
    byeCount,
    champion: null,
  };
}

/**
 * Advance bracket after recording results for a complete round.
 * Reseeds remaining teams (highest vs lowest).
 * @param {Object} bracket - Current bracket state
 * @param {Array} allTeams - All teams array
 * @returns {Object} Updated bracket state
 */
export function advanceRound(bracket, allTeams) {
  const { rounds, matches, byeTeams } = bracket;
  const teamMap = {};
  allTeams.forEach(t => { teamMap[t.seed] = t; });

  // Find current round (first incomplete round that has all teams assigned)
  let currentRoundIdx = -1;
  for (let i = 0; i < rounds.length; i++) {
    const round = rounds[i];
    const allComplete = round.matchIds.every(id => matches[id].completed);
    if (!allComplete) {
      currentRoundIdx = i;
      break;
    }
  }

  if (currentRoundIdx === -1) return bracket; // All done

  const currentRound = rounds[currentRoundIdx];
  const allComplete = currentRound.matchIds.every(id => matches[id].completed);
  if (!allComplete) return bracket; // Not ready to advance

  // Collect winners from this round
  const winners = currentRound.matchIds
    .map(id => matches[id].winner_seed)
    .filter(s => s !== null)
    .map(s => teamMap[s]);

  // For round 1, fill in the QF opponents (bye teams are already placed)
  if (currentRoundIdx === 0) {
    // Round 1 just completed. Fill in QF opponents for bye teams.
    // The bye teams are already in QF slots. We need to place R1 winners as opponents.
    // Reseed: sort R1 winners by seed, then pair highest bye vs lowest R1 winner
    const r1Winners = [...winners].sort((a, b) => a.seed - b.seed);
    const nextRoundIdx = 1; // QF round
    if (nextRoundIdx < rounds.length) {
      const qfRound = rounds[nextRoundIdx];
      // Bye teams already in teamA slots. Place R1 winners in teamB slots.
      // Reseeding: highest bye (seed 1) vs lowest R1 winner, etc.
      for (let i = 0; i < qfRound.matchIds.length; i++) {
        const matchId = qfRound.matchIds[i];
        const match = matches[matchId];
        if (match.hasBye && i < r1Winners.length) {
          // Place R1 winner as opponent (lowest seed winner goes to highest bye)
          match.teamB = r1Winners[r1Winners.length - 1 - i];
        } else if (!match.hasBye) {
          // Non-bye QF match (if any extra R1 winners)
          // This shouldn't happen in a standard 12-team bracket with 4 byes
        }
      }
    }
    return { ...bracket, matches, rounds };
  }

  // For later rounds: collect all winners and reseed
  let advancingTeams = [...winners].sort((a, b) => a.seed - b.seed);

  // Check for championship
  if (advancingTeams.length === 1) {
    bracket.champion = advancingTeams[0];
    return bracket;
  }

  // Assign to next round matches (highest vs lowest)
  const nextRoundIdx = currentRoundIdx + 1;
  if (nextRoundIdx >= rounds.length) return bracket;

  const nextRound = rounds[nextRoundIdx];
  const numMatches = Math.floor(advancingTeams.length / 2);

  for (let i = 0; i < numMatches && i < nextRound.matchIds.length; i++) {
    const matchId = nextRound.matchIds[i];
    const high = advancingTeams[i];
    const low = advancingTeams[advancingTeams.length - 1 - i];
    matches[matchId].teamA = high;
    matches[matchId].teamB = low;
  }

  return { ...bracket, matches, rounds };
}

/**
 * Get display-friendly bracket data for rendering
 */
export function getBracketDisplayData(bracket, allTeams) {
  if (!bracket || !bracket.rounds) return [];
  const teamMap = {};
  if (allTeams) allTeams.forEach(t => { teamMap[t.seed] = t; });

  return bracket.rounds.map(round => ({
    ...round,
    matches: round.matchIds.map(id => {
      const match = bracket.matches[id];
      return {
        ...match,
        teamAName: match.teamA?.name || (match.teamA ? teamMap[match.teamA]?.name : 'TBD'),
        teamBName: match.teamB?.name || (match.teamB ? teamMap[match.teamB]?.name : 'TBD'),
        teamASeed: match.teamA?.seed || null,
        teamBSeed: match.teamB?.seed || null,
      };
    }),
  }));
}
