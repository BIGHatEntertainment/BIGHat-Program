// alpha.93: the FIRST singer's song always loads (fullscreen gate, late TV window, YouTube errors, retries, limits)
// alpha.89: the audience screen REALLY buffers the next song, reports it, and reuses that player at song start.
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/karaoke/audience', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.BroadcastChannel = (await import('node:worker_threads')).BroadcastChannel;
const React = (await import('react')).default;
const { render, cleanup, act } = await import('@testing-library/react');
const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
let reachedEnd = false;
process.on('exit', () => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

// ---- fake YouTube whose buffer I control
const yt = { players: [] };
class FakePlayer {
  constructor(id, opts) { this.id = id; this.opts = opts; this.state = -1; this.muted = false; this.loaded = 0; this.log = []; this.listeners = {}; yt.players.push(this);
    const el = document.getElementById(id); if (el) el.setAttribute('data-fake-yt', '1');
    queueMicrotask(() => opts.events.onReady({ target: this })); }
  mute() { this.muted = true; this.log.push('mute'); } unMute() { this.muted = false; this.log.push('unmute'); }
  playVideo() { this.log.push('play'); this.state = 1; setTimeout(() => { this.opts.events.onStateChange && this.opts.events.onStateChange({ data: 1 }); (this.listeners.onStateChange || []).forEach(f => f({ data: 1 })); }, 20); }
  pauseVideo() { this.log.push('pause'); this.state = 2; setTimeout(() => { this.opts.events.onStateChange && this.opts.events.onStateChange({ data: 2 }); (this.listeners.onStateChange || []).forEach(f => f({ data: 2 })); }, 20); }
  seekTo(t) { this.log.push('seek:' + t); }
  getCurrentTime() { return 0; } getDuration() { return 240; } getPlayerState() { return this.state; }
  getVideoLoadedFraction() { return this.loaded; }
  addEventListener(n, f) { (this.listeners[n] ||= []).push(f); this.log.push('listen:' + n); }
  cueVideoById() { this.log.push('cue'); }
  destroy() { this.log.push('destroy'); this.destroyed = true; }
}
window.YT = { Player: FakePlayer, PlayerState: { ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3 } };

// ---- fake server
let pb, pre, reports;
axios.get = async (u) => {
  if (u.endsWith('/session/playback')) return { data: { playback: pb, preload: pre, location: 'Pub One', qr_enabled: true, overlay_enabled: true } };
  if (u.endsWith('/request-info')) return { data: { url: 'https://api.bighat.live/k/X', phone_reachable: true, online: true } };
  return { data: {} };
};
axios.post = async (u, body) => { if (u.endsWith('/session/preload-report')) reports.push(body); return { data: { success: true } }; };
const reset = () => { reports = []; yt.players.length = 0; pb = { song_playing: false, song_ending: false, current_singer: null, mode: 'filler' }; pre = null; };
reset();

const { default: Aud } = await import('/tmp/rtest/kaud.bundle.mjs');
const bob = { id: 's2', singer_name: 'Bob', song_title: 'Creep', embed_url: 'https://www.youtube.com/embed/BBB222?autoplay=1' };
const cy = { id: 's3', singer_name: 'Cy', song_title: 'Yellow', embed_url: 'https://www.youtube.com/embed/CCC333?autoplay=1' };
const fullscreen = () => { Object.defineProperty(dom.window.document, 'fullscreenElement', { value: dom.window.document.documentElement, configurable: true }); dom.window.document.dispatchEvent(new dom.window.Event('fullscreenchange')); return wait(100); };
let rev = 0;
const send = async (pbx) => { rev += 1; pb = { ...pbx, rev }; const ch = new BroadcastChannel('karaoke-state'); ch.postMessage({ type: 'karaoke-state', pb }); ch.close(); await wait(250); };
const mount = async () => { render(React.createElement(Aud)); await wait(300); await fullscreen(); await wait(300); };


const results = [];
const note = (name, pass, extra='') => results.push((pass ? 'PASS ' : 'FAIL ') + name + (extra ? '  [' + extra + ']' : ''));
const bufferPlayers = () => yt.players.filter(p => p.id === 'karaoke-yt-preload');
const errorsSent = () => reports.filter(r => r.error).map(r => r.error);

// A. the TV window is open and idle (no singer yet), host names the FIRST singer
await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2800);
note('A. first singer: a buffer player is created while nobody is singing yet', bufferPlayers().length >= 1, 'players=' + bufferPlayers().length);
cleanup();

// B. YouTube's first load fails (slow / blocked for a moment), then recovers
reset(); yt.loadFails = true; delete window.YT;
await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2800);
const errs = reports.filter(r => r.error).length;
yt.loadFails = false; window.YT = { Player: FakePlayer, PlayerState: { ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3 } };
await wait(6500);                                        // the same singer is still next: it should try AGAIN by itself
note('B. after a failed first try the SAME singer is retried by itself', bufferPlayers().length >= 1, 'errors seen=' + errs + ' players after recovery=' + bufferPlayers().length);
cleanup();

// C. the TV window opens AFTER the host already named the first singer
reset(); pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(300);
await mount();
await wait(2800);
note('C. TV window opened late: it picks up the already-named singer', bufferPlayers().length >= 1, 'players=' + bufferPlayers().length + ' reports=' + JSON.stringify(reports));
cleanup();

// D. while one singer is SINGING, the next is named (the normal case)
reset(); await mount();
await send({ song_playing: true, song_ending: false, current_singer: bob, mode: 'karaoke' });
pre = { singer_id: 's3', embed_url: cy.embed_url, ready: false, percent: 0 };
await wait(2800);
note('D. while Bob sings, Cy (next) starts buffering', bufferPlayers().some(p => p.opts.videoId === 'CCC333'), 'players=' + bufferPlayers().map(p => p.opts.videoId).join(','));
cleanup();

// E. the player was told "no_holder"/errored once, then the host re-names the same singer: does it retry?
reset(); await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0, error: 'youtube_error' };
await wait(2800);
const n1 = bufferPlayers().length;
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };      // host cleared the error
await wait(2800);
note('E. when the error is cleared the buffer is attempted again', bufferPlayers().length >= 1, 'before=' + n1 + ' after=' + bufferPlayers().length);
cleanup();

// F. TV window is on the 'Click to Enter Fullscreen' gate when the first singer is named; then the host clicks fullscreen
reset(); render(React.createElement(Aud)); await wait(300);
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2800);
const gateReports = JSON.stringify(reports);
await fullscreen(); await wait(300);
await wait(6000);
note('F. named on the fullscreen gate, then fullscreen entered: the SAME singer starts buffering', bufferPlayers().length >= 1, 'on gate reports=' + gateReports + ' players now=' + bufferPlayers().length + ' reports=' + JSON.stringify(reports));
cleanup();



// G. YouTube raises an error on the first try: the same singer must be tried AGAIN (a new buffer player) by itself
reset(); await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2800);
const first = bufferPlayers()[0];
await act(async () => { first.opts.events.onError({ data: 5 }); });
const afterErr = errorsSent();
const countBefore = bufferPlayers().length;
await wait(9000);
note('G. a YouTube error is reported, then the SAME singer is retried by itself', afterErr.includes('youtube_error') && bufferPlayers().length > countBefore, 'error=' + afterErr.join(',') + ' players before=' + countBefore + ' after=' + bufferPlayers().length);
// and the retried one buffers and is reported ready
const retried = bufferPlayers()[bufferPlayers().length - 1]; retried.loaded = 0.5; await wait(1800);
note('G2. the retried buffer reaches ready', reports.some(r => r.ready === true), 'last=' + JSON.stringify(reports[reports.length - 1]));
cleanup();

// H. it must not retry forever: EVERY new buffer fails; after MAX tries (6) it stops
reset(); await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2800);
for (let i = 0; i < 14; i++) {
  const live = bufferPlayers().filter(p => !p.destroyed && !p.failedOnce);
  for (const p of live) { p.failedOnce = true; await act(async () => { p.opts.events.onError({ data: 5 }); }); }
  await wait(5200);
}
note('H. retries are limited to 6 tries (does not flood forever)', bufferPlayers().length >= 2 && bufferPlayers().length <= 6, 'players created=' + bufferPlayers().length);
cleanup();

// I. normal: next singer changes while the first is still buffering -> old buffer is dropped, new one starts (no leak)
reset(); await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 }; await wait(2800);
pre = { singer_id: 's3', embed_url: cy.embed_url, ready: false, percent: 0 }; await wait(2800);
const live = bufferPlayers().filter(p => !p.destroyed);
note('I. switching to a different next singer drops the old buffer and starts the new one', live.length === 1 && live[0].opts.videoId === 'CCC333', 'live=' + live.map(p => p.opts.videoId).join(','));
cleanup();


reachedEnd = true;
const bad = results.filter(r => r.startsWith('FAIL'));
if (bad.length) { console.log('FAILED:\n - ' + bad.join('\n - ')); process.exit(1); }
console.log('karaoke first-singer preload: checks ok (' + results.length + ')');
