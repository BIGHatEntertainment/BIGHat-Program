// alpha.91: a quiet safety net for the Bingo host. The song the host SEES as "up next" and the video that
// is preloaded and played must be the same song, from the CURRENT round. Nothing is shown to anyone: when a
// preloaded address does not match, it is thrown away and rebuilt from the round's own list.

/** The address a song's video is streamed from, for one theme and number. */
export const mediaUrl = (api, theme, number) => `${api}/bingo/media/${encodeURIComponent(theme)}/${number}`;

/** Which theme and number an address stands for, or null if it is not one of our stream addresses. */
export function parseMediaUrl(url) {
  if (typeof url !== 'string') return null;
  const m = url.match(/\/bingo\/media\/([^/?#]+)\/(\d+)(?:[?#].*)?$/);
  if (!m) return null;
  let theme = m[1];
  try { theme = decodeURIComponent(theme); } catch { /* keep it as it is */ }
  return { theme, number: parseInt(m[2], 10) };
}

/**
 * Is this address the right video for this theme and song number?
 * Streamed songs carry both in the address, so they can be checked exactly.
 * A local file address (a blob) carries nothing to check, so it is trusted only if it was made for this very number.
 */
export function isRightVideo(url, theme, number, madeFor) {
  const p = parseMediaUrl(url);
  if (p) return p.theme === theme && p.number === Number(number);
  if (typeof url === 'string' && url.startsWith('blob:')) return !!madeFor && madeFor.theme === theme && madeFor.number === Number(number);
  return false;
}

/**
 * Look a preloaded entry up. Returns the entry only if it is for this round and this number;
 * a wrong or stale one is dropped from the cache (the caller then builds a fresh one).
 */
export function takePreloaded(cache, theme, number) {
  const e = cache[number];
  if (!e) return null;
  if (e.theme === theme && e.number === Number(number) && isRightVideo(e.url, theme, number, e)) return e;
  delete cache[number];
  return null;
}

/**
 * alpha.91: the quiet self-check for the NEXT song. It compares what the host is shown as "up next" with what is
 * actually preloaded, and says what to do. It never shows anything; the host just calls the fixes it returns.
 *   nextSong   the proposed song object (number, title) shown to the host, or null
 *   songList   the current round's songs [{ number, title }]
 *   videoFiles the current round's video links { number: link }
 *   cache      the preload cache { number: { url, ready, theme, number } }
 *   theme      the round the lists above belong to
 * Returns { ok, fixes: [...] } where each fix is one of
 *   { do: 'drop', number }     remove a wrong or stale preload entry
 *   { do: 'preload', number }  (re)load the right video for this number
 *   { do: 'replace-next', song } the proposed song is not in this round's list: use this one instead
 */
export function checkNextSong({ nextSong, songList, videoFiles, cache, theme, pool }) {
  const fixes = [];
  if (!nextSong) return { ok: true, fixes };
  const inList = (songList || []).find(s => s.number === nextSong.number);
  if (!inList) {
    // the name on screen is not a song of this round at all: fall back to the pool's first song that is
    const n = (pool || []).find(x => (songList || []).some(s => s.number === x));
    if (n != null) fixes.push({ do: 'replace-next', song: songList.find(s => s.number === n) });
    return { ok: false, fixes };
  }
  if (inList.title !== nextSong.title) fixes.push({ do: 'replace-next', song: inList });   // same number, another round's title
  const e = (cache || {})[nextSong.number];
  const good = e && e.theme === theme && e.number === Number(nextSong.number) && isRightVideo(e.url, theme, nextSong.number, e);
  if (e && !good) fixes.push({ do: 'drop', number: nextSong.number });
  if (!good && videoFiles && videoFiles[nextSong.number]) fixes.push({ do: 'preload', number: nextSong.number });
  return { ok: fixes.length === 0, fixes };
}
