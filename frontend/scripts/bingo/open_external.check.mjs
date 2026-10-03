// alpha.71: Purchase button opens the store in the user's own browser
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://127.0.0.1:8001/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const opened = []; dom.window.open = (u, t, f) => { opened.push({ u, t, f }); return {}; };
const lib = await import('/tmp/rtest/openext.bundle.mjs');

// 1. normal browser -> window.open, new tab, no opener
let r = await lib.openExternal('https://bighat.live/shop/karaoke');
ok(r === true && opened.length === 1 && opened[0].u === 'https://bighat.live/shop/karaoke' && opened[0].t === '_blank' && /noopener/.test(opened[0].f), 'in a normal browser it opens a new tab with noopener');
// 2. refuses anything that is not a web link
opened.length = 0;
for (const bad of ['javascript:alert(1)', 'file:///C:/Windows/System32/cmd.exe', 'C:\\Windows\\notepad.exe', '', null, undefined, 'bighat.live/shop', 'data:text/html,<b>x</b>', 'ftp://x.com/a']) {
  const res = await lib.openExternal(bad);
  ok(res === false, 'refuses ' + JSON.stringify(bad));
}
ok(opened.length === 0, 'refused links never reach window.open');
ok(lib.isWebLink('http://example.com') && lib.isWebLink('https://bighat.live/shop?x=1&y=2'), 'http and https are web links');
// 3. desktop app -> the shell plugin, NOT window.open
dom.window.__TAURI_INTERNALS__ = {}; globalThis.__shellCalls = [];
const lib2 = await import('/tmp/rtest/openext_tauri.bundle.mjs');
opened.length = 0;
r = await lib2.openExternal('https://bighat.live/shop/karaoke');
ok(r === true && globalThis.__shellCalls.length === 1 && globalThis.__shellCalls[0] === 'https://bighat.live/shop/karaoke', 'in the desktop app it hands the link to the system browser via the shell plugin: ' + JSON.stringify(globalThis.__shellCalls));
ok(opened.length === 0, 'and does NOT use window.open (which the desktop app blocks)');
// 4. plugin fails -> still tries window.open
globalThis.__shellFail = true; opened.length = 0;
r = await lib2.openExternal('https://bighat.live/shop/karaoke');
ok(opened.length === 1, 'if the shell plugin throws, falls back to window.open instead of doing nothing');
// 5. the real card calls it
const fs = await import('node:fs');
const card = fs.readFileSync('/root/workspace/BIGHat-Program/frontend/src/components/AppCards.js', 'utf8');
ok(/openExternal\(`\$\{STORE_BASE\}\$\{app\.storePath\}`\)/.test(card) && !/window\.open\(`\$\{STORE_BASE\}/.test(card), 'the Purchase button uses openExternal, not window.open');
ok(/STORE_BASE = 'https:\/\/bighat\.live\/shop'/.test(card), 'and still points at the store');
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('open external link: checks ok');
process.exit(0);
