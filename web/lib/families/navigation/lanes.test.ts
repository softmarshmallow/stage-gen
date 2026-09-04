import { describe, expect, test } from "bun:test";

import { buildNavGraph, laneAtColumn, movementCapabilities, navReach, reachOf, terrainLanes } from "./index";

// E4 for `navigation`: one graph, two bodies with different repertoires, and
// one lane rule where there were two.
//
// The two bodies are the platformer's player-shaped navigator — which climbs,
// drops through decks and has a second jump in the air — and a creature-shaped
// one, which has none of those and a slower walk. The plan's E4 for this family
// is "the mob reaching decks through the bot's graph", and this is that: the
// creature's own capabilities, over the same map, through the same
// `buildNavGraph`, reaching a deck by the one move it does have.
//
// Wiring live creatures onto the graph is deliberately not done here. It would
// move every frame of the platformer's golden with no evidence behind the
// movement, which is the shape of change step 4 refused when it put the
// missing first-frame dust back. What is proved here is that the graph answers
// for a creature; what a creature does with the answer is a step that can
// measure it.

const TILE = 64;
const BASELINE = 720;

function surfaces(heights: readonly number[]): number[] {
  return heights.map((height) => BASELINE - height * TILE);
}

/** The bot's repertoire: the controller's own constants. */
const AGILE = movementCapabilities({
  walkSpeed: 200,
  runSpeed: 540,
  jumpVelocity: 520,
  airJumpVelocity: 440,
  gravity: 1500,
  stepSeconds: 1 / 30,
  stepUpTolerance: 1,
  canClimb: true,
  canDropThrough: true,
});

/** A creature's: one jump, no ladders, no dropping through anything. */
const PLODDING = movementCapabilities({
  ...AGILE,
  walkSpeed: 90,
  runSpeed: 90,
  airJumpVelocity: null,
  canClimb: false,
  canDropThrough: false,
});

describe("the one lane rule, where there were two", () => {
  test("cutting the whole field and finding one lane agree, column for column", () => {
    const field = {
      columns: 12,
      surfaceAt: (column: number) => surfaces([1, 1, 1, 2, 2, 0, 0, 0, 0, 3, 3, 1])[column]!,
      tolerance: 0,
    };
    const lanes = terrainLanes(field);
    expect(lanes.map((lane) => [lane.startColumn, lane.endColumn])).toEqual([
      [0, 3],
      [3, 5],
      [5, 9],
      [9, 11],
      [11, 12],
    ]);
    // The creature's question, asked of every column, has to land in the lane
    // the graph's cut put it in. These really are two walks — one forward, one
    // outward from a point — so the agreement is measured rather than assumed.
    for (let column = 0; column < field.columns; column += 1) {
      const found = laneAtColumn(field, column);
      const owning = lanes.find(
        (lane) => column >= lane.startColumn && column < lane.endColumn,
      );
      expect(found).toEqual(owning!);
    }
  });

  test("a tolerance widens both cuts identically", () => {
    // Surfaces a unit apart are one lane at tolerance 1 and two at tolerance 0,
    // and the two derivations move together.
    const field = (tolerance: number) => ({
      columns: 4,
      surfaceAt: (column: number) => [100, 101, 102, 200][column]!,
      tolerance,
    });
    expect(terrainLanes(field(0)).length).toBe(4);
    expect(terrainLanes(field(1)).map((lane) => lane.endColumn)).toEqual([3, 4]);
    expect(laneAtColumn(field(1), 1)).toEqual({ startColumn: 0, endColumn: 3, surface: 100 });
    expect(laneAtColumn(field(0), 1)).toEqual({ startColumn: 1, endColumn: 2, surface: 101 });
  });

  test("the field refuses what it cannot cut", () => {
    const field = { columns: 2, surfaceAt: () => 0, tolerance: 0 };
    expect(() => laneAtColumn(field, 2)).toThrow("must lie inside the field");
    expect(() => laneAtColumn(field, -1)).toThrow("must lie inside the field");
    expect(() => terrainLanes({ ...field, tolerance: -1 })).toThrow("finite and nonnegative");
    expect(() =>
      terrainLanes({ columns: 2, surfaceAt: () => Number.NaN, tolerance: 0 }),
    ).toThrow("lane surfaces must be finite");
    // An empty field is an empty cut, not a refusal: a map with no columns has
    // no lanes, which is an answer.
    expect(terrainLanes({ columns: 0, surfaceAt: () => 0, tolerance: 0 })).toEqual([]);
  });
});

describe("one graph, two repertoires", () => {
  const input = {
    columnSurfaceY: surfaces([1, 1, 1, 1, 1, 1, 1, 1]),
    tileUnits: TILE,
    platforms: [
      // One tile of rise above the floor: inside a single jump for either body.
      { id: "low-deck", left: TILE * 2, right: TILE * 4, deckY: BASELINE - TILE * 2 },
      // Two tiles: the agile body needs its air jump, and the creature has none.
      { id: "high-deck", left: TILE * 5, right: TILE * 7, deckY: BASELINE - TILE * 3 },
    ],
    climbables: [
      {
        id: "ladder",
        centerX: TILE * 6.5,
        upperDeckY: BASELINE - TILE * 3,
        lowerSurfaceY: BASELINE - TILE,
      },
    ],
  };

  test("the creature reaches a deck through the same graph the bot walks", () => {
    const creature = buildNavGraph({ ...input, capabilities: PLODDING });
    const floor = creature.nodes.find((node) => node.kind === "terrain")!;
    const reach = navReach(creature, floor.id);
    const low = reachOf(reach, "platform:low-deck");
    expect(low).not.toBeNull();
    expect(low!.firstLink!.move).toBe("jump");
    // And it is the same node the agile body reaches, by the same move.
    const bot = buildNavGraph({ ...input, capabilities: AGILE });
    expect(reachOf(navReach(bot, floor.id), "platform:low-deck")!.firstLink!.move).toBe("jump");
  });

  test("a repertoire it does not have is a place that does not exist", () => {
    const bot = buildNavGraph({ ...input, capabilities: AGILE });
    const creature = buildNavGraph({ ...input, capabilities: PLODDING });
    const moves = (graph: typeof bot) => new Set(graph.links.map((link) => link.move));
    // The agile body climbs, double-jumps and drops through.
    expect(moves(bot).has("climb")).toBe(true);
    expect(moves(bot).has("double_jump")).toBe(true);
    expect(moves(bot).has("drop_through")).toBe(true);
    // The creature does none of those, and the high deck is not somewhere it
    // fails to reach — it is somewhere that is not there.
    expect(moves(creature).has("climb")).toBe(false);
    expect(moves(creature).has("double_jump")).toBe(false);
    expect(moves(creature).has("drop_through")).toBe(false);
    const floor = creature.nodes.find((node) => node.kind === "terrain")!;
    expect(reachOf(navReach(creature, floor.id), "platform:high-deck")).toBeNull();
    expect(reachOf(navReach(bot, floor.id), "platform:high-deck")).not.toBeNull();
  });

  test("a jump link is a promise the traversal core keeps", () => {
    // The admission ran `simulateJumpArc` — the same integrator the controller
    // steps — so a rise the graph admits is a rise the body flies, and one it
    // refuses is one no amount of steering reaches. Raise the deck past the
    // agile body's two impulses and the link disappears rather than becoming a
    // route it fails at.
    const unreachable = buildNavGraph({
      ...input,
      platforms: [{ id: "sky", left: TILE * 2, right: TILE * 4, deckY: BASELINE - TILE * 9 }],
      climbables: [],
      capabilities: AGILE,
    });
    expect(unreachable.links.some((link) => link.to === "platform:sky")).toBe(false);
  });
});
