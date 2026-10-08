// alpha.70: Karaoke HOST player - tabs, filler, queue, search, QR requests, and following the AUDIENCE clock
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/karaoke/player', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage','DataTransfer']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.BroadcastChannel = (await import('node:worker_threads')).BroadcastChannel;
// fake audio: records what the player does to it
const audioLog = [];
dom.window.HTMLMediaElement.prototype.play = function () { audioLog.push('play:' + this.src.split('/').slice(-2).join('/')); this._playing = true; return Promise.resolve(); };
dom.window.HTMLMediaElement.prototype.pause = function () { audioLog.push('pause'); this._playing = false; this.dispatchEvent(new dom.window.Event('pause')); };
globalThis.AudioContext = class { createMediaElementSource() { return { connect() {} }; } createGain() { const g = { gain: { value: 1 }, connect() {} }; globalThis.__gain = g; return g; } };
dom.window.AudioContext = globalThis.AudioContext;
globalThis.confirm = dom.window.confirm = () => true;
let promptAnswer = 'Walk-up Wendy'; dom.window.prompt = () => promptAnswer;
const opened = []; dom.window.open = (u) => { opened.push(u); return { closed: false, focus() {} }; };

const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
let reachedEnd = false;
process.on('exit', () => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

// ---------------- fake server
let S;
const fresh = () => {
  S = {
    session: { id: 'sess', location: 'Pub One', host: 'Pat', is_active: true, qr_enabled: true, overlay_enabled: true, filler_folder: '' },
    folders: [{ name: 'ABBA', tracks: 2 }, { name: 'Queen', tracks: 1 }],
    tracks: [{ id: 'ABBA/SOS.mp3', name: 'SOS.mp3', artist: 'ABBA' }, { id: 'ABBA/Waterloo.mp3', name: 'Waterloo.mp3', artist: 'ABBA' }, { id: 'Queen/Radio.mp3', name: 'Radio.mp3', artist: 'Queen' }],
    queue: [], requests: [], pb: { song_playing: false, current_singer: null, mode: 'filler' }, preload: null, rev: 0,
    posts: [], deletes: [], fillerOk: true, searchFails: false, nextId: 1,
  };
};
fresh();
const entry = (name, song = '', url = '') => ({ id: 'e' + (S.nextId++), singer_name: name, song_title: song, song_artist: '', embed_url: url, status: 'waiting', position: S.queue.length, duration_seconds: 200 });
axios.get = async (u, cfg) => {
  if (u.endsWith('/session/active')) return { data: { session: S.session } };
  if (u.endsWith('/request-info')) return { data: globalThis.__reqInfo || { url: 'http://192.168.1.5:8001/karaoke/request', phone_reachable: false } };
  if (u.endsWith('/filler/folders')) { if (!S.fillerOk) throw new Error('x'); return { data: { ok: true, folders: S.folders, tracks: S.tracks.length } }; }
  if (u.endsWith('/filler/tracks')) { if (!S.fillerOk) { const e = new Error('404'); e.response = { status: 404 }; throw e; } const f = (cfg && cfg.params && cfg.params.folder) || ''; return { data: { tracks: f ? S.tracks.filter(t => t.artist === f) : S.tracks } }; }
  if (u.endsWith('/karaoke/queue')) return { data: { queue: S.queue.filter(e => e.status !== 'done') } };
  if (u.endsWith('/requests/pending')) return { data: { requests: S.requests.filter(r => r.status === 'pending') } };
  if (u.endsWith('/session/playback')) return { data: { playback: S.pb, preload: S.preload } };
  const chk = /\/youtube\/check\/([A-Za-z0-9_-]+)$/.exec(u);
  if (chk) { (S.checks ||= []).push(chk[1]); if (S.checkDown) { const e = new Error('offline'); throw e; } return { data: S.checkAnswers && S.checkAnswers[chk[1]] || { known: true, playable: true, reason: '' } }; }
  if (u.endsWith('/youtube/search')) {
    if (S.searchFails) { const e = new Error('x'); e.response = { data: { detail: 'No YouTube key saved. Add it in Karaoke Setup.' } }; throw e; }
    return { data: { results: [{ id: 'vid1', title: 'Africa - Karaoke', artist: 'KaraFun', source: 'youtube', duration_seconds: 245, embed_url: 'https://www.youtube.com/embed/vid1AAAAAAA?autoplay=1', thumbnail: '' }] } };
  }
  return { data: {} };
};
axios.post = async (u, body) => {
  S.posts.push({ u: u.replace('http://x/api/karaoke', ''), body });
  if (u.endsWith('/session/playback')) { S.rev += 1; const same = S.pb.current_singer && body.current_singer && S.pb.current_singer.id === body.current_singer.id; S.pb = { ...body, rev: S.rev, audience_started: same ? S.pb.audience_started : false, audience_time: same ? S.pb.audience_time : 0, audience_duration: same ? S.pb.audience_duration : 0, video_ended: same ? S.pb.video_ended : false }; return { data: { success: true, rev: S.rev } }; }
  if (u.endsWith('/session/preload')) { (S.preloadPosts ||= []).push(body); S.preload = body.singer_id ? { singer_id: body.singer_id, embed_url: body.embed_url, ready: false } : null; return { data: { success: true } }; }
  if (u.endsWith('/queue/add')) {
    if (body.assign_to) { const e = S.queue.find(x => x.id === body.assign_to); Object.assign(e, { song_title: body.song_title, song_artist: body.song_artist, embed_url: body.embed_url, duration_seconds: body.duration_seconds }); return { data: { success: true } }; }
    const e = entry(body.singer_name, body.song_title, body.embed_url); S.queue.push(e); return { data: { success: true, entry: e } };
  }
  if (u.endsWith('/queue/next')) {
    const cur = S.queue.find(e => e.status === 'current'); if (cur) { cur.status = 'waiting'; cur.song_title = ''; cur.embed_url = ''; cur.position = 99; }
    const nxt = S.queue.filter(e => e.status === 'waiting').sort((a, b) => a.position - b.position)[0];
    if (nxt) { nxt.status = 'current'; return { data: { success: true, current: nxt } }; } return { data: { success: true, current: null } };
  }
  if (u.endsWith('/queue/finish-current')) { const cur = S.queue.find(e => e.status === 'current'); if (cur) { cur.status = 'waiting'; cur.song_title = ''; cur.embed_url = ''; cur.position = 99; } return { data: { success: true } }; }
  if (u.endsWith('/queue/reorder')) { body.order.forEach((id, i) => { S.queue.find(e => e.id === id).position = i; }); S.queue.sort((a, b) => a.position - b.position); return { data: { success: true } }; }
  if (u.includes('/requests/') && u.endsWith('/accept')) { const id = u.split('/requests/')[1].split('/')[0]; const r = S.requests.find(x => x.id === id); r.status = 'accepted'; S.queue.push(entry(r.singer_name, r.song_title)); return { data: { success: true } }; }
  if (u.includes('/requests/') && u.endsWith('/reject')) { const id = u.split('/requests/')[1].split('/')[0]; S.requests.find(x => x.id === id).status = 'rejected'; return { data: { success: true } }; }
  if (u.endsWith('/session/end')) { S.session.is_active = false; return { data: { success: true } }; }
  return { data: { success: true } };
};
axios.delete = async (u) => { S.deletes.push(u); const id = u.split('/').pop(); S.queue = S.queue.filter(e => e.id !== id); return { data: { success: true } }; };

const { default: Player } = await import('/tmp/rtest/kplayer.bundle.mjs');
const app = () => render(React.createElement(MemoryRouter, { initialEntries: ['/karaoke/player'] },
  React.createElement(Routes, null,
    React.createElement(Route, { path: '/karaoke/player', element: React.createElement(Player) }),
    React.createElement(Route, { path: '/karaoke', element: React.createElement('div', { 'data-testid': 'lobby' }, 'LOBBY') }))));
const click = (id) => act(async () => { fireEvent.click(q(id)); await new Promise(r => setTimeout(r, 150)); });
const lastPb = () => S.pb;

// alpha.89: a dataTransfer that behaves like Chromium/WebView2 (the old fake returned anything for any key):
//  - getData only returns what setData wrote, for exactly that type
//  - the drop is only delivered when dragover accepted it (preventDefault)
//  - effectAllowed / dropEffect must be compatible, or the drop never fires
const realDT = () => ({ _d: {}, effectAllowed: 'uninitialized', dropEffect: 'none',
  setData(k, v) { this._d[String(k).toLowerCase()] = String(v); }, getData(k) { return this._d[String(k).toLowerCase()] || ''; },
  get types() { return Object.keys(this._d); } });
const compatible = (allowed, drop) => allowed === 'uninitialized' || allowed === 'all' || (allowed === 'copyMove' && (drop === 'copy' || drop === 'move')) || allowed.toLowerCase() === drop.toLowerCase();
// does a drag from `from` onto `to` really end in a drop, the way a browser decides it?
const realDrag = async (from, to) => {
  const dt = realDT();
  fireEvent.dragStart(from, { dataTransfer: dt });
  const over = new dom.window.Event('dragover', { bubbles: true, cancelable: true }); over.dataTransfer = dt;
  await act(async () => { to.dispatchEvent(over); });
  const accepted = over.defaultPrevented && compatible(dt.effectAllowed, dt.dropEffect);
  if (!accepted) return { dropped: false, dt };
  await act(async () => { fireEvent.drop(to, { dataTransfer: dt }); await new Promise(r => setTimeout(r, 200)); });
  return { dropped: true, dt };
};

// the audience screen, played by the test: it listens on the same channel and can report
const audience = new BroadcastChannel('karaoke-state'); const heard = []; audience.onmessage = (e) => heard.push(e.data);

// ---------- 1. opens on the Filler tab, no session -> back to the lobby
fresh(); S.session = null; app(); await wait(300);
ok(!!q('lobby'), 'no active session sends you back to the Karaoke lobby');
cleanup();

// ---------- 2. Filler tab
fresh(); app(); await wait(500);
ok(!!q('karaoke-player') && /Pub One/.test(q('karaoke-location-label').textContent), 'player opens and shows the location');
ok(!!q('karaoke-filler-tab'), 'opens on the Filler tab');
ok(!!q('karaoke-tab-filler') && !!q('karaoke-tab-karaoke'), 'has the Filler and Karaoke tabs');
ok(!document.body.textContent.includes('PartyTyme') && !document.body.textContent.includes('Stingray'), 'no PartyTyme / Stingray tabs (dropped on purpose)');
ok(/ABBA/.test(q('karaoke-filler-list').textContent) && /Queen/.test(q('karaoke-filler-list').textContent) && /SOS/.test(q('karaoke-filler-list').textContent), 'tracks are listed, grouped under their artist');
ok([...q('karaoke-filler-folder').options].map(o => o.textContent).join('|') === 'All folders|ABBA (2)|Queen (1)', 'folder switcher lists the folders');
await click('karaoke-track-1');
ok(audioLog.some(l => l === 'play:ABBA/Waterloo.mp3'), 'clicking a track plays it from the drive: ' + audioLog.join(','));
ok(/Waterloo/.test(q('karaoke-filler-now').textContent), 'Now Playing shows the track');
await click('karaoke-filler-next-btn');
ok(audioLog.some(l => l === 'play:Queen/Radio.mp3'), 'Next Song plays the next track');
await click('karaoke-filler-next-btn');
ok(audioLog[audioLog.length - 1] === 'play:ABBA/SOS.mp3', 'and wraps back to the first track');
// auto-play
const audioEl = q('karaoke-filler-audio');
const before = audioLog.length;
await act(async () => { audioEl.dispatchEvent(new dom.window.Event('ended')); }); await wait(100);
ok(audioLog.length === before, 'auto-play OFF: a finished track does not start another');
await click('karaoke-filler-autoplay-btn');
const idxBefore = audioLog.length;
await act(async () => { audioEl.dispatchEvent(new dom.window.Event('ended')); }); await wait(100);
ok(audioLog.length > idxBefore && /play:/.test(audioLog[audioLog.length - 1]), 'auto-play ON: a finished track starts the next one');
// shuffle
await click('karaoke-filler-shuffle-btn');
ok(document.querySelectorAll('[data-testid^="karaoke-track-"]').length === 3 && !/uppercase/.test(q('karaoke-filler-list').innerHTML.slice(0, 40)), 'shuffle gives a flat list of all tracks');
await click('karaoke-filler-shuffle-btn');
// volume: max master x filler = 150% via the gain node
fireEvent.change(q('karaoke-master-volume'), { target: { value: '1' } }); fireEvent.change(q('karaoke-filler-volume'), { target: { value: '1' } }); await wait(100);
ok(/150%/.test(q('karaoke-master-volume').parentElement.textContent), 'master volume shows up to 150%');
ok(Math.abs((globalThis.__gain && globalThis.__gain.gain.value) - 1.5) < 1e-9 && audioEl.volume === 1, 'over 100%: the audio is at full and the gain node boosts it to 1.5');
// folder switch
await act(async () => { fireEvent.change(q('karaoke-filler-folder'), { target: { value: 'Queen' } }); await new Promise(r => setTimeout(r, 250)); });
ok(document.querySelectorAll('[data-testid^="karaoke-track-"]').length === 1, 'choosing a folder shows only its tracks');
// overlay + QR + audience window
// alpha.95: the overlay and the QR are ALWAYS on, so there are no buttons for them
ok(!q('karaoke-overlay-toggle') && !q('karaoke-qr-toggle-btn'), 'no Overlay button and no QR button in the header');
ok(!S.posts.some(p => p.u === '/session/overlay'), 'nothing tries to switch the overlay or QR off');
await click('karaoke-audience-btn');
ok(opened.length === 1 && /\/karaoke\/audience$/.test(opened[0]), 'in a browser, Audience View opens the TV window as a pop-up');
cleanup();

// ---------- 2b. alpha.89: in the DESKTOP app the Audience View is a real native window (a pop-up never opens there)
globalThis.__fakeTauri = true; globalThis.__nativeOpens = []; globalThis.__nativeFocus = []; globalThis.__nativeClosed = []; globalThis.__nativeFails = null; opened.length = 0;
fresh(); app(); await wait(400);
await click('karaoke-audience-btn'); await wait(200);
ok(globalThis.__nativeOpens.length === 1, 'desktop: clicking Audience View opens ONE native window: ' + JSON.stringify(globalThis.__nativeOpens));
const no = globalThis.__nativeOpens[0] || {};
ok(no.label === 'karaoke-audience' && no.path === '/karaoke/audience', 'desktop: it is the karaoke-audience window pointing at /karaoke/audience');
ok(opened.length === 0, 'desktop: no pop-up is attempted (it would never open in the desktop app)');
await click('karaoke-audience-btn'); await wait(200);
ok(globalThis.__nativeOpens.length === 1 && globalThis.__nativeFocus.length === 1, 'desktop: clicking again just brings the same window forward, it does not open another');
cleanup();
// when the window cannot be made the host is TOLD, not left with a dead button
globalThis.__nativeOpens = []; globalThis.__nativeFails = 'window create failed'; globalThis.__toasts = [];
fresh(); app(); await wait(400);
await click('karaoke-audience-btn'); await wait(200);
ok((globalThis.__toasts || []).some(t => /could not open/i.test(String(t[0])) && /window create failed/.test(String(t[0]))), 'desktop: a failure shows the host a plain message with the reason: ' + JSON.stringify(globalThis.__toasts));
cleanup();
globalThis.__fakeTauri = false; globalThis.__nativeFails = null;

// ---------- 3. drive unplugged
fresh(); S.fillerOk = false; app(); await wait(500);
ok(/Plug in the external drive/.test((q('karaoke-filler-note') || {}).textContent || ''), 'unplugged drive shows a plug-it-in note on the Filler tab');
S.fillerOk = true; await click('karaoke-filler-reload-btn'); await wait(250);
ok(!q('karaoke-filler-note') && document.querySelectorAll('[data-testid^="karaoke-track-"]').length === 3, 'Reload finds the music once the drive is back');
cleanup();

// ---------- 4. Karaoke tab: queue, search, assign
fresh(); app(); await wait(400);
await click('karaoke-tab-karaoke');
ok(!!q('karaoke-karaoke-tab') && /No one singing/.test(q('karaoke-no-singer').textContent), 'Karaoke tab opens with no one singing');
for (const n of ['Ann', 'Bob']) { await act(async () => { fireEvent.change(q('karaoke-add-singer-input'), { target: { value: n } }); fireEvent.click(q('karaoke-add-singer-btn')); await new Promise(r => setTimeout(r, 150)); }); }
await wait(300);
ok(S.queue.length === 2 && /Ann/.test(q('karaoke-queue').textContent) && /Bob/.test(q('karaoke-queue').textContent), 'singers are added to the queue');
ok(/Pick a song for Ann/.test(q('karaoke-next-singer-btn').textContent) && q('karaoke-next-singer-btn').disabled, 'Next Singer says to pick a song first and is disabled');
// search
await act(async () => { fireEvent.change(q('karaoke-song-search'), { target: { value: 'africa' } }); await new Promise(r => setTimeout(r, 700)); });
ok(!!q('karaoke-result-vid1') && /Africa - Karaoke/.test(q('karaoke-result-vid1').textContent) && /4:05/.test(q('karaoke-result-vid1').textContent), 'search shows results with their length (4:05)');
// alpha.92: the "Give to..." button is gone: songs are given by dragging onto a singer (or right-click)
ok(!q('karaoke-give-vid1') && !/Give to\.\.\./.test(q('karaoke-results').textContent), 'there is no "Give to..." button on the songs any more');
// right click -> give to Ann
await act(async () => { fireEvent.contextMenu(q('karaoke-result-vid1'), { clientX: 10, clientY: 10 }); });
ok(!!q('karaoke-context-menu') && /Give this song to/.test(q('karaoke-context-menu').textContent), 'right-clicking a song opens the give-to menu');
await act(async () => { fireEvent.click(q('karaoke-assign-' + S.queue[0].id)); await new Promise(r => setTimeout(r, 200)); });
ok(S.queue[0].song_title === 'Africa - Karaoke' && /vid1/.test(S.queue[0].embed_url), 'the song is given to that singer');
// alpha.92: POINTER drag (does not use the browser's own drag events). jsdom has no layout, so rows get boxes by position.
const rowsBox = () => { const list = q('karaoke-queue'); [...list.children].forEach((r, i) => { r.__box = { top: 100 + i * 50, bottom: 140 + i * 50 }; }); };
dom.window.document.elementFromPoint = (x, y) => {
  const rows = [...dom.window.document.querySelectorAll('[data-drop-singer]')];
  return rows.find(r => r.__box && y >= r.__box.top && y <= r.__box.bottom) || dom.window.document.body;
};
const pdrag = async (from, to, points) => {          // press on `from`, move through y values, release
  const ev = (type, x, y) => new dom.window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 });
  const pev = (type, x, y) => { const e = ev(type, x, y); Object.defineProperty(e, 'pointerId', { value: 1 }); return e; };
  await act(async () => { from.dispatchEvent(pev('pointerdown', 50, 50)); });
  for (const y of points) await act(async () => { dom.window.dispatchEvent(pev('pointermove', 60, y)); await new Promise(r => setTimeout(r, 20)); });
  await act(async () => { dom.window.dispatchEvent(pev('pointerup', 60, points[points.length - 1])); await new Promise(r => setTimeout(r, 250)); });
};
rowsBox();
// a tiny movement is a click, not a drag
const tiny = JSON.stringify(S.queue.map(e => e.song_title));
const orderBefore = S.queue.map(e => e.singer_name).join(',');
await act(async () => { q('karaoke-queue-' + S.queue[1].id).dispatchEvent(Object.assign(new dom.window.MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 50, clientY: 160 }), { pointerId: 1 })); });
await act(async () => { dom.window.dispatchEvent(Object.assign(new dom.window.MouseEvent('pointermove', { bubbles: true, clientX: 52, clientY: 162 }), { pointerId: 1 })); });
ok(!q('karaoke-drag-chip'), 'a movement of a few pixels does not start a drag (no chip)');
await act(async () => { dom.window.dispatchEvent(Object.assign(new dom.window.MouseEvent('pointerup', { bubbles: true, clientX: 52, clientY: 162 }), { pointerId: 1 })); await new Promise(r => setTimeout(r, 250)); });
ok(S.queue.map(e => e.singer_name).join(',') === orderBefore && JSON.stringify(S.queue.map(e => e.song_title)) === tiny, 'a tiny movement is treated as a click, nothing changes');
// drag the song onto Bob (second row: y 150..190)
await act(async () => { q('karaoke-result-vid1').dispatchEvent(Object.assign(new dom.window.MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 50, clientY: 50 }), { pointerId: 1 })); });
await act(async () => { dom.window.dispatchEvent(Object.assign(new dom.window.MouseEvent('pointermove', { bubbles: true, clientX: 80, clientY: 90 }), { pointerId: 1 })); });
ok(!!q('karaoke-drag-chip') && /Africa/.test(q('karaoke-drag-chip').textContent), 'while dragging, a chip with the song name follows the pointer');
await act(async () => { dom.window.dispatchEvent(Object.assign(new dom.window.MouseEvent('pointermove', { bubbles: true, clientX: 80, clientY: 170 }), { pointerId: 1 })); });
await wait(80);
ok(/Drop to give/.test(q('karaoke-drag-chip').textContent) && /rgba\(34,\s*197,\s*94,\s*0\.28\)/.test(q('karaoke-queue-' + S.queue[1].id).getAttribute('style') || ''), 'the singer under the pointer lights up and the chip says "Drop to give"');
await act(async () => { dom.window.dispatchEvent(Object.assign(new dom.window.MouseEvent('pointerup', { bubbles: true, clientX: 80, clientY: 170 }), { pointerId: 1 })); await new Promise(r => setTimeout(r, 250)); });
ok(S.queue[1].song_title === 'Africa - Karaoke' && /vid1/.test(S.queue[1].embed_url), 'dragging a song onto a singer gives it to them');
ok(!q('karaoke-drag-chip'), 'the chip goes away after the drop');
// let go over empty space: nothing changes
S.queue.forEach((e) => { e.song_title = ''; e.embed_url = ''; });          // everyone empty, so a wrong hand-out shows
const none = JSON.stringify(S.queue.map(e => e.song_title));
await pdrag(q('karaoke-result-vid1'), null, [90, 150, 400, 410]);          // passes OVER a singer, then ends in empty space
ok(JSON.stringify(S.queue.map(e => e.song_title)) === none, 'letting go away from every singer gives the song to nobody');
// reorder: drag Bob (row 2) above Ann (row 1)
await pdrag(q('karaoke-queue-' + S.queue[1].id), null, [160, 130, 118]);
await wait(300);
ok(S.queue[0].singer_name === 'Bob', 'dragging a singer up reorders the queue: ' + S.queue.map(e => e.singer_name).join(','));
// search error
S.searchFails = true;
await act(async () => { fireEvent.change(q('karaoke-song-search'), { target: { value: 'zzz zzz' } }); await new Promise(r => setTimeout(r, 700)); });
ok(/Add it in Karaoke Setup/.test((q('karaoke-search-error') || {}).textContent || ''), 'no YouTube key: the search says to add it in Karaoke Setup');
S.searchFails = false;
cleanup();

// ---------- 5. QR requests
fresh(); app(); await wait(300); await click('karaoke-tab-karaoke');
S.requests = [{ id: 'r1', singer_name: 'Zed', song_title: 'Africa', song_artist: 'Toto', status: 'pending' }, { id: 'r2', singer_name: 'Yan', song_title: 'Creep', song_artist: '', status: 'pending' }];
await wait(4300);
ok(!!q('karaoke-requests') && /Zed/.test(q('karaoke-requests').textContent) && /Yan/.test(q('karaoke-requests').textContent), 'pending phone requests show up for the host');
await click('karaoke-accept-r1'); await wait(300);
ok(S.queue.some(e => e.singer_name === 'Zed' && e.song_title === 'Africa'), 'Accept puts the singer in the queue with their song');
await click('karaoke-reject-r2'); await wait(200);
ok(!S.queue.some(e => e.singer_name === 'Yan') && !/Yan/.test((q('karaoke-requests') || { textContent: '' }).textContent), 'Reject removes it and does not queue them');
cleanup();

// ---------- 6. A SONG: preload gate, start, follow the AUDIENCE clock, finish
fresh();
S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1'), entry('Bob', 'Creep', 'https://www.youtube.com/embed/BBB222?autoplay=1'), entry('Cy')];
app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(1500);
ok(S.preload && S.preload.singer_id === S.queue[0].id && S.preload.embed_url.includes('AAA111'), 'host tells the audience which song to load next');
// alpha.98 (user report): the next singer is available AT ONCE, like the prototype. No "loading 0%" gate, no Start anyway / Retry.
ok(!q('karaoke-next-singer-btn').disabled && /Next Singer: Ann/.test(q('karaoke-next-singer-btn').textContent), 'Next Singer is ready as soon as the singer has a song: ' + q('karaoke-next-singer-btn').textContent);
ok(!q('karaoke-buffer') && !q('karaoke-start-anyway-btn') && !q('karaoke-retry-load-btn'), 'there is no loading bar, no "Start anyway" and no "Retry loading" any more');
// start filler first so we can hear it fade
await click('karaoke-tab-filler'); await click('karaoke-track-0'); await click('karaoke-tab-karaoke'); await wait(300);
heard.length = 0; audioLog.length = 0;
await click('karaoke-next-singer-btn'); await wait(300);
ok(/Ann/.test(q('karaoke-current-name').textContent), 'Ann is now singing');
ok(S.pb.song_playing === true && S.pb.current_singer.singer_name === 'Ann' && S.pb.mode === 'karaoke', 'the audience is told: Ann, playing, karaoke mode');
// alpha.93: WHILE Ann sings, the next singer (Bob) is handed to the audience screen to load
await wait(1500);
ok(S.preload && S.preload.singer_id === S.queue.find(e => e.singer_name === 'Bob').id && /BBB222/.test(S.preload.embed_url), 'while Ann is singing, Bob (next up) is handed to the audience to preload');
ok(heard.some(m => m.type === 'karaoke-state' && m.pb.current_singer && m.pb.current_singer.singer_name === 'Ann' && typeof m.pb.rev === 'number' && m.pb.rev === S.rev), 'the instant message carries the SAME revision number the server holds');
ok('alpha.99: host sends the waiting singers to the TV in its state message', heard.some(m => m.type === 'karaoke-state' && Array.isArray(m.waiting) && m.waiting.some(w => w.singer_name === 'Bob')));
await wait(3400);
ok(audioLog.includes('pause'), 'filler music fades out and stops when the song starts');
// the host shows the AUDIENCE time, not its own count
S.pb = { ...S.pb, audience_started: true, audience_time: 61, audience_duration: 200 }; await wait(1300);
ok(/1:01/.test(q('karaoke-elapsed').textContent) && /on the TV/.test(q('karaoke-now-singing').textContent), 'host shows the AUDIENCE clock (1:01) and that it is on the TV');
ok(q('karaoke-progress').style.width === '31%', 'progress bar follows the audience: ' + q('karaoke-progress').style.width);
await wait(2000);
ok(/1:01/.test(q('karaoke-elapsed').textContent), 'the host does not tick on its own: with the audience stuck at 1:01 so is the host');
// deliberate pause
await click('karaoke-pause-song-btn');
ok(S.pb.song_playing === false && S.pb.current_singer.singer_name === 'Ann', 'pause is sent to the audience as a deliberate command');
await click('karaoke-pause-song-btn');
ok(S.pb.song_playing === true, 'play resumes');
// last 3 seconds, by the AUDIENCE clock
S.pb = { ...S.pb, audience_time: 198 }; await wait(1500);
ok(S.pb.song_ending === true, 'when the AUDIENCE gets to the last 3 seconds the host starts the fade');
// the audience says ended -> singer finished, filler returns, singer goes to the bottom
audioLog.length = 0; heard.length = 0;
S.pb = { ...S.pb, video_ended: true }; await wait(1600);
ok(!q('karaoke-now-singing') && S.queue.every(e => e.status !== 'current'), 'when the AUDIENCE reports the song ended, the singer is finished (nobody is current)');
ok(S.queue.find(e => e.singer_name === 'Ann').status === 'waiting' && S.queue.find(e => e.singer_name === 'Ann').song_title === '', 'Ann goes back in line with no song');
ok(S.pb.song_playing === false && S.pb.current_singer === null && S.pb.mode === 'filler', 'the audience is told to go back to the music view');
// alpha.96: the TV goes back to the music, but the HOST stays on the Karaoke tab to pick the next singer
ok(!q('karaoke-filler-tab') && !!q('karaoke-no-singer'), 'after the song the host STAYS on the Karaoke tab (is not thrown over to Filler)');
ok(audioLog.some(l => l.startsWith('play:')), 'filler music starts again after the song');
// only ONE finish even though the audience keeps saying ended
const finishes = S.posts.filter(p => p.u === '/queue/finish-current').length;
await wait(2200);
ok(S.posts.filter(p => p.u === '/queue/finish-current').length === finishes && finishes === 1, 'the end of a song is handled exactly once (' + finishes + ')');
cleanup();

// ---------- 7. End Song button fades 3 s then ends
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1')];
app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(300);
await click('karaoke-next-singer-btn'); await wait(100);
ok(/Ann/.test((q('karaoke-current-name') || {}).textContent || ''), 'the host starts the singer with one press');
await click('karaoke-end-song-btn');
ok(S.pb.song_ending === true && S.pb.current_singer && S.pb.current_singer.singer_name === 'Ann', 'End Song first tells the TV to fade (singer still on screen)');
await wait(3300);
ok(S.pb.current_singer === null && !q('karaoke-now-singing') && !q('karaoke-filler-tab') && !!q('karaoke-no-singer'), 'then, 3 seconds later, the song is over and the host STAYS on the Karaoke tab');
cleanup();

// ---------- 7b. alpha.96: a song the TV could not play is explained, and the host can pick another in one tap
fresh(); S.queue = [entry('Ann', 'Africa - Karaoke', 'https://www.youtube.com/embed/AAA111?autoplay=1'), entry('Bob', 'Hello', 'https://www.youtube.com/embed/BBB222?autoplay=1')]; app(); await wait(400);
await click('karaoke-tab-karaoke'); await wait(300);
await click('karaoke-next-singer-btn'); await wait(500);
ok(/Ann/.test((q('karaoke-current-name') || {}).textContent || ''), 'Ann is singing (setup for the failed-song test)');
ok(!q('karaoke-song-error'), 'no failure notice while the song plays fine');
S.pb = { ...S.pb, video_error: '101' }; await wait(1500);
ok(!!q('karaoke-song-error') && /could not play/i.test(q('karaoke-song-error').textContent), 'the TV could not play it: the host sees a notice');
ok(/does not allow it to be played/i.test((q('karaoke-song-error-why') || {}).textContent || ''), 'and it says WHY in plain words (the owner does not allow it): ' + ((q('karaoke-song-error-why') || {}).textContent || '(no notice)'));
ok(!!q('karaoke-song-error-pick-another'), 'there is a "Pick another song" button');
await click('karaoke-song-error-pick-another'); await wait(900);
ok(!q('karaoke-now-singing') && S.queue.find(e => e.singer_name === 'Ann').status === 'waiting' && S.queue.find(e => e.singer_name === 'Ann').song_title === '', 'one tap: Ann goes back in line with no song, nobody is stuck');
ok(!q('karaoke-filler-tab'), 'and the host stays on the Karaoke tab');
S.pb = { ...S.pb, video_error: '' };
cleanup();
fresh(); S.queue = [entry('Ann', 'Africa - Karaoke', 'https://www.youtube.com/embed/AAA111?autoplay=1')]; app(); await wait(400);
await click('karaoke-tab-karaoke'); await click('karaoke-next-singer-btn'); await wait(400);
S.pb = { ...S.pb, video_error: 'no_youtube' }; await wait(1500);
ok(/could not reach YouTube/i.test((q('karaoke-song-error-why') || {}).textContent || ''), 'if the TV cannot reach YouTube at all, it says that (not the video\'s fault)');
cleanup();

// ---------- 8. end the night
fresh(); app(); await wait(400);
const ended = []; audience.onmessage = (e) => ended.push(e.data);
await click('karaoke-end-night-btn'); await wait(200);
ok(S.session.is_active === false && !!q('lobby') && ended.some(m => m.ended), 'End the night closes the session, tells the TV, and returns to the lobby');
cleanup();

audience.close();

// ---------- alpha.82: the QR must be a link a PHONE can open (cloud relay)
{
  const goKaraoke = async () => { await click('karaoke-tab-karaoke'); await wait(300); };
  // a) relay link -> QR shows and encodes exactly that link
  fresh(); globalThis.__reqInfo = { url: 'https://api.bighat.live/k/ABCDEFGHIJKLMNOP', phone_reachable: true, online: true };
  app(); await wait(500); await goKaraoke();
  const qrBox = q('karaoke-host-qr');
  ok(!!qrBox, 'QR: shown when the cloud relay gave a phone-reachable link');
  ok(qrBox && qrBox.querySelector('svg') != null, 'QR: it is a real QR image');
  ok(!q('karaoke-qr-offline'), 'QR: no offline note while the link is ready');
  cleanup();
  // b) only the PC's own address -> NO QR (a phone cannot open it), and the host is told why
  fresh(); globalThis.__reqInfo = { url: 'http://192.168.1.5:8001/karaoke/request', phone_reachable: false, online: null };
  app(); await wait(500); await goKaraoke();
  ok(!q('karaoke-host-qr'), 'QR: NOT shown for a PC-only address (phones cannot open it)');
  ok(!!q('karaoke-qr-offline') && /internet connection/i.test(q('karaoke-qr-offline')?.textContent || ''), 'QR: host sees a plain note instead of a blank corner');
  ok(/by hand/i.test(q('karaoke-qr-offline')?.textContent || ''), 'QR: the note says songs can still be added by hand');
  cleanup();
  // c) alpha.95: even an old session saved with the QR "off" still shows it (it is always on)
  fresh(); S.session.qr_enabled = false; globalThis.__reqInfo = { url: 'https://api.bighat.live/k/ABCDEFGHIJKLMNOP', phone_reachable: true, online: true };
  app(); await wait(500); await goKaraoke();
  ok(!!q('karaoke-host-qr'), 'QR: an old session saved with the QR off still shows it');
  cleanup();
  // d) link becomes ready later (internet came back) -> QR appears by itself, no reload
  fresh(); globalThis.__reqInfo = { url: 'http://192.168.1.5:8001/karaoke/request', phone_reachable: false };
  app(); await wait(500); await goKaraoke();
  ok(!q('karaoke-host-qr'), 'QR: starts hidden while offline');
  globalThis.__reqInfo = { url: 'https://api.bighat.live/k/ZZZZZZZZZZZZZZZZ', phone_reachable: true, online: true };
  await act(async () => { await new Promise(r => setTimeout(r, 10500)); });
  ok(!!q('karaoke-host-qr') && !q('karaoke-qr-offline'), 'QR: appears on its own within ~10 s once the link is ready');
  cleanup();
  globalThis.__reqInfo = null;
}

// ---------- 7. alpha.89: the RIGHT side is the Audience Preview, then the Request QR, then the requests, then In Queue
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1'), entry('Bob')];
S.requests = [{ id: 'r1', singer_name: 'Zed', song_title: 'Africa', song_artist: 'Toto', status: 'pending' }];
globalThis.__reqInfo = { url: 'https://api.bighat.live/k/ABC', phone_reachable: true, online: true };
app(); await wait(400);
for (const tab of ['karaoke-tab-filler', 'karaoke-tab-karaoke']) {
  await click(tab); await wait(400);
  const panel = q('karaoke-right-panel');
  ok(!!panel, tab + ': the right panel is there');
  if (!panel) continue;
  const order = ['karaoke-preview', 'karaoke-qr-card', 'karaoke-requests', 'karaoke-queue-count'].map(id => panel.innerHTML.indexOf('data-testid="' + id + '"'));
  ok(order.every(i => i > -1), tab + ': panel has the preview, the request QR, the song requests and the queue count: ' + order.join(','));
  ok(order.every((v, i) => i === 0 || v > order[i - 1]), tab + ': and in that order, top to bottom: ' + order.join(','));
}
ok(!!q('karaoke-host-qr') && !!q('karaoke-host-qr').querySelector('svg'), 'the QR is a real code the phones can scan');
ok(/Zed/.test(q('karaoke-requests').textContent) && q('karaoke-requests-count').textContent.startsWith('1'), 'a pending phone request shows in Song Requests');
ok(q('karaoke-queue-count').textContent.trim() === '2', 'In Queue counts the singers who are waiting');
ok(!!q('karaoke-preview-idle'), 'with nobody singing the preview says it is waiting');
ok(!!q('karaoke-preview-open-audience'), 'and, with the TV screen closed, the preview offers to open it');
await act(async () => { fireEvent.click(q('karaoke-accept-r1')); await new Promise(r => setTimeout(r, 200)); });
ok(S.posts.some(p => /accept/.test(p.u)), 'Accept sends the request to the queue');
cleanup();
fresh(); S.queue = [entry('Ann')]; app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(300);
ok(!!q('karaoke-qr-card') && !!q('karaoke-preview'), 'the QR card and the preview are both on the host screen');
cleanup();
globalThis.__reqInfo = { url: '', phone_reachable: false, online: false };
fresh(); app(); await wait(400);
ok(/internet connection/i.test((q('karaoke-qr-offline') || {}).textContent || '') && !q('karaoke-host-qr'), 'with no link the QR card says why instead of showing a broken code');
cleanup();
globalThis.__reqInfo = null;

// ---------- 7c. alpha.99: a song YouTube will not embed is stopped when it is GIVEN to a singer, with the reason, instead of failing on the TV
const assignViaMenu = async (id) => {
  await act(async () => { fireEvent.contextMenu(q('karaoke-result-vid1'), { clientX: 10, clientY: 10 }); });
  await act(async () => { fireEvent.click(q('karaoke-assign-' + id)); await new Promise(r => setTimeout(r, 300)); });
};
const searchAfrica = async () => { await act(async () => { fireEvent.change(q('karaoke-song-search'), { target: { value: 'africa' } }); await new Promise(r => setTimeout(r, 700)); }); };
fresh(); S.queue = [entry('Ann')]; S.checks = []; S.checkAnswers = { vid1AAAAAAA: { known: true, playable: false, reason: 'The owner of this video does not allow it to be played outside YouTube.' } };
app(); await wait(400); await click('karaoke-tab-karaoke'); await searchAfrica();
const toasts = []; const sonner = (await import('sonner')).toast; const origErr = sonner.error; sonner.error = (m) => { toasts.push(String(m)); };
await assignViaMenu(S.queue[0].id);
ok(S.checks.includes('vid1AAAAAAA'), 'when a song is given to a singer, YouTube is asked about that video');
ok(S.queue[0].song_title === '' || !S.queue[0].song_title, 'a song YouTube says cannot play is NOT given to the singer');
ok(toasts.some(t => /does not allow it to be played outside YouTube/.test(t) && /Africa - Karaoke/.test(t)), 'the host is told which song and why: ' + (toasts[0] || '(no message)'));
cleanup();
// a playable song goes through and asks only once
fresh(); S.queue = [entry('Ann')]; S.checks = []; S.checkAnswers = {};
app(); await wait(400); await click('karaoke-tab-karaoke'); await searchAfrica(); await assignViaMenu(S.queue[0].id);
ok(S.queue[0].song_title === 'Africa - Karaoke' && S.checks.filter(c => c === 'vid1AAAAAAA').length === 1, 'a playable song is given to the singer (checked once)');
cleanup();
// the check cannot reach YouTube: the show is never blocked
fresh(); S.queue = [entry('Ann')]; S.checks = []; S.checkDown = true;
app(); await wait(400); await click('karaoke-tab-karaoke'); await searchAfrica(); await assignViaMenu(S.queue[0].id);
ok(S.queue[0].song_title === 'Africa - Karaoke', 'if the check cannot be made the song is still given (the show is never blocked)');
S.checkDown = false; sonner.error = origErr; cleanup();

// ---------- 7d. alpha.99: like the prototype, the HOST warms the next singer's song in a hidden muted iframe (never the playing one)
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1'), entry('Bob', 'Creep', 'https://www.youtube.com/embed/BBB222?autoplay=1')];
app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(600);
const hw = () => document.querySelector('[data-testid="karaoke-host-warm-iframe"]');
ok(!!hw() && /embed\/AAA111\?autoplay=0&mute=1&preload=auto/.test(hw().src), 'the host warms the first waiting singer\'s song, muted and not playing: ' + ((hw() || {}).src || '(none)'));
ok(hw() && hw().getAttribute('referrerpolicy') === 'strict-origin-when-cross-origin', 'the host warm-up iframe also asks for the referrer');
await click('karaoke-next-singer-btn'); await wait(900);
ok(!!hw() && /BBB222/.test(hw().src) && !/AAA111/.test(hw().src), 'once Ann is singing, the host warms Bob (the next one), never Ann\'s own song: ' + ((hw() || {}).src || '(none)'));
cleanup();
fresh(); S.queue = [entry('Ann')]; app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(500);
ok(!hw(), 'a singer with no song is not warmed');
cleanup();
// the SAME karaoke video chosen for two singers: while the first is singing it is NOT loaded a second time
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/SAMEvid1234?autoplay=1'), entry('Bob', 'Africa', 'https://www.youtube.com/embed/SAMEvid1234?autoplay=1')];
app(); await wait(400); await click('karaoke-tab-karaoke'); await click('karaoke-next-singer-btn'); await wait(900);
ok(/Ann/.test((q('karaoke-current-name') || {}).textContent || '') && !hw(), 'the same video for the next singer is not loaded a second time while it is playing');
cleanup();

// ---------- 8. alpha.98: the next singer is handed to the TV to warm, and NOTHING on the host can sit at "loading 0%"
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1'), entry('Bob')]; S.preloadPosts = [];
app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(1200);
ok(S.preloadPosts.some(p => p.singer_id === S.queue[0].id && /AAA111/.test(p.embed_url)), 'the host tells the TV which song is next so it can warm it');
ok(!q('karaoke-buffer') && !q('karaoke-start-anyway-btn') && !q('karaoke-retry-load-btn'), 'no loading bar and no loading buttons, even with the TV closed');
ok(!q('karaoke-next-singer-btn').disabled && /Next Singer: Ann/.test(q('karaoke-next-singer-btn').textContent), 'Next Singer is ready (no 0% lock) even though the TV never reported any progress');
S.preload = { singer_id: S.queue[0].id, error: 'youtube_error', percent: 0 }; await wait(1200);
ok(!q('karaoke-buffer') && !q('karaoke-next-singer-btn').disabled, 'a stale "could not load" report from the old preload cannot lock or hide anything');
await click('karaoke-next-singer-btn'); await wait(400);
ok(/Ann/.test((q('karaoke-current-name') || {}).textContent || ''), 'one press starts the singer');
ok(S.pb.song_playing === true && S.pb.current_singer && /AAA111/.test(S.pb.current_singer.embed_url), 'and the TV is told to play that song');
cleanup();
fresh(); S.queue = [entry('Ann')]; app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(800);
ok(q('karaoke-next-singer-btn').disabled && /Pick a song for Ann/.test(q('karaoke-next-singer-btn').textContent), 'a singer with NO song still says "Pick a song" and cannot start');
cleanup();

reachedEnd = true;
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke player: checks ok');
process.exit(0);
