// Run:  cd frontend && npm i --no-save react@18 react-dom@18 && node scripts/final_board.check.mjs
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';
const out = new URL('./.final_board_check.tmp.mjs', import.meta.url).pathname;
await build({ entryPoints: ['src/components/trivia/final/FinalScoresBoard.jsx'], bundle: true, format: 'esm', platform: 'node',
  loader: { '.js': 'jsx', '.jsx': 'jsx' }, external: ['react', 'react-dom'], outfile: out, logLevel: 'error' });
const { default: Board, scrollSeconds } = await import(out);
const teams = (n) => Array.from({ length: n }, (_, i) => ({ name: 'T' + i, total: 100 - i, roundScores: [1, 2] }));
const html = (n, extra = {}) => renderToStaticMarkup(React.createElement(Board, { teams: teams(n), rounds: [{ label: 'MC', multiplier: 1 }, { label: 'BIG', multiplier: 3 }], ...extra }));
const fails = [];
const ok = (c, m) => { if (!c) fails.push(m); };
ok([0, 3, 4].every((n) => scrollSeconds(n) === 20), 'min 20s');
ok(scrollSeconds(12) === 60 && scrollSeconds(100) === 150, '5s/team, max 150s');
for (const n of [1, 5]) ok(!html(n).includes('class="final-board-track"'), `${n} teams should not scroll`);
for (const n of [6, 40]) ok(html(n).includes('class="final-board-track"'), `${n} teams should scroll`);
ok((html(40).match(/data-testid="final-team-/g) || []).length === 40, 'every team rendered');
ok(html(3).includes('synthwave-backdrop'), 'scoreboard backdrop present');
ok(html(3, { location: 'A & B', date: 'May 1' }).includes('A &amp; B') && html(3, { location: 'x', date: 'May 1' }).includes('May 1'), 'location + date shown');
ok(html(3).includes('BIG x3'), 'round chips');
ok(html(3).includes('🏆') && html(3).includes('🥈') && html(3).includes('🥉'), 'top 3 medals');
ok(renderToStaticMarkup(React.createElement(Board, { teams: null, rounds: undefined })).includes('Final Scores'), 'null-safe');
console.log(fails.length ? 'FAILED: ' + fails.join('; ') : 'final board: all checks ok');
process.exit(fails.length ? 1 : 0);
