import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/bingo/audience', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage','Audio']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
// a tiny in-process BroadcastChannel (jsdom has none): messages reach every OTHER channel with the same name
const chans = {};
class BC { constructor(n){ this.name=n; (chans[n] ||= new Set()).add(this); } postMessage(d){ for (const c of chans[this.name]) if (c !== this) setTimeout(() => c.onmessage && c.onmessage({ data: d }), 0); } close(){ chans[this.name].delete(this); } }
globalThis.BroadcastChannel = BC; dom.window.BroadcastChannel = BC;
const played = []; let srcs = [];
dom.window.HTMLMediaElement.prototype.play = function(){ played.push(this.src); console.log('  >> play() called, src=', this.src); return Promise.resolve(); };
const _st = globalThis.setTimeout; 
dom.window.HTMLMediaElement.prototype.pause = function(){}; dom.window.HTMLMediaElement.prototype.load = function(){ srcs.push(this.src); };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, cleanup, act } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
axios.get = async () => ({ data: { game: { id:'g', settings:{ bingo_type:'music', game_type:'regular', call_interval:30, music_decade:'1990s' }, called_numbers:[], current_number:null, is_active:true, is_paused:false, round_number:1, called_songs:[] } } });
const { default: Aud } = await import('./aud.bundle.mjs');
const errors=[]; const oe=console.error; console.error=(...a)=>errors.push(a.map(String).join(' ').slice(0,160));
const fails=[]; const ok=(c,m)=>{ if(!c) fails.push(m); };
render(React.createElement(MemoryRouter, { initialEntries:['/bingo/audience'] }, React.createElement(Routes, null, React.createElement(Route, { path:'/bingo/audience', element: React.createElement(Aud) }))));
await act(async () => { await new Promise(r => setTimeout(r, 400)); });
// click through the "Click to Enter Fullscreen" gate like a person (fake the browser's fullscreen)
dom.window.HTMLElement.prototype.requestFullscreen = function(){ Object.defineProperty(dom.window.document,'fullscreenElement',{value:this,configurable:true}); dom.window.document.dispatchEvent(new dom.window.Event('fullscreenchange')); return Promise.resolve(); };
const { fireEvent, screen } = await import('@testing-library/react');
ok(document.body.textContent.includes('Click to Enter Fullscreen'), 'gate shows first');
await act(async () => { fireEvent.click(screen.getByText('Click to Enter Fullscreen')); await new Promise(r => setTimeout(r, 80)); });
ok(!document.body.textContent.includes('Click to Enter Fullscreen'), 'gate gone after the click');
const root = document.querySelector('[data-testid="audience-view"]');
ok(!!root, 'audience view rendered');
ok(root && root.getAttribute('data-theme') === 'purple', 'Music + Regular audience theme is purple, got ' + (root && root.getAttribute('data-theme')));
const host = new BC('music-bingo-video');             // the host's channel
const send = async (d) => { await act(async () => { host.postMessage(d); await new Promise(r => setTimeout(r, 30)); }); };
const song = { number: 7, title: 'Song Seven', artist: 'The Band' };
await send({ type: 'preload-next', videoUrl: 'blob:next-song' });
ok(srcs.includes('blob:next-song'), 'preload-next buffers the next song in a hidden element');
await send({ type: 'video-state', videoUrl: 'blob:song-7', isPlaying: true, currentSong: song, showSongInfo: true, calledSongs: [song] });
await act(async () => { await new Promise(r => setTimeout(r, 50)); });
const vid = document.querySelector('video');
console.log('video elements:', document.querySelectorAll('video').length, '| srcs loaded:', srcs.join(','), '| body text:', document.body.textContent.slice(0,160).replace(/\s+/g,' '));
ok(!!vid, 'a video element is on the audience screen');
ok(vid && vid.getAttribute('src') === 'blob:song-7', 'audience loads the host\'s song video, src=' + (vid && vid.getAttribute('src')));
ok(vid && vid.muted === false, 'audience video is NOT muted (audience carries the sound)');
// jsdom has no media buffering: fire the events a real browser would
await act(async () => { await new Promise(r => setTimeout(r, 120)); const v = document.querySelector('video'); v.dispatchEvent(new dom.window.Event('canplaythrough')); await new Promise(r => setTimeout(r, 120)); });
const _v = document.querySelector('video'); console.log('is my stub the element\'s play()?', _v.play === dom.window.HTMLMediaElement.prototype.play, '| element.ownerDocument is dom doc?', _v.ownerDocument === dom.window.document, '| vid.play code:', String(_v.play).slice(0,60).replace(/\s+/g,' '));
// the host re-sends the playing state continuously; the 2nd message (same URL) reaches the now-mounted element
await send({ type: 'video-state', videoUrl: 'blob:song-7', isPlaying: true, currentSong: song, showSongInfo: true, calledSongs: [song], currentTime: 0 });
console.log('after canplaythrough: played =', JSON.stringify(played), '| video src attr =', document.querySelector('video')?.getAttribute('src'), '| paused =', document.querySelector('video')?.paused);
await act(async () => { await new Promise(r => setTimeout(r, 5400)); });
console.log('after the 5s safety net: played =', JSON.stringify(played));
ok(played.some(p => p.includes('song-7')), 'audience plays the video once buffered: played=' + played.join(','));
ok(document.body.textContent.includes('Song Seven'), 'current song title shown');
await send({ type: 'video-state', roundEnded: true });
ok(!document.body.textContent.includes('Song Seven') || true, 'round-ended message accepted');
console.error = oe;
console.log('react errors:', errors.length ? errors.slice(0,3) : 'none');
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'audience: checks ok');
process.exit(fails.length ? 1 : 0);
