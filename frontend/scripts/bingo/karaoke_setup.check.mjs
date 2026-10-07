// alpha.70: Karaoke Setup page + Karaoke lobby
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/karaoke', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','FormData','File','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.__locations = [{ id: 'l1', name: 'Pub One' }, { id: 'l2', name: 'Bar Two' }];
globalThis.__triviaEnv = { user: { id: 'me', name: 'Pat Q', role: 'master_admin', email: 'p@x' }, calls: [] };
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
const { default: KaraokeSetup } = await import('/tmp/rtest/ksetup.bundle.mjs');
const { default: KaraokeLobby } = await import('/tmp/rtest/klobby.bundle.mjs');
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 250) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

let server;
const fresh = () => {
  server = {
    setup: { folders: { root: 'C:\\Docs\\Karaoke', overlay: 'C:\\Docs\\Karaoke\\Master Overlay', logos: 'C:\\Docs\\Karaoke\\Venue Logos', songs: 'C:\\Docs\\Karaoke\\Song Library' },
      filler_folder: '', filler: { ok: false, error: 'no_folder', folders: [], tracks: 0 }, youtube_key_set: false, youtube_key_hint: '',
      overlay: { custom: false, size: [1920, 1080] } },
    filler: { ok: true, folders: [{ name: 'ABBA', tracks: 12 }, { name: 'Queen', tracks: 9 }], loose_tracks: 0, tracks: 21 },
    posts: [], deletes: [],
  };
};
fresh();
axios.get = async (u) => {
  if (/\/karaoke\/venue-logo-status\//.test(u)) return { data: { has_logo: decodeURIComponent(u.split('/venue-logo-status/')[1]) === 'Pub One' } };
  if (u.endsWith('/karaoke/setup')) return { data: server.setup };
  if (u.endsWith('/karaoke/filler/folders')) return { data: server.filler };
  if (u.endsWith('/native/locations')) return { data: [{ id: 'l1', name: 'Pub One' }, { id: 'l2', name: 'Bar Two' }] };
  return { data: {} };
};
axios.post = async (u, body) => {
  server.posts.push({ u, body });
  if (u.endsWith('/karaoke/setup/filler-scan')) return { data: body.filler_folder === 'E:\\Filler' ? server.filler : { ok: false, error: 'drive_missing', folders: [], tracks: 0 } };
  if (u.endsWith('/karaoke/setup')) { server.setup = { ...server.setup, filler_folder: body.filler_folder, youtube_key_set: !!body.youtube_api_key || server.setup.youtube_key_set, youtube_key_hint: body.youtube_api_key ? 'AIza...abcd' : server.setup.youtube_key_hint }; return { data: server.setup }; }
  if (u.endsWith('/karaoke/overlay/master')) { const f = body.get('file'); return { data: f.name === 'small.png' ? { saved: false, error: 'wrong_size', width: 1280, height: 720 } : { saved: true, width: 1920, height: 1080 } }; }
  if (u.includes('/karaoke/venue-logo/')) { const f = body.get('file'); return { data: f.name === 'tiny.png' ? { saved: false, error: 'too_small', width: 100, height: 100 } : { saved: true, width: 150, height: 150 } }; }
  if (u.endsWith('/karaoke/session/create')) return { data: { success: true, session: {} } };
  return { data: {} };
};
axios.delete = async (u) => { server.deletes.push(u); return { data: {} }; };

const app = (start) => render(React.createElement(MemoryRouter, { initialEntries: [start] },
  React.createElement(Routes, null,
    React.createElement(Route, { path: '/karaoke', element: React.createElement(KaraokeLobby) }),
    React.createElement(Route, { path: '/karaoke/setup', element: React.createElement(KaraokeSetup) }),
    React.createElement(Route, { path: '/karaoke/player', element: React.createElement('div', { 'data-testid': 'player-page' }, 'PLAYER') }),
    React.createElement(Route, { path: '/', element: React.createElement('div', { 'data-testid': 'home' }, 'HOME') }))));
const pick = (input, name) => {
  const f = new dom.window.File([new Uint8Array(100)], name, { type: 'image/png' });
  Object.defineProperty(input, 'files', { value: [f], configurable: true });
  return act(async () => { fireEvent.change(input); await new Promise(r => setTimeout(r, 200)); });
};

// ---------- LOBBY ----------
fresh(); app('/karaoke'); await wait(400);
ok(!!q('karaoke-lobby'), 'lobby opens');
ok(!!q('karaoke-setup-btn'), 'lobby has the Karaoke Setup button');
ok(!!q('karaoke-no-key-warning'), 'lobby warns when no YouTube key is saved');
const sel = q('karaoke-location');
ok(!!sel && [...sel.options].map(o => o.value).join() === ',Pub One,Bar Two', 'location drop-down lists the locations');
const fsel = q('karaoke-filler');
ok(!!fsel, 'filler music drop-down is in the main lobby');
ok([...fsel.options].map(o => o.textContent).join('|') === 'All folders (21 tracks)|ABBA (12)|Queen (9)', 'filler drop-down: All folders, then each folder with its count: ' + (fsel ? [...fsel.options].map(o => o.textContent).join('|') : ''));
// launch without a location is blocked
await act(async () => { fireEvent.click(q('karaoke-launch')); }); await wait();
ok(!server.posts.some(p => p.u.endsWith('/session/create')), 'cannot launch without a location');
// alpha.95: the venue's logo goes on the TV overlay, so the lobby tells the host if it is missing
ok(!q('karaoke-logo-status'), 'no logo message until a location is chosen');
await act(async () => { fireEvent.change(q('karaoke-location'), { target: { value: 'Bar Two' } }); await new Promise(r => setTimeout(r, 250)); });
ok(!!q('karaoke-logo-status') && /no logo yet/i.test(q('karaoke-logo-status').textContent) && !!q('karaoke-logo-setup-btn'), 'a venue WITHOUT a logo shows a warning and a button to load one');
if (q('karaoke-logo-setup-btn')) await act(async () => { fireEvent.click(q('karaoke-logo-setup-btn')); await new Promise(r => setTimeout(r, 200)); });
ok(!q('karaoke-lobby') && !!document.querySelector('[data-testid="karaoke-setup"], [data-testid="karaoke-setup-page"], [data-testid^="karaoke-overlay"], [data-testid^="karaoke-logo-upload"]'), 'the button goes to the Karaoke Setup screen');
cleanup(); fresh(); app('/karaoke'); await wait(400);
await act(async () => { fireEvent.change(q('karaoke-location'), { target: { value: 'Pub One' } }); await new Promise(r => setTimeout(r, 250)); });
ok(!!q('karaoke-logo-status') && /logo is loaded/i.test(q('karaoke-logo-status').textContent) && !q('karaoke-logo-setup-btn'), 'a venue WITH a logo says it is loaded, no warning');
// a missing logo never stops the night: Bar Two can still launch
await act(async () => { fireEvent.change(q('karaoke-location'), { target: { value: 'Bar Two' } }); await new Promise(r => setTimeout(r, 250)); });
await act(async () => { fireEvent.click(q('karaoke-launch')); await new Promise(r => setTimeout(r, 300)); });
ok(server.posts.some(p => p.u.endsWith('/session/create') && p.body.location === 'Bar Two'), 'a venue without a logo can still start the show');
cleanup(); fresh(); app('/karaoke'); await wait(400);
// pick and launch
await act(async () => { fireEvent.change(q('karaoke-location'), { target: { value: 'Pub One' } }); fireEvent.change(q('karaoke-filler'), { target: { value: 'ABBA' } }); });
ok(!q('karaoke-qr-toggle') && /always shown/i.test(q('karaoke-qr-note').textContent), 'there is no QR switch in the lobby: it says the QR is always shown');
await act(async () => { fireEvent.click(q('karaoke-launch')); await new Promise(r => setTimeout(r, 300)); });
const created = server.posts.find(p => p.u.endsWith('/session/create'));
ok(created && created.body.location === 'Pub One' && created.body.filler_folder === 'ABBA' && created.body.qr_enabled === undefined && created.body.host === 'Pat Q', 'launch sends location, host and chosen filler folder (no QR setting any more): ' + JSON.stringify(created && created.body));
ok(!!q('player-page'), 'launch goes to the player');
cleanup();

// drive unplugged
fresh(); server.filler = { ok: false, error: 'drive_missing', folders: [], tracks: 0 };
app('/karaoke'); await wait(400);
ok(!q('karaoke-filler') && /Plug in the external drive/.test((q('karaoke-filler-message') || {}).textContent || ''), 'unplugged drive shows a plug-it-in message, not a broken drop-down');
await act(async () => { fireEvent.change(q('karaoke-location'), { target: { value: 'Bar Two' } }); });
server.filler = { ok: true, folders: [{ name: 'Queen', tracks: 9 }], loose_tracks: 0, tracks: 9 };
await act(async () => { fireEvent.click(q('karaoke-filler-refresh-btn')); await new Promise(r => setTimeout(r, 250)); });
ok(!!q('karaoke-filler') && [...q('karaoke-filler').options].length === 2, 'Refresh finds the drive once it is plugged in');
await act(async () => { fireEvent.click(q('karaoke-launch')); await new Promise(r => setTimeout(r, 300)); });
ok(!!q('player-page'), 'can still launch with no filler chosen');
cleanup();

// setup button navigates
fresh(); app('/karaoke'); await wait(300);
await act(async () => { fireEvent.click(q('karaoke-setup-btn')); }); await wait();
ok(!!q('karaoke-setup-page'), 'Karaoke Setup button opens Karaoke Setup');
cleanup();

// ---------- SETUP PAGE ----------
fresh(); app('/karaoke/setup'); await wait(400);
ok(!!q('karaoke-setup-page'), 'setup page opens');
ok(/Master Overlay/.test(q('karaoke-folder-list').textContent) && /Venue Logos/.test(q('karaoke-folder-list').textContent), 'shows the created Karaoke folders');
ok(/BIG Hat overlay/.test(q('karaoke-overlay-section').textContent) && !q('karaoke-overlay-reset-btn'), 'default overlay is shown; no reset button yet');
ok(!!q('karaoke-overlay-preview') && /karaoke\/overlay\/master/.test(q('karaoke-overlay-preview').src), 'overlay preview comes from the backend');
// overlay: wrong size
await pick(q('karaoke-overlay-input'), 'small.png');
ok(/1920 x 1080.*1280 x 720/.test(q('karaoke-overlay-note').textContent), 'wrong-size overlay is refused with the real sizes: ' + q('karaoke-overlay-note').textContent);
// overlay: good
await pick(q('karaoke-overlay-input'), 'mine.png');
ok(/saved/i.test(q('karaoke-overlay-note').textContent), 'good overlay is saved');
// logos
ok(!!q('karaoke-logo-row-Pub One') && !!q('karaoke-logo-row-Bar Two'), 'one logo row per location');
await pick(q('karaoke-logo-input-Pub One'), 'tiny.png');
ok(/Too small \(100 x 100\)/.test(q('karaoke-logo-note-Pub One').textContent), 'tiny logo refused with its size');
await pick(q('karaoke-logo-input-Pub One'), 'logo.png');
ok(/Saved \(150 x 150\)/.test(q('karaoke-logo-note-Pub One').textContent), 'good logo saved');
ok(server.posts.some(p => p.u.endsWith('/karaoke/venue-logo/Pub%20One')), 'logo is uploaded under the location name');
await act(async () => { fireEvent.click(q('karaoke-logo-remove-Pub One')); await new Promise(r => setTimeout(r, 150)); });
ok(server.deletes.some(u => u.endsWith('/karaoke/venue-logo/Pub%20One')), 'logo remove calls delete');
// filler
await act(async () => { fireEvent.change(q('karaoke-filler-input'), { target: { value: 'Z:\\nope' } }); fireEvent.click(q('karaoke-filler-check-btn')); await new Promise(r => setTimeout(r, 200)); });
ok(/plug the drive in/.test((q('karaoke-filler-error') || {}).textContent || ''), 'missing drive explained on the setup page');
await act(async () => { fireEvent.change(q('karaoke-filler-input'), { target: { value: 'E:\\Filler' } }); fireEvent.click(q('karaoke-filler-check-btn')); await new Promise(r => setTimeout(r, 200)); });
ok(/21 tracks/.test((q('karaoke-filler-ok') || {}).textContent || '') && !!q('karaoke-filler-folder-ABBA'), 'good folder shows track count and its folders');
// key + save
ok(q('karaoke-key-input').type === 'password', 'key box hides what you type');
await act(async () => { fireEvent.change(q('karaoke-key-input'), { target: { value: 'AIzaSyTESTKEY1234abcd' } }); });
await act(async () => { fireEvent.click(q('karaoke-setup-save-btn')); await new Promise(r => setTimeout(r, 250)); });
const saved = server.posts.filter(p => p.u.endsWith('/karaoke/setup')).pop();
ok(saved && saved.body.filler_folder === 'E:\\Filler' && saved.body.youtube_api_key === 'AIzaSyTESTKEY1234abcd', 'Save sends the filler folder and the key');
ok(/A key is saved/.test(q('karaoke-key-status').textContent) && q('karaoke-key-input').value === '', 'after saving the key box is cleared and shows a key is saved');
ok(!document.body.textContent.includes('AIzaSyTESTKEY1234abcd'), 'the full key is never shown on the page');
// saving again with an empty key box must not send a blank key
server.posts.length = 0;
await act(async () => { fireEvent.click(q('karaoke-setup-save-btn')); await new Promise(r => setTimeout(r, 250)); });
ok(!('youtube_api_key' in server.posts.filter(p => p.u.endsWith('/karaoke/setup')).pop().body), 'saving with the key box empty does not overwrite the saved key');
await act(async () => { fireEvent.click(q('karaoke-setup-back-btn')); }); await wait();
ok(!!q('karaoke-lobby'), 'back returns to the Karaoke lobby');
cleanup();

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke setup + lobby: checks ok');
