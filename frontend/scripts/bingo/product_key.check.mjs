// alpha.80: Product Key tab
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) { try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default; const { render, fireEvent, cleanup, act } = await import('@testing-library/react'); const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const wait = (ms = 150) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
let status = { main_key: 'BHE-…DDDD', owns_standalone: true, addons: { music_bingo: false, karaoke: false }, extra_keys: [] };
const posts = []; let reply = null;
axios.get = async () => ({ data: status });
axios.post = async (u, body) => { posts.push(body.product_key); if (reply?.fail) { const e = new Error('x'); e.response = reply.fail; throw e; } return { data: reply.data }; };
const { default: Tab } = await import('/tmp/rtest/productkey.bundle.mjs');
let err = '', okmsg = '';
const mount = () => render(React.createElement(Tab, { setError: (m) => { err = m; }, setSuccess: (m) => { okmsg = m; } }));
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const type = async (v) => { await act(async () => { fireEvent.change(q('product-key-input'), { target: { value: v } }); }); };

mount(); await wait(250);
ok(/Unlocked/.test(q('product-standalone')?.textContent), 'base program shows Unlocked');
ok(/Locked/.test(q('product-music_bingo')?.textContent) && !/Unlocked/.test(q('product-music_bingo').textContent), 'Music Bingo shows Locked');
ok(/Locked/.test(q('product-karaoke')?.textContent), 'Karaoke shows Locked');
ok(q('product-key-submit').disabled, 'Unlock is disabled while the box is empty');

// success: bingo unlocks
reply = { data: { owns_standalone: true, addons: { music_bingo: true, karaoke: false }, extra_keys: [{ key: 'BHE-…HHHH', unlocks: ['music_bingo'] }], main_key: 'BHE-…DDDD' } };
await type('  bhe-eeee-ffff-gggg-hhhh '); ok(!q('product-key-submit').disabled, 'Unlock enables once text is typed');
await act(async () => { fireEvent.click(q('product-key-submit')); }); await wait(250);
ok(posts.length === 1 && posts[0] === 'bhe-eeee-ffff-gggg-hhhh', 'the typed key (trimmed) is sent (got ' + JSON.stringify(posts) + ')');
ok(/Unlocked/.test(q('product-music_bingo').textContent), 'Music Bingo flips to Unlocked');
ok(/Locked/.test(q('product-karaoke').textContent) && !/Unlocked/.test(q('product-karaoke').textContent), 'Karaoke stays Locked');
ok(q('product-key-input').value === '', 'the box is cleared after success');
ok(/accepted/i.test(okmsg), 'success message shown');
const refreshCalls = globalThis.__refreshCalls;
ok(refreshCalls.n === 1, 'the app-wide license info is refreshed after success so dashboard cards unlock (got ' + refreshCalls.n + ')');
ok(/Extra key BHE-…HHHH \(Music Bingo\)/.test(document.body.textContent), 'extra key listed with what it unlocks');
ok(!document.body.textContent.includes('bhe-eeee'), 'the full key is never shown back');

const before = refreshCalls.n;
// rejected key -> clear message, nothing changes
reply = { fail: { status: 400, data: { detail: { error: 'invalid_key', message: 'That key was not accepted.' } } } };
await type('BHE-1111-2222-3333-4444'); await act(async () => { fireEvent.click(q('product-key-submit')); }); await wait(250);
ok(err === 'That key was not accepted.', 'rejected key shows the server message (got ' + err + ')');
ok(refreshCalls.n === before, 'a rejected key does not refresh anything');
ok(q('product-key-input').value === 'BHE-1111-2222-3333-4444', 'the typed key stays so it can be fixed');

// offline
reply = { fail: { status: 503, data: { detail: { error: 'network_error', message: '' } } } };
await act(async () => { fireEvent.click(q('product-key-submit')); }); await wait(250);
ok(/network_error|reach|internet/i.test(err), 'offline gives a readable message (got ' + err + ')');

// not master admin
reply = { fail: { status: 403, data: { detail: 'master_admin_required' } } };
await act(async () => { fireEvent.click(q('product-key-submit')); }); await wait(250);
ok(/master admin/i.test(err) || /master_admin_required/.test(err), 'non-master gets a clear message (got ' + err + ')');

// double click while busy only sends once
posts.length = 0; let release; reply = null;
axios.post = (u, body) => { posts.push(body.product_key); return new Promise((r) => { release = () => r({ data: status }); }); };
await type('BHE-5555-6666-7777-8888');
await act(async () => { fireEvent.click(q('product-key-submit')); fireEvent.click(q('product-key-submit')); }); await wait(50);
ok(posts.length === 1, 'double-click sends once (got ' + posts.length + ')');
await act(async () => { release(); }); await wait(100);
cleanup();
console.log(fails.length ? 'FAIL:\n - ' + fails.join('\n - ') : 'product key tab: all checks ok');
process.exit(fails.length ? 1 : 0);
