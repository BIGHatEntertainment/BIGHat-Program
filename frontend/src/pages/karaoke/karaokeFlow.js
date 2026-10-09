// alpha.70: the Karaoke rules as plain functions, so they can be tested without a screen.
// The Player calls these. Nothing here touches the page, the network or timers.

export const FADE_SECONDS = 3;          // the last 3 seconds of a song fade out, filler fades back in over 3 seconds
export const PRELOAD_READY = 100;       // alpha.89: "Next Singer" waits until the audience says the buffer is enough (percent of what we NEED)
export const BUFFER_NEED_SECONDS = 45;  // alpha.89: how many seconds of the song must be buffered up front (a short song needs all of it)
export const AMP_FACTOR = 1.5;          // master volume goes to 150%
export const FILLER_FADE_STEPS = 30;

/** Real volume to give the filler player: master x boost x filler slider (can be over 1, then the gain node boosts it). */
export const fillerVolume = (master, filler) => master * AMP_FACTOR * filler;

/** Split a requested volume into what the audio element takes (max 1) and what the gain node takes. */
export const splitVolume = (v) => (v <= 1 ? { element: v, gain: 1 } : { element: 1, gain: v });

/** The singer who sings next: the first waiting one. */
export const nextWaiting = (queue) => (queue || []).filter((e) => e.status === "waiting").sort((a, b) => a.position - b.position)[0] || null;

/** Does this waiting singer have a song picked? Only singers with a song can be started. */
export const hasSong = (entry) => !!(entry && entry.song_title && entry.embed_url);

/**
 * alpha.89: how much of the song is buffered, as a percent of what we need.
 * YouTube only buffers part of a paused video, so "enough" is the first BUFFER_NEED_SECONDS
 * (or the whole song when it is shorter). loadedFraction is 0..1 from YouTube's getVideoLoadedFraction().
 */
export function bufferStatus(loadedFraction, duration, need = BUFFER_NEED_SECONDS) {
  const d = Number(duration) || 0;
  const f = Math.max(0, Math.min(1, Number(loadedFraction) || 0));
  if (d <= 0) return { percent: 0, bufferedSeconds: 0, ready: false };
  const target = Math.min(need, d);
  const bufferedSeconds = f * d;
  const percent = Math.max(0, Math.min(100, Math.round((bufferedSeconds / target) * 100)));
  return { percent, bufferedSeconds: Math.round(bufferedSeconds * 10) / 10, ready: bufferedSeconds >= target - 0.25 };
}

/**
 * alpha.89: what the host should SHOW for the queued singer's buffer.
 *  state: "none" (no song / nobody next), "no_screen" (TV window not open, so nothing can load),
 *         "loading" (bar), "ready" (green).
 */
export function bufferView({ next, preload, audienceOpen }) {
  if (!next || !hasSong(next)) return { state: "none", percent: 0 };
  const pre = preload && preload.singer_id === next.id ? preload : null;
  if (pre && pre.ready) return { state: "ready", percent: 100 };
  if (!audienceOpen) return { state: "no_screen", percent: pre ? Math.min(99, pre.percent || 0) : 0 };
  if (pre && pre.error) return { state: "error", percent: pre.percent || 0, error: pre.error };
  return { state: "loading", percent: pre ? Math.min(99, pre.percent || 0) : 0 };
}

/** alpha.89: true on the moment a singer's buffer turns ready (so the host is told ONCE per singer). */
export const justBecameReady = (prevReadyFor, view, singerId) => view.state === "ready" && prevReadyFor !== singerId;

/**
 * Can the host press Next Singer now?
 *  - someone must be waiting and have a song
 *  - the video must be loaded enough (or it was never going to preload, e.g. no internet check)
 */
export function nextSingerState(queue, preloadPercent) {
  const next = nextWaiting(queue);
  if (!next) return { enabled: false, reason: "no_one_waiting" };
  if (!hasSong(next)) return { enabled: false, reason: "no_song", singer: next };
  // alpha.103: NO loading lock. The first port had none; a slow or failed preload must never stop the host from starting a song.
  return { enabled: true, reason: "ready", singer: next };
}

/**
 * Seconds until the "fade out" should start, from the AUDIENCE's real clock.
 * Returns 0 when it is time (or the song is shorter than the fade), null when we cannot tell yet.
 */
export function secondsUntilFade(audienceTime, duration) {
  if (!duration || duration <= 0) return null;
  return Math.max(0, duration - FADE_SECONDS - (audienceTime || 0));
}

/** Where is the song, as the audience sees it? Used for the progress bar. */
export function songProgress(audienceTime, duration) {
  if (!duration || duration <= 0) return { percent: 0, elapsed: audienceTime || 0, remaining: null };
  const t = Math.min(audienceTime || 0, duration);
  return { percent: Math.round((t / duration) * 100), elapsed: t, remaining: Math.max(0, duration - t) };
}

/** mm:ss */
export const clock = (secs) => {
  const s = Math.max(0, Math.floor(secs || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

/**
 * What should the host do on the latest audience report?
 *  - started   -> remember the song is really on screen
 *  - ending    -> true during the last FADE_SECONDS (the screen is fading)
 *  - ended     -> the song is over: finish the singer and bring filler back
 * `playback` is what the server holds (session/playback).
 */
/** alpha.96: what a YouTube player error means, in words a host can act on. `code` is YouTube's number, or one of our own words. */
export function explainVideoError(code) {
  const c = String(code || "");
  if (!c) return "";
  if (c === "101" || c === "150") return "The owner of this video does not allow it to be played outside YouTube.";
  if (c === "100") return "This video was removed or is private.";
  if (c === "2") return "This video link is not valid.";
  if (c === "5") return "The video player had a problem with this video.";
  if (c.startsWith("fallback_")) {   // alpha.108: YouTube's own player gave up and the TV switched to the downloaded file
    const why = c.slice(9);
    if (why === "150" || why === "101") return "YouTube does not allow this song to be embedded (error " + why + "). The TV is using the downloaded file instead.";
    if (why === "153") return "YouTube rejected the player setup (error 153). The TV is using the downloaded file instead.";
    if (why === "timeout") return "YouTube's player did not start in time. The TV is using the downloaded file instead.";
    if (why === "no_youtube") return "The TV could not reach YouTube's player. It is using the downloaded file instead.";
    return "YouTube's player had a problem (" + why + "). The TV is using the downloaded file instead.";
  }
  if (c === "stream") return "The song could not be downloaded for the TV. Check the internet connection, or pick another song.";
  if (c === "stream_signin") return "YouTube wants a sign-in before it will give this song. Sign in to YouTube once in Edge or Chrome on this PC, then try again.";
  if (c === "stream_blocked") return "YouTube refused to send this song (403). Try another version of the song.";
  if (c === "stream_ratelimit") return "YouTube is limiting downloads from this connection. Wait a few minutes.";
  if (c === "stream_ffmpeg") return "The video tool (ffmpeg) is missing from this install.";
  if (c === "stream_network") return "This PC cannot reach YouTube. Check its internet connection.";
  if (c === "stream_private" || c === "stream_unavailable") return "This video is private or no longer available. Pick another version.";
  if (c === "stream_region") return "This video is blocked in this country. Pick another version.";
  if (c === "stream_age") return "This video is age-restricted. Pick another version.";
  if (c.startsWith("stream_")) return "The song could not be downloaded for the TV. Pick another version.";
  if (c === "no_youtube") return "The TV screen could not reach YouTube. Check its internet connection.";
  return "This video could not be played.";
}

export function readAudience(playback) {
  const pb = playback || {};
  const duration = pb.audience_duration || 0;
  const time = pb.audience_time || 0;
  const untilFade = secondsUntilFade(time, duration);
  return {
    started: !!pb.audience_started,
    time,
    duration,
    ending: untilFade === 0 && pb.audience_started && !pb.video_ended,
    ended: !!pb.video_ended,
    error: pb.video_error || "",
  };
}

/** Group tracks by artist for the Filler tab (shuffled list stays flat). */
export function groupByArtist(tracks) {
  const groups = {};
  for (const t of tracks || []) (groups[t.artist || "Unknown"] ||= []).push(t);
  return Object.keys(groups).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())).map((artist) => ({ artist, tracks: groups[artist] }));
}

/** Fisher-Yates shuffle that never changes the input. */
export function shuffle(list, rand = Math.random) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** Index of the next filler track (wraps around). */
export const nextTrackIndex = (current, count) => (count <= 0 ? -1 : current + 1 < count ? current + 1 : 0);

/** Volume for step i of n when fading from `from` to `to`. */
export const fadeVolume = (from, to, step, steps = FILLER_FADE_STEPS) => from + (to - from) * Math.min(1, step / steps);
