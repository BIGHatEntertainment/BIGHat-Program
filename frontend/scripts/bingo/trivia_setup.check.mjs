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

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('trivia setup move: checks ok');
