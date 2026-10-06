// alpha.82: the Story QR helper - relay link on success, plain reason on every kind of failure
const axios = (await import('axios')).default;
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const { publishStoryQr } = await import('/tmp/rtest/storyqr.bundle.mjs');
let seen = null;
axios.post = async (u, body, cfg) => { seen = { u, cfg }; return globalThis.__reply(); };

globalThis.__reply = () => ({ data: { success: true, url: 'https://api.bighat.live/d/AAAAAAAAAAAAAAAAAAAAAA', expires_at: 'x' } });
let r = await publishStoryQr('http://x/api', 'f7d5c4aa-2eb');
ok(r.url === 'https://api.bighat.live/d/AAAAAAAAAAAAAAAAAAAAAA' && r.message === null, 'success: the QR gets the relay link (never the PC address)');
ok(seen.u === 'http://x/api/story-generator/qr-publish/f7d5c4aa-2eb', 'asks the PC to publish the stored video by its id');
ok(seen.cfg.timeout >= 120000, 'waits long enough for a big upload');

globalThis.__reply = () => ({ data: { success: false, error: 'offline', message: 'Could not reach the QR service. Check the internet connection.' } });
r = await publishStoryQr('http://x/api', 'f1');
ok(r.url === null && /internet connection/.test(r.message), 'offline: no QR, and the host is told to check the internet');

globalThis.__reply = () => ({ data: { success: false } });
r = await publishStoryQr('http://x/api', 'f1');
ok(r.url === null && r.message.length > 10, 'a failure with no reason still gives a readable message');

globalThis.__reply = () => { const e = new Error('Network Error'); throw e; };
r = await publishStoryQr('http://x/api', 'f1');
ok(r.url === null && /not available/.test(r.message), 'the PC program itself unreachable/errored: no crash, plain message');

globalThis.__reply = () => ({ data: { success: true, url: '' } });
r = await publishStoryQr('http://x/api', 'f1');
ok(r.url === null, 'an empty link is never used for a QR');
console.log(fails.length ? 'FAILED:\n - ' + fails.join('\n - ') : 'story qr helper: checks ok');
process.exit(fails.length ? 1 : 0);
