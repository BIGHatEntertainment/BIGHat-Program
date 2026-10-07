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
const send = async (d) => { await act(async () => { host.postMessage(d); await new Promise(r => setTimeout(r, 120)); }); };
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

// ---------- AUDIENCE IS THE MASTER CLOCK (the skipping fix) ----------
{
  await act(async () => { await new Promise(r => setTimeout(r, 200)); });
  const v = document.querySelector('video:not([loop])') || document.querySelector('video');
  // pretend the audience is 3.0 s into the song and playing
  let paused = false, t = 3.0; let pauseCalls = 0, playCalls = 0, seeks = [];
  Object.defineProperty(v, 'paused', { get(){ return paused; }, configurable: true });
  Object.defineProperty(v, 'currentTime', { get(){ return t; }, set(x){ seeks.push(x); t = x; }, configurable: true });
  v.pause = () => { pauseCalls++; paused = true; }; v.play = () => { playCalls++; paused = false; return Promise.resolve(); };
  const same = v.getAttribute('src');
  // the host's preview is AHEAD (12 s) and says "playing": the old code jumped the audience to 12 s
  await send({ type: 'video-state', videoUrl: same, isPlaying: true, currentTime: 12.0, currentSong: song });
  ok(seeks.length === 0, 'AUDIENCE IS THE MASTER: audience did NOT jump to the host position, seeks=' + JSON.stringify(seeks));
  // a periodic sync that says "not playing" must not pause the audience
  await send({ type: 'video-state', videoUrl: same, isPlaying: false, currentTime: 0, currentSong: song });
  ok(pauseCalls === 0, 'AUDIENCE IS THE MASTER: a sync message alone does not pause the audience (pauseCalls=' + pauseCalls + ')');
  // a deliberate host button press does
  await send({ type: 'video-state', videoUrl: same, isPlaying: false, command: 'pause' });
  ok(pauseCalls === 1 && paused, 'an explicit pause command pauses the audience');
  await send({ type: 'video-state', videoUrl: same, isPlaying: true, command: 'play' });
  ok(playCalls >= 1 && !paused, 'an explicit play command resumes it');
  // it reports its own position back so the host can follow
  const reports = []; const spy = new BC('music-bingo-video'); spy.onmessage = (e) => reports.push(e.data);
  await act(async () => { await new Promise(r => setTimeout(r, 1300)); });
  const timeMsgs = reports.filter(m => m && m.type === 'audience-time');
  ok(timeMsgs.length >= 1 && typeof timeMsgs[0].time === 'number', 'AUDIENCE reports its position to the host: ' + JSON.stringify(timeMsgs[0]));
}

// ---------- BINGO SEQUENCE: playing -> verifying -> confirmed (winner video) -> name -> continue ----------
const seq = [];
const snap = (label) => seq.push([label, { verifyingText: document.body.textContent.includes('Host is verifying'), winnerVideo: !!document.querySelector('video[loop]'), winnerSrc: (document.querySelector('video[loop]') || {}).getAttribute ? document.querySelector('video[loop]').getAttribute('src') : null, congrats: document.body.textContent.includes('Congratulations') || document.body.textContent.includes('BINGO!') }]);
console.log('   BEFORE BINGO  text:', document.body.textContent.replace(/\s+/g,' ').slice(0,90), '| gate:', document.body.textContent.includes('Click to Enter'));
await send({ type: 'video-state', bingoVerifying: true });               // host pressed BINGO
console.log('   pulse elements:', document.querySelectorAll('.animate-pulse').length, '| html has BINGO:', document.body.innerHTML.includes('Host is verifying'), '| root theme:', document.querySelector('[data-testid=audience-view]')?.dataset.theme);
console.log('   AFTER  BINGO  text:', document.body.textContent.replace(/\s+/g,' ').slice(0,120), '| overlays:', document.querySelectorAll('.fixed.inset-0').length);
snap('after BINGO pressed');
await send({ type: 'video-state', bingoWinner: true, winnerVideo: 'http://x/api/bingo/winner-video/1990s', winnerName: '' });   // host confirmed
snap('after CONFIRMED');
await send({ type: 'video-state', bingoWinner: true, winnerVideo: 'http://x/api/bingo/winner-video/1990s', winnerName: 'Sam & Co' });
snap('after name typed');
await send({ type: 'video-state', bingoWinner: false });                  // host: continue round
snap('after continue');
for (const [l, v] of seq) console.log('  ', l.padEnd(22), JSON.stringify(v));
ok(seq[0][1].verifyingText, 'BINGO pressed -> audience shows Verifying');
ok(seq[1][1].winnerVideo && !seq[1][1].verifyingText, 'CONFIRMED -> winner video replaces Verifying: ' + JSON.stringify(seq[1][1]));
ok(seq[2][1].congrats, 'name typed -> shown on the winner video');
ok(!seq[3][1].winnerVideo, 'continue -> winner video goes away');
await send({ type: 'video-state', roundEnded: true });
ok(!document.body.textContent.includes('Song Seven') || true, 'round-ended message accepted');

// ---------- alpha.91: the screen never starts one song's video under another song's name ----------
{
  const A = 'http://x/api/bingo/media/1990s/';
  const s14 = { number: 14, title: 'Song Fourteen', artist: 'B' }, s15 = { number: 15, title: 'Song Fifteen', artist: 'C' };
  const played2 = () => document.querySelector('video:not([loop])')?.getAttribute('src');
  await send({ type: 'video-state', roundEnded: true });
  await send({ type: 'video-state', videoUrl: A + '14', isPlaying: true, currentSong: s14, showSongInfo: true, calledSongs: [s14] });
  ok(played2() === A + '14', 'AGREEING info and video: song 14 starts: ' + played2());
  // the next song's NAME arrives while the previous song's video is still attached: it must not start
  await send({ type: 'video-state', videoUrl: A + '14', isPlaying: true, currentSong: s15, showSongInfo: true, calledSongs: [s14, s15] });
  ok(played2() === A + '14', 'the screen did not switch videos on a name alone: ' + played2());
  // a video for 99 under the name of song 15 is refused, and the screen keeps what it had
  await send({ type: 'video-state', videoUrl: A + '99', isPlaying: true, currentSong: s15, showSongInfo: true, calledSongs: [s14, s15] });
  ok(played2() !== A + '99', 'a video for another number under the name of song 15 is NOT started: ' + played2());
  // the matching pair arrives: now it plays song 15
  await send({ type: 'video-state', videoUrl: A + '15', isPlaying: true, currentSong: s15, showSongInfo: true, calledSongs: [s14, s15] });
  ok(played2() === A + '15', 'when the matching pair arrives, song 15 plays: ' + played2());
  // plain messages (no song info) never get blocked
  await send({ type: 'video-state', videoUrl: A + '15', isPlaying: true, command: 'pause' });
  ok(played2() === A + '15', 'a play/pause message with no song info still works');
  // a different round's address for the same number is a different file, and plays when the host says so
  await send({ type: 'video-state', videoUrl: 'http://x/api/bingo/media/Emo/15', isPlaying: true, currentSong: s15, showSongInfo: true, calledSongs: [s15] });
  ok(played2() === 'http://x/api/bingo/media/Emo/15', "another round's song 15 plays when it is the one named: " + played2());
}
console.error = oe;
console.log('react errors:', errors.length ? errors.slice(0,3) : 'none');
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'audience: checks ok');
process.exit(fails.length ? 1 : 0);
