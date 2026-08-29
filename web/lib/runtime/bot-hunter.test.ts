import { describe, expect, test } from "bun:test";
import { BOT_PRIORITY, INITIAL_BOT_MEMORY, type BotContext, type BotMemory } from "./bot-behavior";
import {
  HUNTER_BOT_PROFILE,
  HUNTER_BOT_TUNING,
  botProfileWithout,
  collectBehavior,
  engageBehavior,
  healBehavior,
  patrolBehavior,
  planTravel,
  pursueBehavior,
  standDownBehavior,
} from "./bot-hunter";
import {
  DEFAULT_MOVEMENT_CAPABILITIES,
  buildNavGraph,
  locateNavNode,
  movementCapabilities,
  navReach,
  type NavGraph,
} from "./bot-navigation";
import type { BotWorldView } from "./bot-view";
import { NEUTRAL_PLAYER_INTENT } from "./player-intent";

const TILE = 64;
const BASELINE = 720;
const GROUND = BASELINE - TILE;

function graphFor(heights: readonly number[], platforms: readonly { id: string; left: number; right: number; deckY: number }[] = []): NavGraph {
  return buildNavGraph({
    columnSurfaceY: heights.map((height) => BASELINE - height * TILE),
    tileUnits: TILE,
    platforms,
    climbables: [],
    capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
  });
}

const FLAT = graphFor([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]);

function worldView(overrides: Partial<BotWorldView> = {}): BotWorldView {
  const base: BotWorldView = {
    nowMs: 1_000,
    deltaMs: 1000 / 30,
    self: {
      x: 300,
      y: GROUND,
      facing: "right",
      vx: 0,
      vy: 0,
      airborne: false,
      support: "terrain",
      airJumpsUsed: 0,
      hp: 6,
      maxHp: 6,
      defeated: false,
      attacking: false,
    },
    threats: [],
    pickups: [],
    healingCarried: false,
    combatEnabled: true,
    navigation: FLAT,
    bounds: { left: 0, right: 640 },
  };
  return { ...base, ...overrides, self: { ...base.self, ...(overrides.self ?? {}) } };
}

function contextFor(view: BotWorldView, memory: BotMemory = INITIAL_BOT_MEMORY): BotContext {
  const standing = locateNavNode(view.navigation, view.self.x, view.self.y);
  return {
    view,
    memory,
    tuning: HUNTER_BOT_TUNING,
    capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
    reach: standing ? navReach(view.navigation, standing.id) : [],
    standingOn: standing?.id ?? null,
  };
}

describe("standing down", () => {
  test("a defeated character presses nothing at all", () => {
    const proposal = standDownBehavior.consider(
      contextFor(worldView({ self: { defeated: true } as never })),
    );
    expect(proposal?.priority).toBe(BOT_PRIORITY.standDown);
    expect(proposal?.intent).toEqual(NEUTRAL_PLAYER_INTENT);
  });

  test("a world with no navigable surface is the same answer", () => {
    const proposal = standDownBehavior.consider(
      contextFor(worldView({ navigation: { nodes: [], links: [] } })),
    );
    expect(proposal?.goal).toBe("stand_down");
  });

  test("an ordinary frame is declined", () => {
    expect(standDownBehavior.consider(contextFor(worldView()))).toBeNull();
  });
});

describe("healing", () => {
  test("it drinks below the threshold and only while carrying something", () => {
    const low = { hp: 2, maxHp: 6 } as never;
    // Low, but with an empty bag: there is nothing to spend, so there is nothing to propose.
    expect(healBehavior.consider(contextFor(worldView({ self: low })))).toBeNull();
    const proposal = healBehavior.consider(
      contextFor(worldView({ self: low, healingCarried: true })),
    );
    expect(proposal?.intent.useHealing).toBe(true);
    expect(proposal?.reason).toBe("hp 2/6");
  });

  test("a healthy character does not spend a potion", () => {
    expect(
      healBehavior.consider(contextFor(worldView({ healingCarried: true }))),
    ).toBeNull();
  });

  test("a full character at the threshold still does not, because a drink would be refused", () => {
    const proposal = healBehavior.consider(
      contextFor(worldView({ healingCarried: true, self: { hp: 6, maxHp: 6 } as never })),
    );
    expect(proposal).toBeNull();
  });

  test("it outbids fighting, which is what keeps the character alive in a hunting ground", () => {
    expect(BOT_PRIORITY.heal).toBeGreaterThan(BOT_PRIORITY.engage);
  });
});

describe("engaging", () => {
  test("a mob within reach is attacked", () => {
    const proposal = engageBehavior.consider(
      contextFor(worldView({ threats: [{ id: "mob_1", x: 340, y: GROUND, hp: 2 }] })),
    );
    expect(proposal?.goal).toBe("engage");
    expect(proposal?.intent.attack).toBe(true);
    expect(proposal?.targetId).toBe("mob_1");
  });

  test("a mob behind the character is turned onto before the swing lands", () => {
    const proposal = engageBehavior.consider(
      contextFor(worldView({ threats: [{ id: "mob_1", x: 260, y: GROUND, hp: 2 }] })),
    );
    expect(proposal?.intent.left).toBe(true);
    expect(proposal?.intent.right).toBe(false);
  });

  test("a mob a deck above is not in reach however close it looks", () => {
    expect(
      engageBehavior.consider(
        contextFor(worldView({ threats: [{ id: "mob_1", x: 305, y: GROUND - TILE * 3, hp: 2 }] })),
      ),
    ).toBeNull();
  });

  test("a package without combat never swings", () => {
    expect(
      engageBehavior.consider(
        contextFor(
          worldView({ combatEnabled: false, threats: [{ id: "mob_1", x: 340, y: GROUND, hp: 2 }] }),
        ),
      ),
    ).toBeNull();
  });
});

describe("travel", () => {
  test("a point on the same shelf is walked to directly", () => {
    const plan = planTravel(contextFor(worldView()), { x: 600, y: GROUND });
    expect(plan?.intent.right).toBe(true);
    expect(plan?.cost).toBeGreaterThan(0);
  });

  test("a point on another shelf opens with the move that leads there", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 2, 2, 2]);
    const plan = planTravel(contextFor(worldView({ navigation: graph, self: { x: 60 } as never })), {
      x: 400,
      y: BASELINE - TILE * 2,
    });
    expect(plan).not.toBeNull();
    expect(plan!.intent.right).toBe(true);
  });

  test("a point with no route at all is refused rather than walked toward", () => {
    const graph = graphFor([1, 1, 1, 1], [{ id: "sky", left: 0, right: 256, deckY: BASELINE - TILE * 8 }]);
    const plan = planTravel(contextFor(worldView({ navigation: graph })), {
      x: 128,
      y: BASELINE - TILE * 8,
    });
    expect(plan).toBeNull();
  });
});

describe("pursuit", () => {
  test("it goes to the mob that is cheapest to reach, not the nearest on screen", () => {
    // The near mob is up a shelf that has to be jumped; the far one is a straight walk.
    const graph = graphFor([2, 2, 1, 1, 1, 1, 1, 1]);
    const context = contextFor(
      worldView({
        navigation: graph,
        self: { x: 400, y: GROUND } as never,
        threats: [
          { id: "mob_high", x: 60, y: BASELINE - TILE * 2, hp: 2 },
          { id: "mob_flat", x: 600, y: GROUND, hp: 2 },
        ],
      }),
    );
    expect(pursueBehavior.consider(context)?.targetId).toBe("mob_flat");
  });

  test("an unreachable mob is not a target", () => {
    const graph = graphFor([1, 1, 1, 1], [{ id: "sky", left: 0, right: 256, deckY: BASELINE - TILE * 8 }]);
    expect(
      pursueBehavior.consider(
        contextFor(
          worldView({
            navigation: graph,
            threats: [{ id: "mob_sky", x: 128, y: BASELINE - TILE * 8, hp: 2 }],
          }),
        ),
      ),
    ).toBeNull();
  });

  test("a mob beyond the pursuit range is left alone", () => {
    expect(
      pursueBehavior.consider(
        contextFor(worldView({ threats: [{ id: "mob_far", x: 9_000, y: GROUND, hp: 2 }] })),
      ),
    ).toBeNull();
  });

  test("the mob already being chased keeps the lead over an equal rival", () => {
    const view = worldView({
      threats: [
        { id: "mob_a", x: 200, y: GROUND, hp: 2 },
        { id: "mob_b", x: 400, y: GROUND, hp: 2 },
      ],
    });
    expect(pursueBehavior.consider(contextFor(view))?.targetId).toBe("mob_a");
    const chasingB = contextFor(view, { ...INITIAL_BOT_MEMORY, targetId: "mob_b" });
    expect(pursueBehavior.consider(chasingB)?.targetId).toBe("mob_b");
  });
});

describe("collecting", () => {
  test("a drop within range is walked over", () => {
    const proposal = collectBehavior.consider(
      contextFor(worldView({ pickups: [{ id: "drop_1", x: 420, y: GROUND, settled: true }] })),
    );
    expect(proposal?.goal).toBe("collect");
    expect(proposal?.intent.right).toBe(true);
  });

  test("loot is swept before the next mob is chased, and after the current one is finished", () => {
    expect(BOT_PRIORITY.collect).toBeGreaterThan(BOT_PRIORITY.pursue);
    expect(BOT_PRIORITY.collect).toBeLessThan(BOT_PRIORITY.engage);
  });
});

describe("patrolling", () => {
  test("it never declines, because a still character reads as a broken one", () => {
    const proposal = patrolBehavior.consider(contextFor(worldView()));
    expect(proposal.goal).toBe("patrol");
    expect(proposal.intent.right).toBe(true);
  });

  test("it walks the way the bookkeeping is pointing", () => {
    const proposal = patrolBehavior.consider(
      contextFor(worldView(), { ...INITIAL_BOT_MEMORY, patrolSign: -1 }),
    );
    expect(proposal.intent.left).toBe(true);
  });

  test("a long stall against something the graph does not model is jumped out of", () => {
    const stuck = contextFor(worldView(), {
      ...INITIAL_BOT_MEMORY,
      stuckFrames: HUNTER_BOT_TUNING.stuckFramesBeforeJump,
    });
    expect(patrolBehavior.consider(stuck).intent.jump).toBe(true);
  });
});

describe("profiles", () => {
  test("the shipped hunter carries every behaviour and the default body", () => {
    expect(HUNTER_BOT_PROFILE.roster.map((behavior) => behavior.id)).toEqual([
      "stand_down",
      "heal",
      "engage",
      "collect",
      "pursue",
      "patrol",
    ]);
    expect(HUNTER_BOT_PROFILE.capabilities).toEqual(DEFAULT_MOVEMENT_CAPABILITIES);
  });

  test("switching a behaviour off removes it, and leaves the rest untouched", () => {
    const noLoot = botProfileWithout(HUNTER_BOT_PROFILE, ["collect"]);
    expect(noLoot.roster.map((behavior) => behavior.id)).not.toContain("collect");
    expect(noLoot.roster).toHaveLength(HUNTER_BOT_PROFILE.roster.length - 1);
    expect(noLoot.id).not.toBe(HUNTER_BOT_PROFILE.id);
    expect(HUNTER_BOT_PROFILE.roster).toHaveLength(6);
  });

  test("a profile can be given a different body without touching a behaviour", () => {
    const grounded = { ...HUNTER_BOT_PROFILE, capabilities: movementCapabilities({ airJumpVelocity: null }) };
    expect(grounded.capabilities.airJumpVelocity).toBeNull();
    expect(grounded.roster).toBe(HUNTER_BOT_PROFILE.roster);
  });
});
