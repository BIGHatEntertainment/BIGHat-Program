// alpha.98: play a karaoke song the way the PROTOTYPE does: a plain YouTube iframe, nothing else.
// A plain iframe cannot tell us the time or when the song ends, so a small clock does it from the song's known length
// (the length the host got from the YouTube search). The clock reports exactly what the old player reported:
//   started (once), time (every second while playing), ended (once, at the end).

/** The address of the plain player. Same form as the prototype: autoplay, no controls, JS control switched on for pause/resume. */
export const embedSrc = (videoId) =>
  `https://www.youtube.com/embed/${encodeURIComponent(videoId)}?autoplay=1&controls=0&rel=0&modestbranding=1&enablejsapi=1`;

/** alpha.99: YouTube's embedded player (error 153 "video unavailable") needs the page to send a proper referrer. A browser does this
 *  by default; a desktop webview may not, so every YouTube iframe asks for it explicitly. This is YouTube's own documented fix. */
export const IFRAME_REFERRER = "strict-origin-when-cross-origin";

/** Ask the iframe to play / pause / change volume (YouTube's own message format; works without loading any script). */
export const sendCommand = (iframe, func, args = []) => {
  try {
    if (iframe && iframe.contentWindow) iframe.contentWindow.postMessage(JSON.stringify({ event: "command", func, args }), "*");
  } catch { /* the frame is gone */ }
};

/**
 * A song clock. now() is injectable so it can be tested without waiting.
 *   start(durationSeconds)  begin at 0:00
 *   pause() / resume()      the clock stops and restarts without losing its place
 *   tick()                  call once a second: returns { time, ended }
 * With no known length the song never ends by itself (the host's End Song button ends it, as in the prototype).
 */
export function makeSongClock(now = () => Date.now()) {
  let startedAt = 0, pausedAt = 0, pausedTotal = 0, duration = 0, running = false, done = false;
  const elapsed = () => Math.max(0, ((pausedAt || now()) - startedAt - pausedTotal) / 1000);
  return {
    start(d) { startedAt = now(); pausedAt = 0; pausedTotal = 0; duration = Number(d) > 0 ? Number(d) : 0; running = true; done = false; },
    pause() { if (running && !pausedAt) pausedAt = now(); },
    resume() { if (running && pausedAt) { pausedTotal += now() - pausedAt; pausedAt = 0; } },
    stop() { running = false; },
    isRunning: () => running,
    isPaused: () => !!pausedAt,
    tick() {
      if (!running) return { time: 0, ended: false };
      let t = elapsed();
      if (duration && t >= duration) { t = duration; if (!done) { done = true; return { time: t, ended: true }; } }
      return { time: t, ended: false };
    },
  };
}
