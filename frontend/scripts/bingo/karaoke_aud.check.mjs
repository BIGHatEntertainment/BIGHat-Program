// alpha.98: Karaoke AUDIENCE screen. Songs play in a PLAIN YouTube iframe (like the prototype); a clock reports started/time/ended.
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
let pb, reports, queue, pre = null;
const reset = () => { pre = null; reports = []; queue = [{ id: 'q1', singer_name: 'Bob', song_title: 'Creep', status: 'waiting' }, { id: 'q2', singer_name: 'Cy', song_title: '', status: 'waiting' }];
  pb = { song_playing: false, song_ending: false, current_singer: null, mode: 'filler' }; };
reset();
axios.get = async (u) => {
  if (u.endsWith('/session/playback')) return { data: { playback: pb, location: 'Pub One', qr_enabled: true, overlay_enabled: true, preload: pre } };
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
const iframes = () => [...document.querySelectorAll('iframe')];
const playing = () => iframes().find(f => f.getAttribute('data-testid') === 'karaoke-audience-iframe');
const warm = () => iframes().find(f => f.getAttribute('data-testid') === 'karaoke-warm-iframe');
const sent = [];                                                   // commands the audience sends INTO the YouTube iframe
const hook = (f) => { if (f && f.contentWindow && !f.__hooked) { f.__hooked = true; f.contentWindow.postMessage = (m) => sent.push(JSON.parse(m).func); } };

// 2. host starts Ann's song -> a plain iframe with the prototype's address, and NO YouTube script player at all
const yt0 = yt.players.length;
await send(ch, { song_playing: true, current_singer: { ...ann, duration_seconds: 5 }, mode: 'karaoke' });
await wait(300);
ok(!!playing(), 'a song starts in a plain iframe');
ok(playing() && /^https:\/\/www\.youtube\.com\/embed\/AAA111\?autoplay=1&controls=0&rel=0&modestbranding=1/.test(playing().src), 'the address is the prototype form: ' + (playing() || {}).src);
ok(playing() && /enablejsapi=1/.test(playing().src), 'JS control is on so pause/play can be sent');
ok(yt.players.length === yt0, 'NO YouTube JavaScript player is created for the song (that is what failed with error 101)');
ok(!q('karaoke-audience-yt-problem'), 'no "could not load" message');
// 3. the host is told: started once, then time every second, then ended at the song length
await wait(300);
ok(reports.filter(r => r.started === true && r.singer_id === 's1').length === 1 && reports.find(r => r.started).duration === 5, 'AUDIENCE REPORTS started once, with the real length: ' + JSON.stringify(reports.slice(0, 2)));
await wait(2300);
const times = reports.filter(r => typeof r.time === 'number').map(r => r.time);
ok(times.length >= 2 && times[times.length - 1] > times[0], 'time is reported every second and goes up: ' + JSON.stringify(times.map(t => Math.round(t * 10) / 10)));
await wait(3200);
ok(reports.filter(r => r.ended === true).length === 1, 'ENDED is reported exactly once, at the song length: ' + JSON.stringify(reports.filter(r => r.ended)));
const reportsAfterEnd = reports.length; await wait(2200);
ok(!reports.slice(reportsAfterEnd).some(r => typeof r.time === 'number'), 'and the time stops being reported after the end');

// 4. pause stops the clock without losing the place; play carries on (no restart)
reports.length = 0; sent.length = 0;
await send(ch, { song_playing: true, current_singer: { ...bob, duration_seconds: 60 }, mode: 'karaoke' }); await wait(300);
ok(playing() && /BBB222/.test(playing().src), 'a new song replaces the iframe with the new video');
hook(playing());
await wait(2300);
const beforePause = Math.max(...reports.filter(r => typeof r.time === 'number').map(r => r.time));
await send(ch, { song_playing: false, current_singer: { ...bob, duration_seconds: 60 }, mode: 'karaoke' }); await wait(300);
ok(sent.includes('pauseVideo'), 'pausing sends pauseVideo into the iframe: ' + JSON.stringify(sent));
reports.length = 0; await wait(2300);
ok(!reports.some(r => typeof r.time === 'number'), 'while paused no time is reported');
await send(ch, { song_playing: true, current_singer: { ...bob, duration_seconds: 60 }, mode: 'karaoke' }); await wait(300);
ok(sent.includes('playVideo'), 'pressing play sends playVideo (the same iframe, not rebuilt)');
await wait(2300);
const afterPlay = reports.filter(r => typeof r.time === 'number').map(r => r.time);
ok(afterPlay.length && afterPlay[0] >= beforePause - 0.5 && afterPlay[0] < beforePause + 3.5, 'carries on from where it paused (about ' + Math.round(beforePause) + 's), not from 0: ' + JSON.stringify(afterPlay.map(t => Math.round(t))));
ok(iframes().filter(f => f.getAttribute('data-testid') === 'karaoke-audience-iframe').length === 1, 'still one song iframe');

// 5. a song with NO known length never ends by itself (the host End Song button does)
reports.length = 0;
await send(ch, { song_playing: true, current_singer: { ...ann, id: 's9', duration_seconds: 0 }, mode: 'karaoke' }); await wait(3500);
ok(!reports.some(r => r.ended), 'no known length: the audience never declares the song over by itself');

// 6. the song is over: the iframe is removed and the music view comes back
await send(ch, { song_playing: false, current_singer: null, mode: 'filler' }); await wait(400);
ok(!playing(), 'when the song is over the iframe is removed');
ok(/Music Playing/.test(q('karaoke-audience-video').textContent), 'and the music view returns');

// 7. YOUR REPORT: the next singer and song show BEFORE anyone presses play, and are never hidden by the player
ok(/UP NEXT.*Bob.*Creep/.test(q('karaoke-audience-chyron').textContent), 'the up-next bar shows the next singer and song before play: ' + q('karaoke-audience-chyron').textContent.slice(0, 80));
await send(ch, { song_playing: false, current_singer: { ...ann, duration_seconds: 200 }, mode: 'karaoke' }, {}); await wait(400);
ok(!!q('karaoke-audience-singer') && /Ann/.test(q('karaoke-audience-singer').textContent), 'a chosen singer is shown by name BEFORE the song is started: ' + ((q('karaoke-audience-singer') || {}).textContent || '(nothing)').slice(0, 60));
ok(!playing(), 'and the video does not start until the host presses play');

// 8. the next song is warmed in a hidden iframe, never the one that is playing
pre = { singer_id: 's2', embed_url: bob.embed_url, ready: false, percent: 0 };
await send(ch, { song_playing: true, current_singer: { ...ann, duration_seconds: 200 }, mode: 'karaoke' }); await wait(3000);
ok(!!warm() && /BBB222/.test(warm().src) && /mute=1/.test(warm().src) && /autoplay=0/.test(warm().src), 'the next song is warmed muted, not autoplaying: ' + ((warm() || {}).src || '(none)'));
ok(playing() && /AAA111/.test(playing().src), 'while the current song plays on');
pre = { singer_id: 's1', embed_url: ann.embed_url, ready: false, percent: 0 }; await wait(3000);
ok(!warm(), 'a "next" that is the SAME video as the one playing is never warmed (no second copy)');

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke audience: checks ok');
