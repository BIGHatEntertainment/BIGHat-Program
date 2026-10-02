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

// ---------- 1. first screen ----------
mount();
await waitFor(() => screen.getByText('Select Bingo Type'));
ok(text().includes('Select Bingo Type'), 'first screen is Select Bingo Type');
ok(!text().includes('Quick Play'), 'no Quick Play screen');
ok(!text().includes('Select Game Type'), 'Regular/Lightning is NOT shown first');
const t = text();
ok(t.indexOf('Traditional Bingo') > -1 && t.indexOf('Music Bingo') > -1 && t.indexOf('Traditional Bingo') < t.indexOf('Music Bingo'), 'Traditional tile first, Music tile second');
ok(screen.getByTestId('wizard-next-btn').disabled, 'Next disabled until a tile is picked');
ok(document.querySelector('h1').textContent.trim() === 'Bingo', 'title says Bingo before a pick');

// ---------- 2. Traditional path ----------
await click('Traditional Bingo');
ok(!screen.getByTestId('wizard-next-btn').disabled, 'Next enabled after picking');
await next();
ok(text().includes('Select Game Type') && text().includes('Regular Bingo') && text().includes('Lightning Bingo'), 'Traditional -> Regular/Lightning');
await click('Lightning Bingo'); await next();
ok(text().includes('Select Round Type'), 'then Round Type'); await next();
ok(text().includes('Number Call Interval') && text().includes('10 sec'), 'then Call Interval (lightning speeds)');
ok(screen.getByTestId('start-custom-btn'), 'last step has Start Game');
await act(async () => { fireEvent.click(screen.getByTestId('start-custom-btn')); });
await waitFor(() => screen.getByText('HOST-PAGE'));
ok(created && created.bingo_type === 'traditional' && created.game_type === 'lightning' && created.call_interval === 10 && created.preset_mode === false, 'game created: traditional + lightning + 10s -> ' + JSON.stringify(created));
cleanup();

// ---------- 3. Music path ----------
created = null; mount();
await waitFor(() => screen.getByText('Select Bingo Type'));
await click('Music Bingo');
ok(document.querySelector('h1').textContent.trim() === 'Music Bingo', 'title becomes Music Bingo after picking Music');
await next();
await waitFor(() => screen.getByText('Select Music Theme'));
await click('1990s'); await next();
ok(text().includes('Select Game Speed') && text().includes('Regular') && text().includes('Lightning'), 'Music -> decade -> Regular/Lightning');
await next(); ok(text().includes('Select Round Type'), 'then Round Type');
await next(); ok(text().includes('Song Duration'), 'then Song Duration');
await act(async () => { fireEvent.click(screen.getByTestId('start-custom-btn')); });
await waitFor(() => screen.getByText('HOST-PAGE'));
ok(created && created.bingo_type === 'music' && created.music_decade === '1990s' && created.game_type === 'regular' && created.call_interval === 30, 'game created: music + 1990s + regular + 30s -> ' + JSON.stringify(created));
cleanup();

// ---------- 4. back on first screen ----------
mount();
await waitFor(() => screen.getByText('Select Bingo Type'));
await act(async () => { fireEvent.click(screen.getByTestId('wizard-back-btn')); });
ok(text().includes('DASHBOARD-PAGE'), 'Back on first screen -> dashboard');
cleanup();

// ---------- 5. back inside the wizard keeps the pick ----------
mount();
await waitFor(() => screen.getByText('Select Bingo Type'));
await click('Music Bingo'); await next();
await act(async () => { fireEvent.click(screen.getByTestId('wizard-back-btn')); });
ok(text().includes('Select Bingo Type'), 'Back from step 1 -> first screen');
ok(!screen.getByTestId('wizard-next-btn').disabled, 'pick is remembered');
cleanup();


// ---------- 6. Music theme step: folder rules ----------
const getBefore = axios.get;
const theme = (cfg, list) => { axios.get = async () => ({ data: { success: true, configured: cfg, themes: list } }); };
const toMusicStep = async () => { mount(); await waitFor(() => screen.getByText('Select Bingo Type')); await click('Music Bingo'); await next(); await waitFor(() => screen.getByText('Select Music Theme')); };

// 6a. no folder set up yet
theme(false, []); await toMusicStep();
ok(!!document.querySelector('[data-testid="no-themes"]'), 'no folder -> setup message shown');
ok(text().includes("isn't set up yet"), 'message says the folder is not set up');
ok(screen.getByTestId('wizard-next-btn').disabled, 'no folder -> Next stays off');
ok(!text().includes('SharePoint') && !text().includes('1980s'), 'no SharePoint wording, no invented decades');
cleanup();

// 6b. folder set, but every theme switched off
theme(true, []); await toMusicStep();
ok(text().includes('No Music Bingo themes are switched on'), 'folder set but nothing on -> says so');
ok(screen.getByTestId('wizard-next-btn').disabled, 'nothing on -> Next stays off');
cleanup();

// 6c. themes available: Next is off until one is chosen, then the game gets that theme
theme(true, [{id:'Emo',name:'Emo',videos:12,ready:true,enabled:true},{id:'Pop Punk',name:'Pop Punk',videos:9,ready:true,enabled:true}]);
created = null; await toMusicStep();
ok(!document.querySelector('[data-testid="no-themes"]'), 'themes found -> no setup message');
ok(text().includes('Emo') && text().includes('Pop Punk') && !text().includes('1980s'), 'tiles are the folder themes only');
ok(screen.getByTestId('wizard-next-btn').disabled, 'Next off until a theme is chosen (nothing preselected)');
await click('Pop Punk'); ok(!screen.getByTestId('wizard-next-btn').disabled, 'Next on after choosing a theme');
await next(); await next(); await next();
await act(async () => { fireEvent.click(screen.getByTestId('start-custom-btn')); });
await waitFor(() => screen.getByText('HOST-PAGE'));
ok(created && created.bingo_type === 'music' && created.music_decade === 'Pop Punk', 'game created with the chosen folder theme -> ' + JSON.stringify(created));
cleanup();
// 6d. the lobby has the Bingo Setup button and it goes to setup
axios.get = getBefore; mount(); await waitFor(() => screen.getByText('Select Bingo Type'));
ok(!!screen.getByTestId('bingo-setup-btn'), 'Bingo Setup button on the main page');
cleanup();

console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'lobby walk-through: all checks ok');
process.exit(fails.length ? 1 : 0);
