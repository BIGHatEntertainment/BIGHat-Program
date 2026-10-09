// alpha.70: Karaoke rules (queue, preload gate, fade timing from the audience clock, volume, filler order)
import * as f from '/root/workspace/BIGHat-Program/frontend/src/pages/karaoke/karaokeFlow.js';
const fails = []; const ok = (c, m) => { if (!c) fails.push(m); };
const eq = (a, b, m) => ok(JSON.stringify(a) === JSON.stringify(b), m + ' -> got ' + JSON.stringify(a));
const near = (a, b, m) => ok(Math.abs(a - b) < 1e-9, m + ' -> got ' + a);

// next singer
const q = [
  { id: 'a', status: 'waiting', position: 2, song_title: 'A', embed_url: 'u' },
  { id: 'b', status: 'waiting', position: 1, song_title: '', embed_url: '' },
  { id: 'c', status: 'current', position: 0, song_title: 'C', embed_url: 'u' },
  { id: 'd', status: 'done', position: 3 },
];
ok(f.nextWaiting(q).id === 'b', 'next singer is the lowest-position WAITING one (not current, not done)');
ok(f.nextWaiting([]) === null && f.nextWaiting(null) === null, 'empty queue has no next singer');
eq(f.nextSingerState(q, 100).reason, 'no_song', 'a singer with no song picked cannot start');
const q2 = q.filter((e) => e.id !== 'b');
ok(f.nextSingerState(q2, 0).enabled === true && f.nextSingerState(q2, 99).enabled === true, 'alpha.103: a waiting singer with a song can ALWAYS start, however little has loaded (no loading lock)');
ok(f.nextSingerState(q2, 100).enabled === true, 'still enabled at 100%');
eq(f.nextSingerState([], 100).reason, 'no_one_waiting', 'no one waiting');
ok(f.nextWaiting(q).id === 'b' && q[0].id === 'a', 'does not reorder the queue it was given');

// fade timing from the AUDIENCE clock
eq(f.secondsUntilFade(10, 200), 187, 'fade starts 3 s before the end: 10 s in on a 200 s song -> 187 s to go');
eq(f.secondsUntilFade(197, 200), 0, 'at 197 of 200 it is time to fade');
eq(f.secondsUntilFade(250, 200), 0, 'past the end never goes negative');
eq(f.secondsUntilFade(1, 2), 0, 'a song shorter than the fade fades immediately');
eq(f.secondsUntilFade(5, 0), null, 'unknown duration -> cannot tell');
eq(f.songProgress(50, 200).percent, 25, 'progress is a percent of the audience time');
eq(f.songProgress(300, 200).percent, 100, 'progress never passes 100');
eq(f.songProgress(5, 0).remaining, null, 'unknown duration has no remaining time');
eq(f.clock(125), '2:05', 'clock 125 -> 2:05'); eq(f.clock(9), '0:09', 'clock 9 -> 0:09'); eq(f.clock(-4), '0:00', 'clock never negative'); eq(f.clock(3600), '60:00', 'clock hour');

// what the host reads from the audience
const idle = f.readAudience(null);
ok(!idle.started && !idle.ending && !idle.ended, 'no audience report yet -> nothing started, ending or ended');
ok(f.readAudience({ audience_started: true, audience_time: 100, audience_duration: 200 }).ending === false, 'mid-song is not ending');
ok(f.readAudience({ audience_started: true, audience_time: 198, audience_duration: 200 }).ending === true, 'last 3 s is ending');
ok(f.readAudience({ audience_started: true, audience_time: 199, audience_duration: 200, video_ended: true }).ending === false, 'once ended it is not "ending" any more');
ok(f.readAudience({ audience_started: true, video_ended: true }).ended === true, 'ended is passed through');
ok(f.readAudience({ audience_started: false, audience_time: 198, audience_duration: 200 }).ending === false, 'a song that never started cannot be ending');

// volume
near(f.fillerVolume(0.8, 0.5), 0.6, 'filler volume = master x 1.5 x filler (0.8 x 1.5 x 0.5 = 0.6)');
eq(f.splitVolume(0.6), { element: 0.6, gain: 1 }, 'under 100%: the audio element does it');
eq(f.splitVolume(1.5), { element: 1, gain: 1.5 }, 'over 100%: element at max, gain node does the rest');
near(f.fillerVolume(1, 1), 1.5, 'max is 150%');

// filler order
const tracks = [{ id: '1', artist: 'queen' }, { id: '2', artist: 'ABBA' }, { id: '3', artist: 'ABBA' }, { id: '4' }];
const g = f.groupByArtist(tracks);
eq(g.map((x) => x.artist), ['ABBA', 'queen', 'Unknown'].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())), 'artists sorted A-Z ignoring case');
eq(g.find((x) => x.artist === 'ABBA').tracks.length, 2, 'tracks grouped under their artist');
ok(g.find((x) => x.artist === 'Unknown').tracks.length === 1, 'no artist -> Unknown');
const a = [1, 2, 3, 4, 5, 6];
const s = f.shuffle(a, () => 0.3);
eq(a, [1, 2, 3, 4, 5, 6], 'shuffle does not change the original');
eq([...s].sort(), [1, 2, 3, 4, 5, 6], 'shuffle keeps every track once');
eq(f.shuffle([], Math.random), [], 'shuffle of nothing is nothing');
eq(f.nextTrackIndex(0, 3), 1, 'next track'); eq(f.nextTrackIndex(2, 3), 0, 'wraps to the first track'); eq(f.nextTrackIndex(0, 0), -1, 'no tracks -> -1');
near(f.fadeVolume(0, 0.6, 15, 30), 0.3, 'fade-in is linear: half way is half volume');
near(f.fadeVolume(0.6, 0, 30, 30), 0, 'fade-out ends at zero'); near(f.fadeVolume(0, 1, 99, 30), 1, 'fade never overshoots');

if (fails.length) { console.log('FAILED:\n - ' + fails.join('\n - ')); process.exit(1); }
console.log('karaoke rules: checks ok');
