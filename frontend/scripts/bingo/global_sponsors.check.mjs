// alpha.88: Global Slides panel: Sponsor slides (many, ordered) + the ONE final sponsor slide.
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','File','FormData','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
let reachedEnd = false;
process.on('exit', () => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

let server;                    // the fake backend's settings
const calls = [];
const base = 'http://x/api/native/global-slides';
axios.get = async (url) => { calls.push(['GET', url]); return { data: JSON.parse(JSON.stringify(server)) }; };
axios.put = async (url, body) => { calls.push(['PUT', url, body]); if (body.sponsors?.images) server.sponsors.images = body.sponsors.images; if (body.sponsors && 'enabled' in body.sponsors) server.sponsors.enabled = body.sponsors.enabled; return { data: JSON.parse(JSON.stringify(server)) }; };
axios.post = async (url, fd) => { const f = fd.get('file'); calls.push(['POST', url, f && f.name]);
  if (!/\/(sponsor_final|sponsors|company|rules|format_bg)\/upload$/.test(url)) return { data: JSON.parse(JSON.stringify(server)) };
  if (url.endsWith('/sponsor_final/upload')) server.sponsors.final = 'final-' + f.name;
  else if (url.endsWith('/sponsors/upload')) server.sponsors.images.push('sp-' + f.name);
  return { data: JSON.parse(JSON.stringify(server)) }; };
axios.delete = async (url) => { calls.push(['DELETE', url]); const n = url.split('/').pop();
  server.sponsors.images = server.sponsors.images.filter(x => x !== n); if (server.sponsors.final === n) server.sponsors.final = null;
  return { data: JSON.parse(JSON.stringify(server)) }; };
const fresh = (sp) => ({ company: { enabled: true, images: [] }, rules: { enabled: true, images: [] },
  sponsors: Object.assign({ enabled: true, images: [], final: null }, sp), format: { enabled: true, background: null, show_themes: true } });

const { default: Panel } = await import('/tmp/rtest/gsp.bundle.mjs');
const mount = async () => { render(React.createElement(Panel, { canEdit: true, setError: (m) => fails.push('panel error: ' + m), setSuccess: () => {} })); await wait(300); };

// 1. empty state
server = fresh({}); await mount();
ok(!!q('global-sponsors') && !!q('global-sponsor-final'), 'panel shows a Sponsor slides group and a Final sponsor slide card');
ok(/Nothing uploaded yet/.test(q('global-sponsors').textContent), 'sponsor group says nothing is uploaded');
ok(!!q('global-sponsor-final-empty') && !q('global-sponsor-final-img'), 'final slide card says none is uploaded');
ok(/Upload final slide/.test(q('global-sponsor-final-upload').textContent), 'final button says Upload when empty');
ok(!q('global-sponsor-final-remove'), 'no Remove button on an empty final slot');
// section order on the page: sponsor slides first, final slide right after them
const html = document.body.innerHTML;
ok(html.indexOf('global-sponsors"') < html.indexOf('global-sponsor-final"') && html.indexOf('global-rules"') < html.indexOf('global-sponsors"'), 'order on the page: rules, then sponsor slides, then the final slide');
ok(q('global-sponsors-file').hasAttribute('multiple'), 'sponsor slides accept many files');
ok(!q('global-sponsor-final-file').hasAttribute('multiple'), 'the final slide accepts ONE file');

// 2. uploading goes to the right place
calls.length = 0;
const f = (n) => new window.File([new Uint8Array([1])], n, { type: 'image/png' });
await act(async () => { fireEvent.change(q('global-sponsors-file'), { target: { files: [f('a.png'), f('b.png')] } }); }); await wait(300);
ok(calls.filter(c => c[0] === 'POST').map(c => c[1].replace(base, '') + ':' + c[2]).join(',') === '/sponsors/upload:a.png,/sponsors/upload:b.png', 'two sponsor files post to /sponsors/upload in order: ' + JSON.stringify(calls));
ok(!!q('global-sponsors-img-0') && !!q('global-sponsors-img-1'), 'both uploaded sponsor slides are shown, numbered in order');
calls.length = 0;
await act(async () => { fireEvent.change(q('global-sponsor-final-file'), { target: { files: [f('join.png')] } }); }); await wait(300);
ok(calls.filter(c => c[0] === 'POST').map(c => c[1].replace(base, '')).join(',') === '/sponsor_final/upload', 'the final slide posts to /sponsor_final/upload');
ok(!!q('global-sponsor-final-img') && /Replace final slide/.test(q('global-sponsor-final-upload').textContent), 'final slide now shows a preview and the button says Replace');
ok((q('global-sponsor-final-img')?.querySelector('img')?.getAttribute('src') || '').endsWith('/file/final-join.png'), 'the final preview is the final file');

// 3. order: moving a sponsor slide later changes the saved order, and never touches the final slot
calls.length = 0;
const moveLater = q('global-sponsors-img-0')?.querySelectorAll('button')[1];
if (moveLater) await act(async () => { fireEvent.click(moveLater); }); await wait(300);
const put = calls.find(c => c[0] === 'PUT');
ok(put && JSON.stringify(put[2]) === JSON.stringify({ sponsors: { images: ['sp-b.png', 'sp-a.png'] } }), 'move later saves the new order: ' + JSON.stringify(put && put[2]));
ok(server.sponsors.final === 'final-join.png', 'reordering leaves the final slide alone');
ok((q('global-sponsors-img-0')?.querySelector('img')?.getAttribute('src') || '').endsWith('/sp-b.png'), 'the screen shows the new order');

// 4. removing
calls.length = 0;
if (q('global-sponsor-final-remove')) await act(async () => { fireEvent.click(q('global-sponsor-final-remove')); }); else fails.push('no Remove button to click on the final slide'); await wait(300);
ok(calls.some(c => c[0] === 'DELETE' && c[1].endsWith('/file/final-join.png')), 'Remove deletes the final file');
ok(!!q('global-sponsor-final-empty'), 'after Remove the final card is empty again');
ok(!!q('global-sponsors-img-1'), 'removing the final slide keeps the other sponsor slides');

// 5. on/off switch
calls.length = 0;
if (q('global-sponsors-enabled')) await act(async () => { fireEvent.click(q('global-sponsors-enabled')); }); else fails.push('no on/off box for the sponsor slides'); await wait(300);
const t = calls.find(c => c[0] === 'PUT');
ok(t && JSON.stringify(t[2]) === JSON.stringify({ sponsors: { enabled: false } }), 'the Show-in-presentations box saves sponsors.enabled: ' + JSON.stringify(t && t[2]));
cleanup();

// 6. a non-editor sees the slides but no buttons
server = fresh({ images: ['sp-a.png'], final: 'final-x.png' });
render(React.createElement(Panel, { canEdit: false, setError: () => {}, setSuccess: () => {} })); await wait(300);
ok(!!q('global-sponsors-img-0') && !!q('global-sponsor-final-img'), 'a viewer still sees the sponsor slides');
ok(!q('global-sponsors-upload') && !q('global-sponsor-final-upload') && !q('global-sponsor-final-remove'), 'a viewer gets no upload or remove buttons');
cleanup();

reachedEnd = true;
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('global sponsors: checks ok');
