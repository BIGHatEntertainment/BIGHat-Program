// alpha.69: Trivia Setup moved from the Admin page into the Trivia player
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/trivia', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','FormData','File','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, screen, fireEvent, cleanup, act, waitFor } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
axios.get = async () => ({ data: [] });
axios.post = async () => ({ data: {} });
globalThis.__triviaEnv = { user: null, calls: [] };
const env = { state: globalThis.__triviaEnv };
const { default: TriviaSetupPage } = await import('/tmp/rtest/tsetup.bundle.mjs');
const { default: TriviaDashboard } = await import('/tmp/rtest/tdash.bundle.mjs');
const { default: AdminPage } = await import('/tmp/rtest/admin.bundle.mjs');
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
let reachedEnd = false;
process.on('exit', () => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 250) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const app = (start) => render(React.createElement(MemoryRouter, { initialEntries: [start] },
  React.createElement(Routes, null,
    React.createElement(Route, { path: '/trivia', element: React.createElement(TriviaDashboard) }),
    React.createElement(Route, { path: '/trivia/setup', element: React.createElement(TriviaSetupPage) }),
    React.createElement(Route, { path: '/admin', element: React.createElement(AdminPage) }),
    React.createElement(Route, { path: '/', element: React.createElement('div', { 'data-testid': 'home' }, 'HOME') }))));
const as = (role) => { env.state.user = { id: 'me', name: 'Pat Q', role }; env.state.calls.length = 0; };

// 1. master admin: button on the Trivia screen -> setup page with the whole Trivia Setup
as('master_admin'); app('/trivia'); await wait();
ok(!!q('trivia-setup-btn'), 'master admin sees the Trivia Setup button on the Trivia screen');
await act(async () => { fireEvent.click(q('trivia-setup-btn')); }); await wait(400);
ok(!!q('trivia-setup-page'), 'button opens the Trivia Setup page');
ok(!!q('trivia-setup'), 'the real Trivia Setup component is on the page');
ok(!!q('global-setup-btn') && !!q('new-location-btn'), 'Global Setup + New location buttons are there');
ok(!!q('location-card-pub-one'), 'locations load and are listed');
ok(env.state.calls.includes('getUsers'), 'master admin loads the user list (for admin assignments)');
await act(async () => { fireEvent.click(q('location-card-pub-one')); }); await wait(300);
ok(!!q('location-editor'), 'opening a location shows its editor');
ok(!!q('upload-branding-btn') && !!q('overlays-section') && !!q('location-slide-style-section'), 'editor has branding, overlays and slide style');
ok(!!q('admin-assignments'), 'master admin sees admin assignments');
await act(async () => { fireEvent.click(q('trivia-setup-back-btn')); }); await wait();
ok(!!q('trivia-dashboard'), 'back button returns to the Trivia screen');
cleanup();

// 2. plain admin: button + page, no user list call, no master-only controls
as('admin'); app('/trivia'); await wait();
ok(!!q('trivia-setup-btn'), 'admin sees the Trivia Setup button');
await act(async () => { fireEvent.click(q('trivia-setup-btn')); }); await wait(400);
ok(!!q('trivia-setup-page') && !!q('location-card-pub-one'), 'admin can open Trivia Setup and sees locations');
ok(!env.state.calls.includes('getUsers'), 'admin does not request the user list');
ok(!q('new-location-btn'), 'admin cannot create locations (master only, as before)');
cleanup();

// 3. host: no button, and the page bounces back to the Trivia screen
as('host'); app('/trivia'); await wait();
ok(!q('trivia-setup-btn'), 'host does NOT see the Trivia Setup button');
cleanup();
as('host'); app('/trivia/setup'); await wait(400);
ok(!q('trivia-setup-page') && !!q('trivia-dashboard'), 'host opening /trivia/setup is sent back to the Trivia screen');
cleanup();

// 4. Admin page: Trivia Setup tab is gone, other tabs stay
as('master_admin'); app('/admin'); await wait(400);
ok(!!q('admin-page'), 'Admin page still opens');
const tabs = [...document.querySelectorAll('button')].map(b => b.textContent.trim());
ok(!tabs.includes('Trivia Setup'), 'Admin page no longer has a Trivia Setup tab: ' + tabs.join('|').slice(0, 120));
ok(tabs.some(t => /User Management/.test(t)) && tabs.some(t => /Event Management/.test(t)), 'User Management + Event Management tabs are still there');
cleanup();


// alpha.86: Trivia Setup lists only places priced for trivia, and tells the master how many are waiting for a price
const P = (id, name) => ({ id, slug: id, name, branding_images: [], overlay_images: [], assigned_user_ids: [] });
globalThis.__locGames = []; globalThis.__locationsByGame = { trivia: [P('a', 'Priced Pub')] }; globalThis.__allLocations = [P('a', 'Priced Pub'), P('b', 'No Price Bar'), P('c', 'Also No Price')];
as('master_admin'); app('/trivia/setup'); await wait(500);
ok(globalThis.__locGames.includes('trivia'), 'Trivia Setup asks only for places on for TRIVIA (got: ' + JSON.stringify(globalThis.__locGames) + ')');
ok(!!q('location-card-a') && !q('location-card-b') && !q('location-card-c'), 'only the trivia-priced place is listed');
ok(/2 places are not listed/.test(q('trivia-noprice-note')?.textContent || '') && /Schedule/.test(q('trivia-noprice-note')?.textContent || ''), 'the master is told 2 places are waiting for a price, and where to set it (got: ' + (q('trivia-noprice-note')?.textContent || 'no note') + ')');
cleanup();
globalThis.__locGames = []; globalThis.__locationsByGame = { trivia: [P('a', 'Priced Pub')] }; globalThis.__allLocations = [P('a', 'Priced Pub'), P('b', 'No Price Bar')];
as('master_admin'); app('/trivia/setup'); await wait(500);
ok(/1 place is not listed because it has no trivia price/.test(q('trivia-noprice-note')?.textContent || ''), 'one waiting place uses the singular wording (got: ' + (q('trivia-noprice-note')?.textContent || 'no note') + ')');
cleanup();
globalThis.__locationsByGame = { trivia: [P('a', 'Priced Pub')] }; globalThis.__allLocations = [P('a', 'Priced Pub')];
as('master_admin'); app('/trivia/setup'); await wait(500);
ok(!q('trivia-noprice-note') && !!q('location-card-a'), 'when every place is priced there is no note');
cleanup();
globalThis.__locationsByGame = { trivia: [] }; globalThis.__allLocations = [P('b', 'No Price Bar')];
as('master_admin'); app('/trivia/setup'); await wait(500);
ok(/1 place is not listed/.test(q('trivia-noprice-note')?.textContent || ''), 'with nothing priced yet the master still sees why the list is empty');
cleanup();
globalThis.__locationsByGame = null; globalThis.__allLocations = null; globalThis.__locGames = [];


// 6. alpha.88: each location has ONE sponsor slide image (upload / replace / remove)
globalThis.__sponsorCalls = [];
globalThis.__allLocations = null; globalThis.__locationsByGame = null;
globalThis.__locations = [{ id: 'l1', slug: 'pub-one', name: 'Pub One', branding_images: [], overlay_images: [], admin_user_ids: [] }];
as('master_admin'); app('/trivia/setup'); await wait(400);
await act(async () => { fireEvent.click(q('location-card-pub-one')); }); await wait(300);
ok(!!q('location-sponsor-section'), 'the location editor has a Sponsor slide section');
ok(!!q('sponsor-empty') && !q('sponsor-preview'), 'a location with no sponsor image says so and shows no preview');
ok(!q('remove-sponsor-btn'), 'no Remove button when there is nothing to remove');
ok(/Upload/.test(q('upload-sponsor-btn')?.textContent || ''), 'the button says Upload when empty');
ok(!q('upload-sponsor-input')?.hasAttribute('multiple'), 'only ONE sponsor image can be picked');
const fileA = new window.File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' });
await act(async () => { fireEvent.change(q('upload-sponsor-input'), { target: { files: [fileA] } }); }); await wait(300);
ok(JSON.stringify(globalThis.__sponsorCalls) === JSON.stringify([['upload', 'l1', 'logo.png']]), 'picking a file uploads it to THIS location: ' + JSON.stringify(globalThis.__sponsorCalls));
cleanup();

globalThis.__sponsorCalls = [];
globalThis.__locations = [{ id: 'l1', slug: 'pub-one', name: 'Pub One', branding_images: [], overlay_images: [], admin_user_ids: [],
  sponsor_image: { id: 'sp-1', filename: 'old.png', size: 2048, mime: 'image/png', ext: '.png' } }];
as('master_admin'); app('/trivia/setup'); await wait(400);
await act(async () => { fireEvent.click(q('location-card-pub-one')); }); await wait(300);
ok(!!q('sponsor-preview') && !q('sponsor-empty'), 'a location with a sponsor image shows its preview');
ok((q('sponsor-preview')?.querySelector('img')?.getAttribute('src') || '').endsWith('/l1/sponsor/raw?v=sp-1'), 'the preview loads THIS location\'s sponsor image: ' + q('sponsor-preview')?.querySelector('img')?.getAttribute('src'));
ok(/Replace/.test(q('upload-sponsor-btn')?.textContent || ''), 'the button says Replace when an image exists');
ok(!!q('remove-sponsor-btn'), 'a Remove button is shown');
await act(async () => { fireEvent.click(q('remove-sponsor-btn')); }); await wait(300);
ok(JSON.stringify(globalThis.__sponsorCalls) === JSON.stringify([['delete', 'l1']]), 'Remove deletes THIS location\'s sponsor image: ' + JSON.stringify(globalThis.__sponsorCalls));
cleanup();
globalThis.__locations = null; globalThis.__sponsorCalls = [];

reachedEnd = true;
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
reachedEnd = true;
console.log('trivia setup move: checks ok');
