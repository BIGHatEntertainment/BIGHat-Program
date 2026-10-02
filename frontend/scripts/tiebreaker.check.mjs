import { needsTiebreaker as n } from '../src/lib/tiebreaker.js';
const T = (...v) => v.map((t, i) => ({ name: 'T' + i, total: t }));
const cases = [
  ['tie for 1st', T(50, 50, 40, 30), true],
  ['tie for 3rd', T(60, 50, 40, 40, 30), true],
  ['tie for 5th', T(60, 50, 40, 30, 20, 20, 10), true],
  ['tie for 6th (outside)', T(60, 50, 40, 30, 20, 10, 10), false],
  ['tie for 7th (outside)', T(70, 60, 50, 40, 30, 20, 10, 10), false],
  ['no ties at all', T(60, 50, 40, 30, 20, 10), false],
  ['1,2,2,4 style', T(60, 50, 50, 30), true],
  ['5th place shared with 6th and 7th', T(90, 80, 70, 60, 50, 50, 50), true],
  ['one team', T(10), false],
  ['empty', [], false],
  ['unnamed team ignored', [{ name: '', total: 5 }, { name: 'A', total: 5 }, { name: 'B', total: 4 }], false],
  ['string totals', [{ name: 'A', total: '12' }, { name: 'B', total: 12 }], true],
  ['all zero, two teams', T(0, 0), true],
];
let bad = 0;
for (const [label, teams, want] of cases) { const got = n(teams); if (got !== want) { bad++; console.log('FAIL', label, got); } }
console.log(bad ? bad + ' failed' : 'all ' + cases.length + ' tie cases ok');
