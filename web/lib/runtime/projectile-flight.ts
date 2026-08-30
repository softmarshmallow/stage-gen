// The arithmetic of a thrown object, with no Phaser in it.
//
// Split from the pool that owns the sprites for the reason the combat rules were split from the
// Mob and Player classes: everything a shot does that can be *wrong* — how far it reaches, what it
// hits, when it gives up — is arithmetic, and arithmetic can be tested without a browser. What is
// left in `projectiles.ts` is a sprite, a depth and a texture key.
//
// Motion is sampled purely from the caller's `dtMs`. No tween, no `delayedCall`, no `Math.random`.
// The deterministic transcript is the only reason the runtime can be verified frame by frame, and
// a shot whose position depended on wall-clock time would be the one moving object in the scene
// that replayed differently every time.

/** An axis-aligned box in world pixels. The shape `Mob.snapshot().renderBounds` already returns. */
export type Aabb = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
}>;

/**
 * One shot in flight.
 *
 * `spawnX` is carried for the whole life of the shot even though nothing moves it, because the
 * scene seeds its critical roll from where the throw *started*. Seeding from the impact point
 * would make the same fight roll different criticals depending on how far the target had walked,
 * which is exactly the divergence the deterministic seed exists to prevent.
 */
export type ShotState = Readonly<{
  id: string;
  x: number;
  y: number;
  vxPx: number;
  vyPx: number;
  /** Path budget left, in pixels. Counted along the travelled distance, not the displacement. */
  remainingPx: number;
  spawnX: number;
  dirSign: 1 | -1;
  halfWidthPx: number;
  halfHeightPx: number;
}>;

/** Why a shot left the world. `null` means it is still flying. */
export type ShotExpiry = "range" | "terrain" | "world" | "hit" | null;

export type LaunchInput = Readonly<{
  id: string;
  /** The character's ground contact point. */
  originX: number;
  footY: number;
  /** The character's drawn height, which the release height is a fraction of. */
  bodyHeightPx: number;
  dirSign: 1 | -1;
  tilePixels: number;
  speedTilesPerSecond: number;
  maxRangeTiles: number;
  releaseForwardTiles: number;
  releaseHeightFraction: number;
  halfWidthTiles: number;
  halfHeightTiles: number;
}>;

function requireFinite(value: number, label: string): number {
  if (!Number.isFinite(value)) throw new Error(`${label} must be finite`);
  return value;
}

/** Place a shot at the moment it leaves the hand. */
export function launchShot(input: LaunchInput): ShotState {
  const tile = requireFinite(input.tilePixels, "projectile tile size");
  if (tile <= 0) throw new Error("projectile tile size must be positive");
  requireFinite(input.originX, "projectile origin x");
  requireFinite(input.footY, "projectile foot y");
  if (!Number.isFinite(input.bodyHeightPx) || input.bodyHeightPx <= 0) {
    throw new Error("projectile body height must be positive");
  }
  const x = input.originX + input.dirSign * input.releaseForwardTiles * tile;
  // Measured up from the feet, because `sprite.y` is the ground contact point for every actor in
  // this scene. A release fraction of 0.5 on a 154px character puts the throw at chest height.
  const y = input.footY - input.releaseHeightFraction * input.bodyHeightPx;
  return Object.freeze({
    id: input.id,
    x,
    y,
    vxPx: input.dirSign * input.speedTilesPerSecond * tile,
    vyPx: 0,
    remainingPx: input.maxRangeTiles * tile,
    spawnX: x,
    dirSign: input.dirSign,
    halfWidthPx: input.halfWidthTiles * tile,
    halfHeightPx: input.halfHeightTiles * tile,
  });
}

/**
 * Step a shot forward by one frame.
 *
 * The range budget is spent on the *path* length rather than the horizontal displacement, so a
 * class that later throws in an arc cannot buy extra reach by falling. With a flat throw the two
 * are identical, which is why this costs nothing today and prevents a surprise later.
 */
export function advanceShot(
  shot: ShotState,
  dtMs: number,
  gravityPxPerSecond2: number,
): ShotState {
  if (!Number.isFinite(dtMs) || dtMs < 0) {
    throw new Error("projectile step requires a nonnegative finite delta");
  }
  const dt = dtMs / 1000;
  const vyPx = shot.vyPx + gravityPxPerSecond2 * dt;
  const dx = shot.vxPx * dt;
  const dy = vyPx * dt;
  return Object.freeze({
    ...shot,
    x: shot.x + dx,
    y: shot.y + dy,
    vyPx,
    remainingPx: shot.remainingPx - Math.hypot(dx, dy),
  });
}

/** The shot's collision box at its current position. */
export function shotBounds(shot: ShotState): Aabb {
  return Object.freeze({
    left: shot.x - shot.halfWidthPx,
    right: shot.x + shot.halfWidthPx,
    top: shot.y - shot.halfHeightPx,
    bottom: shot.y + shot.halfHeightPx,
  });
}

/** Whether two boxes touch. Edge contact counts, which is what makes a grazing hit connect. */
export function boxesOverlap(a: Aabb, b: Aabb): boolean {
  return a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top;
}

export type WorldLimits = Readonly<{
  /** Left and right edges of the map in world pixels. */
  minX: number;
  maxX: number;
  /** Ground height at the shot's column, or null when the caller has no terrain to ask. */
  surfaceYAt: ((x: number) => number) | null;
}>;

/**
 * Why this shot should stop, or `null` to keep flying.
 *
 * Range is checked before terrain so a shot that runs out of budget exactly as it reaches a
 * hillside reports the reason that is actually true of it. `hit` is never returned here — that is
 * the caller's answer, because only the caller knows what the shot was allowed to hit.
 */
export function shotExpiry(shot: ShotState, world: WorldLimits): ShotExpiry {
  if (shot.remainingPx <= 0) return "range";
  if (shot.x < world.minX || shot.x > world.maxX) return "world";
  if (world.surfaceYAt && shot.y >= world.surfaceYAt(shot.x)) return "terrain";
  return null;
}

export type ShotTarget = Readonly<{ bounds: Aabb }>;

/**
 * The index of the first target the shot's box overlaps, or -1.
 *
 * "First" is the caller's order, not the nearest: the scene scans mobs in ladder-index order, and
 * a replay that picked the geometrically nearest target would diverge the moment two mobs stood at
 * the same distance. Deterministic beats nearest, and at these speeds nothing distinguishes them.
 */
export function firstOverlappingTarget(
  shot: ShotState,
  targets: readonly ShotTarget[],
  skip: ReadonlySet<number> = EMPTY_SKIP,
): number {
  const box = shotBounds(shot);
  for (let index = 0; index < targets.length; index += 1) {
    if (skip.has(index)) continue;
    if (boxesOverlap(box, targets[index].bounds)) return index;
  }
  return -1;
}

/** Shared empty set, so the common single-target call allocates nothing per frame. */
const EMPTY_SKIP: ReadonlySet<number> = Object.freeze(new Set<number>());
