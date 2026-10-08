// alpha.97: global + venue slide background colors: "Use default" really reverts, and a venue that matches global follows it
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','Event','MouseEvent','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const axios = (await import('axios')).default;
const { default: Panel } = await import('/tmp/rtest/sstyle.bundle.mjs');
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 250) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const DEFAULT = { mode: 'default', color: '#1657E8', fill: 'gradient' };

// a fake server that REMEMBERS what is saved, like the real one
let disk;
const fresh = () => { disk = { global: { ...DEFAULT }, loc: { use_global: true, background: { ...DEFAULT } }, puts: [] }; };
axios.get = async (u) => {
  if (/slide-style\/global$/.test(u)) return { data: { background: disk.global } };
  if (/locations\/.*\/slide-style$/.test(u)) return { data: { use_global: disk.loc.use_global, background: disk.loc.background, global: disk.global } };
  throw new Error('GET ' + u);
};
axios.put = async (u, body) => {
  disk.puts.push({ u, body });
  if (/slide-style\/global$/.test(u)) disk.global = { ...body.background };
  else { disk.loc.use_global = body.use_global; disk.loc.background = { ...body.background }; }
  return { data: { success: true } };
};
const pickColor = async (hex) => { await act(async () => { fireEvent.change(q('bg-color-input'), { target: { value: hex } }); }); };
const css = () => (q('bg-preview').style.background || '');

// 1. GLOBAL: pick a custom color and save it
fresh(); render(React.createElement(Panel, { scope: 'global', canEdit: true })); await wait();
await pickColor('#aa0000'); await act(async () => { fireEvent.click(q('slide-style-save')); }); await wait(100);
ok(disk.global.mode === 'custom' && disk.global.color === '#aa0000', 'a custom global color is saved: ' + JSON.stringify(disk.global));
ok(/170, 0, 0|aa0000/i.test(css()), 'and the preview shows it');

// 2. GLOBAL: tick "Use default blue gradient". It must REVERT AND SAVE by itself (no separate Save needed)
await act(async () => { fireEvent.click(q('bg-reset-toggle')); }); await wait(100);
ok(disk.global.mode === 'default' && disk.global.color === '#1657E8', 'ticking "Use default" saves the default straight away: ' + JSON.stringify(disk.global));
ok(!/170, 0, 0|aa0000/i.test(css()), 'and the preview goes back to blue');
cleanup();

// 3. the saved default survives closing and reopening the panel
render(React.createElement(Panel, { scope: 'global', canEdit: true })); await wait();
ok(q('bg-reset-toggle').checked === true && !/170, 0, 0|aa0000/i.test(css()), 'reopened: still the default blue');
cleanup();

// 4. the "Reset to default" button does the same
fresh(); disk.global = { mode: 'custom', color: '#00aa00', fill: 'solid' };
render(React.createElement(Panel, { scope: 'global', canEdit: true })); await wait();
await act(async () => { fireEvent.click(q('slide-style-reset')); }); await wait(100);
ok(disk.global.mode === 'default' && disk.global.color === '#1657E8' && disk.global.fill === 'gradient', 'the Reset button saves a clean default: ' + JSON.stringify(disk.global));
cleanup();

// 5. a VENUE that matches global follows a global change while its panel is open
fresh(); disk.global = { mode: 'custom', color: '#aa0000', fill: 'solid' };
render(React.createElement(Panel, { scope: 'location', locationId: 'l1', canEdit: true })); await wait();
ok(/170, 0, 0|aa0000/i.test(css()), 'a venue that matches global shows the global custom color');
disk.global = { ...DEFAULT };                       // the host resets the GLOBAL in another tab
await act(async () => { dom.window.dispatchEvent(new dom.window.Event('focus')); }); await wait(300);
ok(!/170, 0, 0|aa0000/i.test(css()), 'after the global is reset, the venue preview goes back to blue without reloading: ' + css().slice(0, 60));
cleanup();

// 6. a venue with its OWN color is not touched by a global reset
fresh(); disk.loc = { use_global: false, background: { mode: 'custom', color: '#00aa00', fill: 'solid' } }; disk.global = { mode: 'custom', color: '#aa0000', fill: 'solid' };
render(React.createElement(Panel, { scope: 'location', locationId: 'l1', canEdit: true })); await wait();
disk.global = { ...DEFAULT }; await act(async () => { dom.window.dispatchEvent(new dom.window.Event('focus')); }); await wait(300);
ok(/0, 170, 0|00aa00/i.test(css()) && q('match-global-toggle').checked === false, 'a venue with its own color keeps it, and its checkbox is not flipped');
cleanup();

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('slide style panel: checks ok');
