// alpha.78: Buy buttons + downloads must work INSIDE the desktop app.
// (alpha.71 trusted the Tauri shell plugin and the address bighat.live/shop/... -- the plugin did not work for the
//  customer and that address is a 404 page.  This check guards the replacement.)
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import path from 'node:path';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://127.0.0.1:8001/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const opened = []; const alerts = []; const backend = [];
dom.window.open = (u, t, f) => { opened.push(u); return null; };      // the desktop window blocks this
dom.window.alert = (m) => alerts.push(m);
globalThis.alert = dom.window.alert;
globalThis.fetch = async (url, opts) => {                                // pretend backend
  backend.push({ url: String(url), body: opts?.body });
  if (String(url).endsWith('/store-links')) return { ok: true, json: async () => ({ default: 'https://bighat.live/', karaoke: 'https://bighat.live/k', story: 'https://bighat.live/s' }) };
  return { ok: true, json: async () => ({ ok: true }) };
};
const lib = await import('/tmp/rtest/openext_tauri.bundle.mjs');
dom.window.__TAURI_INTERNALS__ = {};
globalThis.__shellCalls = []; globalThis.__shellFail = false;

// 1. desktop app: the click goes to the BACKEND, not the shell plugin and not window.open
let r = await lib.openExternal('https://bighat.live/x');
ok(r === true, 'desktop: link reports success');
ok(backend.some(b => b.url.endsWith('/api/native/system/open-url') && /bighat\.live\/x/.test(b.body)), 'desktop: asks the backend to open the link');
ok(opened.length === 0 && globalThis.__shellCalls.length === 0, 'desktop: does not depend on window.open or the shell plugin');

// 2. openStore uses the backend's address for each product
backend.length = 0;
await lib.openStore('karaoke');
ok(backend[0].url.endsWith('/api/native/system/store-links') && /bighat\.live\/k/.test(backend[1].body), 'openStore("karaoke") opens the address the backend gave');
backend.length = 0; await lib.openStore('nonsense');
ok(/"url":"https:\/\/bighat\.live\/"/.test(backend[1].body), 'an unknown product falls back to the home page');

// 3. only web links
for (const bad of ['javascript:alert(1)', 'file:///C:/Windows/System32/cmd.exe', 'C:\\Windows\\notepad.exe', '', null, undefined]) ok(await lib.openExternal(bad) === false, 'refuses ' + JSON.stringify(bad));

// 4. nothing works -> the user is told, never a silent dead button
globalThis.fetch = async () => { throw new Error('offline'); };
globalThis.__shellFail = true;                                           // the shell plugin fails as well
alerts.length = 0; opened.length = 0;
r = await lib.openExternal('https://bighat.live/x');
ok(r === false && alerts.length === 1 && /bighat\.live\/x/.test(alerts[0]), 'if it cannot open, the user sees the link in a message');

// 5. the real screens use it
const SRC = '/root/workspace/BIGHat-Program/frontend/src';
const read = (p) => fs.readFileSync(path.join(SRC, p), 'utf8');
const cards = read('components/AppCards.js');
ok(/openStore\(app\.id\)/.test(cards) && !/window\.open\(/.test(cards), 'Karaoke "Add Karaoke" button calls openStore');
ok(!/bighat\.live\/shop/.test(cards), 'no address that does not exist (bighat.live/shop/...) is left in the cards');
ok(/openStore\('standalone'\)/.test(cards), 'the locked Trivia card has a Buy link');
ok(/openStore\('standalone'\)/.test(read('components/LicenseActivationDialog.jsx')), 'the license-key dialog has a "get one" link');
const story = read('pages/story/StoryGeneratorPage.jsx');
ok(/openStore\('story'\)/.test(story) && /isLockedReply/.test(story), 'Story page: Get-the-Story-Generator button + clear "not unlocked" message');

// 6. no screen may download with the old, desktop-blocked way
const hits = [];
(function walk(d) { for (const f of fs.readdirSync(d, { withFileTypes: true })) {
  const p = path.join(d, f.name);
  if (f.isDirectory()) walk(p);
  else if (/\.(js|jsx)$/.test(f.name) && !/lib[\\/]saveFile\.js$/.test(p) && !/SlotMachineRandomizer|PresentationMode|audienceWindow|openExternal|HostDashboard|KaraokePlayer|ScoreboardDashboard|TriviaAudienceView/.test(p)) {
    const t = fs.readFileSync(p, 'utf8');
    if (/\.download\s*=|\ba\.click\(\)|\blink\.click\(\)|window\.open\(/.test(t)) hits.push(path.relative(SRC, p));
  } } })(SRC);
ok(hits.length === 0, 'no screen uses <a download> / window.open directly: ' + hits.join(', '));

ok(/openNativeAudience\(\{ label: 'scoreboard-live'/.test(read('pages/scoreboard/ScoreboardDashboard.js')), 'Scoreboard Live View opens a real app window in the desktop app');
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('buy buttons + downloads: checks ok');
