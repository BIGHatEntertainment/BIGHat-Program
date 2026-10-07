// alpha.91: the quiet song check. Run: node song_guard.check.mjs (from a folder with node_modules)
import { parseMediaUrl, isRightVideo, takePreloaded, mediaUrl, checkNextSong } from '../../src/pages/bingo/songGuard.js';
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
let reachedEnd = false;
process.on('exit', () => { if (!reachedEnd) { console.log('FAILED: the check stopped early and never reached its summary'); process.exitCode = 1; } });
const A = 'http://x/api';

// the address says which round and which song it is
ok(JSON.stringify(parseMediaUrl(mediaUrl(A, '1990s', 14))) === JSON.stringify({ theme: '1990s', number: 14 }), 'a stream address is read back into its round and number');
ok(parseMediaUrl(mediaUrl(A, 'Hip Hop & R&B', 7)).theme === 'Hip Hop & R&B', 'a round name with spaces and symbols survives the round trip');
ok(parseMediaUrl('blob:http://x/abc') === null && parseMediaUrl(null) === null && parseMediaUrl('http://x/other') === null, 'anything that is not a stream address reads as nothing');
ok(parseMediaUrl(mediaUrl(A, '1990s', 14) + '?v=2').number === 14, 'a query string does not hide the number');

// the right video for the right round and number, and only that
ok(isRightVideo(mediaUrl(A, '1990s', 14), '1990s', 14), 'right round and right number passes');
ok(isRightVideo(mediaUrl(A, '1990s', 14), '1990s', '14'), 'a number written as text still matches');
ok(!isRightVideo(mediaUrl(A, '1980s', 14), '1990s', 14), 'the same number from ANOTHER round is refused');
ok(!isRightVideo(mediaUrl(A, '1990s', 15), '1990s', 14), 'another number from the same round is refused');
ok(!isRightVideo(undefined, '1990s', 14) && !isRightVideo('', '1990s', 14), 'a missing address is refused');
ok(isRightVideo('blob:http://x/abc', '1990s', 14, { theme: '1990s', number: 14 }), 'a local file made for this round and number passes');
ok(!isRightVideo('blob:http://x/abc', '1990s', 14, { theme: '1980s', number: 14 }), 'a local file made for another round is refused');
ok(!isRightVideo('blob:http://x/abc', '1990s', 14), 'a local file with no record of what it was made for is refused');

// the preload cache: only an entry for THIS round and THIS number is ever handed back
const mk = (theme, n) => ({ url: mediaUrl(A, theme, n), ready: true, theme, number: n });
let cache = { 2: mk('1980s', 2), 5: mk('1990s', 5), 9: { url: mediaUrl(A, '1990s', 9), ready: true } /* no record of its round */ };
ok(takePreloaded(cache, '1990s', 2) === null && !(2 in cache), "another round's preloaded video is dropped, never used");
ok(takePreloaded(cache, '1990s', 5)?.number === 5 && 5 in cache, "this round's preloaded video is returned (and kept until the song starts)");
ok(takePreloaded(cache, '1990s', 9) === null && !(9 in cache), 'a preloaded entry that does not say which round it is for is dropped');
cache = { 3: { ...mk('1990s', 3), url: mediaUrl(A, '1990s', 4) } };
ok(takePreloaded(cache, '1990s', 3) === null && !(3 in cache), 'an entry filed under 3 whose address is song 4 is dropped');
ok(takePreloaded({}, '1990s', 1) === null, 'an empty cache gives nothing');

// the quiet self-check for the proposed next song
const T = '1990s';
const list = [{ number: 1, title: 'One' }, { number: 2, title: 'Two' }, { number: 3, title: 'Three' }];
const files = { 1: 'f1', 2: 'f2', 3: 'f3' };
const good = (n) => ({ url: mediaUrl(A, T, n), ready: true, theme: T, number: n });
const chk = (o) => checkNextSong({ nextSong: list[1], songList: list, videoFiles: files, cache: {}, theme: T, pool: [2, 3, 1], ...o });
ok(chk({ cache: { 2: good(2) } }).ok, 'everything matches: nothing to fix');
ok(chk({ nextSong: null }).ok, 'no proposed song: nothing to check');
let r = chk({ cache: {} });
ok(!r.ok && r.fixes.length === 1 && r.fixes[0].do === 'preload' && r.fixes[0].number === 2, 'nothing preloaded yet: preload the right song: ' + JSON.stringify(r.fixes));
r = chk({ cache: { 2: { ...good(2), theme: '1980s', url: mediaUrl(A, '1980s', 2) } } });
ok(r.fixes.some(f => f.do === 'drop' && f.number === 2) && r.fixes.some(f => f.do === 'preload' && f.number === 2), "another round's video for song 2: dropped and the right one preloaded: " + JSON.stringify(r.fixes));
r = chk({ cache: { 2: { ...good(2), theme: '1980s' } } });
ok(r.fixes.some(f => f.do === 'drop') && r.fixes.some(f => f.do === 'preload'), 'an entry that says it was made for another round (even with a matching address) is dropped and rebuilt: ' + JSON.stringify(r.fixes));
r = chk({ cache: { 2: { ...good(2), url: mediaUrl(A, T, 3) } } });
ok(r.fixes.some(f => f.do === 'drop') && r.fixes.some(f => f.do === 'preload'), 'song 2 filed with the address of song 3: dropped and rebuilt: ' + JSON.stringify(r.fixes));
r = chk({ cache: { 2: { url: mediaUrl(A, T, 2), ready: true } } });
ok(r.fixes.some(f => f.do === 'drop') && r.fixes.some(f => f.do === 'preload'), 'an entry with no record of its round: dropped and rebuilt');
r = chk({ nextSong: { number: 2, title: 'Other Round Two' }, cache: { 2: good(2) } });
ok(r.fixes.length === 1 && r.fixes[0].do === 'replace-next' && r.fixes[0].song.title === 'Two', "the title on screen is another round's: replaced by this round's: " + JSON.stringify(r.fixes));
r = chk({ nextSong: { number: 77, title: 'Ghost' }, pool: [9, 3] });
ok(!r.ok && r.fixes.length === 1 && r.fixes[0].song.number === 3, 'a song that is not in this round at all: the first real song of the pool is used: ' + JSON.stringify(r.fixes));
r = chk({ nextSong: { number: 77, title: 'Ghost' }, pool: [9] });
ok(!r.ok && r.fixes.length === 0, 'nothing valid to fall back to: no fix, and no crash');
r = chk({ videoFiles: {}, cache: {} });
ok(r.ok, 'a song with no video file at all is left alone (nothing to preload)');

reachedEnd = true;
if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('song guard: checks ok');
