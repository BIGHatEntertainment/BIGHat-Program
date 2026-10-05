// alpha.79: the Schedule's Add Event form + Monthly Calendar
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/schedule', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage']) {
  try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {}
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default;
const { render, fireEvent, cleanup, act } = await import('@testing-library/react');
const axios = (await import('axios')).default;
const sonner = await import('sonner');
const toasts = []; sonner.toast.success = (m) => toasts.push(['ok', m]); sonner.toast.error = (m) => toasts.push(['err', m]);
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const wait = (ms = 150) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const byText = (re, tag = 'button') => [...document.querySelectorAll(tag)].find(b => re.test(b.textContent));
const submit = async () => { await act(async () => { fireEvent.submit(document.querySelector('form')); await new Promise(r => setTimeout(r, 200)); }); };
const lastErr = () => (toasts.filter(t => t[0] === 'err').pop() || [])[1] || '';

// ================= Add Event form =================
let venues = [], events = []; const posts = [];
axios.get = async (u) => ({ data: /venues/.test(u) ? venues : /employees/.test(u) ? [] : events });
axios.post = async (u, body) => { posts.push({ u, body }); return { data: { id: 'new', ...body } }; };
axios.put = async () => ({ data: {} }); axios.delete = async () => ({ data: {} });
const { default: EventManager } = await import('/tmp/rtest/evmgr.bundle.mjs');
const open = async () => { await act(async () => { fireEvent.click(byText(/Add Event/i)); }); await wait(100); };
const set = (id, v) => fireEvent.change(document.getElementById(id), { target: { value: v } });

// 1. no venues exist yet -> the host is told what to do, instead of an empty pick-list
render(React.createElement(EventManager, { currentUser: { id: 'a', is_admin: true } })); await wait(300);
await open();
ok(document.querySelector('[data-testid="no-venues-hint"]'), 'no venues: the form says to add venues first');

// 2. blank form -> says exactly what is missing, sends nothing
posts.length = 0; toasts.length = 0;
await submit();
ok(posts.length === 0, 'blank form: nothing is sent');
ok(/Event Title/.test(lastErr()) && /Venue/.test(lastErr()) && /Date/.test(lastErr()) && /Time/.test(lastErr()), 'blank form: names every missing field (got: ' + lastErr() + ')');
cleanup();

// 3. with venues; choose none -> "Venue" is named
venues = [{ id: 'v1', name: 'Monkey Pants' }, { id: 'v2', name: 'Roses By The Stairs' }];
render(React.createElement(EventManager, { currentUser: { id: 'a', is_admin: true } })); await wait(300);
await open();
ok(!document.querySelector('[data-testid="no-venues-hint"]'), 'with venues: no warning');
set('title', 'Trivia Night'); set('date', '2026-10-12'); set('time', '19:00');
posts.length = 0; toasts.length = 0; await submit();
ok(posts.length === 0 && /Venue/.test(lastErr()) && !/Date|Time|Title/.test(lastErr()), 'only the Venue is missing -> only Venue is named (got: ' + lastErr() + ')');

// 4. valid event, with pay 0 and a special event
posts.length = 0; toasts.length = 0;
await act(async () => { fireEvent.click([...document.querySelectorAll('[role="option"]')].find(o => o.dataset.value === 'v2')); }); await wait(50);
set('pay_rate', '0'); set('duration_hours', '2.5'); set('notes', 'bring a mic');
await act(async () => { fireEvent.click(document.getElementById('is_special_event')); }); await wait(50);
await submit();
const p = posts.find(x => /\/events$/.test(x.u))?.body;
ok(!!p, 'valid form: the event is sent');
ok(p && p.venue_id === 'v2' && p.title === 'Trivia Night' && p.event_type === 'Trivia', 'venue/title/type sent');
ok(p && p.duration_hours === 2.5, 'duration sent as a number');
ok(p && p.pay_rate === 0, 'a pay rate of 0 is kept as 0, not dropped to empty (got ' + (p && p.pay_rate) + ')');
ok(p && p.is_special_event === true, 'special event flag sent');
ok(p && p.notes === 'bring a mic', 'notes sent');
ok(p && /^2026-10-1[23]T/.test(p.date), 'date sent as a date-time');
ok(toasts.some(t => t[0] === 'ok'), 'success message shown');
cleanup();

// 5. EDITING an event that is paid $0/hour must keep the 0 (it used to turn into an empty box)
events = [{ id: 'e1', title: 'Charity Night', event_type: 'Trivia', venue_id: 'v1', date: '2026-10-20T19:00:00.000Z', duration_hours: 2, pay_rate: 0, notes: '', is_special_event: false }];
render(React.createElement(EventManager, { currentUser: { id: 'a', is_admin: true } })); await wait(300);
ok(/\$0\/hour/.test(document.body.textContent), 'a $0/hour event shows its pay on the list');
await act(async () => { fireEvent.click(document.querySelector('button[title="Edit event"]')); }); await wait(100);
ok(document.getElementById('pay_rate') && document.getElementById('pay_rate').value === '0', 'editing a $0/hour event shows 0, not blank (got "' + (document.getElementById('pay_rate') || {}).value + '")');
events = [];
cleanup();

// ================= Monthly calendar =================
const { default: MonthlyCalendarDialog } = await import('/tmp/rtest/mcal.bundle.mjs');
const now = new Date(); const Y = now.getFullYear(), M = now.getMonth();
const at = (d, h, m = 0) => new Date(Y, M, d, h, m).toISOString();
const evs = [
  { id: 'a', title: 'Trivia Night', event_type: 'Trivia', venue_id: 'v1', date: at(12, 19), claimed_by: null },
  { id: 'b', title: 'Trivia Night', event_type: 'Trivia', venue_id: 'v2', date: at(12, 20), claimed_by: 'me' },
  { id: 'c', title: 'Halloween Bash', event_type: 'Special', venue_id: 'v1', date: at(28, 21), is_special_event: true },
  { id: 'd', title: 'Early Karaoke', event_type: 'Karaoke', venue_id: 'v2', date: at(12, 17) },
  { id: 'e', title: 'Next Month Bingo', event_type: 'Music Bingo', venue_id: 'v1', date: new Date(Y, M + 1, 3, 19).toISOString() },
  { id: 'f', title: 'Mystery', event_type: 'Brand New Type', venue_id: 'v9', date: at(5, 19) },
];
const cal = (props = {}) => render(React.createElement(MonthlyCalendarDialog, { open: true, onOpenChange() {}, events: evs, venues, currentUserId: 'me', onEventClick() {}, ...props }));
const chips = () => [...document.querySelectorAll('[data-testid="calendar-event"]')];
cal(); await wait(100);
ok(chips().length === 5, 'this month shows its 5 events, not next month (got ' + chips().length + ')');
ok(chips().some(c => /Monkey Pants/.test(c.textContent)) && chips().some(c => /Roses By The Stairs/.test(c.textContent)), 'each event shows WHERE it is');
const day12 = chips().filter(c => /Trivia Night|Early Karaoke/.test(c.textContent));
ok(day12.length === 3, 'three events on the 12th are all there');
ok(/Early Karaoke/.test(day12[0].textContent), 'the earliest event on a day comes first (got ' + day12[0].textContent.slice(0, 30) + ')');
ok(/★/.test(chips().find(c => /Halloween/.test(c.textContent)).textContent), 'a special event is marked with a star');
ok(/Mystery/.test(document.body.textContent), 'an event with an unknown type/venue still appears');
ok(chips().find(c => /Mystery/.test(c.textContent)).title.includes('Mystery'), 'hover title has the event name');
// filter
const filter = document.querySelector('[data-testid="calendar-venue-filter"]');
ok(!!filter, 'location filter is shown');
const btns = [...filter.querySelectorAll('button')].map(b => b.textContent);
ok(btns[0] === 'All locations' && btns.includes('Monkey Pants') && btns.includes('Roses By The Stairs'), 'filter lists All + each location with an event this month (got ' + btns.join('|') + ')');
ok(!btns.some(b => /Next Month/.test(b)), 'filter does not list places with no event this month');
await act(async () => { fireEvent.click([...filter.querySelectorAll('button')].find(b => b.textContent === 'Monkey Pants')); }); await wait(50);
ok(chips().length === 2 && chips().every(c => /Monkey Pants/.test(c.textContent)), 'filtering to one location shows only its events (got ' + chips().length + ')');
await act(async () => { fireEvent.click([...document.querySelectorAll('[data-testid="calendar-venue-filter"] button')][0]); }); await wait(50);
ok(chips().length === 5, '"All locations" brings everything back');
ok(/Special/.test(document.body.textContent) && document.querySelector('.bg-purple-500'), 'legend includes Special');
cleanup();
// no venues passed (older page) -> still works, no filter
cal({ venues: [] }); await wait(100);
ok(chips().length === 5 && !document.querySelector('[data-testid="calendar-venue-filter"]'), 'without venue info the calendar still shows events (no filter)');
cleanup();
// empty month
cal({ events: [] }); await wait(100);
ok(chips().length === 0, 'empty calendar renders');

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('schedule form + calendar: checks ok');
