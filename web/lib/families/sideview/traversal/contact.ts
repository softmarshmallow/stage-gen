// What a body meets when it moves: the step under a standing foot, the faces a
// walk crosses, and the surface a fall arrives at.
//
// Three resolutions, all pure, all in one length unit chosen by the caller. The
// platformer integrates in pixels over a projected heightfield; the runner
// integrates in rows inside the occupancy grid itself. Neither unit appears
// here — a tolerance is in the same unit as a foot, a tile is in the same unit
// as an x, and that is the whole of the genericity the plan asks for.
//
// The one place the two genres genuinely disagree is what a descending foot
// already below the terrain means, and it is a parameter rather than a branch.
// The platformer **clamps**: a horizontal step can carry an already-falling
// foot into a raised column, and pinning it to that column's surface is the
// forgiving answer a walker wants. The runner **requires a crossing**: its track
// is admitted so that no arc ever needs to arrive from inside a step's face, so
// a foot that gets there did not land, it was buried, and the genre's own
// consequence table answers for that. Both answers are correct for their genre
// and neither can be derived from the other, so `terrainEntry` names which one
// is in force.

/** How a body is currently held up. A `platform` is a one-way deck. */
export type SurfaceSupport = "terrain" | "platform" | "climbable" | "air";

/** The least a one-way deck has to state for a fall to land on it. */
export interface OneWayDeck {
  readonly id: string;
  readonly left: number;
  readonly right: number;
  readonly deckY: number;
}

export type TerrainStepResolution = Readonly<{
  footY: number;
  support: Extract<SurfaceSupport, "terrain" | "air">;
}>;

/**
 * Resolve a standing foot against the surface under it.
 *
 * A drop past the tolerance is a fall: the foot stays where it is and the
 * caller hands it to gravity. Snapping it down instead teleports a body through
 * every descending step, so a one-cell kerb and a four-cell cliff both read as
 * flat walking.
 *
 * A rise is absorbed rather than refused, because the caller that cares has
 * already stopped the foot at the column face (`resolveTerrainWalk`) and the
 * only bodies that arrive under solid ground are ones that would otherwise be
 * sealed inside a hill with no input that frees them. A genre that treats
 * arriving under the surface as fatal — the runner does — compares the returned
 * `footY` against the one it passed in and answers for the difference itself:
 * this resolution says where the surface is, not what being under it costs.
 */
export function resolveTerrainStep(input: Readonly<{
  footY: number;
  surfaceY: number;
  tolerance: number;
}>): TerrainStepResolution {
  for (const value of [input.footY, input.surfaceY, input.tolerance]) {
    if (!Number.isFinite(value)) throw new Error("terrain step values must be finite");
  }
  if (input.tolerance < 0) throw new Error("terrain step tolerance must be nonnegative");
  if (input.surfaceY > input.footY + input.tolerance) {
    return Object.freeze({ footY: input.footY, support: "air" as const });
  }
  return Object.freeze({ footY: input.surfaceY, support: "terrain" as const });
}

export type TerrainWalkResolution = Readonly<{
  x: number;
  blocked: boolean;
  /** Column whose face stopped the move, or null when nothing did. */
  blockedColumn: number | null;
}>;

/**
 * Resolve horizontal motion against the surface columns it crosses.
 *
 * A column whose surface stands above the foot is a wall, whatever the foot is
 * currently supported by, so the same face that refuses a walk also refuses a
 * jump that has not yet cleared it and a drift that would slide into a cliff
 * mid-fall. The foot is left `contactGap` clear of the face rather than on it,
 * so the column lookup still resolves to the side it is standing on.
 *
 * Descents are not walls: walking off a ledge stays a fall. Callers that cannot
 * intentionally leave their current shelf may set `allowDescents` false.
 *
 * The runner has no caller for this and never will: auto-run has no horizontal
 * intent, so there is no walk to stop. It is in the core anyway because the
 * *core* is what a body on an occupancy grid does, not what one genre's body
 * happens to do — the cinematic platformer and the jumper both need it, and a
 * walk resolved against a different surface rule than the one the landing uses
 * is exactly the drift this family exists to prevent.
 */
export function resolveTerrainWalk(input: Readonly<{
  previousX: number;
  nextX: number;
  footY: number;
  /** Width of one grid column, in the caller's own unit. */
  tileUnits: number;
  surfaceAt: (column: number) => number;
  tolerance: number;
  /** Distance kept between a blocked foot and the face it stopped against. */
  contactGap: number;
  allowDescents?: boolean;
}>): TerrainWalkResolution {
  for (const value of [
    input.previousX,
    input.nextX,
    input.footY,
    input.tileUnits,
    input.tolerance,
    input.contactGap,
  ]) {
    if (!Number.isFinite(value)) throw new Error("terrain walk values must be finite");
  }
  if (input.tileUnits <= 0) throw new Error("terrain walk tile size must be positive");
  if (input.tolerance < 0) throw new Error("terrain walk tolerance must be nonnegative");
  const unblocked: TerrainWalkResolution = Object.freeze({
    x: input.nextX,
    blocked: false,
    blockedColumn: null,
  });
  const from = Math.floor(input.previousX / input.tileUnits);
  const to = Math.floor(input.nextX / input.tileUnits);
  if (from === to) return unblocked;
  const step = to > from ? 1 : -1;
  const allowDescents = input.allowDescents ?? true;
  for (let column = from + step; step > 0 ? column <= to : column >= to; column += step) {
    const surfaceY = input.surfaceAt(column);
    if (!Number.isFinite(surfaceY)) throw new Error("terrain walk surface must be finite");
    const sameLevel = Math.abs(surfaceY - input.footY) <= input.tolerance;
    if (sameLevel || (allowDescents && surfaceY > input.footY)) continue;
    return Object.freeze({
      x:
        step > 0
          ? column * input.tileUnits - input.contactGap
          : (column + 1) * input.tileUnits,
      blocked: true,
      blockedColumn: column,
    });
  }
  return unblocked;
}

/**
 * How a descending foot may take the terrain.
 *
 * `clamp` — any sample at or below the surface while descending lands on it.
 * `crossing` — landing requires having been above the surface at the start of
 * the step; a foot that is below it without having crossed is `buried`, and
 * what that costs is the genre's to say.
 */
export type TerrainEntry = "clamp" | "crossing";

export type LandingSupport = Exclude<SurfaceSupport, "climbable"> | "buried";

export type LandingResolution = Readonly<{
  footY: number;
  vy: number;
  support: LandingSupport;
  supportId: string | null;
}>;

/**
 * Resolve one-way deck crossings, then the terminal terrain candidate.
 *
 * Decks are one-way in both directions of the word: they are only taken while
 * descending, and only by a foot that crossed the deck line during this step,
 * so an ascending arc passes through the deck it will later land on. Terrain is
 * solid rather than one-way, and `terrainEntry` says how solid.
 */
export function resolveVerticalLanding(input: Readonly<{
  x: number;
  previousFootY: number;
  nextFootY: number;
  vy: number;
  terrainY: number;
  decks?: readonly OneWayDeck[];
  ignoredDeckId?: string | null;
  terrainEntry: TerrainEntry;
}>): LandingResolution {
  for (const value of [input.x, input.previousFootY, input.nextFootY, input.vy, input.terrainY]) {
    if (!Number.isFinite(value)) throw new Error("landing coordinates must be finite");
  }
  const airborne: LandingResolution = Object.freeze({
    footY: input.nextFootY,
    vy: input.vy,
    support: "air" as const,
    supportId: null,
  });
  if (input.vy >= 0) {
    const crossed = (input.decks ?? [])
      .filter(
        (deck) =>
          deck.id !== input.ignoredDeckId &&
          input.x >= deck.left &&
          input.x <= deck.right &&
          input.previousFootY <= deck.deckY &&
          input.nextFootY >= deck.deckY,
      )
      .sort((left, right) => left.deckY - right.deckY || left.id.localeCompare(right.id));
    const deck = crossed[0];
    if (deck) {
      return Object.freeze({
        footY: deck.deckY,
        vy: 0,
        support: "platform" as const,
        supportId: deck.id,
      });
    }
  }
  if (input.terrainEntry === "clamp") {
    if (input.vy >= 0 && input.nextFootY >= input.terrainY) {
      return Object.freeze({
        footY: input.terrainY,
        vy: 0,
        support: "terrain" as const,
        supportId: null,
      });
    }
    return airborne;
  }
  if (input.nextFootY < input.terrainY) return airborne;
  if (input.vy >= 0 && input.previousFootY <= input.terrainY) {
    return Object.freeze({
      footY: input.terrainY,
      vy: 0,
      support: "terrain" as const,
      supportId: null,
    });
  }
  // Below the surface without having crossed it from above: ascending into a
  // face, or carried into a wall while already beneath its rim.
  return Object.freeze({
    footY: input.nextFootY,
    vy: input.vy,
    support: "buried" as const,
    supportId: null,
  });
}
