import { describe, expect, test } from "bun:test";
import {
  IDLE_ATTACK_WINDOW,
  nextAttackHitTick,
  stepAttackWindow,
  type AttackWindowState,
} from "./attack-window";
import { weaponClassProfile } from "./weapon-class";

const MELEE = weaponClassProfile("melee_dps_v1");
const RANGED = weaponClassProfile("ranged_dps_v1");

function commit(
  profile = MELEE,
  nowMs = 1_000,
  state: AttackWindowState = IDLE_ATTACK_WINDOW,
) {
  return stepAttackWindow({ profile, state, nowMs, requested: true, blocked: false });
}

function at(profile: typeof MELEE, state: AttackWindowState, nowMs: number, requested = false) {
  return stepAttackWindow({ profile, state, nowMs, requested, blocked: false });
}

describe("committing to an action", () => {
  test("the melee commitment and window are exactly the shipped numbers", () => {
    // The values that used to be ATTACK_DURATION_MS / _FROM / _TO. Every package published so far
    // was played at them, so the table and this arithmetic together must still produce them.
    const started = commit(MELEE, 1_000);
    expect(started.committed).toBe(true);
    expect(started.attackUntil).toBe(1_333);
    expect(at(MELEE, started, 1_079).attackActive).toBe(false);
    expect(at(MELEE, started, 1_080).attackActive).toBe(true);
    expect(at(MELEE, started, 1_250).attackActive).toBe(true);
    expect(at(MELEE, started, 1_251).attackActive).toBe(false);
    expect(at(MELEE, started, 1_332).attacking).toBe(true);
    expect(at(MELEE, started, 1_333).attacking).toBe(false);
  });

  test("the throw commits for longer and opens later, which is what the reach costs", () => {
    const started = commit(RANGED, 1_000);
    expect(started.attackUntil).toBe(1_400);
    expect(at(RANGED, started, 1_159).attackActive).toBe(false);
    expect(at(RANGED, started, 1_160).attackActive).toBe(true);
    expect(at(RANGED, started, 1_260).attackActive).toBe(true);
    expect(at(RANGED, started, 1_261).attackActive).toBe(false);
  });

  test("an unrequested frame commits to nothing", () => {
    expect(stepAttackWindow({
      profile: MELEE,
      state: IDLE_ATTACK_WINDOW,
      nowMs: 1_000,
      requested: false,
      blocked: false,
    })).toMatchObject({ committed: false, attacking: false, attackActive: false });
  });

  test("a blocked character commits to nothing, however hard the key is asked for", () => {
    // Defeat and hanging off a climbable both arrive here as `blocked`.
    expect(stepAttackWindow({
      profile: MELEE,
      state: IDLE_ATTACK_WINDOW,
      nowMs: 1_000,
      requested: true,
      blocked: true,
    }).committed).toBe(false);
  });
});

describe("what a second request during an action does", () => {
  test("nothing, until the whole commitment has elapsed", () => {
    // Not merely until the hit window closes. A fresh swing during the recovery frames would let a
    // held key produce a rate the animation cannot draw.
    const started = commit(MELEE, 1_000);
    for (const t of [1_100, 1_260, 1_332]) {
      expect(at(MELEE, started, t, true).committed).toBe(false);
      expect(at(MELEE, started, t, true).attackUntil).toBe(1_333);
    }
    const again = at(MELEE, started, 1_333, true);
    expect(again.committed).toBe(true);
    expect(again.attackUntil).toBe(1_666);
  });

  test("a request while the blow is live cannot restart the action", () => {
    const started = commit(MELEE, 1_000);
    const live = at(MELEE, started, 1_100);
    expect(live.attackActive).toBe(true);
    expect(at(MELEE, live, 1_100, true).committed).toBe(false);
  });
});

describe("which blow is due", () => {
  const SWEEP = weaponClassProfile("melee_sweep_v1");

  function tick(profile: typeof MELEE, state: AttackWindowState, nowMs: number, fired: number) {
    return nextAttackHitTick({ profile, state: at(profile, state, nowMs), nowMs, ticksFired: fired });
  }

  test("a single-blow class is due exactly once, when its window opens", () => {
    const started = commit(MELEE, 1_000);
    expect(tick(MELEE, started, 1_079, 0)).toBeNull();
    expect(tick(MELEE, started, 1_080, 0)).toBe(0);
    expect(tick(MELEE, started, 1_200, 0)).toBe(0);
    expect(tick(MELEE, started, 1_200, 1)).toBeNull();
    expect(tick(MELEE, started, 1_251, 0)).toBeNull();
  });

  test("a multi-hit class spaces its blows from the window opening", () => {
    const started = commit(SWEEP, 1_000);
    expect(tick(SWEEP, started, 1_080, 0)).toBe(0);
    expect(tick(SWEEP, started, 1_124, 1)).toBeNull();
    expect(tick(SWEEP, started, 1_125, 1)).toBe(1);
    expect(tick(SWEEP, started, 1_170, 2)).toBe(2);
    expect(tick(SWEEP, started, 1_200, 3)).toBeNull();
  });

  test("a long frame yields one blow per call, so a combo spreads across frames", () => {
    const started = commit(SWEEP, 1_000);
    let fired = 0;
    const landed: number[] = [];
    for (const nowMs of [1_240, 1_241, 1_242, 1_243]) {
      const due = tick(SWEEP, started, nowMs, fired);
      if (due !== null) {
        landed.push(due);
        fired = due + 1;
      }
    }
    expect(landed).toEqual([0, 1, 2]);
  });

  test("a blow that would fall after the window closes is never due", () => {
    const crowded = { ...SWEEP, hitsPerAction: 10, hitIntervalMs: 40 };
    const started = commit(crowded, 1_000);
    // Tick 4 is due at 240 ms, tick 5 at 280 ms, past the 250 ms close.
    expect(tick(crowded, started, 1_249, 4)).toBe(4);
    expect(tick(crowded, started, 1_249, 5)).toBeNull();
    expect(tick(crowded, started, 1_280, 5)).toBeNull();
  });

  test("a negative or fractional fired count is refused", () => {
    const started = commit(SWEEP, 1_000);
    expect(() => tick(SWEEP, started, 1_100, -1)).toThrow("ticks fired");
    expect(() => tick(SWEEP, started, 1_100, 0.5)).toThrow("ticks fired");
  });
});

describe("the commit signal", () => {
  test("is true on exactly the frame the action starts, and never again during it", () => {
    // The caller clears its once-per-action hit latch on this, so a second true would let one
    // swing land twice.
    const started = commit(MELEE, 1_000);
    expect(started.committed).toBe(true);
    let state: AttackWindowState = started;
    let commits = 0;
    for (let t = 1_016; t < 1_333; t += 16) {
      const step = at(MELEE, state, t, true);
      if (step.committed) commits += 1;
      state = step;
    }
    expect(commits).toBe(0);
  });
});
