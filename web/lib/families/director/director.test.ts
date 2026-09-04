import { describe, expect, test } from "bun:test";
import {
  armAt,
  enterPhase,
  phaseElapsed,
  triggerReached,
  type DirectorPhaseState,
} from "./set-piece";
import { SwapLedger, type DirectorSwap } from "./swaps";
import { parseDirectorBlock } from "./manifest";

// --- E4: one set-piece machine, two genres that share no vocabulary ---------------------------

type RunnerPhase = "idle" | "arena_pending" | "cut_in" | "battle" | "retreat" | "cooldown";
type RunnerOutcome = "defeated" | "exhausted";
type GatePhase = "armed" | "engaged" | "ended";
type GateOutcome = "won";

describe("E4: the director machine instantiated into two shapes", () => {
  test("a runner-shaped set-piece: six phases, a column datum, and a locomotion swap", () => {
    const state: DirectorPhaseState<RunnerPhase, RunnerOutcome> = {
      phase: "idle",
      phaseStartedAt: null,
      outcome: null,
    };
    // The trigger is a column on an endless track.
    const trigger = armAt(120);
    expect(triggerReached(trigger, 119.9)).toBe(false);
    expect(triggerReached(trigger, 120)).toBe(true);
    enterPhase(state, "arena_pending", 4);
    expect(phaseElapsed(state, 4.5)).toBeCloseTo(0.5, 9);
    enterPhase(state, "battle", 6);
    expect(state.phase).toBe("battle");
    // And the swap the fight has in force while it runs.
    let locomotion = "run";
    const ledger = new SwapLedger();
    const thrust: DirectorSwap = {
      id: "locomotion",
      apply: () => {
        locomotion = "thrust";
      },
      revert: () => {
        locomotion = "run";
      },
    };
    expect(ledger.apply(thrust)).toBe(true);
    expect(locomotion).toBe("thrust");
    // Applying twice is once: a set-piece re-entering its own battle phase does
    // not stack a second swap it would then have to unstack.
    expect(ledger.apply(thrust)).toBe(false);
    ledger.revertAll();
    expect(locomotion).toBe("run");
    state.outcome = "defeated";
    enterPhase(state, "retreat", 9);
  });

  test("a platformer-shaped set-piece: three phases, a pixel datum, and a soundtrack swap", () => {
    const state: DirectorPhaseState<GatePhase, GateOutcome> = {
      phase: "armed",
      phaseStartedAt: null,
      outcome: null,
    };
    // The same statement about one axis, in the other genre's unit.
    expect(triggerReached(armAt(2304), 1948)).toBe(false);
    expect(triggerReached(armAt(2304), 2312)).toBe(true);
    let pool = ["road_theme", "road_theme_b"];
    const ledger = new SwapLedger();
    const before = [...pool];
    ledger.apply({
      id: "soundtrack",
      apply: () => {
        pool = ["road_theme"];
      },
      revert: () => {
        pool = before;
      },
    });
    enterPhase(state, "engaged", 8600);
    expect(pool).toEqual(["road_theme"]);
    expect(ledger.ids()).toEqual(["soundtrack"]);
    ledger.revertAll();
    state.outcome = "won";
    enterPhase(state, "ended", 12000);
    expect(pool).toEqual(["road_theme", "road_theme_b"]);
    expect(ledger.ids()).toEqual([]);
  });
});

describe("the machine's own rules", () => {
  test("a phase that has never been entered has no elapsed time, which is an answer", () => {
    const state: DirectorPhaseState<GatePhase, GateOutcome> = {
      phase: "armed",
      phaseStartedAt: null,
      outcome: null,
    };
    expect(phaseElapsed(state, 100)).toBe(null);
  });

  test("a trigger is reached by advancing, and the direction is not a parameter", () => {
    // A set-piece that could fire backwards would fire on the way *out* of an
    // arena as well as into it. Both genres advance; neither needs the choice.
    expect(triggerReached(armAt(10), 11)).toBe(true);
    expect(triggerReached(armAt(10), 9)).toBe(false);
    expect(() => armAt(Number.POSITIVE_INFINITY)).toThrow("finite datum");
  });

  test("swaps are put back in reverse order, because they compose", () => {
    const log: string[] = [];
    const ledger = new SwapLedger();
    ledger.apply({ id: "a", apply: () => log.push("+a"), revert: () => log.push("-a") });
    ledger.apply({ id: "b", apply: () => log.push("+b"), revert: () => log.push("-b") });
    expect(ledger.inForce("b")).toBe(true);
    ledger.revertAll();
    expect(log).toEqual(["+a", "+b", "-b", "-a"]);
    // And reverting twice is not reverting twice.
    ledger.revertAll();
    expect(log).toEqual(["+a", "+b", "-b", "-a"]);
  });

  test("E7: a set-piece with nothing to swap is an empty ledger and not a special case", () => {
    const ledger = new SwapLedger();
    ledger.revertAll();
    expect(ledger.ids()).toEqual([]);
  });
});

describe("the blocks the family gates for itself", () => {
  test("the platformer's gate refuses when the map its anchor lives in moves", () => {
    expect(() =>
      parseDirectorBlock(
        { maps: "platformer-maps-block-v2" },
        { block: "maps", version: "platformer-maps-block-v1" },
      ),
    ).toThrow('manifest block "maps" is published as platformer-maps-block-v2');
  });

  test("and the runner's refuses when the chunks its arena is a role of move", () => {
    expect(() =>
      parseDirectorBlock(
        { segments: "runner-segments-block-v2" },
        { block: "segments", version: "runner-segments-block-v1" },
      ),
    ).toThrow('manifest block "segments" is published as runner-segments-block-v2');
  });
});
