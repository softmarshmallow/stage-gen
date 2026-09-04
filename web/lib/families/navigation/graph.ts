// Navigation — the model of how a character gets from where it stands to where it wants to be.
//
// One graph, derived from the traversal core, for every character that moves
// under its own steam. This file was the bot's; the ruling is that it was never
// the bot's, because nothing in it mentions a bot. What made it look like one
// character's property was that the *other* character with the same problem —
// the wandering creature — had a second, incompatible derivation of the same
// lanes over the same heightfield, so the two never met.
//
// A jump link is a promise, and it is kept only because the admission and the
// physics read one integrator: `simulateJumpArc` is the traversal family's, the
// same fixed-step semi-implicit Euler the controller steps. That is the whole
// reason this family sits on top of `sideview/traversal` rather than beside it.
//
// This is the first layer of the bot, and deliberately the one that knows nothing about *why* a
// destination was chosen. A behaviour picks a target; navigation answers two questions about it:
// can I reach it, and what do I press this frame to get closer. Keeping those apart is what lets
// the character's repertoire grow without rewriting a single decision: teaching it to double jump,
// to climb, or to drop through a floor changes the graph and the steering, and every behaviour
// that merely wanted to reach something inherits the new ability for free.
//
// The repertoire itself is data, not code. `MovementCapabilities` states what this character can
// physically do — how fast it walks, how hard it jumps, whether it has a second jump in the air,
// whether it may climb or drop through. Links are admitted into the graph only when the character
// that owns those capabilities can actually traverse them, and a jump is admitted only after it is
// proved by the same fixed-step integration the player's own physics runs. A bot with no air jump
// is therefore not a bot that tries and fails to reach the high ledge: it is a bot for which the
// high ledge does not exist, and which walks around instead.
//
// Nothing here touches an engine. Nodes, links and steering are plain values over world units, and
// the only output is the same nine-boolean intent a keyboard produces. A port to another runtime
// reimplements the adapter that builds the graph and the one that applies the intent; this file
// translates as-is.

import { simulateJumpArc } from "../sideview/traversal";
import { terrainLanes, type LaneSpan } from "./lanes";

/**
 * What a character can physically do, as parameters rather than as branches.
 *
 * Defaults mirror the player controller's own constants, which is the point: the bot's model of
 * itself is the same model the physics uses, so a route it believes in is a route it can fly. A
 * caller that wants a weaker or stronger navigator overrides fields instead of forking the graph.
 */
export type MovementCapabilities = Readonly<{
  walkSpeed: number;
  runSpeed: number;
  jumpVelocity: number;
  /** The impulse a mid-air jump spends, or null for a character with only one jump. */
  airJumpVelocity: number | null;
  gravity: number;
  stepSeconds: number;
  /** A rise no taller than this is walked up; anything taller needs a jump. */
  stepUpTolerance: number;
  canClimb: boolean;
  canDropThrough: boolean;
}>;

/**
 * Close a capability set, refusing one that cannot describe a body.
 *
 * The defaults are the caller's, not the family's: a genre binds its own
 * controller constants so that the model a navigator has of itself is the model
 * its physics uses, and a navigator that is deliberately weaker overrides a
 * field rather than forking the graph.
 */
export function movementCapabilities(
  base: MovementCapabilities,
  overrides: Partial<MovementCapabilities> = {},
): MovementCapabilities {
  const merged = { ...base, ...overrides };
  for (const value of [
    merged.walkSpeed,
    merged.runSpeed,
    merged.jumpVelocity,
    merged.gravity,
    merged.stepSeconds,
    merged.stepUpTolerance,
  ]) {
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error("movement capabilities must be positive and finite");
    }
  }
  if (merged.airJumpVelocity !== null && !(merged.airJumpVelocity > 0)) {
    throw new Error("an air jump must be a positive impulse or absent");
  }
  return Object.freeze(merged);
}

/**
 * The moves in the character's traversal vocabulary.
 *
 * Growing this list is how navigation grows. A new move needs a rule that admits its links to the
 * graph and a branch that steers it; behaviours never mention moves at all.
 */
export type NavMove =
  | "walk"
  | "step_down"
  | "jump"
  | "double_jump"
  | "climb"
  | "drop_through";

export type NavNodeKind = "terrain" | "platform";

/** One level standing surface. Feet rest at `surfaceY` anywhere between `left` and `right`. */
export type NavNode = Readonly<{
  id: string;
  kind: NavNodeKind;
  left: number;
  right: number;
  surfaceY: number;
}>;

/** One traversal from `from` to `to`, launched at `fromX` and landing at `toX`. */
export type NavLink = Readonly<{
  id: string;
  from: string;
  to: string;
  move: NavMove;
  fromX: number;
  toX: number;
  /** Positive upward, so a climb and a jump report a rise and a fall reports a negative one. */
  rise: number;
  gap: number;
  climbableId: string | null;
  /** Roughly the seconds the move costs, which is what makes the cheapest path the fastest one. */
  cost: number;
}>;

export type NavGraph = Readonly<{
  nodes: readonly NavNode[];
  links: readonly NavLink[];
}>;

export const EMPTY_NAV_GRAPH: NavGraph = Object.freeze({
  nodes: Object.freeze([]),
  links: Object.freeze([]),
});

/**
 * Penalties, in seconds, for moves that cost more than the ground they cover.
 *
 * A jump is not merely the time it takes; it commits the character to an arc it cannot steer out
 * of, so an equally long walk is worth preferring. A drop through a floor is cheap but irreversible
 * from below, and a double jump is the most committing move there is.
 */
const MOVE_PENALTY_SECONDS: Readonly<Record<NavMove, number>> = Object.freeze({
  walk: 0,
  step_down: 0.1,
  jump: 0.35,
  double_jump: 0.7,
  climb: 0.3,
  drop_through: 0.25,
});

export type NavPlatformInput = Readonly<{
  id: string;
  left: number;
  right: number;
  deckY: number;
}>;

export type NavClimbableInput = Readonly<{
  id: string;
  centerX: number;
  upperDeckY: number;
  lowerSurfaceY: number;
}>;

export type NavGraphInput = Readonly<{
  /** Resolved standing surface for every terrain column, left to right, in world units. */
  columnSurfaceY: readonly number[];
  tileUnits: number;
  platforms: readonly NavPlatformInput[];
  climbables: readonly NavClimbableInput[];
  capabilities: MovementCapabilities;
}>;

/** Half a tile, which is how far past an edge a landing point sits so a ledge is actually cleared. */
const LEDGE_MARGIN_FRACTION = 0.5;

function horizontalGap(
  from: Readonly<{ left: number; right: number }>,
  to: Readonly<{ left: number; right: number }>,
): number {
  if (to.left > from.right) return to.left - from.right;
  if (from.left > to.right) return from.left - to.right;
  return 0;
}

/** The span two nodes share, or null when they merely touch or miss entirely. */
function overlapSpan(
  a: Readonly<{ left: number; right: number }>,
  b: Readonly<{ left: number; right: number }>,
): Readonly<{ left: number; right: number }> | null {
  const left = Math.max(a.left, b.left);
  const right = Math.min(a.right, b.right);
  return right > left ? { left, right } : null;
}

/**
 * A point on `node` at `x`, pulled inside its edges.
 *
 * Landing points have to sit inside the shelf they name rather than on its lip: steering walks
 * toward the landing point, and one exactly on the edge is a point the character oscillates around
 * as it crosses back and forth over it.
 */
function pointInside(node: Readonly<{ left: number; right: number }>, x: number, margin: number): number {
  const inset = Math.min(margin, (node.right - node.left) / 2);
  return Math.min(node.right - inset, Math.max(node.left + inset, x));
}

/**
 * Whether a rise-and-gap is jumpable, and with which of the character's two jumps.
 *
 * Both answers come from `simulatePlatformJump`, the same semi-implicit integration the controller
 * steps, so the graph cannot promise an arc the character will fall short of. The single jump is
 * tried first: a route that does not need the air jump should not spend it.
 */
function jumpMoveFor(
  rise: number,
  gap: number,
  capabilities: MovementCapabilities,
): Extract<NavMove, "jump" | "double_jump"> | null {
  const shared = {
    rise: Math.max(0, rise),
    gap: Math.max(0, gap),
    horizontalSpeed: capabilities.runSpeed,
    jumpVelocity: capabilities.jumpVelocity,
    gravity: capabilities.gravity,
    stepSeconds: capabilities.stepSeconds,
    maximumSteps: 120,
  };
  if (simulateJumpArc({ ...shared, airJumpVelocity: null }).reachable) return "jump";
  if (capabilities.airJumpVelocity === null) return null;
  return simulateJumpArc({ ...shared, airJumpVelocity: capabilities.airJumpVelocity }).reachable
    ? "double_jump"
    : null;
}

function linkCost(
  move: NavMove,
  fromX: number,
  toX: number,
  capabilities: MovementCapabilities,
): number {
  return Math.abs(toX - fromX) / capabilities.runSpeed + MOVE_PENALTY_SECONDS[move];
}

function makeLink(input: Readonly<{
  from: NavNode;
  to: NavNode;
  move: NavMove;
  fromX: number;
  toX: number;
  gap: number;
  climbableId?: string | null;
  capabilities: MovementCapabilities;
}>): NavLink {
  return Object.freeze({
    id: `${input.from.id}>${input.to.id}:${input.move}`,
    from: input.from.id,
    to: input.to.id,
    move: input.move,
    fromX: input.fromX,
    toX: input.toX,
    rise: input.from.surfaceY - input.to.surfaceY,
    gap: input.gap,
    climbableId: input.climbableId ?? null,
    cost: linkCost(input.move, input.fromX, input.toX, input.capabilities),
  });
}

/**
 * Cut the terrain into level lanes, as nodes.
 *
 * The cut itself is `lanes.ts` — one derivation for both the graph and the
 * creature that never had a graph — and this is only the projection of a span
 * onto a node. A lane is precisely the run the controller walks without leaving
 * the ground: `resolveTerrainWalk` treats any column standing above the foot as
 * a wall, so slopes do not exist here and a terrain of stepped tiles is a stack
 * of level shelves, which is what it is.
 */
function laneNodes(
  columnSurfaceY: readonly number[],
  tileUnits: number,
  tolerance: number,
): NavNode[] {
  return terrainLanes({
    columns: columnSurfaceY.length,
    surfaceAt: (column) => columnSurfaceY[column]!,
    tolerance,
  }).map((span: LaneSpan, index: number) =>
    Object.freeze({
      id: `terrain:${index}`,
      kind: "terrain" as const,
      left: span.startColumn * tileUnits,
      right: span.endColumn * tileUnits,
      surfaceY: span.surface,
    }),
  );
}

/**
 * Links between two shelves that share a boundary.
 *
 * Terrain lanes tile the map end to end, so "shares a boundary" and "is the next lane along" are
 * the same statement, and two lanes with a third between them are deliberately not linked: clearing
 * an intervening shelf is not a move this model describes, and pretending otherwise would hand the
 * steering an arc the character flies into the side of.
 */
function neighbourLink(
  from: NavNode,
  to: NavNode,
  boundary: number,
  towardSign: 1 | -1,
  tileUnits: number,
  capabilities: MovementCapabilities,
): NavLink | null {
  const margin = tileUnits * LEDGE_MARGIN_FRACTION;
  const fromX = pointInside(from, boundary, 1);
  const toX = pointInside(to, boundary + towardSign * margin, 1);
  const climb = from.surfaceY - to.surfaceY;
  if (Math.abs(climb) <= capabilities.stepUpTolerance) {
    return makeLink({ from, to, move: "walk", fromX, toX, gap: 0, capabilities });
  }
  if (climb < 0) {
    return makeLink({ from, to, move: "step_down", fromX, toX, gap: 0, capabilities });
  }
  const move = jumpMoveFor(climb, 0, capabilities);
  return move ? makeLink({ from, to, move, fromX, toX, gap: 0, capabilities }) : null;
}

/**
 * Links between a deck and anything else within reach of it.
 *
 * Decks are the one geometry that can sit over, beside, or under another, so their rules are stated
 * per relationship rather than per neighbour: a shelf above is jumped to, a shelf that runs out
 * past the deck's edge is stepped off onto, and a shelf directly underneath is dropped through when
 * the character has that move at all. A deck a shelf neither overlaps nor reaches is not linked,
 * and is simply somewhere the bot does not go.
 */
function deckLinks(
  from: NavNode,
  to: NavNode,
  tileUnits: number,
  capabilities: MovementCapabilities,
): NavLink[] {
  const margin = tileUnits * LEDGE_MARGIN_FRACTION;
  const gap = horizontalGap(from, to);
  if (gap > tileUnits * 4) return [];
  const overlap = overlapSpan(from, to);
  const climb = from.surfaceY - to.surfaceY;
  const links: NavLink[] = [];
  if (Math.abs(climb) <= capabilities.stepUpTolerance) {
    if (gap > tileUnits * 0.5) return [];
    const boundary = to.left >= from.right ? from.right : from.left;
    const towardSign = to.left >= from.right ? 1 : -1;
    return [
      makeLink({
        from,
        to,
        move: "walk",
        fromX: pointInside(from, boundary, 1),
        toX: pointInside(to, boundary + towardSign * margin, 1),
        gap,
        capabilities,
      }),
    ];
  }
  if (climb > 0) {
    // `to` stands above `from`, so the only way onto it is an arc the physics agrees with.
    const move = jumpMoveFor(climb, gap, capabilities);
    if (!move) return [];
    const launchX = overlap
      ? pointInside(from, (overlap.left + overlap.right) / 2, 1)
      : pointInside(from, to.left >= from.right ? from.right : from.left, 1);
    const landX = pointInside(to, launchX, Math.min(margin, (to.right - to.left) / 2));
    return [makeLink({ from, to, move, fromX: launchX, toX: landX, gap, capabilities })];
  }
  // `to` lies below. Walking off an edge works only where `to` actually continues past it.
  const side = to.left < from.left ? -1 : to.right > from.right ? 1 : 0;
  if (side !== 0) {
    const edgeX = side < 0 ? from.left : from.right;
    links.push(
      makeLink({
        from,
        to,
        move: "step_down",
        fromX: pointInside(from, edgeX, 1),
        toX: pointInside(to, edgeX + side * margin, 1),
        gap,
        capabilities,
      }),
    );
  }
  if (
    capabilities.canDropThrough &&
    from.kind === "platform" &&
    overlap &&
    overlap.right - overlap.left >= tileUnits * 0.25
  ) {
    const throughX = (overlap.left + overlap.right) / 2;
    links.push(
      makeLink({ from, to, move: "drop_through", fromX: throughX, toX: throughX, gap: 0, capabilities }),
    );
  }
  return links;
}

/**
 * Derive the traversal graph for one map.
 *
 * Every link is admitted by a rule that names a real mechanic — walking a level shelf, stepping off
 * a ledge, jumping a rise the physics proves reachable, climbing a declared zone, dropping through
 * a one-way deck — and no link is admitted that the supplied capabilities cannot perform. The
 * result is a graph specific to *this* character in *this* world, which is why it is rebuilt on map
 * entry against the capabilities of whoever is about to walk it.
 */
export function buildNavGraph(input: NavGraphInput): NavGraph {
  if (!Number.isFinite(input.tileUnits) || input.tileUnits <= 0) {
    throw new Error("nav graph requires a positive tile size");
  }
  for (const surface of input.columnSurfaceY) {
    if (!Number.isFinite(surface)) throw new Error("nav graph surfaces must be finite");
  }
  const capabilities = input.capabilities;
  const lanes = laneNodes(input.columnSurfaceY, input.tileUnits, capabilities.stepUpTolerance);
  const platforms: NavNode[] = input.platforms.map((platform) =>
    Object.freeze({
      id: `platform:${platform.id}`,
      kind: "platform" as const,
      left: platform.left,
      right: platform.right,
      surfaceY: platform.deckY,
    }),
  );
  const nodes = [...lanes, ...platforms];
  const links: NavLink[] = [];

  for (let index = 0; index + 1 < lanes.length; index += 1) {
    const left = lanes[index]!;
    const right = lanes[index + 1]!;
    const boundary = left.right;
    for (const [from, to, sign] of [
      [left, right, 1],
      [right, left, -1],
    ] as const) {
      const link = neighbourLink(from, to, boundary, sign, input.tileUnits, capabilities);
      if (link) links.push(link);
    }
  }

  for (const from of nodes) {
    for (const to of nodes) {
      if (from.id === to.id) continue;
      if (from.kind === "terrain" && to.kind === "terrain") continue;
      links.push(...deckLinks(from, to, input.tileUnits, capabilities));
    }
  }

  if (capabilities.canClimb) {
    for (const climbable of input.climbables) {
      const at = (surfaceY: number) =>
        nodes.find(
          (node) =>
            Math.abs(node.surfaceY - surfaceY) <= capabilities.stepUpTolerance &&
            node.left <= climbable.centerX &&
            climbable.centerX <= node.right,
        );
      const upper = at(climbable.upperDeckY);
      const lower = at(climbable.lowerSurfaceY);
      if (!upper || !lower || upper.id === lower.id) continue;
      for (const [from, to] of [
        [lower, upper],
        [upper, lower],
      ] as const) {
        links.push(
          makeLink({
            from,
            to,
            move: "climb",
            fromX: climbable.centerX,
            toX: climbable.centerX,
            gap: 0,
            climbableId: climbable.id,
            capabilities,
          }),
        );
      }
    }
  }

  links.sort((left, right) => left.id.localeCompare(right.id));
  return Object.freeze({ nodes: Object.freeze(nodes), links: Object.freeze(links) });
}

/** What it costs to stand on a node, and the first move of the cheapest way there. */
export type NavReach = Readonly<{
  nodeId: string;
  cost: number;
  /** Null for the node already occupied. */
  firstLink: NavLink | null;
}>;

/**
 * Cost and opening move to every node reachable from `fromNodeId`.
 *
 * One search per frame answers every "can I get there, and how do I start" question the behaviours
 * have, which is why the bot carries no path in memory: re-deriving is cheaper than invalidating,
 * and a plan that is recomputed from the world each frame cannot go stale behind a moving target.
 * Ties break on link id so two equal routes always resolve the same way, on every replay.
 */
export function navReach(graph: NavGraph, fromNodeId: string): readonly NavReach[] {
  const settled = new Map<string, NavReach>();
  const best = new Map<string, number>([[fromNodeId, 0]]);
  const opening = new Map<string, NavLink | null>([[fromNodeId, null]]);
  const pending = new Set<string>([fromNodeId]);
  if (!graph.nodes.some((node) => node.id === fromNodeId)) return Object.freeze([]);
  while (pending.size > 0) {
    let currentId: string | null = null;
    let currentCost = Number.POSITIVE_INFINITY;
    for (const candidate of pending) {
      const cost = best.get(candidate) ?? Number.POSITIVE_INFINITY;
      if (cost < currentCost || (cost === currentCost && (currentId === null || candidate < currentId))) {
        currentId = candidate;
        currentCost = cost;
      }
    }
    if (currentId === null) break;
    pending.delete(currentId);
    settled.set(
      currentId,
      Object.freeze({
        nodeId: currentId,
        cost: currentCost,
        firstLink: opening.get(currentId) ?? null,
      }),
    );
    for (const link of graph.links) {
      if (link.from !== currentId || settled.has(link.to)) continue;
      const cost = currentCost + link.cost;
      const known = best.get(link.to);
      if (known !== undefined && known <= cost) continue;
      best.set(link.to, cost);
      opening.set(link.to, currentId === fromNodeId ? link : opening.get(currentId) ?? link);
      pending.add(link.to);
    }
  }
  return Object.freeze(
    [...settled.values()].sort((left, right) => left.nodeId.localeCompare(right.nodeId)),
  );
}

export function reachOf(reach: readonly NavReach[], nodeId: string): NavReach | null {
  return reach.find((entry) => entry.nodeId === nodeId) ?? null;
}

/**
 * Which node a point stands on.
 *
 * Never returns null for a non-empty graph, and that is deliberate: a character mid-jump is over
 * some shelf even when it is on none of them, and a navigator that loses itself between two nodes
 * would stop dead exactly when it most needs to keep steering. The nearest surface under the foot
 * wins, falling back to the nearest surface at all.
 */
export function locateNavNode(
  graph: NavGraph,
  x: number,
  footY: number,
): NavNode | null {
  if (graph.nodes.length === 0) return null;
  const score = (node: NavNode): readonly [number, number, number] => {
    const horizontal = node.left <= x && x <= node.right ? 0 : Math.min(Math.abs(node.left - x), Math.abs(node.right - x));
    const below = node.surfaceY >= footY - 1 ? 0 : 1;
    return [horizontal, below, Math.abs(node.surfaceY - footY)];
  };
  let bestNode = graph.nodes[0]!;
  let bestScore = score(bestNode);
  for (const node of graph.nodes.slice(1)) {
    const candidate = score(node);
    const better =
      candidate[0] < bestScore[0] ||
      (candidate[0] === bestScore[0] &&
        (candidate[1] < bestScore[1] ||
          (candidate[1] === bestScore[1] &&
            (candidate[2] < bestScore[2] ||
              (candidate[2] === bestScore[2] && node.id < bestNode.id)))));
    if (better) {
      bestNode = node;
      bestScore = candidate;
    }
  }
  return bestNode;
}

