// v32.2.9: "Auto-advance songs" for Music Bingo and Traditional Bingo.
// When the host turned it ON, the moment the call timer reaches 0 the screen does exactly what the host's click on
// "Next song" / "Call next number" does. It NEVER starts a round, and it never restarts a stopped timer.
//
// The rule lives here as a pure function so it can be tested without a screen. ANY doubt means "do not advance".

/** The only ways the countdown ends. `running` timers that run out are "expired"; everything else is a stop. */
export const REASON = {
  FIRE: "fire",
  OFF: "switch is off",
  NOT_EXPIRED: "timer did not run out",
  NOT_RUNNING: "timer was stopped",
  BINGO: "a bingo is being verified or celebrated",
  ROUND_OVER: "the round is over",
  PAUSED: "the game is paused",
  NOTHING_LEFT: "no songs or numbers left",
  BUSY: "the last call is still going out",
};

/**
 * @param {object} s
 *  enabled        the saved switch (must be exactly true)
 *  expired        the countdown reached 0 on its own
 *  wasRunning     the timer was running when it reached 0 (a stopped timer never advances)
 *  bingoActive    verify dialog or winner video is showing
 *  roundOver      the round-over pop-up is open
 *  paused         the host paused the game
 *  remaining      songs (music) or numbers (traditional) still to call
 *  busy           a call is in flight / cooldown
 * @returns {{fire: boolean, reason: string}}
 */
export function decideAutoAdvance(s) {
  const no = (reason) => ({ fire: false, reason });
  if (!s || s.enabled !== true) return no(REASON.OFF);
  if (s.bingoActive) return no(REASON.BINGO);
  if (s.roundOver) return no(REASON.ROUND_OVER);
  if (s.paused) return no(REASON.PAUSED);
  if (!s.wasRunning) return no(REASON.NOT_RUNNING);
  if (!s.expired) return no(REASON.NOT_EXPIRED);
  if (!(s.remaining > 0)) return no(REASON.NOTHING_LEFT);
  if (s.busy) return no(REASON.BUSY);
  return { fire: true, reason: REASON.FIRE };
}

/** Only a real boolean true from the server counts as ON. */
export const isOn = (resp) => !!resp && resp.enabled === true;
