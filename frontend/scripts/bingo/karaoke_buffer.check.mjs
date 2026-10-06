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

// 1. the host names the next singer: the audience screen starts BUFFERING it (muted, then held at the start)
await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2500);                                       // the screen polls for the preload every couple of seconds
const buf = yt.players.find(p => p.id === 'karaoke-yt-preload');
ok(!!buf, 'a buffering player was created for the next song');
if (buf) {
  ok(buf.opts.playerVars.mute === 1 && buf.log.includes('mute'), 'it loads MUTED, so nobody hears it');
  ok(buf.log.includes('play'), 'it is actually STARTED (a merely cued video downloads nothing)');
  ok(buf.log.includes('pause') && buf.log.includes('seek:0'), 'it is held paused at 0:00 after it starts');
  ok(!buf.log.includes('cue'), 'it does not rely on cueVideoById, which does not download');
  ok(buf.opts.playerVars.width === undefined && String(buf.opts.width) === '100%', 'it is full size (a 1px video is not buffered by Chromium)');
  ok(!!document.getElementById('karaoke-yt-preload'), 'it lives in the page, not in a detached node');
}

// 2. progress is reported as a REAL percent of the first 45 seconds, never ready too early
reports.length = 0;
if (buf) { buf.loaded = 0.05; }                         // 12 s of a 240 s song = 27 %
await wait(2000);
const mid = reports.filter(r => 'percent' in r).pop();
ok(mid && mid.percent >= 20 && mid.percent <= 35 && !mid.ready, 'at 12 seconds buffered it reports about 27 percent and not ready: ' + JSON.stringify(mid));
ok(mid && mid.singer_id === 's2', 'the report names the singer it is for');
reports.length = 0;
if (buf) buf.loaded = 0.2;                              // 48 s = enough
await wait(2000);
ok(reports.some(r => r.ready === true && r.percent === 100), 'at 48 seconds buffered it reports READY: ' + JSON.stringify(reports));
const readyCount = reports.filter(r => r.ready === true).length;
await wait(2000);
ok(reports.filter(r => r.ready === true).length === readyCount, 'READY is reported once, not over and over');

// 3. the host presses Next Singer: that same player is reused. No second player, no reload.
const before = yt.players.length;
pre = null;
await send({ song_playing: true, song_ending: false, current_singer: bob, mode: 'karaoke' });
await wait(1200);
const songPlayers = yt.players.filter(p => p.id !== 'karaoke-yt-preload' && p.opts.videoId === 'BBB222');
ok(songPlayers.length === 0, 'the song did NOT create a second player for the same video (it reused the buffered one): ' + yt.players.map(p => p.id + ':' + p.opts.videoId).join(','));
ok(yt.players.length === before, 'no extra player was made at song start');
if (buf) {
  ok(!buf.destroyed, 'the buffered player was not destroyed');
  ok(buf.log.includes('unmute'), 'it is un-muted so the room hears it');
  ok(buf.log.lastIndexOf('play') > buf.log.lastIndexOf('pause'), 'and it plays');
  ok(buf.log.includes('listen:onStateChange'), 'the clock/end tracking is attached to it');
  ok(q('karaoke-buffer-host')?.style.opacity === '1', 'the buffered video is revealed');
}

// 4. a song that was NOT buffered still starts the normal way
reset(); cleanup();
await mount();
await send({ song_playing: true, song_ending: false, current_singer: cy, mode: 'karaoke' });
await wait(1200);
const normal = yt.players.filter(p => p.id === 'karaoke-yt' && p.opts.videoId === 'CCC333');
ok(normal.length === 1, 'with nothing buffered, the song starts the normal way');

// 5. buffering for the wrong song is never reused
reset(); cleanup();
await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2500);
const bb = yt.players.find(p => p.id === 'karaoke-yt-preload'); if (bb) bb.loaded = 0.3;
await wait(2000);
await send({ song_playing: true, song_ending: false, current_singer: cy, mode: 'karaoke' });       // a DIFFERENT singer starts
await wait(1200);
ok(yt.players.some(p => p.id === 'karaoke-yt' && p.opts.videoId === 'CCC333'), "a different singer's song loads normally and does not use Bob's buffer");

// 6. the host moves on to someone else before it is ready: the old buffer is dropped
reset(); cleanup();
await mount();
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await wait(2500);
const first = yt.players.find(p => p.id === 'karaoke-yt-preload');
pre = { singer_id: 's3', embed_url: cy.embed_url, ready: false, percent: 0 };
await wait(2500);
ok(first && first.destroyed, 'when the next singer changes, the old buffering player is destroyed');
ok(yt.players.some(p => p.opts.videoId === 'CCC333'), "and the new next singer's song starts buffering");
cleanup();

reachedEnd = true;
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke buffer: checks ok');
