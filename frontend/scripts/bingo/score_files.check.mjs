// alpha.97: the Scoreboard finds the nights Trivia saved on this PC. Uses the REAL api helper names, so a wrong name fails loudly.
const axios = (await import('axios')).default;
const real = await import('/tmp/rtest/sfiles.bundle.mjs');
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const calls = [];
// a fake server shaped exactly like the real backend answers
const night = { file_name: '2026-10-07_Test_Venue.json', venue: 'Test_Venue', last_modified: 'x', data: { teams: [{ name: 'Quiz Whiz', total: 11 }], rounds: [{ label: 'R1' }] } };
let synced = false, serverDown = false;
axios.post = async (u) => { calls.push('POST ' + u); if (serverDown) throw new Error('down'); synced = true; return { data: { synced: [night.file_name], count: 1, source: 'local' } }; };
axios.get = async (u) => { calls.push('GET ' + u); if (serverDown) throw new Error('down'); return { data: { files: synced ? [night] : [], count: synced ? 1 : 0 } }; };

// 1. a night saved by Trivia is found and carries its teams
let r = await real.loadLocalScores();
ok(r.count === 1 && r.files.length === 1 && r.files[0].data.teams[0].name === 'Quiz Whiz', 'the saved night is found with its teams: ' + JSON.stringify(r).slice(0, 120));
ok(calls[0].startsWith('POST') && /sharepoint\/sync$/.test(calls[0]) && /scoreboard\/scores$/.test(calls[1]), 'it syncs first and then reads the scores: ' + calls.join(' , '));
ok(!calls.some(c => /sharepoint\.com|graph\.microsoft/.test(c)), 'nothing goes to Microsoft');

// 2. an empty folder is not an error
synced = false; calls.length = 0; axios.post = async (u) => { calls.push('POST ' + u); return { data: { synced: [], count: 0, source: 'local' } }; };
r = await real.loadLocalScores();
ok(r.count === 0 && Array.isArray(r.files) && r.files.length === 0, 'no saved nights is just an empty list, not an error');

// 3. venues come from the folder names, once each, sorted, case-insensitive
const v = real.venuesOf([{ venue: 'Zed Bar' }, { venue: 'Test_Venue' }, { venue: 'test_venue' }, { venue: '' }, {}, null]);
ok(JSON.stringify(v) === JSON.stringify(['Test_Venue', 'Zed Bar']), 'venues listed once and sorted: ' + JSON.stringify(v));

// 4. the server being down is reported (it throws) so the page can say so
serverDown = true; let threw = false; try { await real.loadLocalScores(); } catch { threw = true; }
ok(threw, 'if the program cannot read the files the error is passed on so the page can tell the host');

// 4b. the folder scan itself fails (but old rows are still readable): the host must still be told, not shown a stale list as if fine
serverDown = false; axios.post = async () => { throw new Error('could not read the folder'); }; axios.get = async () => ({ data: { files: [night], count: 1 } });
threw = false; try { await real.loadLocalScores(); } catch { threw = true; }
ok(threw, 'a failed folder scan is reported, even when older saved rows could still be listed');

// 5. the helper names the page uses really exist (this is the check that would have caught syncSharePoint)
const api = (await import('/tmp/rtest/sapi.bundle.mjs')).default;
for (const fn of ['syncScores', 'getScores', 'getSharePointFileContent']) ok(typeof api[fn] === 'function', 'the Scoreboard api has ' + fn);
ok(typeof api.syncSharePoint === 'undefined', 'there is no "syncSharePoint" (the page must not call it)');

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('score files: checks ok');
