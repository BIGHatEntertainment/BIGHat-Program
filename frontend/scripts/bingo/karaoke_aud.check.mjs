// alpha.70: Karaoke AUDIENCE screen - it is the clock. Runs against a fake YouTube player I control.
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
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

// ---- fake YouTube
const yt = { players: [], loadFails: false };
class FakePlayer {
  constructor(id, opts) { this.id = id; this.opts = opts; this.state = -1; this.time = 0; this.log = []; yt.players.push(this); queueMicrotask(() => opts.events.onReady({ target: this })); }
  playVideo() { this.log.push('play'); this.state = 1; this.opts.events.onStateChange({ data: 1 }); }
  pauseVideo() { this.log.push('pause'); this.state = 2; this.opts.events.onStateChange({ data: 2 }); }
  seekTo(t) { this.log.push('seek:' + t); }
  getCurrentTime() { return this.time; }
  getDuration() { return 200; }
  getPlayerState() { return this.state; }
  destroy() { this.log.push('destroy'); this.destroyed = true; }
  fire(state) { this.state = state; this.opts.events.onStateChange({ data: state }); }
}
const installYT = () => { window.YT = { Player: FakePlayer, PlayerState: { ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3 } }; };
installYT();
// the page appends <script src=youtube>; in the failing case fire its onerror
const origAppend = dom.window.document.head.appendChild.bind(dom.window.document.head);
dom.window.document.head.appendChild = (el) => { if (el.tagName === 'SCRIPT' && yt.loadFails) { setTimeout(() => el.onerror && el.onerror(), 0); return el; } return origAppend(el); };

// ---- fake server
let pb, reports, queue;
const reset = () => { reports = []; queue = [{ id: 'q1', singer_name: 'Bob', song_title: 'Creep', status: 'waiting' }, { id: 'q2', singer_name: 'Cy', song_title: '', status: 'waiting' }];
  pb = { song_playing: false, song_ending: false, current_singer: null, mode: 'filler' }; };
reset();
axios.get = async (u) => {
  if (u.endsWith('/session/playback')) return { data: { playback: pb, location: 'Pub One', qr_enabled: true, overlay_enabled: true } };
  if (u.endsWith('/karaoke/queue')) return { data: { queue } };
  if (u.endsWith('/request-info')) return { data: globalThis.__reqInfo || { url: 'https://api.bighat.live/k/AUDQRLINKAUDQRLINK', phone_reachable: true, online: true } };
  return { data: {} };
};
axios.post = async (u, body) => { if (u.endsWith('/session/audience-report')) reports.push(body); return { data: { success: true } }; };

const { default: Aud } = await import('/tmp/rtest/kaud.bundle.mjs');
const ann = { id: 's1', singer_name: 'Ann', song_title: 'Africa', song_artist: 'Toto', embed_url: 'https://www.youtube.com/embed/AAA111?autoplay=1' };
const bob = { id: 's2', singer_name: 'Bob', song_title: 'Creep', embed_url: 'https://www.youtube.com/embed/BBB222?autoplay=1' };
let rev = 0;
const send = (ch, pbx, extra = {}) => { rev += 1; const withRev = { ...pbx, rev }; pb = withRev; ch.postMessage({ type: 'karaoke-state', pb: withRev, ...extra }); return wait(120); };
const fullscreen = () => { Object.defineProperty(dom.window.document, 'fullscreenElement', { value: dom.window.document.documentElement, configurable: true }); dom.window.document.dispatchEvent(new dom.window.Event('fullscreenchange')); return wait(100); };

// 1. fullscreen gate first, then the screen
render(React.createElement(Aud)); await wait(300);
ok(!!q('karaoke-audience-fullscreen-gate'), 'shows "Click to Enter Fullscreen" first');
await fullscreen();
ok(!!q('karaoke-audience') && !q('karaoke-audience-fullscreen-gate'), 'after fullscreen the TV screen shows');
ok(/karaoke\/overlay\/master/.test(q('karaoke-audience-overlay').src), 'uses the master overlay from Karaoke Setup');
ok(/venue-logo\/Pub%20One/.test((q('karaoke-audience-logo').querySelector('img') || {}).src || ''), 'venue logo comes from Karaoke Setup, by location');
ok(q('karaoke-audience-logo').querySelector('img').style.objectFit === 'contain', 'logo fits inside its window (not cropped)');
ok(!!q('karaoke-audience-qr'), 'request QR box shows');
{ const ov = document.querySelector('img[src*="/karaoke/overlay/master"]'); ok(!!ov && ov.style.display !== 'none' && ov.style.visibility !== 'hidden' && ov.style.opacity !== '0', 'the overlay image is on the audience screen and visible'); }
ok(/Music Playing/.test(q('karaoke-audience-video').textContent), 'no singer yet: music-playing view');
await wait(500);
ok(/UP NEXT.*Bob.*Creep/.test(q('karaoke-audience-chyron').textContent) && /Cy/.test(q('karaoke-audience-chyron').textContent), 'up-next bar lists the waiting singers: ' + q('karaoke-audience-chyron').textContent);

const ch = new BroadcastChannel('karaoke-state');
// 2. host starts Ann's song -> audience creates ONE player for that video and plays it
await send(ch, { song_playing: true, current_singer: ann, mode: 'karaoke' });
await wait(200);
ok(yt.players.length === 1 && yt.players[0].opts.videoId === 'AAA111', 'a new song creates one YouTube player for the right video');
const P = yt.players[0];
ok(P.opts.playerVars.controls === 0 && P.opts.playerVars.autoplay === 1, 'player has no controls and autoplays');
ok(P.log.includes('play'), 'audience starts playing');
await wait(300);
ok(reports.some(r => r.started === true && r.singer_id === 's1' && r.duration === 200), 'AUDIENCE REPORTS started (with the real duration) for that singer: ' + JSON.stringify(reports.slice(0, 2)));
// 3. the audience clock ticks into reports every second
P.time = 42.5; await wait(1200);
ok(reports.some(r => r.time === 42.5), 'audience reports its real play time every second');
// 4. routine sync from the host with a LATER time must NOT seek or restart
const before = P.log.length;
await send(ch, { song_playing: true, current_singer: ann, mode: 'karaoke' });
await send(ch, { song_playing: true, current_singer: ann, mode: 'karaoke' });
ok(yt.players.length === 1, 'the same song is never restarted');
ok(!P.log.slice(before).includes('destroy') && !P.log.some(l => l.startsWith('seek')), 'the audience NEVER seeks to the host position');
// 4b. a LATE copy from the server with an older revision must not stop or restart the song
const savedPb = pb;
pb = { song_playing: false, song_ending: false, current_singer: null, mode: 'filler', rev: 0 };
await wait(2800);
ok(!P.destroyed && yt.players.length === 1, 'a late, older server copy cannot kill the song that is playing');
pb = savedPb;
// 5. deliberate pause, then deliberate play
await send(ch, { song_playing: false, current_singer: ann, mode: 'karaoke' });
ok(P.log[P.log.length - 1] === 'pause', 'a deliberate host pause pauses the audience video');
const stopped = reports.length; P.time = 50; await wait(1200);
ok(!reports.slice(stopped).some(r => r.time === 50), 'no time reports while paused');
await send(ch, { song_playing: true, current_singer: ann, mode: 'karaoke' });
ok(P.log[P.log.length - 1] === 'play' && yt.players.length === 1, 'a deliberate play resumes the SAME video (no restart, no seek)');
// 6. last 3 seconds: fade
await send(ch, { song_playing: true, song_ending: true, current_singer: ann, mode: 'karaoke' });
ok(q('karaoke-audience-video').style.opacity === '0' && /3s/.test(q('karaoke-audience-video').style.transition), 'song ending fades the video out over 3 s');
// 7. YouTube says ENDED -> audience reports ended once
P.fire(0); P.fire(0); await wait(150);
ok(reports.filter(r => r.ended === true).length === 1 && reports.find(r => r.ended).singer_id === 's1', 'audience reports "ended" exactly once, for the right singer');
// 8. back to filler: video removed, music view
await send(ch, { song_playing: false, song_ending: false, current_singer: null, mode: 'filler' });
ok(P.destroyed === true && /Music Playing/.test(q('karaoke-audience-video').textContent), 'after the song the player is destroyed and the music view returns');
ok(q('karaoke-audience-video').style.opacity === '1', 'fade resets for the next song');
// 9. next singer = a brand new player, fresh clock
await send(ch, { song_playing: true, current_singer: bob, mode: 'karaoke' }); await wait(250);
ok(yt.players.length === 2 && yt.players[1].opts.videoId === 'BBB222', 'next singer gets a fresh player');
ok(reports.some(r => r.started === true && r.singer_id === 's2'), 'and reports started under the new singer');
// 10. server refresh (window reloaded mid-song) rebuilds the song without a command
cleanup(); ch.close(); yt.players.length = 0; reset(); rev += 1; pb = { song_playing: true, song_ending: false, current_singer: bob, mode: 'karaoke', rev };
render(React.createElement(Aud)); await fullscreen(); await wait(3200);
ok(yt.players.length === 1 && yt.players[0].opts.videoId === 'BBB222', 'a refreshed audience window picks the current song back up from the server');
// 11. QR address from the backend
ok(q('karaoke-audience-qr') && !!q('karaoke-audience-qr').querySelector('svg'), 'QR is drawn');
// 11b. alpha.95: the QR box is ALWAYS on the big screen. A PC-only address (phones cannot open it) is NOT drawn as a code,
//      the box says it is getting ready instead (a code that goes nowhere would be worse)
cleanup(); reset(); globalThis.__reqInfo = { url: 'http://192.168.1.50:8001/karaoke/request', phone_reachable: false };
render(React.createElement(Aud)); await fullscreen(); await wait(600);
ok(!!q('karaoke-audience-qr') && !q('karaoke-audience-qr').querySelector('svg') && !!q('karaoke-audience-qr-wait'), 'QR box is always there; for a PC-only address it says "getting ready" and draws no useless code');
// 11c. ... and it appears by itself once the cloud link is ready (within ~10 s)
globalThis.__reqInfo = { url: 'https://api.bighat.live/k/LATEREADYLINK1234', phone_reachable: true, online: true };
await act(async () => { await new Promise(r => setTimeout(r, 10600)); });
ok(!!q('karaoke-audience-qr') && !!q('karaoke-audience-qr').querySelector('svg'), 'QR appears on the big screen by itself once the cloud link is ready');
globalThis.__reqInfo = null;
// 12. QR off / overlay off
pb = { ...pb, song_playing: false, current_singer: null };
cleanup();

// 13. YouTube can't load (no internet): fall back to singer + song, tell the host
// (a fresh copy of the page, because the real page remembers a successful YouTube load for its whole life)
const { default: AudFresh } = await import('/tmp/rtest/kaud.bundle.mjs?fresh=' + Date.now());
reset(); yt.loadFails = true; delete window.YT; yt.players.length = 0;
rev += 1; pb = { song_playing: true, song_ending: false, current_singer: ann, mode: 'karaoke', rev };
render(React.createElement(AudFresh)); await fullscreen(); await wait(3200);
ok(!!q('karaoke-audience-singer') && /Ann/.test(q('karaoke-audience-singer').textContent) && /Africa/.test(q('karaoke-audience-singer').textContent), 'no YouTube: audience shows the singer and song instead of a blank box');
ok(!!q('karaoke-audience-yt-problem'), 'and says the video could not load');
cleanup();

// 14. session ended
reset(); yt.loadFails = false; installYT(); yt.players.length = 0;
render(React.createElement(Aud)); await fullscreen(); await wait(300);
const ch2 = new BroadcastChannel('karaoke-state'); ch2.postMessage({ ended: true }); await wait(200);
ok(!!q('karaoke-audience-ended') && /Thanks for singing/.test(q('karaoke-audience-ended').textContent), 'end of night shows the thank-you screen');
ch2.close(); cleanup();

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke audience: checks ok');
process.exit(0);
