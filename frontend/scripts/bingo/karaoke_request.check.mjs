// alpha.70: the phone request page (the QR line) - same as the prototype
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/karaoke/request', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const alerts = []; dom.window.alert = globalThis.alert = (m) => alerts.push(m);
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
let status = 'pending', position = 0, submitFails = null, posts = [], statusGets = 0;
axios.post = async (u, body) => { posts.push(body); if (submitFails) { const e = new Error('x'); e.response = submitFails; throw e; } return { data: { success: true, request_id: 'r1' } }; };
axios.get = async () => { statusGets += 1; return { data: { status, position } }; };
const { default: Page } = await import('/tmp/rtest/kreq.bundle.mjs');
const type = (id, v) => fireEvent.change(q(id), { target: { value: v } });

render(React.createElement(Page)); await wait(100);
ok(/Karaoke Request/.test(document.body.textContent) && /Enter your name and the song you want to sing/.test(document.body.textContent), 'same heading + line as the prototype');
ok(q('karaoke-request-submit').disabled, 'Submit is disabled until there is a name and a song');
type('karaoke-request-name', 'Zed'); await wait(30);
ok(q('karaoke-request-submit').disabled, 'a name alone is not enough');
type('karaoke-request-song', 'Africa'); await wait(30);
ok(!q('karaoke-request-submit').disabled, 'name + song enables Submit (artist is optional)');
type('karaoke-request-artist', 'Toto');
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 100)); });
ok(posts.length === 1 && posts[0].singer_name === 'Zed' && posts[0].song_title === 'Africa' && posts[0].song_artist === 'Toto', 'sends name, song and artist: ' + JSON.stringify(posts[0]));
ok(!!q('karaoke-request-pending') && /Request Submitted!/.test(q('karaoke-request-pending').textContent) && /Waiting for the host to review/.test(q('karaoke-request-pending').textContent), 'shows "Request Submitted! Waiting for the host to review..."');
ok(/Zed/.test(q('karaoke-request-pending').textContent) && /Africa by Toto/.test(q('karaoke-request-pending').textContent), 'repeats what you asked for');
// accepted with people ahead
status = 'accepted'; position = 2; await wait(3400);
ok(!!q('karaoke-request-accepted') && /You're In!/.test(q('karaoke-request-accepted').textContent) && /2 people ahead of you/.test(q('karaoke-request-accepted').textContent), 'accepted: "You\'re In!" and "2 people ahead of you"');
const gets = statusGets; await wait(3400);
ok(statusGets === gets, 'it stops checking once there is an answer');
// another
await act(async () => { fireEvent.click(q('karaoke-request-another')); });
ok(!!q('karaoke-request-name') && q('karaoke-request-name').value === 'Zed' && q('karaoke-request-song').value === '', 'Request Another keeps your name and clears the song');
// 1 person
type('karaoke-request-song', 'Creep'); status = 'accepted'; position = 1;
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 3300)); });
ok(/1 person ahead of you/.test(q('karaoke-request-accepted').textContent), 'singular: "1 person ahead of you"');
await act(async () => { fireEvent.click(q('karaoke-request-another')); });
// rejected
type('karaoke-request-song', 'Nope'); status = 'rejected';
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 3300)); });
ok(!!q('karaoke-request-rejected') && /Request Not Available/.test(q('karaoke-request-rejected').textContent) && /Try requesting a different song/.test(q('karaoke-request-rejected').textContent), 'rejected: "Request Not Available"');
await act(async () => { fireEvent.click(q('karaoke-request-another')); });
// failure shows on the page, not in a pop-up
submitFails = { data: { detail: 'Name and song required' } }; type('karaoke-request-song', 'X');
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 100)); });
ok(/Name and song required/.test((q('karaoke-request-error') || {}).textContent || '') && alerts.length === 0, 'an error shows on the page (no browser pop-up)');
submitFails = {};
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 100)); });
ok(/Check your connection/.test((q('karaoke-request-error') || {}).textContent || ''), 'no connection: a friendly message');
// leaving the page stops the checking
submitFails = null; status = 'pending';
await act(async () => { fireEvent.click(q('karaoke-request-submit')); await new Promise(r => setTimeout(r, 100)); });
cleanup(); const g2 = statusGets; await wait(3500);
ok(statusGets === g2, 'closing the page stops the status checks');
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke request page: checks ok');
process.exit(0);
