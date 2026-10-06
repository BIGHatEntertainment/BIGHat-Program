// alpha.87: winners name placement. Imports the REAL module the Editor uses.
import { readFileSync } from 'node:fs';
import { WINNER_AREA, fitWinnerName } from '../../src/lib/winnerNames.js';
const fails = [];
const ok = (c, m) => { if (!c) fails.push(m); };
let reachedEnd = false;

// 1) three areas, and each is inside the 1920x1080 stage, in the top band only
for (const k of ['1st', '2nd', '3rd']) {
  const a = WINNER_AREA[k];
  ok(!!a, `area ${k} missing`); if (!a) continue;
  ok(a.x >= 0 && a.x + a.w <= 1920, `${k}: area runs off the sides`);
  ok(a.y >= 0 && a.y + a.h <= 260, `${k}: area is not in the top band (ends at ${a.y + a.h})`);
}
// 2) the name always fits on one line inside the area, for short and very long names
const probes = ['A', 'Quiz Khalifa', 'The Fantastic Trivia Mavericks of Monkey Pants',
  'Les Quizerables Wine and Cheese Appreciation Society Of Greater Denver', 'W'.repeat(120), ''];
for (const k of ['1st', '2nd', '3rd']) for (const n of probes) {
  const a = WINNER_AREA[k], fs = fitWinnerName(n, a);
  ok(Number.isInteger(fs) && fs >= 28, `${k}/"${n.slice(0, 12)}": bad size ${fs}`);
  ok(fs <= a.h * 0.62 + 1, `${k}: font ${fs} is taller than the area allows`);
  if (n.length && fs > 28) ok(n.length * fs * 0.62 <= a.w, `${k}/"${n.slice(0, 12)}": too wide at ${fs}`);
}
// 3) longer names never get a bigger font
for (const k of ['1st', '2nd', '3rd']) {
  let prev = 1e9;
  for (let n = 1; n <= 100; n++) { const fs = fitWinnerName('x'.repeat(n), WINNER_AREA[k]); ok(fs <= prev, `${k}: size grew at length ${n}`); prev = fs; }
}
// 4) the Editor uses EACH place's own area for its OWN team (1st = top3[0] ...)
const src = readFileSync(new URL('../../src/pages/trivia/Editor.jsx', import.meta.url), 'utf8');
for (const [word, idx] of [['3rd', 2], ['2nd', 1], ['1st', 0]]) {
  const start = src.indexOf(`id: 'winner-${word}-name'`), end = src.indexOf(`id: 'winner-${word}-score'`);
  ok(start > 0 && end > start, `editor: ${word} name block not found`);
  const block = src.slice(start, end);
  ok(block.includes(`top3[${idx}].name`), `editor: ${word} slide does not use top3[${idx}]`);
  ok(block.includes(`WINNER_AREA['${word}']`), `editor: ${word} slide does not use its own area`);
  const others = ['1st', '2nd', '3rd'].filter(w => w !== word);
  ok(!others.some(o => block.includes(`WINNER_AREA['${o}']`)), `editor: ${word} slide uses another place's area`);
  const score = src.slice(end, src.indexOf('}', src.indexOf('textShadow', end)));
  ok(score.includes(`top3[${idx}].total`), `editor: ${word} score is not top3[${idx}]`);
  ok(!others.some(o => score.includes(`WINNER_AREA['${o}']`)), `editor: ${word} score uses another place's area`);
}
reachedEnd = true;
if (!reachedEnd) fails.push('check never reached the end');
if (fails.length) { console.log('FAILED\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('winner_names checks ok');
