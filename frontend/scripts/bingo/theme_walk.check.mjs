import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/bingo', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, screen, fireEvent, cleanup, act, waitFor } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
let created = null;
axios.get = async () => ({ data: { success: true, configured: true, themes: [{id:'1980s',name:'1980s',videos:40,ready:true,enabled:true},{id:'1990s',name:'1990s',videos:38,ready:true,enabled:true}] } });
axios.post = async (u, body) => { created = body; return { data: { success: true } }; };
const { default: Lobby } = await import('./lobby.bundle.mjs');

const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const mount = () => render(React.createElement(MemoryRouter, { initialEntries: ['/bingo'] },
  React.createElement(Routes, null,
    React.createElement(Route, { path: '/bingo', element: React.createElement(Lobby) }),
    React.createElement(Route, { path: '/', element: React.createElement('div', null, 'DASHBOARD-PAGE') }),
    React.createElement(Route, { path: '/bingo/host', element: React.createElement('div', null, 'HOST-PAGE') }))));
const text = () => document.body.textContent;
const click = async (t) => { await act(async () => { fireEvent.click(screen.getByText(t)); }); };
const next = async () => { await act(async () => { fireEvent.click(screen.getByTestId('wizard-next-btn')); }); };


const theme = () => document.querySelector('[data-testid="bingo-lobby-root"]').getAttribute('data-theme');
const hasThemeClass = () => document.querySelector('[data-testid="bingo-lobby-root"]').classList.contains('bingo-theme');

// 1. main page: blue
mount(); await waitFor(() => screen.getByText('Select Bingo Type'));
ok(hasThemeClass(), 'lobby root carries bingo-theme');
ok(theme() === 'blue', 'main page is blue, got ' + theme());

// 2. Traditional stays blue through every step
await click('Traditional Bingo'); ok(theme() === 'blue', 'Traditional (picked) is blue, got ' + theme());
await next(); ok(theme() === 'blue', 'Traditional / Regular step is blue, got ' + theme());
await next(); ok(theme() === 'blue', 'Traditional / round type is blue, got ' + theme());
// 3. Lightning -> yellow, Regular -> back to blue
await act(async () => { fireEvent.click(screen.getByTestId('wizard-back-btn')); });
await click('Lightning Bingo'); ok(theme() === 'yellow', 'Traditional + Lightning is yellow, got ' + theme());
await click('Regular Bingo'); ok(theme() === 'blue', 'Regular again -> blue, got ' + theme());
await click('Lightning Bingo'); await next(); await next();
ok(theme() === 'yellow', 'stays yellow through Traditional lightning steps, got ' + theme());
cleanup();

// 4. returning to the lobby: fresh mount = blue, rules reset
mount(); await waitFor(() => screen.getByText('Select Bingo Type'));
ok(theme() === 'blue', 'back at the main lobby it reverts to blue, got ' + theme());
ok(!screen.getByTestId('wizard-next-btn') || screen.getByTestId('wizard-next-btn').disabled, 'rules reset: nothing picked, Next off');

// 5. Music: purple; Lightning inside Music: yellow; Regular: purple again
await click('Music Bingo'); ok(theme() === 'purple', 'Music is purple, got ' + theme());
await next(); await waitFor(() => screen.getByText('Select Music Theme'));
ok(theme() === 'purple', 'Music / decade is purple, got ' + theme());
await click('1990s'); await next();
ok(theme() === 'purple', 'Music / speed step is purple until Lightning is picked, got ' + theme());
await click('Lightning'); ok(theme() === 'yellow', 'Music + Lightning is yellow, got ' + theme());
await click('Regular'); ok(theme() === 'purple', 'Music + Regular is purple again, got ' + theme());
cleanup();

// 6. switching Music -> back -> Traditional goes blue
mount(); await waitFor(() => screen.getByText('Select Bingo Type'));
await click('Music Bingo'); await click('Traditional Bingo'); ok(theme() === 'blue', 'Music then Traditional is blue, got ' + theme());
cleanup();

console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'theme walk-through: all checks ok');
process.exit(fails.length ? 1 : 0);
