import { describe, expect, test } from "bun:test";
import {
  MobActionTimingNode,
  MobAwarenessNode,
  MobBehaviorVariation,
  MobFacingNode,
  MobReturnHomeNode,
  constrainMobStrikeToAttackLevel,
  mobLocomotionAnimationNeedsRestart,
  MobPursuitTargetNode,
} from "./mob-behavior";
import { aggressionProfile } from "./combat";

describe("mob awareness node", () => {
  const base = {
    playerObserved: true,
    playerDefeated: false,
    playerWithinPursuitTerritory: true,
    atHome: true,
    homeReturnRequired: false,
    nowMs: 10_000,
    attackReadyAtMs: 0,
  } as const;

  test("acquires inside aggro and returns home instead of stopping after disengagement", () => {
    const profile = aggressionProfile("territorial");
    const awareness = new MobAwarenessNode(profile);
    expect(
      awareness.step({ ...base, distancePx: profile.aggroRadiusPx + 1 }),
    ).toBe("hold");
    expect(awareness.step({ ...base, distancePx: profile.aggroRadiusPx })).toBe(
      "chase",
    );
    expect(
      awareness.step({
        ...base,
        atHome: false,
        distancePx: profile.aggroRadiusPx + 1,
      }),
    ).toBe("return_home");
  });

  test("returns after the player leaves its pursuit territory, then becomes idle at home", () => {
    const profile = aggressionProfile("hunting");
    const awareness = new MobAwarenessNode(profile);
    expect(awareness.step({ ...base, distancePx: 100 })).toBe("chase");
    expect(
      awareness.step({
        ...base,
        distancePx: 100,
        playerWithinPursuitTerritory: false,
        atHome: false,
      }),
    ).toBe("return_home");
    expect(
      awareness.step({
        ...base,
        distancePx: profile.aggroRadiusPx + 1,
        atHome: false,
      }),
    ).toBe("return_home");
    expect(
      awareness.step({
        ...base,
        distancePx: profile.aggroRadiusPx + 1,
        atHome: true,
      }),
    ).toBe("hold");
  });

  test("returns an externally displaced idle mob home instead of starting patrol there", () => {
    const profile = aggressionProfile("territorial");
    const awareness = new MobAwarenessNode(profile);
    expect(
      awareness.step({
        ...base,
        playerObserved: false,
        atHome: false,
        homeReturnRequired: true,
        distancePx: 0,
      }),
    ).toBe("return_home");
    expect(
      awareness.step({
        ...base,
        playerObserved: false,
        atHome: true,
        homeReturnRequired: false,
        distancePx: 0,
      }),
    ).toBe("hold");
  });

  test("keeps an engaged mob in combat recovery throughout its cooldown", () => {
    const profile = aggressionProfile("hunting");
    const awareness = new MobAwarenessNode(profile);

    expect(
      awareness.step({
        ...base,
        distancePx: profile.strikeRangePx,
        attackReadyAtMs: base.nowMs + 500,
      }),
    ).toBe("attack_recovery");
    expect(
      awareness.step({
        ...base,
        nowMs: base.nowMs + 499,
        distancePx: profile.strikeRangePx,
        attackReadyAtMs: base.nowMs + 500,
      }),
    ).toBe("attack_recovery");
  });
});

describe("mob action timing node", () => {
  const base = { windupMs: 300, cooldownMs: 1200 } as const;

  test("varies consecutive actions within the configured delay range", () => {
    const node = new MobActionTimingNode(42, 0.2);
    const first = node.step(base);
    const second = node.step(base);

    expect(first).not.toEqual(second);
    for (const timing of [first, second]) {
      expect(timing.windupMs).toBeGreaterThanOrEqual(240);
      expect(timing.windupMs).toBeLessThanOrEqual(360);
      expect(timing.cooldownMs).toBeGreaterThanOrEqual(960);
      expect(timing.cooldownMs).toBeLessThanOrEqual(1440);
    }
  });

  test("replays the same sequence after reset and differs across mobs", () => {
    const first = new MobActionTimingNode(7, 0.2);
    const other = new MobActionTimingNode(8, 0.2);
    const expected = [first.step(base), first.step(base)];
    first.reset();
    expect([first.step(base), first.step(base)]).toEqual(expected);
    expect(other.step(base)).not.toEqual(expected[0]);
  });

  test("preserves exact authored timing when variance is zero", () => {
    expect(new MobActionTimingNode(1, 0).step(base)).toEqual(base);
  });
});

describe("mob facing node", () => {
  const config = { targetDeadzonePx: 8, movementEpsilonPx: 0.01 } as const;

  test("preserves facing across target jitter and blocked movement", () => {
    const facing = new MobFacingNode(1, config);
    const samples = [-7, 6, -3, 1, 0, -8, 8];

    for (const targetX of samples) {
      expect(facing.faceTarget(0, targetX)).toBe(1);
      expect(facing.followMovement(100, 100)).toBe(1);
    }
  });

  test("turns only after a target leaves the dead zone or movement is applied", () => {
    const facing = new MobFacingNode(1, config);

    expect(facing.faceTarget(100, 91)).toBe(-1);
    expect(facing.faceTarget(100, 108)).toBe(-1);
    expect(facing.followMovement(100, 100.005)).toBe(-1);
    expect(facing.followMovement(100, 101)).toBe(1);
  });

  test("supports explicit reactions and deterministic reset", () => {
    const facing = new MobFacingNode(1, config);

    expect(facing.commit(-1)).toBe(-1);
    facing.reset(1);
    expect(facing.currentDirection).toBe(1);
  });

  test("rejects invalid policy and non-finite samples", () => {
    expect(
      () => new MobFacingNode(1, { ...config, targetDeadzonePx: -1 }),
    ).toThrow();
    const facing = new MobFacingNode(1, config);
    expect(() => facing.faceTarget(Number.NaN, 0)).toThrow();
    expect(() => facing.followMovement(0, Number.POSITIVE_INFINITY)).toThrow();
  });
});

describe("mob return-home node", () => {
  test("walks toward spawn and snaps exactly home on arrival", () => {
    const node = new MobReturnHomeNode(320, 8, 64);
    expect(node.step({ mobX: 200, deltaSeconds: 0.5, speedScale: 1 })).toEqual({
      targetX: 232,
      direction: 1,
      arrived: false,
    });
    expect(node.step({ mobX: 316, deltaSeconds: 0.1, speedScale: 1 })).toEqual({
      targetX: 320,
      direction: 1,
      arrived: true,
    });
    expect(node.step({ mobX: 400, deltaSeconds: 1, speedScale: 1 })).toEqual({
      targetX: 336,
      direction: -1,
      arrived: false,
    });
  });

  test("rejects invalid return movement", () => {
    expect(() => new MobReturnHomeNode(0, -1, 64)).toThrow();
    const node = new MobReturnHomeNode(0, 8, 64);
    expect(() =>
      node.step({ mobX: 10, deltaSeconds: -1, speedScale: 1 }),
    ).toThrow();
  });
});

describe("mob individual behavior variation", () => {
  const config = {
    movementSpeedVarianceRatio: 0.1,
    pursuitSweepVarianceRatio: 0.25,
  } as const;

  test("is stable for one instance and distinct across instance seeds", () => {
    const first = new MobBehaviorVariation(17, config);
    const replay = new MobBehaviorVariation(17, config);
    const second = new MobBehaviorVariation(18, config);

    expect(replay).toEqual(first);
    expect(second).not.toEqual(first);
  });

  test("keeps every sampled value inside its configured symmetric range", () => {
    for (let seed = 0; seed < 100; seed += 1) {
      const variation = new MobBehaviorVariation(seed, config);
      expect(variation.movementSpeedScale).toBeGreaterThanOrEqual(0.9);
      expect(variation.movementSpeedScale).toBeLessThanOrEqual(1.1);
      expect(variation.pursuitSweepScale).toBeGreaterThanOrEqual(0.75);
      expect(variation.pursuitSweepScale).toBeLessThanOrEqual(1.25);
      expect([-1, 1]).toContain(variation.initialDirection);
    }
  });

  test("rejects invalid seeds and unbounded variance", () => {
    expect(() => new MobBehaviorVariation(0.5, config)).toThrow();
    expect(
      () =>
        new MobBehaviorVariation(1, {
          movementSpeedVarianceRatio: 1,
          pursuitSweepVarianceRatio: 0,
        }),
    ).toThrow();
  });
});

describe("mob pursuit target node", () => {
  const config = {
    inaccessibleSweepHalfWidthPx: 96,
    arrivalRadiusPx: 12,
  } as const;

  test("passes through the player's X without changing facing on an unreachable level", () => {
    const node = new MobPursuitTargetNode(config);
    const before = node.step({
      mobX: 499,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: 1,
    });
    const after = node.step({
      mobX: 501,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: before.direction,
    });

    expect(before).toEqual({ targetX: 596, direction: 1, sweeping: true });
    expect(after).toEqual({ targetX: 596, direction: 1, sweeping: true });
  });

  test("selects the opposite corridor endpoint only after arriving", () => {
    const node = new MobPursuitTargetNode(config);
    node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: 1,
    });
    expect(
      node.step({
        mobX: 584,
        playerX: 500,
        attackLevelReachable: false,
        currentDirection: 1,
      }),
    ).toEqual({ targetX: 404, direction: -1, sweeping: true });
  });

  test("uses each mob's current direction to distribute initial target sides", () => {
    const rightNode = new MobPursuitTargetNode(config);
    const leftNode = new MobPursuitTargetNode(config);
    expect(
      rightNode.step({
        mobX: 500,
        playerX: 500,
        attackLevelReachable: false,
        currentDirection: 1,
      }).targetX,
    ).toBe(596);
    expect(
      leftNode.step({
        mobX: 500,
        playerX: 500,
        attackLevelReachable: false,
        currentDirection: -1,
      }).targetX,
    ).toBe(404);
  });

  test("returns to direct pursuit and clears corridor memory on a reachable level", () => {
    const node = new MobPursuitTargetNode(config);
    node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: 1,
    });
    expect(
      node.step({
        mobX: 600,
        playerX: 500,
        attackLevelReachable: true,
        currentDirection: 1,
      }),
    ).toEqual({ targetX: 500, direction: -1, sweeping: false });
    expect(
      node.step({
        mobX: 500,
        playerX: 500,
        attackLevelReachable: false,
        currentDirection: -1,
      }).targetX,
    ).toBe(404);
  });

  test("tries each blocked direction once and then keeps a stable facing", () => {
    const node = new MobPursuitTargetNode(config);
    const first = node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: 1,
    });
    expect(first.direction).toBe(1);
    node.reportBlocked();

    const alternate = node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: first.direction,
    });
    expect(alternate.direction).toBe(-1);
    node.reportBlocked();

    const held = node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: alternate.direction,
    });
    node.reportBlocked();
    const repeated = node.step({
      mobX: 500,
      playerX: 500,
      attackLevelReachable: false,
      currentDirection: held.direction,
    });
    expect(held.direction).toBe(-1);
    expect(repeated.direction).toBe(-1);
  });

  test("rejects invalid corridor configuration", () => {
    expect(
      () =>
        new MobPursuitTargetNode({
          inaccessibleSweepHalfWidthPx: 12,
          arrivalRadiusPx: 12,
        }),
    ).toThrow();
  });
});

describe("mob vertical combat intent", () => {
  test("starts a strike only inside the one-level band", () => {
    const base = {
      requestedIntent: "strike" as const,
      mobFootY: 600,
      tilePixels: 64,
    };
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: 536 })).toBe("strike");
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: 535 })).toBe("chase");
    expect(constrainMobStrikeToAttackLevel({ ...base, playerFootY: null })).toBe("chase");
    expect(
      constrainMobStrikeToAttackLevel({
        ...base,
        requestedIntent: "flee",
        playerFootY: 0,
      }),
    ).toBe("flee");
  });
});

describe("mob locomotion presentation", () => {
  test("recovers after attack completion without interrupting active finite states", () => {
    const base = {
      idleAnimationKey: "petal_puff_idle",
      currentAnimationKey: "petal_puff_attack_anim",
      isPlaying: false,
    } as const;
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "chase" })).toBeTrue();
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "wander" })).toBeTrue();
    expect(
      mobLocomotionAnimationNeedsRestart({ ...base, state: "return_home" }),
    ).toBeTrue();
    expect(
      mobLocomotionAnimationNeedsRestart({
        ...base,
        state: "attack_recovery",
      }),
    ).toBeTrue();
    expect(mobLocomotionAnimationNeedsRestart({ ...base, state: "windup" })).toBeFalse();
    expect(
      mobLocomotionAnimationNeedsRestart({
        ...base,
        state: "wander",
        currentAnimationKey: "petal_puff_idle",
        isPlaying: true,
      }),
    ).toBeFalse();
    expect(
      mobLocomotionAnimationNeedsRestart({
        ...base,
        state: "wander",
        currentAnimationKey: "petal_puff_idle",
      }),
    ).toBeTrue();
  });
});
