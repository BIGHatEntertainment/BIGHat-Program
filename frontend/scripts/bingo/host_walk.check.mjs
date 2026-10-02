import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/bingo/host', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage','BroadcastChannel','Audio']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
dom.window.HTMLMediaElement.prototype.play = function(){ return Promise.resolve(); };
dom.window.HTMLMediaElement.prototype.pause = function(){};
dom.window.HTMLMediaElement.prototype.load = function(){};
globalThis.__sent = [];
globalThis.__hostChannel = null;
class BC { constructor(n){ this.name=n; globalThis.__hostChannel = this; } postMessage(d){ globalThis.__sent.push(d); } close(){} set onmessage(f){ this._h = f; } get onmessage(){ return this._h; } }
globalThis.BroadcastChannel = BC; dom.window.BroadcastChannel = BC;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, screen, cleanup, act, waitFor } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;

const SONGS = Array.from({length: 40}, (_, i) => ({ number: i + 1, title: 'Song ' + (i + 1), artist: 'Artist ' + (i + 1), has_video: i + 1 !== 13 }));
let game = { id: 'g1', settings: { bingo_type: 'music', game_type: 'lightning', round_type: 'traditional', call_interval: 10, music_decade: '1990s', preset_mode: false },
  called_numbers: [], current_number: null, current_letter: null, current_song: null, called_songs: [], is_active: false, is_paused: false, bingo_claimed: false, winner_name: null, round_number: 1, volume: 0.5 };
const calls = [];
axios.get = async (url) => {
  calls.push('GET ' + url.replace('http://x/api',''));
  if (url.includes('/bingo/game/state')) return { data: { game } };
  if (url.includes('/bingo/available-themes')) return { data: { success: true, configured: true, themes: [{id:'1990s',name:'1990s',videos:39},{id:'Emo',name:'Emo',videos:12}] } };
  if (url.includes('/bingo/songlist/')) return { data: { success: true, source: 'local-folder', songs: SONGS, decade: '1990s' } };
  return { data: {} };
};
axios.post = async (url, body) => {
  calls.push('POST ' + url.replace('http://x/api','') + (body ? ' ' + JSON.stringify(body).slice(0, 60) : ''));
  if (url.includes('/player/')) { const e = new Error('Request failed with status code 404'); e.response = { status: 404, data: { detail: 'Not Found' } }; throw e; }
  if (url.includes('/game/start')) game = { ...game, is_active: true };
  if (url.includes('/game/end-round')) game = { ...game, is_active: false };
  if (url.includes('/game/new-round')) game = { ...game, round_number: game.round_number + 1, settings: { ...game.settings, ...(body || {}) }, called_songs: [] };
  return { data: { success: true } };
};
const { default: Host } = await import('./host.bundle.mjs');
const errors = []; const origErr = console.error; console.error = (...a) => { errors.push(a.map(String).join(' ').slice(0, 200)); };
const unhandled = []; process.on('unhandledRejection', (e) => unhandled.push(String(e).slice(0, 160)));

const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
render(React.createElement(MemoryRouter, { initialEntries: ['/bingo/host'] }, React.createElement(Routes, null,
  React.createElement(Route, { path: '/bingo/host', element: React.createElement(Host) }),
  React.createElement(Route, { path: '*', element: React.createElement('div', null, 'OTHER') }))));
await act(async () => { await new Promise(r => setTimeout(r, 400)); });
const root = document.querySelector('[data-testid="host-dashboard"]');
ok(!!root, 'host dashboard rendered');
ok(root && root.getAttribute('data-theme') === 'yellow', 'Music + Lightning host theme is yellow, got ' + (root && root.getAttribute('data-theme')));
ok(calls.some(c => c.includes('/bingo/songlist/1990s')), 'loaded the 1990s song list: ' + calls.filter(c => c.includes('songlist')).join(','));
const text = document.body.textContent;
ok(/Music Bingo|Song|song/i.test(text), 'music host page shows song controls');
console.log('buttons:', [...document.querySelectorAll('button')].map(b => (b.getAttribute('data-testid') || b.textContent.trim()).slice(0, 28)).filter(Boolean).slice(0, 14).join(' | '));
console.log('requests so far:', calls.join('  ;  ').slice(0, 400));

// ---- press Start Game: rewards routes 404 (we have none) but the game must still start ----
const { fireEvent } = await import('@testing-library/react');
const before = calls.length;
await act(async () => { fireEvent.click(screen.getByTestId('start-game-btn')); await new Promise(r => setTimeout(r, 500)); });
const after = calls.slice(before);
ok(after.some(c => c.startsWith('POST /bingo/game/start')), 'Start Game posts /bingo/game/start: ' + after.join(' ; '));
ok(after.some(c => c.includes('/player/game/create')), 'tries the rewards code (expected to 404 here)');
ok(!document.body.textContent.includes('OTHER'), 'did not get kicked out of the host page');
await act(async () => { await new Promise(r => setTimeout(r, 2600)); });   // let one 2s poll bring in is_active
// ---- songs stream from the Bingo folder: no file picker, no manual loading ----
const input = document.querySelector('input[type="file"][webkitdirectory]');
const badge = document.body.textContent;
ok(badge.includes('Bingo folder') && !badge.includes('SharePoint') && !badge.includes('Sample Data'), 'badge says Bingo folder (no SharePoint)');
ok(document.body.textContent.includes('39 songs ready'), '39 playable songs (song 13 has no video): ' + (document.body.textContent.match(/\d+ videos loaded/) || ['none'])[0]);
const btn = () => screen.getByTestId('next-song-btn');
ok(!btn().disabled, 'Next Song is ready straight away, no folder picking');
const playedSrcs = [];
dom.window.HTMLMediaElement.prototype.play = function(){ playedSrcs.push(this.getAttribute('src')); return Promise.resolve(); };
Object.defineProperty(dom.window.HTMLMediaElement.prototype, 'readyState', { get(){ return 4; }, configurable: true });
const sentBefore = globalThis.__sent.length;
const c0 = calls.length;
await act(async () => { fireEvent.click(btn()); await new Promise(r => setTimeout(r, 300)); });
const posted = calls.slice(c0).filter(c => c.startsWith('POST /bingo/game/call-song'));
ok(posted.length === 1, 'first press calls exactly one song: ' + calls.slice(c0).join(' ; '));
const num = Number((posted[0].match(/"number":(\d+)/) || [])[1]);
ok(num >= 1 && num <= 40 && num !== 13, 'the called song has a video (never #13), got ' + num);
await act(async () => { await new Promise(r => setTimeout(r, 400)); });
const hostVideo = document.querySelector('video');
ok(!!hostVideo, 'FIRST SONG: the host <video> element appears');
ok(hostVideo && /\/api\/bingo\/media\/1990s\/\d+$/.test(hostVideo.getAttribute('src') || ''), 'FIRST SONG: host video has the stream link, src=' + (hostVideo && hostVideo.getAttribute('src')));
ok(playedSrcs.length === 0, 'AUDIENCE FIRST: the host preview waits (not started yet): ' + JSON.stringify(playedSrcs));
// the audience window answers "I am playing" -> the host preview starts right away
await act(async () => { globalThis.__hostChannel.onmessage({ data: { type: 'audience-playing', videoUrl: hostVideo.getAttribute('src') } }); await new Promise(r => setTimeout(r, 100)); });
ok(playedSrcs.length >= 1, 'FIRST SONG: host preview plays once the audience is playing: ' + JSON.stringify(playedSrcs));
// the host preview follows the AUDIENCE clock, not the other way round
let seekTo = null; let cur = 0.2;
Object.defineProperty(hostVideo, 'paused', { get(){ return false; }, configurable: true });
Object.defineProperty(hostVideo, 'currentTime', { get(){ return cur; }, set(v){ seekTo = v; cur = v; }, configurable: true });
await act(async () => { globalThis.__hostChannel.onmessage({ data: { type: 'audience-time', time: 6.0, videoUrl: hostVideo.getAttribute('src') } }); });
ok(seekTo === 6.0, 'HOST FOLLOWS AUDIENCE: preview jumped to the audience position, seekTo=' + seekTo);
seekTo = null; cur = 6.4;
await act(async () => { globalThis.__hostChannel.onmessage({ data: { type: 'audience-time', time: 7.0, videoUrl: hostVideo.getAttribute('src') } }); });
ok(seekTo === null, 'small drift (<1.5s) is ignored, no needless seeking, seekTo=' + seekTo);
ok(hostVideo && hostVideo.muted === true, 'host video is silent (audience carries the sound)');
const firstMsgs = globalThis.__sent.slice(sentBefore).filter(m => m && m.type === 'video-state' && m.videoUrl);
ok(firstMsgs.length >= 1 && firstMsgs.some(m => m.isPlaying === true), 'FIRST SONG: the audience is told to play it: ' + JSON.stringify(firstMsgs.map(m => [m.isPlaying, m.videoUrl && m.videoUrl.slice(-18)])));
ok(btn().disabled && /Loading/.test(btn().textContent), 'cooldown: Loading... right after a call');
await act(async () => { fireEvent.click(btn()); await new Promise(r => setTimeout(r, 200)); });
ok(calls.slice(c0).filter(c => c.startsWith('POST /bingo/game/call-song')).length === 1, 'a rapid second press does NOT call another song');
// the channel message the audience receives carries a STREAM link, not a blob
await act(async () => { await new Promise(r => setTimeout(r, 2500)); });   // let the 2s audience sync tick
const urls = globalThis.__sent.map(m => m && m.videoUrl).filter(Boolean);
ok(urls.length > 0 && urls.every(u => /^http:\/\/x\/api\/bingo\/media\/1990s\/\d+$/.test(u)), 'audience gets stream links (not blob:): ' + JSON.stringify(urls.slice(0,2)));
console.log('call-song payload:', posted[0]);

// ---- no audience window open: the preview must still start (4 s fallback) ----
playedSrcs.length = 0;
await act(async () => { await new Promise(r => setTimeout(r, 5300)); });
await act(async () => { fireEvent.click(btn()); await new Promise(r => setTimeout(r, 300)); });
await act(async () => { await new Promise(r => setTimeout(r, 4400)); });
ok(playedSrcs.length >= 1, 'NO AUDIENCE: the host preview starts anyway after the 4 s fallback: ' + JSON.stringify(playedSrcs));

// ================= BINGO NIGHT: Bingo -> verify -> winner video -> name -> End Round =================
{
  const sent0 = globalThis.__sent.length;
  const bingoBtn = document.querySelector('[data-testid="bingo-btn"]');
  ok(bingoBtn && !bingoBtn.disabled, 'BINGO NIGHT: Bingo button is ready');
  await act(async () => { fireEvent.click(bingoBtn); await new Promise(r => setTimeout(r, 400)); });
  const m1 = globalThis.__sent.slice(sent0).filter(m => m && m.bingoVerifying === true);
  ok(m1.length >= 1 && m1.some(m => m.command === 'pause'), 'BINGO NIGHT: audience told "verifying" AND to pause the song: ' + JSON.stringify(m1.map(m => [m.bingoVerifying, m.command])));
  const confirmBtn = [...document.querySelectorAll('button')].find(b => /Confirm Bingo/.test(b.textContent));
  ok(!!confirmBtn, 'BINGO NIGHT: Confirm Bingo button shown');
  await act(async () => { fireEvent.click(confirmBtn); await new Promise(r => setTimeout(r, 500)); });
  const m2 = globalThis.__sent.slice(sent0).filter(m => m && m.bingoWinner === true);
  ok(m2.length >= 1 && /\/bingo-winner-[a-z0-9]+\.mp4$/.test(m2[0].winnerVideo || ''), 'BINGO NIGHT: audience gets the winner video: ' + JSON.stringify(m2[0] && m2[0].winnerVideo));
  ok(m2.every(m => m.bingoVerifying !== true), 'BINGO NIGHT: not stuck on verifying once confirmed');
  const nameBox = document.querySelector('[data-testid="winner-name-input"]');
  ok(!!nameBox, 'BINGO NIGHT: winner name box shown on the host');
  await act(async () => { fireEvent.change(nameBox, { target: { value: 'Sam & Co' } }); });
  const submit = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Submit');
  await act(async () => { fireEvent.click(submit); await new Promise(r => setTimeout(r, 200)); });
  ok(globalThis.__sent.slice(sent0).some(m => m && m.winnerName === 'Sam & Co'), 'BINGO NIGHT: winner name sent to the audience');
  // End Round on the winner screen -> the same pop-up (no more drop to the lobby)
  const winnerEnd = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'End Round' && b.className.includes('px-8'));
  ok(!!winnerEnd, 'BINGO NIGHT: winner screen has End Round');
  const callsBefore = calls.length;
  await act(async () => { fireEvent.click(winnerEnd); await new Promise(r => setTimeout(r, 600)); });
  ok(!!document.querySelector('[data-testid="round-over-dialog"]'), 'BINGO NIGHT: End Round on the winner screen opens the pop-up (not the lobby)');
  ok(!document.body.textContent.includes('OTHER'), 'BINGO NIGHT: host stays on the host page');
  ok(calls.slice(callsBefore).some(c => c.startsWith('POST /bingo/game/end-round')), 'BINGO NIGHT: round ended on the server');
  // leave it as the earlier ROUND OVER section expects: close this pop-up by starting the next round
  const before5 = calls.length;
  await act(async () => { fireEvent.click(document.querySelector('[data-testid="start-next-round-btn"]')); await new Promise(r => setTimeout(r, 600)); });
  ok(calls.slice(before5).some(c => c.startsWith('POST /bingo/game/new-round')), 'BINGO NIGHT: Start next round works from the winner screen too');
}

// ================= ROUND OVER pop-up =================
const enough = () => act(async () => { await new Promise(r => setTimeout(r, 350)); });
const hasDialog = () => !!document.querySelector('[data-testid="round-over-dialog"]');
ok(!hasDialog(), 'ROUND OVER: no pop-up before the round ends');
await act(async () => { {const b=document.querySelector('[data-testid="start-game-btn"]'); if(b) fireEvent.click(b);} await new Promise(r => setTimeout(r, 300)); });
await act(async () => { await new Promise(r => setTimeout(r, 2600)); });
// round 2 is idle after the Bingo-night section: start it, wait for the cooldown, then end it
{ const sb = document.querySelector('[data-testid="start-game-btn"]'); if (sb) await act(async () => { fireEvent.click(sb); await new Promise(r => setTimeout(r, 300)); }); }
await act(async () => { await new Promise(r => setTimeout(r, 2600)); });   // one 2 s poll brings in is_active
const endBtn = [...document.querySelectorAll('button')].find(b => /End Round/.test(b.textContent));
ok(!!endBtn, 'ROUND OVER: End Round button exists');
const before2 = calls.length;
await act(async () => { fireEvent.click(endBtn); await new Promise(r => setTimeout(r, 500)); });
ok(calls.slice(before2).some(c => c.startsWith('POST /bingo/game/end-round')), 'ROUND OVER: the round is ended on the server');
ok(hasDialog(), 'ROUND OVER: the pop-up appears');
ok(document.body.textContent.match(/Round \d+ complete/), 'ROUND OVER: says Round 1 complete');
ok(globalThis.__sent.slice(-6).some(m => m && m.command === 'pause'), 'ROUND OVER: the song is stopped on the audience too');
ok(!!document.querySelector('[data-testid="next-theme-Emo"]') && !!document.querySelector('[data-testid="next-theme-1990s"]'), 'ROUND OVER: offers the themes switched on in Bingo Setup');
ok(document.body.textContent.match(/Start Round \d+/), 'ROUND OVER: button says Start Round 2 (the count keeps going)');
// choose a fresh theme + lightning, start the round
await act(async () => { {const e=document.querySelector('[data-testid="next-theme-Emo"]'); if(e) fireEvent.click(e);} {const e=document.querySelector('[data-testid="next-speed-lightning"]'); if(e) fireEvent.click(e);} });
const before3 = calls.length;
await act(async () => { fireEvent.click(document.querySelector('[data-testid="start-next-round-btn"]')); await new Promise(r => setTimeout(r, 600)); });
const nr = calls.slice(before3).find(c => c.startsWith('POST /bingo/game/new-round'));
ok(nr && nr.includes('"music_decade":"Emo"') && nr.includes('"game_type":"lightning"'), 'ROUND OVER: new-round sent with the fresh theme + speed -> ' + nr);
ok(calls.slice(before3).some(c => c.includes('/bingo/songlist/Emo')), 'ROUND OVER: loads the Emo songs for the new round');
ok(!hasDialog(), 'ROUND OVER: pop-up closes once the next round is ready');

// a round that has not started cannot be ended (the button is off), so start round 2 first
const endBtnIdle = [...document.querySelectorAll('button')].find(b => /End Round/.test(b.textContent));
ok(endBtnIdle && endBtnIdle.disabled, 'ROUND OVER: End Round is off while the new round has not started');
await act(async () => { {const b=document.querySelector('[data-testid="start-game-btn"]'); if(b) fireEvent.click(b);} await new Promise(r => setTimeout(r, 300)); });
await act(async () => { await new Promise(r => setTimeout(r, 2600)); });   // one 2 s poll brings in is_active

// second end-of-round: finalize with a confirmation
await enough();
const endBtn2 = [...document.querySelectorAll('button')].find(b => /End Round/.test(b.textContent));
await act(async () => { fireEvent.click(endBtn2); await new Promise(r => setTimeout(r, 500)); });
ok(hasDialog() && document.body.textContent.match(/Round \d+ complete/), 'ROUND OVER: second time says Round N complete');
const before4 = calls.length;
await act(async () => { fireEvent.click(document.querySelector('[data-testid="end-night-btn"]')); });
ok(document.body.textContent.includes('End the Bingo night?'), 'END NIGHT: asks to confirm first');
ok(!calls.slice(before4).some(c => c.includes('/game/finalize')), 'END NIGHT: nothing is ended before the confirmation');
await act(async () => { fireEvent.click(document.querySelector('[data-testid="end-night-cancel-btn"]')); });
ok(document.body.textContent.match(/Round \d+ complete/), 'END NIGHT: Go back returns to the choices');
await act(async () => { fireEvent.click(document.querySelector('[data-testid="end-night-btn"]')); });
await act(async () => { fireEvent.click(document.querySelector('[data-testid="end-night-confirm-btn"]')); await new Promise(r => setTimeout(r, 600)); });
ok(calls.slice(before4).some(c => c.startsWith('POST /bingo/game/finalize')), 'END NIGHT: finalize sent to the server');
ok(document.body.textContent.includes('OTHER'), 'END NIGHT: goes back to the Bingo lobby');
console.error = origErr;
console.log('react errors:', errors.length ? errors.slice(0, 3) : 'none');
console.log('unhandled rejections:', unhandled.length ? unhandled : 'none');
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'host render: checks ok');
process.exit(fails.length ? 1 : 0);
