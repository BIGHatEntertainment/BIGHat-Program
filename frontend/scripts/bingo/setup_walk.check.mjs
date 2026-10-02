// alpha.69: Bingo Setup - Winner videos section (list, built-in vs yours, Add button, remove)
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/bingo/setup', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','FormData','File']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, screen, fireEvent, act, waitFor } = await import('@testing-library/react');
const { MemoryRouter, Routes, Route } = await import('react-router-dom');
const axios = (await import('axios')).default;
const calls = [];
let videos = [
  { name: "(1980's).mp4", theme: '1980s', size: 5817251, bundled: true },
  { name: '(Generic).mp4', theme: 'generic', size: 99916, bundled: true },
];
axios.get = async (u) => {
  calls.push('GET ' + u);
  if (u.endsWith('/bingo/winner-videos')) return { data: { folder: 'C:\\Users\\me\\AppData\\BIGHat\\winner_videos', videos } };
  return { data: { main_folder: '', ok: false, error: 'no_folder', themes: [] } };
};
let posted = null;
axios.post = async (u, body) => {
  calls.push('POST ' + u);
  if (u.endsWith('/bingo/winner-videos')) {
    posted = body.getAll('files').map(f => f.name);
    videos = [...videos, { name: posted[0], theme: 'zydeco', size: 5000, bundled: false }];
    return { data: { saved: posted, rejected: [], folder: 'x', videos } };
  }
  return { data: {} };
};
axios.delete = async (u) => {
  calls.push('DELETE ' + u);
  videos = videos.filter(v => !u.includes(encodeURIComponent(v.name)));
  return { data: { videos } };
};
const { default: Setup } = await import('./setup.bundle.mjs');
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
render(React.createElement(MemoryRouter, { initialEntries: ['/bingo/setup'] },
  React.createElement(Routes, null, React.createElement(Route, { path: '/bingo/setup', element: React.createElement(Setup) }))));
await waitFor(() => screen.getByTestId('winner-videos-section'));
await act(async () => { await new Promise(r => setTimeout(r, 200)); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
ok(!!q("winner-row-(1980's).mp4") && !!q('winner-row-(Generic).mp4'), 'lists the built-in winner videos');
ok((q('winner-folder') || {}).textContent?.includes('winner_videos'), 'shows where the videos are saved');
ok(!q("winner-remove-(1980's).mp4"), 'built-in videos have no remove button');
ok(!!q('winner-add-btn') && /Add winner videos/.test(q('winner-add-btn').textContent), 'has the Add winner videos button');
ok(q('winner-file-input').multiple === true, 'file picker allows several videos at once');
ok(/mp4/.test(q('winner-file-input').getAttribute('accept') || ''), 'file picker only offers videos');
// pick a file
const f = new dom.window.File([new Uint8Array(5000)], 'Zydeco.mp4', { type: 'video/mp4' });
const input = q('winner-file-input');
Object.defineProperty(input, 'files', { value: [f], configurable: true });
await act(async () => { fireEvent.change(input); await new Promise(r => setTimeout(r, 200)); });
ok(JSON.stringify(posted) === '["Zydeco.mp4"]', 'Add posts the chosen file: ' + JSON.stringify(posted));
ok(calls.some(c => c.endsWith('/api/bingo/winner-videos') && c.startsWith('POST')), 'posts to /bingo/winner-videos');
ok(!!q('winner-row-Zydeco.mp4'), 'the new video appears in the list');
ok(!!q('winner-remove-Zydeco.mp4'), 'your own video has a remove button');
await act(async () => { fireEvent.click(q('winner-remove-Zydeco.mp4')); await new Promise(r => setTimeout(r, 200)); });
ok(calls.some(c => c.startsWith('DELETE') && c.includes('Zydeco.mp4')), 'remove calls delete');
ok(!q('winner-row-Zydeco.mp4'), 'the removed video leaves the list');
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('setup winner videos: checks ok');
