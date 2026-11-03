// v32.2.9: the rule for when the screen may advance by itself. Runs with `craco test` (jest) or plain node (see /tmp runner in the PR).
import { decideAutoAdvance, isOn, REASON } from "./autoAdvance";

const base = { enabled: true, expired: true, wasRunning: true, bingoActive: false, roundOver: false, paused: false, remaining: 5, busy: false };
const go = (o) => decideAutoAdvance({ ...base, ...o });

describe("decideAutoAdvance", () => {
  test("fires only when the switch is on, a RUNNING timer ran out, and nothing blocks", () => {
    expect(go({}).fire).toBe(true);
  });
  test("off means off, including look-alike values", () => {
    for (const v of [false, undefined, null, "true", 1, "on", {}, []]) expect(go({ enabled: v }).fire).toBe(false);
  });
  test("a bingo being verified or celebrated never advances", () => { expect(go({ bingoActive: true }).reason).toBe(REASON.BINGO); });
  test("round over, paused, nothing left, or a call in flight never advance", () => {
    expect(go({ roundOver: true }).fire).toBe(false);
    expect(go({ paused: true }).fire).toBe(false);
    expect(go({ remaining: 0 }).fire).toBe(false);
    expect(go({ remaining: NaN }).fire).toBe(false);
    expect(go({ busy: true }).fire).toBe(false);
  });
  test("a stopped timer never advances, and neither does one that did not run out", () => {
    expect(go({ wasRunning: false }).reason).toBe(REASON.NOT_RUNNING);
    expect(go({ expired: false }).reason).toBe(REASON.NOT_EXPIRED);
  });
  test("missing or empty state never advances", () => {
    expect(decideAutoAdvance(null).fire).toBe(false);
    expect(decideAutoAdvance(undefined).fire).toBe(false);
    expect(decideAutoAdvance({}).fire).toBe(false);
  });
  test("a bingo wins over everything else: even with the timer expired, the switch on and songs left", () => {
    expect(go({ bingoActive: true, expired: true, wasRunning: true, remaining: 40 }).fire).toBe(false);
  });
  test("isOn trusts only a real true from the server", () => {
    expect(isOn({ enabled: true })).toBe(true);
    for (const v of [{ enabled: "true" }, { enabled: 1 }, {}, null, undefined, { enabled: false }]) expect(isOn(v)).toBe(false);
  });
});
