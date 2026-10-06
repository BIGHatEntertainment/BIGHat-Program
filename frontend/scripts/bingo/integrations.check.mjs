// alpha.85: Admin > Integrations > Setup Package screen
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
for (const k of ['window','document','navigator','HTMLElement','Node','MutationObserver','getComputedStyle','requestAnimationFrame','cancelAnimationFrame','localStorage','URL','Blob']) { try { Object.defineProperty(globalThis, k, { value: dom.window[k] ?? globalThis[k], configurable: true, writable: true }); } catch {} }
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = (await import('react')).default; const { render, fireEvent, cleanup, act } = await import('@testing-library/react'); const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const _ce = console.error; console.error = (...a) => { const t = String(a[0] || ''); if (/The above error occurred|Uncaught/.test(t + (a[1] || ''))) fails.push('the screen crashed while drawing: ' + String(a[1] || a[0]).slice(0, 110)); };
let reachedEnd = false;
process.on('exit', (code) => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
process.on('uncaughtException', (e) => { fails.push('the screen crashed: ' + String(e.message || e).slice(0, 120)); });
const wait = (ms = 150) => act(async () => { await new Promise(r => setTimeout(r, ms)); });
const { default: Tab } = await import('/tmp/rtest/integrations.bundle.mjs');

let S, calls;
const reset = (over = {}) => { calls = []; S = { check: { ok: true, exists: true, version: 3, published_at: '2026-10-06T18:00:00Z', published_by: 'Office PC', counts: { venues: 2, people: 4, locations: 1 }, differs: true }, ...over }; };
const PLAN = { venues_new: ['Monkey Pants', 'Roses'], venues_changed: [], pricing_new: ['Monkey Pants'], pricing_changed: [], people_new: ['sam@x.com'], people_changed: [], roles_new: [], images_new: 2, differs: true, warnings: [] };
axios.get = async (u) => { calls.push(['GET', u]); if (u.endsWith('/check')) return { data: S.check }; if (u.endsWith('/export')) return { data: new Blob(['zip']) }; throw new Error('unexpected ' + u); };
axios.post = async (u, body) => {
  calls.push(['POST', u, body]);
  if (u.includes('/publish')) return { data: S.publish || { ok: true, version: 4, counts: {} } };
  if (u.includes('/pull?apply=false') || u.includes('/import?apply=false')) return { data: S.preview || { ok: true, applied: false, plan: PLAN } };
  if (u.includes('/pull?apply=true') || u.includes('/import?apply=true')) return { data: S.applied || { ok: true, applied: true, result: { venues_added: 2, people_added: [{ email: 'sam@x.com', name: 'Sam', role: 'host', temp_password: 'Blue-Tiger-42' }], roles_added: 1, images_added: 2, skipped: [] } } };
  if (u.includes('/transfer/start')) return { data: S.xstart || { ok: true, sent_to: 'ow***@x.com' } };
  if (u.includes('/transfer/confirm')) return { data: S.xconfirm || { ok: true, moved_to: 'new@x.com' } };
  throw new Error('unexpected ' + u);
};
let err = '', okmsg = '';
const mount = (isMaster = true) => render(React.createElement(Tab, { isMaster, setError: (m) => { err = m; }, setSuccess: (m) => { okmsg = m; } }));
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => { await act(async () => { fireEvent.click(q(id)); }); await wait(200); };
const T = () => document.body.textContent;

// 1) master sees all the actions and the differs warning, Google Drive / SharePoint are "coming next" and below the package
reset(); mount(true); await wait(300);
ok(!!q('pkg-btn-publish') && !!q('pkg-btn-pull') && !!q('pkg-btn-export') && !!q('pkg-btn-import'), 'master sees Publish, Pull, Save as file, Load from file');
ok(/version 3/.test(q('pkg-status')?.textContent || '') && /2 venues, 4 people/.test(T()), 'shows the latest version and what is in it');
ok(/does not match/.test(q('pkg-differs')?.textContent || '') && /Click "Pull setup"/.test(q('pkg-differs')?.textContent || ''), 'master is told this computer differs, and what to click');
ok(/Coming next/.test(q('integration-googledrive')?.textContent || '') && /Coming next/.test(q('integration-sharepoint')?.textContent || ''), 'Google Drive and SharePoint are shown as coming next');
ok(q('pkg-card').compareDocumentPosition(q('integration-googledrive')) & 4, 'the Setup Package is at the very top, above the other integrations');
cleanup();

// 2) an admin (not master) cannot act, is told to call the master
reset(); mount(false); await wait(300);
ok(!q('pkg-btn-publish') && !q('pkg-btn-pull') && !q('pkg-btn-import') && !q('pkg-transfer-open'), 'an admin sees NO publish/pull/file/transfer controls');
ok(/call your master admin/i.test(q('pkg-differs')?.textContent || ''), 'an admin who differs is told to call the master admin');
cleanup();

// 3) matches / none yet / cloud unreachable
reset({ check: { ok: true, exists: true, version: 3, differs: false, counts: {} } }); mount(true); await wait(300);
ok(!!q('pkg-matches') && !q('pkg-differs'), 'a matching computer shows the green "matches" line and no warning'); cleanup();
reset({ check: { ok: true, exists: false } }); mount(true); await wait(300);
ok(/No setup has been published/.test(q('pkg-none')?.textContent || '') && /click Publish/.test(q('pkg-none')?.textContent || ''), 'no package yet: the master is told to publish'); cleanup();
reset({ check: { ok: true, exists: false } }); mount(false); await wait(300);
ok(/Ask the master admin/.test(q('pkg-none')?.textContent || ''), 'no package yet: others are told to ask the master'); cleanup();
reset({ check: { ok: false, message: 'Could not reach the setup service. Check the internet connection, or use the file option.' } }); mount(true); await wait(300);
ok(/Could not reach/.test(q('pkg-unreachable')?.textContent || '') && /file option/.test(q('pkg-unreachable').textContent) && !!q('pkg-btn-import'), 'cloud down: plain message, and the file fallback is still there'); cleanup();

// 4) publish
reset(); mount(true); await wait(300); await click('pkg-btn-publish');
ok(calls.some(c => c[0] === 'POST' && c[1].endsWith('/publish')), 'Publish calls the publish route');
ok(/version 4/.test(okmsg), 'success message names the new version (got: ' + okmsg + ')'); cleanup();
reset({ publish: { ok: false, message: 'Another computer published a newer setup. Pull it first, then publish again.' } }); mount(true); await wait(300); await click('pkg-btn-publish');
ok(/newer setup/.test(err), 'a stale publish shows the plain reason (got: ' + err + ')'); cleanup();

// 5) pull: preview first, nothing applied until the master clicks Apply
reset(); mount(true); await wait(300); await click('pkg-btn-pull');
ok(!!q('pkg-preview') && /2 new venues/.test(q('pkg-plan-venues_new')?.textContent || '') && /Monkey Pants, Roses/.test(q('pkg-plan-venues_new').textContent), 'pull shows what will change before anything is written');
ok(/2 new location pictures/.test(q('pkg-plan-images')?.textContent || ''), 'the preview counts new pictures');
ok(!calls.some(c => c[1].includes('apply=true')), 'NOTHING is applied by the preview');
ok(!q('pkg-overwrite'), 'no "replace" option when nothing is different, only new');
await click('pkg-btn-apply');
ok(calls.some(c => c[1].includes('pull?apply=true&overwrite_changed=false')), 'Apply writes it in, without replacing existing details by default');
ok(!!q('pkg-result') && /2 venues, 1 people, 1 assignments, 2 pictures/.test(q('pkg-result').textContent), 'a result summary is shown');
ok(q('pkg-temp-sam@x.com')?.textContent === 'Blue-Tiger-42' && /shown only once/.test(q('pkg-temp-passwords').textContent), 'temporary passwords are shown, with the "only once" warning');
ok(!q('pkg-preview'), 'the preview closes after applying'); cleanup();

// 6) cancel; changed details need an explicit tick; a computer that already matches cannot apply
reset({ preview: { ok: true, plan: { ...PLAN, venues_new: [], pricing_new: [], people_new: [], images_new: 0, venues_changed: ['Monkey Pants'], differs: true } } }); mount(true); await wait(300); await click('pkg-btn-pull');
ok(!!q('pkg-overwrite') && !q('pkg-overwrite').checked, 'different details: a "replace" tick-box appears, OFF by default');
await act(async () => { fireEvent.click(q('pkg-overwrite')); }); await click('pkg-btn-apply');
ok(calls.some(c => c[1].includes('overwrite_changed=true')), 'ticking it sends overwrite_changed=true'); cleanup();
reset(); mount(true); await wait(300); await click('pkg-btn-pull'); await click('pkg-cancel');
ok(!q('pkg-preview') && !calls.some(c => c[1].includes('apply=true')), 'Cancel closes the preview and applies nothing'); cleanup();
reset({ preview: { ok: true, plan: { ...PLAN, venues_new: [], pricing_new: [], people_new: [], images_new: 0, differs: false } } }); mount(true); await wait(300); await click('pkg-btn-pull');
ok(!!q('pkg-plan-same') && q('pkg-btn-apply').disabled, 'a computer that already matches says so and cannot "apply"'); cleanup();

// 7) failures are shown plainly and leave things alone
reset({ preview: { ok: false, message: 'No setup has been published yet. The master admin needs to publish it first.' } }); mount(true); await wait(300); await click('pkg-btn-pull');
ok(/needs to publish/.test(err) && !q('pkg-preview'), 'a failed pull shows the reason and no preview'); cleanup();
reset({ applied: { ok: false, message: 'The setup could not be applied.' } }); mount(true); await wait(300); await click('pkg-btn-pull'); await click('pkg-btn-apply');
ok(/could not be applied/.test(err) && !q('pkg-result'), 'a failed apply shows the reason and no success result'); cleanup();
reset({ applied: { ok: true, applied: true, result: { venues_added: 1, people_added: [], roles_added: 0, images_added: 0, skipped: ['pricing for unknown venue Zed', 'image x.png: this computer has no place called Ghost'] } } });
mount(true); await wait(300); await click('pkg-btn-pull'); await click('pkg-btn-apply');
ok(/Some things were not added/.test(q('pkg-skipped')?.textContent || '') && /unknown venue Zed/.test(q('pkg-skipped').textContent) && !q('pkg-temp-passwords'), 'skipped items are listed; no password table when nobody was added'); cleanup();

// 8) file fallback: choose a file -> preview -> apply uses the file route
reset(); mount(true); await wait(300);
const file = new dom.window.File(['x'], 'bighat-setup-2026-10-06.bighatsetup');
await act(async () => { fireEvent.change(q('pkg-file-input'), { target: { files: [file] } }); }); await wait(300);
ok(!!q('pkg-preview') && calls.some(c => c[1].includes('/import?apply=false')), 'choosing a file shows a preview through the import route');
await click('pkg-btn-apply'); ok(calls.some(c => c[1].includes('/import?apply=true')), 'applying a file uses the import route'); cleanup();
reset(); mount(true); await wait(300); await click('pkg-btn-export');
ok(calls.some(c => c[0] === 'GET' && c[1].endsWith('/export')) && /Downloads folder|saved/i.test(okmsg), 'Save as a file calls export and says it was saved (got: ' + okmsg + ')');
ok(globalThis.__saved && globalThis.__saved.name.endsWith('.bighatsetup'), 'it hands the file to the shared saveBlob helper (the desktop-safe download), named .bighatsetup (got: ' + JSON.stringify(globalThis.__saved) + ')');
ok(!document.querySelector('a[download]'), 'it does NOT leave a hand-made <a download> link behind'); cleanup();
globalThis.__saved = null; globalThis.__saveResult = { ok: false, error: 'disk full' }; reset(); mount(true); await wait(300); await click('pkg-btn-export');
ok(/could not be saved/.test(err) && /disk full/.test(err), 'if saving fails the master sees why, not a false success (got: ' + err + ')'); cleanup(); globalThis.__saveResult = null;

// 9) transfer to a new email
reset(); mount(true); await wait(300); await click('pkg-transfer-open');
ok(q('pkg-btn-xfer-send').disabled, '"Send code" is disabled until an email is typed');
await act(async () => { fireEvent.change(q('pkg-transfer-email'), { target: { value: 'new@x.com' } }); });
await click('pkg-btn-xfer-send');
ok(calls.some(c => c[1].endsWith('/transfer/start') && c[2].to_email === 'new@x.com') && /ow\*\*\*@x.com/.test(okmsg), 'sends the code and shows the masked current email (got: ' + okmsg + ')');
ok(!!q('pkg-transfer-code') && q('pkg-btn-xfer-confirm').disabled, 'a code box appears, and "Move it" waits for 6 digits');
await act(async () => { fireEvent.change(q('pkg-transfer-code'), { target: { value: '123456' } }); }); await click('pkg-btn-xfer-confirm');
ok(calls.some(c => c[1].endsWith('/transfer/confirm') && c[2].code === '123456') && /moved to new@x.com/i.test(okmsg), 'confirming moves it and says where (got: ' + okmsg + ')'); cleanup();
reset({ xconfirm: { ok: false, message: 'That code is not right.' } }); mount(true); await wait(300); await click('pkg-transfer-open');
await act(async () => { fireEvent.change(q('pkg-transfer-email'), { target: { value: 'new@x.com' } }); }); await click('pkg-btn-xfer-send');
await act(async () => { fireEvent.change(q('pkg-transfer-code'), { target: { value: '000000' } }); }); await click('pkg-btn-xfer-confirm');
ok(/not right/.test(err) && !!q('pkg-transfer'), 'a wrong code shows the reason and keeps the box open'); cleanup();

// 10) double click only sends once
reset(); let release; axios.post = (u, b) => { calls.push(['POST', u, b]); return new Promise((r) => { release = () => r({ data: { ok: true, version: 9 } }); }); };
mount(true); await wait(300);
await act(async () => { fireEvent.click(q('pkg-btn-publish')); fireEvent.click(q('pkg-btn-publish')); }); await wait(50);
ok(calls.filter(c => c[0] === 'POST' && c[1].endsWith('/publish')).length === 1, 'double-click sends publish once');
await act(async () => { release(); }); await wait(100); cleanup();

reachedEnd = true;
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'integrations tab: all checks ok');
process.exit(fails.length ? 1 : 0);
