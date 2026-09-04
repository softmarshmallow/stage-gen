import { describe, expect, test } from "bun:test";

import { arbitrate, Awareness, ladder, runAuction } from "./index";
import {
  MOB_AGGRESSIONS,
  aggressionProfile,
  mobIntent,
  type AggressionProfile,
  type MobIntent,
} from "@/lib/sideview-platformer/combat";

// The `actor-ai` evidence, and it is not the evidence the plan predicted.
//
// The plan expected E1 to move — "a different arbitrator produces different
// frames" — and offered a per-archetype behavioural-equivalence suite plus a
// reviewed capture as the substitute. Half of that turned out to be
// unnecessary and half is still owed, and the report says which.
//
// Unnecessary: the creature's "node chain" is not a state machine. `mobIntent`
// is five conditions in a fixed order, and a fixed order *is* a priority
// ladder. Restating it as an auction is the same function, and the first suite
// below proves that exhaustively — every archetype crossed with every distance
// and cadence boundary — rather than by argument. E1 did not move, in either
// genre, and nothing was re-pinned.
//
// Still owed: folding the rest of the creature's chain — facing, pursuit
// target, return-home stepping, action timing — into the bot's behaviour roster
// really would move frames, because those nodes run in an order the roster
// would re-derive, and the tie-breaks and intent shapes differ. That is the
// swap the reviewed capture is for, and it is not taken here.

const BOUNDARY_DISTANCES = [0, 1, 24, 63, 64, 65, 191, 192, 193, 383, 384, 385, 767, 768, 769];

/** The chain exactly as it was written, kept as the thing the auction is measured against. */
function chainIntent(input: {
  profile: AggressionProfile;
  distancePx: number;
  nowMs: number;
  attackReadyAtMs: number;
  playerDefeated: boolean;
}): MobIntent {
  const { profile, distancePx, nowMs, attackReadyAtMs, playerDefeated } = input;
  if (!profile.hostile) return "hold";
  if (playerDefeated || distancePx > profile.aggroRadiusPx) return "hold";
  if (profile.flees) return "flee";
  if (distancePx <= profile.strikeRangePx) {
    return nowMs >= attackReadyAtMs ? "strike" : "attack_recovery";
  }
  return "chase";
}

describe("the auction subsumes the node chain, measured rather than argued", () => {
  test("every archetype, every boundary: the ladder and the chain agree", () => {
    let compared = 0;
    for (const aggression of MOB_AGGRESSIONS) {
      const profile = aggressionProfile(aggression);
      for (const distancePx of [...BOUNDARY_DISTANCES, profile.strikeRangePx, profile.strikeRangePx + 1, profile.aggroRadiusPx]) {
        for (const [nowMs, attackReadyAtMs] of [
          [0, 0],
          [999, 1000],
          [1000, 1000],
          [1001, 1000],
        ] as const) {
          for (const playerDefeated of [false, true]) {
            const input = { profile, distancePx, nowMs, attackReadyAtMs, playerDefeated };
            expect(mobIntent(input)).toBe(chainIntent(input));
            compared += 1;
          }
        }
      }
    }
    // A comparison that silently compared nothing is the one way this passes
    // without measuring anything.
    expect(compared).toBeGreaterThan(500);
  });

  test("the rung order is the tiebreak, and cooldown really does outrank range", () => {
    const relentless = aggressionProfile("relentless");
    const inRangeOnCooldown = {
      profile: relentless,
      distancePx: relentless.strikeRangePx,
      nowMs: 0,
      attackReadyAtMs: 500,
      playerDefeated: false,
    };
    // Both the strike rung and the recovery rung test the same range; the
    // higher one wins on cadence, and the lower one catches what it drops.
    expect(mobIntent(inRangeOnCooldown)).toBe("attack_recovery");
    expect(mobIntent({ ...inRangeOnCooldown, nowMs: 500 })).toBe("strike");
  });
});

describe("the auction itself", () => {
  test("strictly greater wins, so a tie leaves the earlier bidder in place", () => {
    expect(arbitrate([{ priority: 1, id: "a" }, { priority: 1, id: "b" }])).toEqual({
      priority: 1,
      id: "a",
    });
    expect(arbitrate([{ priority: 1, id: "a" }, { priority: 2, id: "b" }])).toEqual({
      priority: 2,
      id: "b",
    });
    // Declining is the normal outcome, and every bidder declining is an answer.
    expect(arbitrate([null, null])).toBeNull();
    expect(arbitrate([])).toBeNull();
  });

  test("a roster of bidders and a ladder of rungs are the same auction", () => {
    type Context = Readonly<{ near: boolean; hurt: boolean }>;
    const context: Context = { near: true, hurt: true };
    const asRoster = runAuction<Context, { priority: number; action: string }>(
      [
        (c) => (c.hurt ? { priority: 900, action: "heal" } : null),
        (c) => (c.near ? { priority: 700, action: "engage" } : null),
        () => ({ priority: 100, action: "patrol" }),
      ],
      context,
    );
    const asLadder = ladder<Context, string>(
      [
        [(c) => c.hurt, "heal"],
        [(c) => c.near, "engage"],
        [() => true, "patrol"],
      ],
      context,
    );
    expect(asRoster!.action).toBe(asLadder!);
    expect(asLadder).toBe("heal");
    // A ladder with no rung holding is the empty auction.
    expect(ladder<Context, string>([[(c) => c.near, "engage"]], { near: false, hurt: false })).toBeNull();
  });
});

// E4 for `actor-ai`: one hysteresis, instantiated per archetype, and the four
// behaviours the plan's equivalence suite names — awareness hysteresis,
// return-home, pursuit level, cadence — characterised so the swap that is still
// owed has a "before" to be measured against.
describe("awareness hysteresis, per archetype", () => {
  const engaged = { canEngage: true, homeReturnRequired: false, atHome: false };
  const lost = { canEngage: false, homeReturnRequired: false, atHome: false };

  test("losing the target is a return, and it persists until home", () => {
    const awareness = new Awareness();
    expect(awareness.mode).toBe("idle");
    expect(awareness.step(engaged)).toBe("engage");
    expect(awareness.mode).toBe("engaged");
    // Not idle: the actor is somewhere it walked to on purpose.
    expect(awareness.step(lost)).toBe("return");
    expect(awareness.step(lost)).toBe("return");
    expect(awareness.step({ ...lost, atHome: true })).toBe("idle");
    expect(awareness.mode).toBe("idle");
    // And having got home, losing nothing keeps it idle.
    expect(awareness.step(lost)).toBe("idle");
  });

  test("a creature that never engaged still returns when it is somewhere it may not be", () => {
    const awareness = new Awareness();
    expect(awareness.step({ ...lost, homeReturnRequired: true })).toBe("return");
    expect(awareness.step(lost)).toBe("return");
    expect(awareness.step({ ...lost, atHome: true })).toBe("idle");
  });

  test("re-engaging mid-return abandons the return, and a reset abandons everything", () => {
    const awareness = new Awareness();
    awareness.step(engaged);
    expect(awareness.step(lost)).toBe("return");
    expect(awareness.step(engaged)).toBe("engage");
    expect(awareness.mode).toBe("engaged");
    awareness.reset();
    expect(awareness.mode).toBe("idle");
    expect(awareness.step(lost)).toBe("idle");
  });

  test("pursuit level and cadence are the profile's, and differ per archetype", () => {
    // The characterisation the swap will be measured against: what each
    // archetype does at its own boundaries, stated once, in one place.
    const at = (aggression: (typeof MOB_AGGRESSIONS)[number], distancePx: number, nowMs = 0) =>
      mobIntent({
        profile: aggressionProfile(aggression),
        distancePx,
        nowMs,
        attackReadyAtMs: 0,
        playerDefeated: false,
      });
    // Passive never reacts at all, at any distance.
    expect(at("passive", 0)).toBe("hold");
    expect(at("passive", 1000)).toBe("hold");
    // Skittish notices and retreats rather than closing.
    expect(at("skittish", 1)).toBe("flee");
    expect(at("skittish", 10_000)).toBe("hold");
    // The three that close differ only in how far away they notice you.
    for (const aggression of ["territorial", "hunting", "relentless"] as const) {
      const profile = aggressionProfile(aggression);
      expect(at(aggression, profile.aggroRadiusPx)).not.toBe("hold");
      expect(at(aggression, profile.aggroRadiusPx + 1)).toBe("hold");
      expect(at(aggression, profile.strikeRangePx)).toBe("strike");
      expect(at(aggression, profile.strikeRangePx + 1)).toBe("chase");
    }
    // And the noticing radii really are ordered, which is the one thing an
    // archetype vocabulary is for.
    const radius = (aggression: (typeof MOB_AGGRESSIONS)[number]) =>
      aggressionProfile(aggression).aggroRadiusPx;
    expect(radius("territorial")).toBeLessThan(radius("hunting"));
    expect(radius("hunting")).toBeLessThan(radius("relentless"));
  });
});
