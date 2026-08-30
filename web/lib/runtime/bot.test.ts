import { describe, expect, test } from "bun:test";
import { BOT_HUMAN_OVERRIDE_HOLD_MS, Bot, isNeutralIntent, resolveBotControl } from "./bot";
import { HUNTER_BOT_PROFILE, botProfileWithout } from "./bot-hunter";
import { buildNavGraph, DEFAULT_MOVEMENT_CAPABILITIES } from "./bot-navigation";
import type { BotWorldView } from "./bot-view";
import { NEUTRAL_PLAYER_INTENT, playerIntent } from "./player-intent";

import { preparedBotWeaponBand } from "./bot-adapter";
import { weaponClassProfile } from "./weapon-class";

/**
 * The melee band, projected the same way the scene projects it.
 *
 * Written as a projection rather than as literals so these fixtures cannot drift from the table
 * the runtime actually fights with: at a 64px tile it is 0 / 42 / 84 units with a 64-unit vertical
 * tolerance, which is exactly what the hunter used to carry as its own constants.
 */
const MELEE_BAND = preparedBotWeaponBand(weaponClassProfile("melee_dps_v1"), 64);

/** Level ground everywhere, so nothing in these fixtures is ever behind a wall. */
const FLAT_TERRAIN = Object.freeze({
  columnSurfaceY: Object.freeze(new Array(64).fill(720 - 64)),
  tileUnits: 64,
});


const TILE = 64;
const BASELINE = 720;
const GROUND = BASELINE - TILE;

const FLAT = buildNavGraph({
  columnSurfaceY: Array.from({ length: 10 }, () => GROUND),
  tileUnits: TILE,
  platforms: [],
  climbables: [],
  capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
});

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
    ammoCarried: true,
    weaponBand: MELEE_BAND,
    terrain: FLAT_TERRAIN,
    combatEnabled: true,
    navigation: FLAT,
    bounds: { left: 0, right: 640 },
  };
  return { ...base, ...overrides, self: { ...base.self, ...(overrides.self ?? {}) } };
}

describe("neutrality", () => {
  test("the resting intent is neutral and any request is not", () => {
    expect(isNeutralIntent(NEUTRAL_PLAYER_INTENT)).toBe(true);
    expect(isNeutralIntent(playerIntent({ toggleInventory: true }))).toBe(false);
    expect(isNeutralIntent(playerIntent({ left: true }))).toBe(false);
  });
});

describe("who is driving", () => {
  test("a touched key is a takeover, and the touch is remembered", () => {
    const control = resolveBotControl({
      humanIntent: playerIntent({ right: true }),
      enabled: true,
      nowMs: 5_000,
      lastHumanInputAtMs: null,
    });
    expect(control.source).toBe("human");
    expect(control.humanInputAtMs).toBe(5_000);
  });

  test("the takeover outlives the keypress, so a look around is not fought over", () => {
    const held = resolveBotControl({
      humanIntent: NEUTRAL_PLAYER_INTENT,
      enabled: true,
      nowMs: 5_000 + BOT_HUMAN_OVERRIDE_HOLD_MS - 1,
      lastHumanInputAtMs: 5_000,
    });
    expect(held.source).toBe("human");
    const released = resolveBotControl({
      humanIntent: NEUTRAL_PLAYER_INTENT,
      enabled: true,
      nowMs: 5_000 + BOT_HUMAN_OVERRIDE_HOLD_MS,
      lastHumanInputAtMs: 5_000,
    });
    expect(released.source).toBe("bot");
    expect(released.humanInputAtMs).toBe(5_000);
  });

  test("switched off, the human drives whether or not they are pressing anything", () => {
    expect(
      resolveBotControl({
        humanIntent: NEUTRAL_PLAYER_INTENT,
        enabled: false,
        nowMs: 90_000,
        lastHumanInputAtMs: null,
      }).source,
    ).toBe("human");
  });

  test("an untouched keyboard hands the frame straight to the bot", () => {
    expect(
      resolveBotControl({
        humanIntent: NEUTRAL_PLAYER_INTENT,
        enabled: true,
        nowMs: 1_000,
        lastHumanInputAtMs: null,
      }).source,
    ).toBe("bot");
  });
});

describe("the bot over successive frames", () => {
  test("an empty world is patrolled rather than stood in", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    const decision = bot.decide(worldView());
    expect(decision.goal).toBe("patrol");
    expect(decision.intent.right).toBe(true);
  });

  test("a mob in reach is fought, and a mob across the map is walked to", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    expect(bot.decide(worldView({ threats: [{ id: "mob_1", x: 340, y: GROUND, hp: 2 }] })).goal).toBe(
      "engage",
    );
    expect(bot.decide(worldView({ threats: [{ id: "mob_1", x: 600, y: GROUND, hp: 2 }] })).goal).toBe(
      "pursue",
    );
  });

  test("wounded with a potion, it drinks before it fights", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    const decision = bot.decide(
      worldView({
        healingCarried: true,
        self: { hp: 1, maxHp: 6 } as never,
        threats: [{ id: "mob_1", x: 320, y: GROUND, hp: 2 }],
      }),
    );
    expect(decision.goal).toBe("heal");
    expect(decision.intent.useHealing).toBe(true);
  });

  test("walking into a wall for long enough eventually produces a jump", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    const wedged = worldView({ self: { vx: 0 } as never });
    let jumped = false;
    for (let frame = 0; frame < 40 && !jumped; frame += 1) {
      jumped = bot.decide(wedged).intent.jump;
    }
    expect(jumped).toBe(true);
  });

  test("the same sequence of views produces the same sequence of intents", () => {
    const views = [
      worldView(),
      worldView({ threats: [{ id: "mob_1", x: 500, y: GROUND, hp: 2 }] }),
      worldView({ threats: [{ id: "mob_1", x: 340, y: GROUND, hp: 2 }] }),
      worldView({ pickups: [{ id: "drop_1", x: 380, y: GROUND, settled: true }] }),
    ];
    const run = () => {
      const bot = new Bot(HUNTER_BOT_PROFILE);
      return views.map((view) => bot.decide(view));
    };
    expect(run()).toEqual(run());
  });

  test("suspending drops the plan but keeps the bearings", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    bot.decide(worldView({ self: { x: 620 } as never }));
    bot.decide(worldView({ threats: [{ id: "mob_1", x: 600, y: GROUND, hp: 2 }] }));
    bot.suspend();
    expect(bot.lastDecision).toBeNull();
    // The patrol direction was turned around by the map edge and survives the takeover.
    expect(bot.decide(worldView()).intent.left).toBe(true);
  });

  test("resetting forgets the map entirely, which is what a rebuilt world requires", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    bot.decide(worldView({ self: { x: 620 } as never }));
    bot.reset();
    expect(bot.decide(worldView()).intent.right).toBe(true);
  });

  test("a profile with looting switched off walks past the drop it would have taken", () => {
    const view = worldView({ pickups: [{ id: "drop_1", x: 420, y: GROUND, settled: true }] });
    expect(new Bot(HUNTER_BOT_PROFILE).decide(view).goal).toBe("collect");
    const noLoot = new Bot(botProfileWithout(HUNTER_BOT_PROFILE, ["collect"]));
    expect(noLoot.decide(view).goal).toBe("patrol");
  });

  test("a swapped profile takes effect without rebuilding the bot", () => {
    const bot = new Bot(HUNTER_BOT_PROFILE);
    expect(bot.profileId).toBe("hunter_v1");
    bot.setProfile(botProfileWithout(HUNTER_BOT_PROFILE, ["pursue"]));
    expect(bot.decide(worldView({ threats: [{ id: "mob_1", x: 600, y: GROUND, hp: 2 }] })).goal).toBe(
      "patrol",
    );
  });
});
