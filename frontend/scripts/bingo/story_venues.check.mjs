// alpha.80: Story Images manager lists the Schedule's venues
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) { try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default; const { render, fireEvent, cleanup, act } = await import('@testing-library/react'); const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const wait = (ms = 150) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const posts = []; let venues = [{ id: '1', name: 'Roses By The Stairs' }, { id: '2', name: 'Monkey Pants' }, { id: '3', name: 'Old Town Pub' }];
let files = { bingo: [{ filename: 'Monkey Pants.jpg', name: 'Monkey Pants', variant: 'location' }], trivia: [], karaoke: [], hosts: [{ filename: 'Alex.gif', name: 'Alex', variant: 'location' }] };
axios.get = async (u) => /\/api\/venues/.test(u) ? { data: venues } : { data: { files: files[u.split('/').pop()] || [], folder: 'C:/x' } };
axios.post = async (u, form) => { posts.push({ u, name: form.get('name'), variant: form.get('variant') }); return { data: { success: true } }; };
const { default: Mgr } = await import('/tmp/rtest/storyimg.bundle.mjs');
const tab = (k) => document.querySelector(`[data-testid="story-images-tab-${k}"]`);
render(React.createElement(Mgr, { onClose() {} })); await wait(300);
// trivia tab: nothing uploaded yet -> every venue needs a picture
let sel = document.querySelector('[data-testid="story-images-venue"]');
ok(!!sel, 'a venue dropdown replaces the free-text name box');
let opts = [...sel.querySelectorAll('option')].map(o => o.textContent.trim());
ok(opts.length === 4 && opts[0].startsWith('Choose'), 'dropdown = "Choose" + 3 venues (got ' + opts.length + ')');
ok(opts.indexOf('Monkey Pants  (needs a picture)') > 0 && opts.some(o => o.startsWith('Old Town Pub')), 'venues are listed, A-Z');
ok(opts.slice(1).join() === [...opts.slice(1)].sort((a, b) => a.localeCompare(b)).join(), 'venues are in alphabetical order');
ok(/Still need a Trivia picture: Monkey Pants, Old Town Pub, Roses By The Stairs/.test(document.querySelector('[data-testid="story-images-missing"]')?.textContent || ''), 'lists which venues still need a Trivia picture');
// bingo tab: Monkey Pants already has one
await act(async () => { fireEvent.click(tab('bingo')); }); await wait(250);
sel = document.querySelector('[data-testid="story-images-venue"]'); opts = [...sel.querySelectorAll('option')].map(o => o.textContent.trim());
ok(opts.includes('Monkey Pants') && !opts.includes('Monkey Pants  (needs a picture)'), 'a venue that has a picture is not marked "needs a picture"');
ok(/Old Town Pub, Roses By The Stairs/.test(document.querySelector('[data-testid="story-images-missing"]')?.textContent || ''), 'only the venues without a Bingo picture are listed as missing');
// upload to a chosen venue
await act(async () => { fireEvent.change(sel, { target: { value: 'Roses By The Stairs' } }); }); await wait(50);
const input = document.querySelector('[data-testid="story-images-file"]');
await act(async () => { fireEvent.change(input, { target: { files: [new dom.window.File([new Uint8Array([255, 216, 255, 1])], 'whatever.jpg', { type: 'image/jpeg' })] } }); }); await wait(200);
ok(posts.length === 1 && posts[0].name === 'Roses By The Stairs' && /story-images\/bingo/.test(posts[0].u), 'uploading uses the chosen venue name, not the file name (got ' + JSON.stringify(posts[0]) + ')');
// hosts tab is not about venues
await act(async () => { fireEvent.click(tab('hosts')); }); await wait(250);
ok(!document.querySelector('[data-testid="story-images-venue"]') && !!document.querySelector('[data-testid="story-images-name"]'), 'hosts still use a typed name');
ok(!document.querySelector('[data-testid="story-images-missing"]'), 'hosts do not list missing venues');
cleanup();
// no venues yet
venues = [];
render(React.createElement(Mgr, { onClose() {} })); await wait(300);
ok(!!document.querySelector('[data-testid="story-images-no-venues"]') && !!document.querySelector('[data-testid="story-images-name"]'), 'no venues: says to add them in the Schedule, and still lets you type a name');
cleanup();
// venue list fails to load
axios.get = async (u) => { if (/\/api\/venues/.test(u)) throw new Error('down'); return { data: { files: [], folder: '' } }; };
render(React.createElement(Mgr, { onClose() {} })); await wait(300);
ok(!!document.querySelector('[data-testid="story-images-name"]'), 'if venues cannot be loaded the manager still works with a typed name');
cleanup();
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('story images + venues: checks ok');
