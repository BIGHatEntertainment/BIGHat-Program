import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/bingo/host', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage','BroadcastChannel','Audio']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
dom.window.HTMLMediaElement.prototype.play = function(){ return Promise.resolve(); };
dom.window.HTMLMediaElement.prototype.pause = function(){};
dom.window.HTMLMediaElement.prototype.load = function(){};
globalThis.__sent = [];
class BC { constructor(n){ this.name=n; } postMessage(d){ globalThis.__sent.push(d); } close(){} set onmessage(f){} }
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
  if (url.includes('/bingo/songlist/')) return { data: { success: true, source: 'local-folder', songs: SONGS, decade: '1990s' } };
  return { data: {} };
};
axios.post = async (url, body) => {
  calls.push('POST ' + url.replace('http://x/api','') + (body ? ' ' + JSON.stringify(body).slice(0, 60) : ''));
  if (url.includes('/player/')) { const e = new Error('Request failed with status code 404'); e.response = { status: 404, data: { detail: 'Not Found' } }; throw e; }
  if (url.includes('/game/start')) game = { ...game, is_active: true };
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
ok(document.body.textContent.includes('39 videos loaded'), '39 playable songs (song 13 has no video): ' + (document.body.textContent.match(/\d+ videos loaded/) || ['none'])[0]);
const btn = () => screen.getByTestId('next-song-btn');
ok(!btn().disabled, 'Next Song is ready straight away, no folder picking');
const c0 = calls.length;
await act(async () => { fireEvent.click(btn()); await new Promise(r => setTimeout(r, 300)); });
const posted = calls.slice(c0).filter(c => c.startsWith('POST /bingo/game/call-song'));
ok(posted.length === 1, 'first press calls exactly one song: ' + calls.slice(c0).join(' ; '));
const num = Number((posted[0].match(/"number":(\d+)/) || [])[1]);
ok(num >= 1 && num <= 40 && num !== 13, 'the called song has a video (never #13), got ' + num);
ok(btn().disabled && /Loading/.test(btn().textContent), 'cooldown: Loading... right after a call');
await act(async () => { fireEvent.click(btn()); await new Promise(r => setTimeout(r, 200)); });
ok(calls.slice(c0).filter(c => c.startsWith('POST /bingo/game/call-song')).length === 1, 'a rapid second press does NOT call another song');
// the channel message the audience receives carries a STREAM link, not a blob
await act(async () => { await new Promise(r => setTimeout(r, 2500)); });   // let the 2s audience sync tick
const urls = globalThis.__sent.map(m => m && m.videoUrl).filter(Boolean);
ok(urls.length > 0 && urls.every(u => /^http:\/\/x\/api\/bingo\/media\/1990s\/\d+$/.test(u)), 'audience gets stream links (not blob:): ' + JSON.stringify(urls.slice(0,2)));
console.log('call-song payload:', posted[0]);
console.error = origErr;
console.log('react errors:', errors.length ? errors.slice(0, 3) : 'none');
console.log('unhandled rejections:', unhandled.length ? unhandled : 'none');
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'host render: checks ok');
process.exit(fails.length ? 1 : 0);
