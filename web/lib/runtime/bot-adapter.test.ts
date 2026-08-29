import { describe, expect, test } from "bun:test";
import { preparedBotSelfView, preparedBotWorldView, preparedNavGraph } from "./bot-adapter";
import { DEFAULT_MOVEMENT_CAPABILITIES, EMPTY_NAV_GRAPH } from "./bot-navigation";
import { facingToward, healthFraction, horizontalDistance, sameFootLevel } from "./bot-view";
import type { PlayerStateSnapshot } from "./player";

const TILE = 64;
const BASELINE = 720;

const SNAPSHOT = {
  state: "walk",
  facing: "right",
  x: 300,
  y: BASELINE - TILE,
  column: 4,
  vx: 200,
  vy: 0,
  airborne: false,
  airJumpsUsed: 0,
  attackActive: false,
  hp: 4,
  maxHp: 6,
  invulnerable: false,
  defeated: false,
  support: "terrain",
  supportId: null,
  ladderId: null,
  platformId: null,
  dropThroughPlatformId: null,
} as unknown as PlayerStateSnapshot;

describe("nav graph from a prepared map", () => {
  test("authored heights become standing surfaces in world units", () => {
    const graph = preparedNavGraph({
      heights: [1, 1, 2, 2],
      tileUnits: TILE,
      baselineY: BASELINE,
      platforms: [],
      climbables: [],
      capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
    });
    expect(graph.nodes.map((node) => node.surfaceY)).toEqual([BASELINE - TILE, BASELINE - TILE * 2]);
  });

  test("declared decks and climbables reach the graph under their own ids", () => {
    const graph = preparedNavGraph({
      heights: [1, 1, 1, 1, 1, 1],
      tileUnits: TILE,
      baselineY: BASELINE,
      platforms: [
        { id: "deck_a", left: 128, right: 320, deckY: BASELINE - TILE * 4, tier: 1 } as never,
      ],
      climbables: [
        {
          id: "ladder_a",
          centerX: 200,
          upperDeckY: BASELINE - TILE * 4,
          lowerSurfaceY: BASELINE - TILE,
        } as never,
      ],
      capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
    });
    expect(graph.nodes.some((node) => node.id === "platform:deck_a")).toBe(true);
    expect(graph.links.some((link) => link.climbableId === "ladder_a")).toBe(true);
  });

  test("a map with no columns produces a graph rather than a failure", () => {
    const graph = preparedNavGraph({
      heights: [],
      tileUnits: TILE,
      baselineY: BASELINE,
      platforms: [],
      climbables: [],
      capabilities: DEFAULT_MOVEMENT_CAPABILITIES,
    });
    expect(graph.nodes).toHaveLength(0);
  });
});

describe("the self view", () => {
  test("an attack animation counts as attacking, wider than the hit window", () => {
    expect(preparedBotSelfView(SNAPSHOT).attacking).toBe(false);
    expect(
      preparedBotSelfView({ ...SNAPSHOT, state: "attack" } as PlayerStateSnapshot).attacking,
    ).toBe(true);
  });

  test("position, health and support carry across unchanged", () => {
    const self = preparedBotSelfView(SNAPSHOT);
    expect(self).toMatchObject({ x: 300, hp: 4, maxHp: 6, support: "terrain", facing: "right" });
  });
});

describe("the world view", () => {
  test("map width becomes the patrol's bounds", () => {
    const view = preparedBotWorldView({
      nowMs: 10,
      deltaMs: 33,
      player: SNAPSHOT,
      threats: [],
      pickups: [],
      healingCarried: false,
      combatEnabled: true,
      navigation: EMPTY_NAV_GRAPH,
      worldWidth: 1_920,
    });
    expect(view.bounds).toEqual({ left: 0, right: 1_920 });
  });
});

describe("view helpers", () => {
  test("health is a fraction, and an empty pool is not a division", () => {
    expect(healthFraction({ hp: 3, maxHp: 6 } as never)).toBe(0.5);
    expect(healthFraction({ hp: 3, maxHp: 0 } as never)).toBe(0);
  });

  test("foot level decides who can be hit, not screen distance", () => {
    expect(sameFootLevel({ y: 100 }, { y: 140 }, 64)).toBe(true);
    expect(sameFootLevel({ y: 100 }, { y: 200 }, 64)).toBe(false);
    expect(horizontalDistance({ x: 10 }, { x: 40 })).toBe(30);
  });

  test("facing a point directly underfoot keeps the facing already held", () => {
    const self = { x: 100, facing: "left" } as never;
    expect(facingToward(self, 100)).toBe("left");
    expect(facingToward(self, 120)).toBe("right");
  });
});
