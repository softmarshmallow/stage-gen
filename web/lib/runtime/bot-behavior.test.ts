import { describe, expect, test } from "bun:test";
import {
  BOT_PRIORITY,
  INITIAL_BOT_MEMORY,
  arbitrate,
  decideBot,
  observeBotMemory,
  type BotBehavior,
  type BotProfile,
  type BotProposal,
  type BotTuning,
} from "./bot-behavior";
import { DEFAULT_MOVEMENT_CAPABILITIES } from "./bot-navigation";
import { HUNTER_BOT_TUNING } from "./bot-hunter";
import { NEUTRAL_PLAYER_INTENT, playerIntent } from "./player-intent";
import type { BotWorldView } from "./bot-view";

const TUNING: BotTuning = HUNTER_BOT_TUNING;

function view(overrides: Partial<BotWorldView> = {}): BotWorldView {
  return {
    nowMs: 1_000,
    deltaMs: 1000 / 30,
    self: {
      x: 300,
      y: 656,
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
    navigation: { nodes: [{ id: "terrain:0", kind: "terrain", left: 0, right: 640, surfaceY: 656 }], links: [] },
    bounds: { left: 0, right: 640 },
    ...overrides,
  };
}

function behavior(id: string, proposal: BotProposal | null): BotBehavior {
  return { id, consider: () => proposal };
}

function proposal(overrides: Partial<BotProposal> = {}): BotProposal {
  return {
    goal: "patrol",
    priority: 100,
    intent: NEUTRAL_PLAYER_INTENT,
    targetId: null,
    reason: "test",
    ...overrides,
  };
}

describe("arbitration", () => {
  test("the loudest bid wins", () => {
    const winner = arbitrate([
      proposal({ goal: "patrol", priority: BOT_PRIORITY.patrol }),
      proposal({ goal: "heal", priority: BOT_PRIORITY.heal }),
      proposal({ goal: "pursue", priority: BOT_PRIORITY.pursue }),
    ]);
    expect(winner?.goal).toBe("heal");
  });

  test("a tie leaves the earlier-declared behaviour in place", () => {
    const winner = arbitrate([
      proposal({ goal: "collect", priority: 500, reason: "first" }),
      proposal({ goal: "pursue", priority: 500, reason: "second" }),
    ]);
    expect(winner?.reason).toBe("first");
  });

  test("a roster that all declines has no winner", () => {
    expect(arbitrate([null, null])).toBeNull();
  });
});

describe("bookkeeping", () => {
  test("asking to move while going nowhere accumulates, and any progress clears it", () => {
    const stuck = observeBotMemory({
      memory: { ...INITIAL_BOT_MEMORY, stuckFrames: 3 },
      view: view(),
      previousIntent: playerIntent({ right: true }),
      tuning: TUNING,
    });
    expect(stuck.stuckFrames).toBe(4);
    const moving = observeBotMemory({
      memory: stuck,
      view: view({ self: { ...view().self, vx: 400 } }),
      previousIntent: playerIntent({ right: true }),
      tuning: TUNING,
    });
    expect(moving.stuckFrames).toBe(0);
  });

  test("standing still on purpose is not being stuck", () => {
    const memory = observeBotMemory({
      memory: { ...INITIAL_BOT_MEMORY, stuckFrames: 5 },
      view: view(),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(memory.stuckFrames).toBe(0);
  });

  test("a character in the air is falling, not wedged", () => {
    const memory = observeBotMemory({
      memory: { ...INITIAL_BOT_MEMORY, stuckFrames: 5 },
      view: view({ self: { ...view().self, airborne: true } }),
      previousIntent: playerIntent({ right: true }),
      tuning: TUNING,
    });
    expect(memory.stuckFrames).toBe(0);
  });

  test("the map edge turns a patrol around and the middle leaves it alone", () => {
    const atRight = observeBotMemory({
      memory: INITIAL_BOT_MEMORY,
      view: view({ self: { ...view().self, x: 620 } }),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(atRight.patrolSign).toBe(-1);
    const middle = observeBotMemory({
      memory: atRight,
      view: view(),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(middle.patrolSign).toBe(-1);
    const atLeft = observeBotMemory({
      memory: middle,
      view: view({ self: { ...view().self, x: 10 } }),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(atLeft.patrolSign).toBe(1);
  });

  test("a target that has left the world is forgotten", () => {
    const kept = observeBotMemory({
      memory: { ...INITIAL_BOT_MEMORY, targetId: "mob_1" },
      view: view({ threats: [{ id: "mob_1", x: 400, y: 656, hp: 2 }] }),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(kept.targetId).toBe("mob_1");
    const dropped = observeBotMemory({
      memory: kept,
      view: view(),
      previousIntent: NEUTRAL_PLAYER_INTENT,
      tuning: TUNING,
    });
    expect(dropped.targetId).toBeNull();
  });
});

describe("one frame of thought", () => {
  function profileOf(roster: readonly BotBehavior[]): BotProfile {
    return {
      id: "test",
      tuning: TUNING,
      roster,
      capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
    };
  }

  test("the winner's intent, goal and target become the frame's answer", () => {
    const decision = decideBot({
      view: view(),
      memory: INITIAL_BOT_MEMORY,
      previousIntent: NEUTRAL_PLAYER_INTENT,
      profile: profileOf([
        behavior("low", proposal({ priority: 10, goal: "patrol" })),
        behavior(
          "high",
          proposal({
            priority: 900,
            goal: "engage",
            targetId: "mob_2",
            intent: playerIntent({ attack: true }),
          }),
        ),
      ]),
      reach: [],
      standingOn: "terrain:0",
    });
    expect(decision.goal).toBe("engage");
    expect(decision.intent.attack).toBe(true);
    expect(decision.memory.targetId).toBe("mob_2");
    expect(decision.memory.lastGoal).toBe("engage");
  });

  test("only the winner's memory patch survives the frame", () => {
    const decision = decideBot({
      view: view(),
      memory: INITIAL_BOT_MEMORY,
      previousIntent: NEUTRAL_PLAYER_INTENT,
      profile: profileOf([
        behavior("loser", proposal({ priority: 10, memory: { patrolSign: -1 } })),
        behavior("winner", proposal({ priority: 20, goal: "collect" })),
      ]),
      reach: [],
      standingOn: "terrain:0",
    });
    expect(decision.memory.patrolSign).toBe(1);
  });

  test("an empty roster stands down rather than inventing an action", () => {
    const decision = decideBot({
      view: view(),
      memory: INITIAL_BOT_MEMORY,
      previousIntent: NEUTRAL_PLAYER_INTENT,
      profile: profileOf([]),
      reach: [],
      standingOn: null,
    });
    expect(decision.goal).toBe("stand_down");
    expect(decision.intent).toEqual(NEUTRAL_PLAYER_INTENT);
  });

  test("the same view and memory decide the same way every time", () => {
    const roster = profileOf([
      behavior("a", proposal({ priority: 50, goal: "collect", targetId: "drop_1" })),
      behavior("b", proposal({ priority: 50, goal: "pursue", targetId: "mob_1" })),
    ]);
    const once = decideBot({
      view: view(),
      memory: INITIAL_BOT_MEMORY,
      previousIntent: NEUTRAL_PLAYER_INTENT,
      profile: roster,
      reach: [],
      standingOn: "terrain:0",
    });
    const twice = decideBot({
      view: view(),
      memory: INITIAL_BOT_MEMORY,
      previousIntent: NEUTRAL_PLAYER_INTENT,
      profile: roster,
      reach: [],
      standingOn: "terrain:0",
    });
    expect(twice).toEqual(once);
  });
});
