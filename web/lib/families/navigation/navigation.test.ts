import { describe, expect, test } from "bun:test";
import {
  DEFAULT_MOVEMENT_CAPABILITIES,
  DEFAULT_NAV_STEER_TUNING,
  buildNavGraph,
  locateNavNode,
  movementCapabilities,
  navReach,
  reachOf,
  steerNav,
  type NavAgentState,
  type NavGraph,
  type NavLink,
} from "@/lib/sideview-platformer/bot-navigation";

const TILE = 64;
const BASELINE = 720;

/** Surfaces for a stepped world, in the runtime's own feet-down world units. */
function surfaces(heights: readonly number[]): number[] {
  return heights.map((height) => BASELINE - height * TILE);
}

function graphFor(
  heights: readonly number[],
  options: Readonly<{
    platforms?: readonly { id: string; left: number; right: number; deckY: number }[];
    climbables?: readonly {
      id: string;
      centerX: number;
      upperDeckY: number;
      lowerSurfaceY: number;
    }[];
    capabilities?: Partial<Parameters<typeof movementCapabilities>[0]>;
  }> = {},
): NavGraph {
  return buildNavGraph({
    columnSurfaceY: surfaces(heights),
    tileUnits: TILE,
    platforms: options.platforms ?? [],
    climbables: options.climbables ?? [],
    capabilities: movementCapabilities(options.capabilities ?? {}),
  });
}

const GROUNDED: NavAgentState = {
  x: 100,
  footY: BASELINE - TILE,
  vx: 0,
  vy: 0,
  airborne: false,
  support: "terrain",
  airJumpsUsed: 0,
};

function linkNamed(graph: NavGraph, id: string): NavLink {
  const link = graph.links.find((candidate) => candidate.id === id);
  if (!link) throw new Error(`no link ${id} in ${graph.links.map((entry) => entry.id).join(", ")}`);
  return link;
}

describe("terrain lanes", () => {
  test("a level run of columns is one shelf, and a step starts another", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1]);
    expect(graph.nodes.map((node) => node.id)).toEqual([
      "terrain:0",
      "terrain:1",
      "terrain:2",
    ]);
    expect(graph.nodes[0]).toMatchObject({ left: 0, right: 192, surfaceY: BASELINE - TILE });
    expect(graph.nodes[1]).toMatchObject({ left: 192, right: 320, surfaceY: BASELINE - TILE * 2 });
  });

  test("flat ground is a single shelf with nothing to traverse", () => {
    const graph = graphFor([1, 1, 1, 1]);
    expect(graph.nodes).toHaveLength(1);
    expect(graph.links).toHaveLength(0);
  });

  test("a step down is free and the same step up is a jump", () => {
    const graph = graphFor([1, 1, 2, 2]);
    expect(linkNamed(graph, "terrain:1>terrain:0:step_down").move).toBe("step_down");
    expect(linkNamed(graph, "terrain:0>terrain:1:jump").move).toBe("jump");
    expect(linkNamed(graph, "terrain:1>terrain:0:step_down").cost).toBeLessThan(
      linkNamed(graph, "terrain:0>terrain:1:jump").cost,
    );
  });

  test("a landing point sits inside the shelf it names, not on its lip", () => {
    const graph = graphFor([1, 1, 2, 2]);
    const up = linkNamed(graph, "terrain:0>terrain:1:jump");
    expect(up.fromX).toBeLessThanOrEqual(128);
    expect(up.toX).toBeGreaterThan(128);
    expect(up.toX).toBeLessThan(256);
  });

  test("shelves with a third between them are not linked to each other", () => {
    const graph = graphFor([1, 1, 2, 2, 1, 1]);
    expect(graph.links.some((link) => link.from === "terrain:0" && link.to === "terrain:2")).toBe(false);
  });
});

describe("capability gating", () => {
  const platforms = [{ id: "deck", left: 128, right: 320, deckY: BASELINE - TILE * 4 }];

  test("a rise the second jump reaches is admitted as a double jump", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1], { platforms });
    expect(linkNamed(graph, "terrain:1>platform:deck:double_jump").move).toBe("double_jump");
  });

  test("the same rise does not exist at all for a character with one jump", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1], {
      platforms,
      capabilities: { airJumpVelocity: null },
    });
    expect(graph.links.some((link) => link.to === "platform:deck")).toBe(false);
    expect(graph.nodes.some((node) => node.id === "platform:deck")).toBe(true);
  });

  test("a rise past both jumps is refused however the character is equipped", () => {
    const graph = graphFor([1, 1, 1, 1], {
      platforms: [{ id: "sky", left: 0, right: 256, deckY: BASELINE - TILE * 8 }],
    });
    expect(graph.links.some((link) => link.to === "platform:sky")).toBe(false);
  });

  test("a character that cannot drop through never gets the link", () => {
    const withDrop = graphFor([1, 1, 1, 1], { platforms });
    const withoutDrop = graphFor([1, 1, 1, 1], {
      platforms,
      capabilities: { canDropThrough: false },
    });
    expect(withDrop.links.some((link) => link.move === "drop_through")).toBe(true);
    expect(withoutDrop.links.some((link) => link.move === "drop_through")).toBe(false);
  });

  test("a climbable joins the deck it serves in both directions, and only when climbing is on", () => {
    const climbables = [
      { id: "ladder_a", centerX: 200, upperDeckY: BASELINE - TILE * 4, lowerSurfaceY: BASELINE - TILE },
    ];
    const graph = graphFor([1, 1, 1, 1, 1, 1], { platforms, climbables });
    const climbs = graph.links.filter((link) => link.move === "climb");
    expect(climbs).toHaveLength(2);
    expect(climbs.every((link) => link.climbableId === "ladder_a")).toBe(true);
    const noClimb = graphFor([1, 1, 1, 1, 1, 1], {
      platforms,
      climbables,
      capabilities: { canClimb: false },
    });
    expect(noClimb.links.some((link) => link.move === "climb")).toBe(false);
  });
});

describe("deck geometry", () => {
  const platforms = [{ id: "deck", left: 128, right: 320, deckY: BASELINE - TILE * 4 }];

  test("stepping off a deck needs ground that continues past its edge", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1], { platforms });
    // terrain:1 lies entirely under the deck's span; there is no edge to walk off onto it.
    expect(graph.links.some((link) => link.id === "platform:deck>terrain:1:step_down")).toBe(false);
    expect(graph.links.some((link) => link.id === "platform:deck>terrain:1:drop_through")).toBe(true);
    expect(graph.links.some((link) => link.id === "platform:deck>terrain:0:step_down")).toBe(true);
  });

  test("shelves that only touch a deck at a point are not dropped onto", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1], { platforms });
    expect(graph.links.some((link) => link.id === "platform:deck>terrain:2:drop_through")).toBe(false);
  });
});

describe("reach", () => {
  test("costs accumulate along the route and name the opening move", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1]);
    const reach = navReach(graph, "terrain:0");
    const near = reachOf(reach, "terrain:1");
    const far = reachOf(reach, "terrain:2");
    expect(reachOf(reach, "terrain:0")).toMatchObject({ cost: 0, firstLink: null });
    expect(far!.cost).toBeGreaterThan(near!.cost);
    expect(far!.firstLink!.id).toBe("terrain:0>terrain:1:jump");
    expect(near!.firstLink!.id).toBe("terrain:0>terrain:1:jump");
  });

  test("a node with no route in is simply absent", () => {
    const graph = graphFor([1, 1, 1, 1], {
      platforms: [{ id: "sky", left: 0, right: 256, deckY: BASELINE - TILE * 8 }],
    });
    expect(reachOf(navReach(graph, "terrain:0"), "platform:sky")).toBeNull();
  });

  test("an unknown starting node reaches nothing rather than throwing", () => {
    expect(navReach(graphFor([1, 1]), "terrain:9")).toHaveLength(0);
  });
});

describe("locating a character", () => {
  test("a standing character is on the shelf under its feet", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1]);
    expect(locateNavNode(graph, 100, BASELINE - TILE)?.id).toBe("terrain:0");
    expect(locateNavNode(graph, 250, BASELINE - TILE * 2)?.id).toBe("terrain:1");
  });

  test("a character mid-jump is still somewhere, because a lost navigator stops dead", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1]);
    expect(locateNavNode(graph, 100, BASELINE - TILE * 3)).not.toBeNull();
  });

  test("an empty graph is the one case with no answer", () => {
    expect(locateNavNode({ nodes: [], links: [] }, 0, 0)).toBeNull();
  });
});

describe("steering", () => {
  const capabilities = DEFAULT_MOVEMENT_CAPABILITIES;

  test("with nowhere to go but along this shelf, it walks and then stops", () => {
    const far = steerNav({ self: GROUNDED, link: null, targetX: 600, capabilities });
    expect(far.right).toBe(true);
    expect(far.run).toBe(true);
    const arrived = steerNav({ self: GROUNDED, link: null, targetX: 104, capabilities });
    expect(arrived.left).toBe(false);
    expect(arrived.right).toBe(false);
  });

  test("a jump is committed near its launch point, not before", () => {
    const graph = graphFor([1, 1, 2, 2]);
    const link = linkNamed(graph, "terrain:0>terrain:1:jump");
    const early = steerNav({ self: { ...GROUNDED, x: 0 }, link, targetX: 200, capabilities });
    expect(early.jump).toBe(false);
    expect(early.right).toBe(true);
    const atEdge = steerNav({
      self: { ...GROUNDED, x: link.fromX - DEFAULT_NAV_STEER_TUNING.launchWindowUnits / 2 },
      link,
      targetX: 200,
      capabilities,
    });
    expect(atEdge.jump).toBe(true);
  });

  test("the air jump is spent at the apex, which is where the proof spent it", () => {
    const graph = graphFor([1, 1, 1, 2, 2, 1, 1, 1], {
      platforms: [{ id: "deck", left: 128, right: 320, deckY: BASELINE - TILE * 4 }],
    });
    const link = linkNamed(graph, "terrain:1>platform:deck:double_jump");
    const airborne = { ...GROUNDED, x: link.fromX, airborne: true, support: "air" as const };
    expect(steerNav({ self: { ...airborne, vy: -200 }, link, targetX: link.toX, capabilities }).jump).toBe(
      false,
    );
    expect(steerNav({ self: { ...airborne, vy: 0 }, link, targetX: link.toX, capabilities }).jump).toBe(true);
    expect(
      steerNav({
        self: { ...airborne, vy: 10, airJumpsUsed: 1 },
        link,
        targetX: link.toX,
        capabilities,
      }).jump,
    ).toBe(false);
  });

  test("a single jump is never re-pressed in the air, whatever the arc is doing", () => {
    const graph = graphFor([1, 1, 2, 2]);
    const link = linkNamed(graph, "terrain:0>terrain:1:jump");
    const airborne = { ...GROUNDED, x: link.fromX, airborne: true, vy: 40, support: "air" as const };
    expect(steerNav({ self: airborne, link, targetX: link.toX, capabilities }).jump).toBe(false);
  });

  test("a climb lines up first, then holds the direction it is travelling", () => {
    const graph = graphFor([1, 1, 1, 1, 1, 1], {
      platforms: [{ id: "deck", left: 128, right: 320, deckY: BASELINE - TILE * 4 }],
      climbables: [
        { id: "ladder_a", centerX: 200, upperDeckY: BASELINE - TILE * 4, lowerSurfaceY: BASELINE - TILE },
      ],
    });
    const up = linkNamed(graph, "terrain:0>platform:deck:climb");
    const away = steerNav({ self: { ...GROUNDED, x: 20 }, link: up, targetX: 200, capabilities });
    expect(away.right).toBe(true);
    expect(away.up).toBe(false);
    const aligned = steerNav({ self: { ...GROUNDED, x: 200 }, link: up, targetX: 200, capabilities });
    expect(aligned.up).toBe(true);
    const onLadder = steerNav({
      self: { ...GROUNDED, x: 200, support: "climbable" },
      link: up,
      targetX: 200,
      capabilities,
    });
    expect(onLadder.up).toBe(true);
    expect(onLadder.down).toBe(false);
  });

  test("dropping through is a down-and-jump once lined up over the hole", () => {
    const graph = graphFor([1, 1, 1, 1], {
      platforms: [{ id: "deck", left: 128, right: 320, deckY: BASELINE - TILE * 4 }],
    });
    const link = linkNamed(graph, "platform:deck>terrain:0:drop_through");
    const onDeck = { ...GROUNDED, x: link.fromX, footY: BASELINE - TILE * 4, support: "platform" as const };
    const intent = steerNav({ self: onDeck, link, targetX: link.toX, capabilities });
    expect(intent.down).toBe(true);
    expect(intent.jump).toBe(true);
  });
});

describe("capability validation", () => {
  test("a negative speed is refused rather than producing a graph nobody can walk", () => {
    expect(() => movementCapabilities({ runSpeed: -1 })).toThrow(/positive/);
    expect(() => movementCapabilities({ airJumpVelocity: 0 })).toThrow(/air jump/);
  });

  test("an absent air jump is a legitimate configuration, not an error", () => {
    expect(movementCapabilities({ airJumpVelocity: null }).airJumpVelocity).toBeNull();
  });
});
