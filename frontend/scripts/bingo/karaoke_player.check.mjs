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
  if (u.endsWith('/request-info')) return { data: { url: 'http://192.168.1.5:8001/karaoke/request' } };
  if (u.endsWith('/filler/folders')) { if (!S.fillerOk) throw new Error('x'); return { data: { ok: true, folders: S.folders, tracks: S.tracks.length } }; }
  if (u.endsWith('/filler/tracks')) { if (!S.fillerOk) { const e = new Error('404'); e.response = { status: 404 }; throw e; } const f = (cfg && cfg.params && cfg.params.folder) || ''; return { data: { tracks: f ? S.tracks.filter(t => t.artist === f) : S.tracks } }; }
  if (u.endsWith('/karaoke/queue')) return { data: { queue: S.queue.filter(e => e.status !== 'done') } };
  if (u.endsWith('/requests/pending')) return { data: { requests: S.requests.filter(r => r.status === 'pending') } };
  if (u.endsWith('/session/playback')) return { data: { playback: S.pb, preload: S.preload } };
  if (u.endsWith('/youtube/search')) {
    if (S.searchFails) { const e = new Error('x'); e.response = { data: { detail: 'No YouTube key saved. Add it in Karaoke Setup.' } }; throw e; }
    return { data: { results: [{ id: 'vid1', title: 'Africa - Karaoke', artist: 'KaraFun', source: 'youtube', duration_seconds: 245, embed_url: 'https://www.youtube.com/embed/vid1?autoplay=1', thumbnail: '' }] } };
  }
  return { data: {} };
};
axios.post = async (u, body) => {
  S.posts.push({ u: u.replace('http://x/api/karaoke', ''), body });
  if (u.endsWith('/session/playback')) { S.rev += 1; const same = S.pb.current_singer && body.current_singer && S.pb.current_singer.id === body.current_singer.id; S.pb = { ...body, rev: S.rev, audience_started: same ? S.pb.audience_started : false, audience_time: same ? S.pb.audience_time : 0, audience_duration: same ? S.pb.audience_duration : 0, video_ended: same ? S.pb.video_ended : false }; return { data: { success: true, rev: S.rev } }; }
  if (u.endsWith('/session/preload')) { S.preload = body.singer_id ? { singer_id: body.singer_id, embed_url: body.embed_url, ready: false } : null; return { data: { success: true } }; }
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
await click('karaoke-overlay-toggle'); await click('karaoke-qr-toggle-btn');
ok(S.posts.some(p => p.u === '/session/overlay' && p.body.overlay_enabled === false), 'overlay toggle is saved');
ok(S.posts.some(p => p.u === '/session/overlay' && p.body.qr_enabled === false), 'QR toggle is saved');
await click('karaoke-audience-btn');
ok(opened.length === 1 && /\/karaoke\/audience$/.test(opened[0]), 'Audience View opens the TV window');
cleanup();

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
// right click -> give to Ann
await act(async () => { fireEvent.contextMenu(q('karaoke-result-vid1'), { clientX: 10, clientY: 10 }); });
ok(!!q('karaoke-context-menu') && /Give this song to/.test(q('karaoke-context-menu').textContent), 'right-clicking a song opens the give-to menu');
await act(async () => { fireEvent.click(q('karaoke-assign-' + S.queue[0].id)); await new Promise(r => setTimeout(r, 200)); });
ok(S.queue[0].song_title === 'Africa - Karaoke' && /vid1/.test(S.queue[0].embed_url), 'the song is given to that singer');
// drag a song onto Bob
const dt = { data: {}, setData(k, v) { this.data[k] = v; }, getData(k) { return this.data[k] || ''; } };
fireEvent.dragStart(q('karaoke-result-vid1'), { dataTransfer: dt });
await act(async () => { fireEvent.drop(q('karaoke-queue-' + S.queue[1].id), { dataTransfer: dt }); await new Promise(r => setTimeout(r, 200)); });
ok(S.queue[1].song_title === 'Africa - Karaoke', 'dragging a song onto a singer gives it to them');
// reorder by dragging Bob above Ann
const dt2 = { data: {}, setData(k, v) { this.data[k] = v; }, getData(k) { return this.data[k] || ''; } };
fireEvent.dragStart(q('karaoke-queue-' + S.queue[1].id), { dataTransfer: dt2 });
await act(async () => { fireEvent.drop(q('karaoke-queue-' + S.queue[0].id), { dataTransfer: dt2 }); await new Promise(r => setTimeout(r, 200)); });
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
ok(q('karaoke-next-singer-btn').disabled && /Loading Ann/.test(q('karaoke-next-singer-btn').textContent), 'Next Singer stays locked while the audience has NOT said it loaded: ' + q('karaoke-next-singer-btn').textContent);
ok(!!q('karaoke-start-anyway-btn'), 'a "Start anyway" way out is offered so the night is never stuck');
S.preload.ready = true; await wait(1500);
ok(!q('karaoke-next-singer-btn').disabled && /Next Singer: Ann/.test(q('karaoke-next-singer-btn').textContent), 'the moment the AUDIENCE reports the video loaded, Next Singer opens');
// start filler first so we can hear it fade
await click('karaoke-tab-filler'); await click('karaoke-track-0'); await click('karaoke-tab-karaoke'); await wait(300);
heard.length = 0; audioLog.length = 0;
await click('karaoke-next-singer-btn'); await wait(300);
ok(/Ann/.test(q('karaoke-current-name').textContent), 'Ann is now singing');
ok(S.pb.song_playing === true && S.pb.current_singer.singer_name === 'Ann' && S.pb.mode === 'karaoke', 'the audience is told: Ann, playing, karaoke mode');
ok(heard.some(m => m.type === 'karaoke-state' && m.pb.current_singer && m.pb.current_singer.singer_name === 'Ann' && typeof m.pb.rev === 'number' && m.pb.rev === S.rev), 'the instant message carries the SAME revision number the server holds');
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
ok(!!q('karaoke-filler-tab'), 'the host is back on the Filler tab');
ok(audioLog.some(l => l.startsWith('play:')), 'filler music starts again after the song');
// only ONE finish even though the audience keeps saying ended
const finishes = S.posts.filter(p => p.u === '/queue/finish-current').length;
await wait(2200);
ok(S.posts.filter(p => p.u === '/queue/finish-current').length === finishes && finishes === 1, 'the end of a song is handled exactly once (' + finishes + ')');
cleanup();

// ---------- 7. End Song button fades 3 s then ends
fresh(); S.queue = [entry('Ann', 'Africa', 'https://www.youtube.com/embed/AAA111?autoplay=1')];
app(); await wait(400); await click('karaoke-tab-karaoke'); await wait(300);
await click('karaoke-start-anyway-btn'); await wait(300);
await click('karaoke-next-singer-btn'); await wait(100);
ok(/Ann/.test((q('karaoke-current-name') || {}).textContent || ''), 'start-anyway let the host start the singer');
await click('karaoke-end-song-btn');
ok(S.pb.song_ending === true && S.pb.current_singer && S.pb.current_singer.singer_name === 'Ann', 'End Song first tells the TV to fade (singer still on screen)');
await wait(3300);
ok(S.pb.current_singer === null && !q('karaoke-now-singing') && !!q('karaoke-filler-tab'), 'then, 3 seconds later, the song is over and the host is back on Filler');
cleanup();

// ---------- 8. end the night
fresh(); app(); await wait(400);
const ended = []; audience.onmessage = (e) => ended.push(e.data);
await click('karaoke-end-night-btn'); await wait(200);
ok(S.session.is_active === false && !!q('lobby') && ended.some(m => m.ended), 'End the night closes the session, tells the TV, and returns to the lobby');
cleanup();

audience.close();
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke player: checks ok');
process.exit(0);
