// alpha.72: Employee form (temp password, real error messages) + dashboard header (no Schedule Admin tab)
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/schedule', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
dom.window.confirm = globalThis.confirm = () => true;
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const { MemoryRouter } = await import('react-router-dom');
const axios = (await import('axios')).default;
const sonner = await import('sonner');
const toasts = []; sonner.toast.success = (m) => toasts.push(['ok', m]); sonner.toast.error = (m) => toasts.push(['err', m]);
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const wait = (ms = 200) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

let employees = [{ id: 'e1', name: 'Ann Admin', email: 'ann@x.com', phone: '', is_admin: true }];
let postReply = null, postError = null; const posts = [], puts = [];
axios.get = async () => ({ data: employees });
axios.post = async (u, body) => { posts.push({ u, body }); if (postError) { const e = new Error('x'); e.response = postError; throw e; } return { data: postReply }; };
axios.put = async (u, body) => { puts.push({ u, body }); return { data: {} }; };
axios.delete = async () => ({ data: {} });
const { default: EmployeeManager } = await import('/tmp/rtest/emgr.bundle.mjs');
const { default: Header } = await import('/tmp/rtest/hdr.bundle.mjs');
const byText = (re, tag = 'button') => [...document.querySelectorAll(tag)].find(b => re.test(b.textContent));
const fill = async (name, email) => {
  await act(async () => { fireEvent.click(byText(/Add Employee/i)); }); await wait(100);
  fireEvent.change(document.getElementById('name'), { target: { value: name } });
  fireEvent.change(document.getElementById('email'), { target: { value: email } });
};
const submit = async () => { await act(async () => { fireEvent.submit(document.querySelector('form')); await new Promise(r => setTimeout(r, 200)); }); };

// ---------- employee form
render(React.createElement(MemoryRouter, null, React.createElement(EmployeeManager))); await wait(300);
ok(/Ann Admin/.test(document.body.textContent), 'employees load');
// 1. a new employee: the temporary password is shown once
postReply = { id: 'e2', name: 'Sam Host', email: 'sam@x.com', temp_password: 'Swift-Otter-4821' };
await fill('Sam Host', 'sam@x.com'); await submit();
ok(posts.length === 1 && posts[0].body.name === 'Sam Host' && posts[0].body.email === 'sam@x.com', 'saves the new employee');
ok(!!q('temp-password-dialog') && /Swift-Otter-4821/.test(q('temp-password-value').textContent), 'shows the temporary password once');
ok(/Sam Host can now sign in/.test(q('temp-password-dialog').textContent) && /sam@x\.com/.test(q('temp-password-dialog').textContent), 'says who it is for and which email to sign in with');
ok(toasts.some(t => t[0] === 'ok' && /added/i.test(t[1])), 'and says the employee was added');
await act(async () => { fireEvent.click(q('temp-password-close')); }); await wait(50);
ok(!q('temp-password-dialog'), 'Done closes it, and it is gone for good');
// 2. a reply with no temp password (the shared default case) shows no pop-up
toasts.length = 0; postReply = { id: 'e3', name: 'Pat', email: 'pat@x.com' };
await fill('Pat', 'pat@x.com'); await submit();
ok(!q('temp-password-dialog'), 'no temporary password in the reply -> no pop-up');
// 3. the real reason is shown
toasts.length = 0; postError = { data: { detail: 'An employee with that email already exists.' } };
await fill('Dupe', 'sam@x.com'); await submit();
ok(toasts.some(t => t[0] === 'err' && t[1] === 'An employee with that email already exists.'), 'a duplicate email shows the real reason, not "Failed to save": ' + JSON.stringify(toasts));
toasts.length = 0; postError = { data: { detail: 'Please enter a valid email address.' } };
await fill('Bad', 'bad@x.com'); await submit();
ok(toasts.some(t => /valid email/.test(t[1])), 'a bad email shows its reason');
toasts.length = 0; postError = {};
await fill('Offline', 'off@x.com'); await submit();
ok(toasts.some(t => t[0] === 'err' && /Check your connection/.test(t[1])), 'no server reply -> a friendly connection message');
postError = null;
// 4. editing sends no password
puts.length = 0;
await act(async () => { fireEvent.click(document.querySelector('[data-testid^="edit-employee"]') || byText(/^$/) || document.querySelectorAll('button')[1]); });
cleanup();

// ---------- header
globalThis.__triviaEnv.user = { id: 'u', name: 'Pat', role: 'admin' };
render(React.createElement(MemoryRouter, null, React.createElement(Header)));
await wait(100);
const nav = [...document.querySelectorAll('nav button, nav a, nav div')].map(n => n.textContent.trim()).filter(Boolean);
ok(!document.body.textContent.includes('Schedule Admin'), 'the dashboard header no longer has a Schedule Admin tab: ' + document.body.textContent.slice(0, 120));
const navText = [...document.querySelectorAll('nav')].map(n => n.textContent).join(' ');
ok(/Dashboard/.test(navText) && /Schedule/.test(navText) && /Admin/.test(navText), 'Dashboard, Schedule and Admin tabs are still there: ' + navText);
cleanup();
globalThis.__triviaEnv.user = { id: 'h', name: 'Hal', role: 'host' };
render(React.createElement(MemoryRouter, null, React.createElement(Header))); await wait(100);
ok(!/Admin/.test([...document.querySelectorAll('nav')].map(n => n.textContent).join(' ')), 'a host sees no Admin tab');
cleanup();

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('employee form + header: checks ok');
process.exit(0);
