import { terrainSurfaceY } from "./terrain";

export const UPPER_PLATFORM_THICKNESS = 32 as const;
export const LADDER_ACTIVATION_HALF_WIDTH = 30 as const;
export const LADDER_ENDPOINT_TOLERANCE = 12 as const;
export const LADDER_VISUAL_OVERSHOOT = 32 as const;
/**
 * On-screen width of a ladder's rails, in world pixels.
 *
 * This sizes the trimmed artwork, so it is the width that appears. It used to size the whole
 * source canvas, and the ladder is painted across 89 of its 256 columns - so 80 here drew 28px
 * of rails beside a 56px-wide character and spent the rest on transparent margin.
 *
 * One tile, which lands just wider than the character's 56px silhouette: a ladder a person
 * straddles reads correctly at roughly their own width, and tile-aligning it keeps it coherent
 * with the terrain grid the platforms are cut from.
 */
export const LADDER_VISUAL_WIDTH = 64 as const;
export const LADDER_SPEED = 180 as const;
export const LADDER_JUMP_VELOCITY = -350 as const;
export const LADDER_JUMP_HORIZONTAL_SPEED = 200 as const;
export const PLATFORMER_WALK_SPEED = 200 as const;
export const PLATFORMER_RUN_SPEED = 540 as const;
export const PLATFORMER_JUMP_VELOCITY = 520 as const;
/**
 * Mid-air jump impulse. Deliberately weaker than the grounded launch so the
 * second jump extends a route rather than doubling it: 520 clears 90px of rise
 * on its own, and the 440 follow-up adds another 64 for a combined 154. A
 * two-tile (128px) rise is therefore unreachable from the ground and reachable
 * with the air jump, which is what makes the mechanic load-bearing in the
 * platform graph instead of decorative.
 */
export const PLATFORMER_AIR_JUMP_VELOCITY = 440 as const;
/** Extra jumps available between two grounded/ladder supports. One → double jump. */
export const PLATFORMER_AIR_JUMPS_MAX = 1 as const;
/**
 * Grace window after leaving a support during which a jump still counts as
 * grounded. Terrain step-downs became real falls, so without this every jump
 * pressed at a ledge silently spent the air jump instead of the ground jump.
 */
export const PLATFORMER_COYOTE_MS = 90 as const;
export const PLATFORMER_GRAVITY = 1500 as const;
export const PLATFORMER_FIXED_STEP_SECONDS = 1 / 30;
/**
 * Downward terrain change a walking foot is allowed to absorb without leaving
 * the surface. Anything past it is a fall resolved by gravity, not a snap.
 */
export const TERRAIN_STEP_DOWN_TOLERANCE = 1 as const;
/**
 * Upward terrain change a walking foot is allowed to absorb. Anything past it
 * is a wall: the column face stops horizontal motion and the only way on top
 * is a jump. This heightfield steps in whole tiles, so in practice every rise
 * is climbed rather than walked.
 */
export const TERRAIN_STEP_UP_TOLERANCE = 1 as const;
/** Gap kept between a blocked foot and the column face it stopped against. */
export const TERRAIN_WALL_CONTACT_GAP = 1 as const;
export const PLATFORM_DROP_THROUGH_MS = 180 as const;
export const PLATFORM_DROP_CLEARANCE = 16 as const;
export const PLATFORM_DROP_SETTLE_FRAMES = 7 as const;
export const VERTICAL_CAMERA_MIN_SCROLL_Y = -512 as const;
export const VERTICAL_CAMERA_MAX_SCROLL_Y = 0 as const;
export const VERTICAL_CAMERA_DEADZONE = Object.freeze({ top: 420, bottom: 528 });

export type UpperPlatform = Readonly<{
  id: string;
  left: number;
  right: number;
  deckY: number;
  tier: number;
  thickness: typeof UPPER_PLATFORM_THICKNESS;
  sourceColumns: Readonly<{ start: number; end: number }>;
}>;

export type LadderZone = Readonly<{
  id: string;
  platformId: string;
  centerX: number;
  upperDeckY: number;
  lowerSurfaceY: number;
  activationHalfWidth: typeof LADDER_ACTIVATION_HALF_WIDTH;
  visualTopOvershoot: typeof LADDER_VISUAL_OVERSHOOT;
  visualBottomOvershoot: typeof LADDER_VISUAL_OVERSHOOT;
  visualWidth: typeof LADDER_VISUAL_WIDTH;
}>;

export type PlayerSupport = "terrain" | "platform" | "ladder" | "air";

export type VerticalWorld = Readonly<{
  platforms: readonly UpperPlatform[];
  ladders: readonly LadderZone[];
}>;

export type PlatformRouteMode = "jump" | "double-jump" | "drop" | "ladder";

export type PlatformRoute = Readonly<{
  id: string;
  from: "terrain" | string;
  to: "terrain" | string;
  mode: PlatformRouteMode;
  rise: number;
  gap: number;
  landingStep: number | null;
  horizontalRange: number | null;
  ladderId: string | null;
}>;

export type JumpReachability = Readonly<{
  reachable: boolean;
  rise: number;
  gap: number;
  apexRise: number;
  landingStep: number | null;
  horizontalRange: number | null;
  /** Step the mid-air impulse was spent on, or null for a single grounded jump. */
  airJumpStep: number | null;
}>;

/**
 * Semi-implicit Euler proof matching Player.update's fixed-step jump order.
 *
 * `airJumpVelocity` proves a double jump. The impulse is spent on the first
 * step the arc stops rising, which is both the height-optimal moment and the
 * one a player naturally hits, so a route proved here is a route a player can
 * fly. Landing still requires a descending foot, so the second arc cannot
 * "land" on a deck it is passing on the way up.
 */
export function simulatePlatformJump(input: Readonly<{
  rise: number;
  gap: number;
  horizontalSpeed?: number;
  jumpVelocity?: number;
  airJumpVelocity?: number | null;
  gravity?: number;
  stepSeconds?: number;
  maximumSteps?: number;
}>): JumpReachability {
  const horizontalSpeed = input.horizontalSpeed ?? PLATFORMER_RUN_SPEED;
  const jumpVelocity = input.jumpVelocity ?? PLATFORMER_JUMP_VELOCITY;
  const airJumpVelocity = input.airJumpVelocity ?? null;
  const gravity = input.gravity ?? PLATFORMER_GRAVITY;
  const stepSeconds = input.stepSeconds ?? PLATFORMER_FIXED_STEP_SECONDS;
  const maximumSteps = input.maximumSteps ?? 120;
  for (const value of [
    input.rise,
    input.gap,
    horizontalSpeed,
    jumpVelocity,
    gravity,
    stepSeconds,
    maximumSteps,
    ...(airJumpVelocity === null ? [] : [airJumpVelocity]),
  ]) {
    if (!Number.isFinite(value)) throw new Error("jump proof values must be finite");
  }
  if (
    input.rise < 0 ||
    input.gap < 0 ||
    horizontalSpeed < 0 ||
    jumpVelocity <= 0 ||
    (airJumpVelocity !== null && airJumpVelocity <= 0) ||
    gravity <= 0 ||
    stepSeconds <= 0 ||
    !Number.isSafeInteger(maximumSteps) ||
    maximumSteps < 1
  ) {
    throw new Error("jump proof values are outside their supported range");
  }
  const targetY = -input.rise;
  let y = 0;
  let vy = -jumpVelocity;
  let apexRise = 0;
  let airJumpStep: number | null = null;
  let airJumpPending = airJumpVelocity !== null;
  for (let step = 1; step <= maximumSteps; step += 1) {
    const previousY = y;
    vy += gravity * stepSeconds;
    if (airJumpPending && vy >= 0) {
      vy = -airJumpVelocity!;
      airJumpPending = false;
      airJumpStep = step;
    }
    y += vy * stepSeconds;
    apexRise = Math.max(apexRise, -y);
    if (vy >= 0 && previousY <= targetY && y >= targetY) {
      const horizontalRange = horizontalSpeed * stepSeconds * step;
      return deepFreeze({
        reachable: input.gap <= horizontalRange,
        rise: input.rise,
        gap: input.gap,
        apexRise,
        landingStep: step,
        horizontalRange,
        airJumpStep,
      });
    }
  }
  return deepFreeze({
    reachable: false,
    rise: input.rise,
    gap: input.gap,
    apexRise,
    landingStep: null,
    horizontalRange: null,
    airJumpStep,
  });
}

export function platformDropRecoverySteps(input: Readonly<{
  fallDistance: number;
  gravity?: number;
  stepSeconds?: number;
  maximumSteps?: number;
}>): number | null {
  const gravity = input.gravity ?? PLATFORMER_GRAVITY;
  const stepSeconds = input.stepSeconds ?? PLATFORMER_FIXED_STEP_SECONDS;
  const maximumSteps = input.maximumSteps ?? 120;
  if (
    !Number.isFinite(input.fallDistance) ||
    input.fallDistance < 0 ||
    !Number.isFinite(gravity) ||
    gravity <= 0 ||
    !Number.isFinite(stepSeconds) ||
    stepSeconds <= 0 ||
    !Number.isSafeInteger(maximumSteps) ||
    maximumSteps < 1
  ) {
    throw new Error("drop proof values are outside their supported range");
  }
  let distance = 0;
  let velocity = 0;
  for (let step = 1; step <= maximumSteps; step += 1) {
    velocity += gravity * stepSeconds;
    distance += velocity * stepSeconds;
    if (distance >= input.fallDistance) return step;
  }
  return null;
}

export type VerticalWorldInput = Readonly<{
  platforms: readonly Omit<UpperPlatform, "thickness">[];
  ladders: readonly Omit<
    LadderZone,
    | "activationHalfWidth"
    | "visualTopOvershoot"
    | "visualBottomOvershoot"
    | "visualWidth"
  >[];
  heights: readonly number[];
  tilePixels: number;
  baselineY: number;
  worldWidth: number;
}>;

export type PlatformRenderPlan = Readonly<{
  body: Readonly<{ x: number; y: number; width: number; height: number }>;
  cap: Readonly<{ x: number; y: number; width: number; height: number }>;
  sides: readonly Readonly<{
    edge: "left" | "right";
    x: number;
    y: number;
    width: number;
    height: number;
  }>[];
}>;

function assertFiniteInteger(value: number, label: string): void {
  if (!Number.isSafeInteger(value)) {
    throw new Error(`${label} must be a finite safe integer`);
  }
}

function assertStableId(value: string, label: string): void {
  if (!/^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$/.test(value) || value.length > 96) {
    throw new Error(`${label} must be a stable lowercase id`);
  }
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) {
      deepFreeze(child);
    }
    Object.freeze(value);
  }
  return value;
}

/**
 * Validate gameplay geometry independently from image alpha, zoom, and DPR.
 * The returned values are detached, x/id ordered, and deeply frozen.
 */
export function createVerticalWorld(input: VerticalWorldInput): VerticalWorld {
  assertFiniteInteger(input.tilePixels, "tilePixels");
  assertFiniteInteger(input.baselineY, "baselineY");
  assertFiniteInteger(input.worldWidth, "worldWidth");
  if (input.tilePixels <= 0 || input.worldWidth <= 0 || input.heights.length === 0) {
    throw new Error("vertical world dimensions must be positive");
  }
  const ids = new Set<string>();
  const platforms = input.platforms.map((source) => {
    assertStableId(source.id, "platform id");
    if (ids.has(source.id)) throw new Error("vertical ids must be unique");
    ids.add(source.id);
    for (const [label, value] of [
      ["platform left", source.left],
      ["platform right", source.right],
      ["platform deckY", source.deckY],
      ["platform tier", source.tier],
      ["platform source start", source.sourceColumns.start],
      ["platform source end", source.sourceColumns.end],
    ] as const) {
      assertFiniteInteger(value, label);
    }
    if (
      source.left < 0 ||
      source.right > input.worldWidth ||
      source.left >= source.right ||
      source.deckY < VERTICAL_CAMERA_MIN_SCROLL_Y ||
      source.deckY + UPPER_PLATFORM_THICKNESS > input.baselineY ||
      source.tier < 1 ||
      source.sourceColumns.start < 0 ||
      source.sourceColumns.end > input.heights.length ||
      source.sourceColumns.start >= source.sourceColumns.end ||
      source.left !== source.sourceColumns.start * input.tilePixels ||
      source.right !== source.sourceColumns.end * input.tilePixels
    ) {
      throw new Error("platform geometry is outside its world/source columns");
    }
    return {
      ...source,
      sourceColumns: { ...source.sourceColumns },
      thickness: UPPER_PLATFORM_THICKNESS,
    } satisfies UpperPlatform;
  });
  platforms.sort(
    (left, right) =>
      left.left - right.left ||
      left.deckY - right.deckY ||
      left.id.localeCompare(right.id),
  );
  // Decks may share columns as long as they occupy different bands, which is
  // what lets a route run above another one. Only a genuine solid-body
  // intersection is rejected, so the check is two-dimensional and pairwise:
  // sorting by `left` no longer implies neighbours are the only candidates.
  for (let index = 0; index < platforms.length; index += 1) {
    for (let other = index + 1; other < platforms.length; other += 1) {
      const a = platforms[index]!;
      const b = platforms[other]!;
      if (b.left >= a.right || a.left >= b.right) continue;
      const aBottom = a.deckY + UPPER_PLATFORM_THICKNESS;
      const bBottom = b.deckY + UPPER_PLATFORM_THICKNESS;
      if (b.deckY >= aBottom || a.deckY >= bBottom) continue;
      throw new Error("platform interiors must not overlap");
    }
  }

  const platformById = new Map(platforms.map((platform) => [platform.id, platform]));
  const ladders = input.ladders.map((source) => {
    assertStableId(source.id, "ladder id");
    if (ids.has(source.id)) throw new Error("vertical ids must be unique");
    ids.add(source.id);
    const platform = platformById.get(source.platformId);
    if (!platform) throw new Error("ladder must name an existing platform");
    for (const [label, value] of [
      ["ladder centerX", source.centerX],
      ["ladder upperDeckY", source.upperDeckY],
      ["ladder lowerSurfaceY", source.lowerSurfaceY],
    ] as const) {
      assertFiniteInteger(value, label);
    }
    if (
      source.centerX < platform.left ||
      source.centerX > platform.right ||
      source.upperDeckY !== platform.deckY ||
      source.lowerSurfaceY - source.upperDeckY !== input.tilePixels * 4
    ) {
      throw new Error("ladder endpoints must span one valid four-tile rise");
    }
    const column = Math.floor(source.centerX / input.tilePixels);
    if (column < 0 || column + 1 >= input.heights.length) {
      throw new Error("ladder lower endpoint requires a right terrain neighbor");
    }
    const neighbor = column + 1;
    const expectedSurface = terrainSurfaceY(
      input.heights[column]!,
      input.tilePixels,
      input.baselineY,
    );
    const neighborSurface = terrainSurfaceY(
      input.heights[neighbor]!,
      input.tilePixels,
      input.baselineY,
    );
    if (
      source.lowerSurfaceY !== expectedSurface ||
      expectedSurface !== neighborSurface
    ) {
      throw new Error("ladder requires a flat lower terrain endpoint");
    }
    return {
      ...source,
      activationHalfWidth: LADDER_ACTIVATION_HALF_WIDTH,
      visualTopOvershoot: LADDER_VISUAL_OVERSHOOT,
      visualBottomOvershoot: LADDER_VISUAL_OVERSHOOT,
      visualWidth: LADDER_VISUAL_WIDTH,
    } satisfies LadderZone;
  });
  ladders.sort((left, right) => left.centerX - right.centerX || left.id.localeCompare(right.id));
  return deepFreeze({ platforms, ladders });
}

export type DemoVerticalSelection = Readonly<{
  world: VerticalWorld;
  routes: readonly PlatformRoute[];
  reservedColumns: readonly number[];
}>;

export const VERTICAL_TRAVERSAL_ASSET_KEYS = deepFreeze([
  "ladder",
  "character_climb",
] as const);
export const VERTICAL_ASSET_ERROR_MAX_LENGTH = 240;

export type VerticalTraversalAssetReadiness = Readonly<{
  ladderAssetLoaded: boolean;
  climbAssetLoaded: boolean;
}>;

function boundedVerticalAssetError(role: string, error: unknown): string {
  const detail = error instanceof Error ? error.message : String(error);
  const message = `required vertical ${role} asset failed: ${detail}`;
  return message.length <= VERTICAL_ASSET_ERROR_MAX_LENGTH
    ? message
    : `${message.slice(0, VERTICAL_ASSET_ERROR_MAX_LENGTH - 1)}…`;
}

/** Load the traversal texture set and remove both keys after any failure. */
export async function prepareVerticalTraversalAssets(input: Readonly<{
  selected: DemoVerticalSelection | null;
  loadLadder: () => Promise<void>;
  loadClimb: () => Promise<void>;
  removeAsset: (key: (typeof VERTICAL_TRAVERSAL_ASSET_KEYS)[number]) => void;
  recordError: (message: string) => void;
}>): Promise<VerticalTraversalAssetReadiness> {
  if (!input.selected) {
    return { ladderAssetLoaded: false, climbAssetLoaded: false };
  }
  let ladderAssetLoaded = false;
  let climbAssetLoaded = false;
  try {
    await input.loadLadder();
    ladderAssetLoaded = true;
  } catch (error) {
    input.recordError(boundedVerticalAssetError("ladder", error));
  }
  try {
    await input.loadClimb();
    climbAssetLoaded = true;
  } catch (error) {
    input.recordError(boundedVerticalAssetError("character climb", error));
  }
  if (!ladderAssetLoaded || !climbAssetLoaded) {
    for (const key of VERTICAL_TRAVERSAL_ASSET_KEYS) {
      try {
        input.removeAsset(key);
      } catch (error) {
        input.recordError(boundedVerticalAssetError(`${key} cleanup`, error));
      }
    }
    return { ladderAssetLoaded: false, climbAssetLoaded: false };
  }
  return { ladderAssetLoaded: true, climbAssetLoaded: true };
}

const EMPTY_VERTICAL_WORLD: VerticalWorld = deepFreeze({
  platforms: [],
  ladders: [],
});
const EMPTY_PLATFORM_ROUTES: readonly PlatformRoute[] = deepFreeze([]);

/** Commit selected geometry only after its required traversal rasters loaded. */
export function verticalFeatureAfterAssetLoad(
  selected: DemoVerticalSelection | null,
  ladderAssetLoaded: boolean,
): DemoVerticalSelection {
  if (!selected || !ladderAssetLoaded) {
    return deepFreeze({
      world: EMPTY_VERTICAL_WORLD,
      routes: EMPTY_PLATFORM_ROUTES,
      reservedColumns: [],
    });
  }
  return selected;
}

/** Atomically bind collision/routes only after assets and render groups exist. */
export function activateVerticalFeatureTransaction(input: Readonly<{
  selected: DemoVerticalSelection | null;
  ladderAssetLoaded: boolean;
  climbAssetLoaded: boolean;
  platformMaterialsReady: boolean;
  assemblePlatforms: (platforms: readonly UpperPlatform[]) => void;
  assembleLadders: (ladders: readonly LadderZone[]) => void;
  rollbackRendering: () => void;
  commit: (selection: DemoVerticalSelection) => void;
}>): boolean {
  const inactive = verticalFeatureAfterAssetLoad(input.selected, false);
  input.commit(inactive);
  if (
    !input.selected ||
    !input.ladderAssetLoaded ||
    !input.climbAssetLoaded ||
    !input.platformMaterialsReady
  ) {
    input.rollbackRendering();
    return false;
  }
  const active = verticalFeatureAfterAssetLoad(input.selected, true);
  try {
    input.assemblePlatforms(active.world.platforms);
    input.assembleLadders(active.world.ladders);
    input.commit(active);
  } catch (error) {
    input.rollbackRendering();
    input.commit(inactive);
    throw error;
  }
  return true;
}

export function verticalSpawnAllowed(
  reservedColumns: ReadonlySet<number>,
  column: number,
): boolean {
  assertFiniteInteger(column, "spawn column");
  return column >= 0 && !reservedColumns.has(column);
}

/** Named platform-graph shapes the preview can lay into a stage. */
export type DemoVerticalLayoutKind = "ascent" | "gauntlet" | "spires";

type DemoPlatformSpec = Readonly<{
  id: string;
  /** Half-open column span relative to the layout's start column. */
  start: number;
  end: number;
  /** Deck elevation above the layout's base terrain surface, in tiles. */
  tiers: number;
}>;

type DemoLadderSpec = Readonly<{
  id: string;
  platformId: string;
  /** Column carrying the ladder axis, relative to the layout's start column. */
  column: number;
}>;

type DemoTraversalSpec = Readonly<{
  id: string;
  from: "terrain" | string;
  to: string;
  mode: Extract<PlatformRouteMode, "jump" | "double-jump">;
}>;

type DemoLayout = Readonly<{
  kind: DemoVerticalLayoutKind;
  /** Columns the layout occupies, counted from its start column. */
  width: number;
  platforms: readonly DemoPlatformSpec[];
  ladders: readonly DemoLadderSpec[];
  traversals: readonly DemoTraversalSpec[];
}>;

/**
 * Elevation, in tiles, a ladder spans. `createVerticalWorld` only accepts a
 * four-tile rise, so a ladder's platform must sit exactly that far above its
 * flat terrain endpoint.
 */
const DEMO_LADDER_TIERS = 4;

/**
 * The three stage shapes.
 *
 * `ascent` keeps the original four-tier staircase as its spine — the same ids,
 * columns and decks — and grows around it: a stacked upper branch reached by
 * doubling back left off the summit, and a forward chain past it. Stacking is
 * what makes a branch possible at all; before decks could share columns, every
 * platform had to queue up in a single left-to-right line and the "graph" only
 * ever had one path through it.
 *
 * `gauntlet` trades height for spacing — narrow stones over wide gaps, so the
 * pressure is on horizontal commitment. `spires` inverts that into stacked
 * towers with short, tall hops. Each declares which of its edges genuinely
 * needs the air jump, and the builder proves both halves of that claim.
 */
const DEMO_LAYOUTS: Readonly<Record<DemoVerticalLayoutKind, DemoLayout>> = deepFreeze({
  ascent: {
    kind: "ascent",
    width: 39,
    platforms: [
      { id: "tier-1-launch", start: 0, end: 6, tiers: 1 },
      { id: "tier-2-transfer", start: 7, end: 13, tiers: 2 },
      { id: "tier-3-bridge", start: 14, end: 20, tiers: 3 },
      { id: "tier-4-summit", start: 21, end: 27, tiers: 4 },
      { id: "sky-ledge", start: 16, end: 20, tiers: 6 },
      { id: "sky-cap", start: 22, end: 26, tiers: 7 },
      { id: "stone-first", start: 28, end: 30, tiers: 4 },
      { id: "stone-second", start: 31, end: 33, tiers: 6 },
      { id: "sky-span", start: 34, end: 39, tiers: 6 },
    ],
    ladders: [
      { id: "ladder-summit", platformId: "tier-4-summit", column: 26 },
    ],
    traversals: [
      { id: "jump-1", from: "terrain", to: "tier-1-launch", mode: "jump" },
      { id: "jump-2", from: "tier-1-launch", to: "tier-2-transfer", mode: "jump" },
      { id: "jump-3", from: "tier-2-transfer", to: "tier-3-bridge", mode: "jump" },
      { id: "jump-4", from: "tier-3-bridge", to: "tier-4-summit", mode: "jump" },
      { id: "jump-5", from: "tier-4-summit", to: "sky-ledge", mode: "double-jump" },
      { id: "jump-6", from: "sky-ledge", to: "sky-cap", mode: "jump" },
      { id: "jump-7", from: "tier-4-summit", to: "stone-first", mode: "jump" },
      { id: "jump-8", from: "stone-first", to: "stone-second", mode: "double-jump" },
      { id: "jump-9", from: "stone-second", to: "sky-span", mode: "jump" },
    ],
  },
  gauntlet: {
    kind: "gauntlet",
    width: 38,
    platforms: [
      { id: "gate-plinth", start: 0, end: 5, tiers: 1 },
      { id: "gate-step", start: 7, end: 10, tiers: 2 },
      { id: "long-span", start: 12, end: 19, tiers: 2 },
      { id: "span-relay", start: 21, end: 24, tiers: 3 },
      { id: "high-post", start: 26, end: 32, tiers: 4 },
      { id: "watch-roost", start: 27, end: 31, tiers: 6 },
      { id: "far-stone", start: 34, end: 38, tiers: 4 },
    ],
    ladders: [{ id: "ladder-post", platformId: "high-post", column: 31 }],
    traversals: [
      { id: "jump-1", from: "terrain", to: "gate-plinth", mode: "jump" },
      { id: "jump-2", from: "gate-plinth", to: "gate-step", mode: "jump" },
      { id: "jump-3", from: "gate-step", to: "long-span", mode: "jump" },
      { id: "jump-4", from: "long-span", to: "span-relay", mode: "jump" },
      { id: "jump-5", from: "span-relay", to: "high-post", mode: "jump" },
      { id: "jump-6", from: "high-post", to: "watch-roost", mode: "double-jump" },
      { id: "jump-7", from: "high-post", to: "far-stone", mode: "jump" },
    ],
  },
  spires: {
    kind: "spires",
    width: 36,
    platforms: [
      { id: "base-court", start: 0, end: 7, tiers: 1 },
      { id: "first-spire", start: 9, end: 12, tiers: 3 },
      { id: "second-spire", start: 14, end: 17, tiers: 5 },
      { id: "spire-shelf", start: 9, end: 12, tiers: 6 },
      { id: "third-spire", start: 19, end: 22, tiers: 7 },
      { id: "keep-deck", start: 24, end: 31, tiers: 4 },
      { id: "keep-crown", start: 26, end: 30, tiers: 7 },
      { id: "far-landing", start: 33, end: 36, tiers: 2 },
    ],
    ladders: [{ id: "ladder-keep", platformId: "keep-deck", column: 29 }],
    traversals: [
      { id: "jump-1", from: "terrain", to: "base-court", mode: "jump" },
      { id: "jump-2", from: "base-court", to: "first-spire", mode: "double-jump" },
      { id: "jump-3", from: "first-spire", to: "second-spire", mode: "double-jump" },
      { id: "jump-4", from: "second-spire", to: "spire-shelf", mode: "jump" },
      { id: "jump-5", from: "second-spire", to: "third-spire", mode: "double-jump" },
      { id: "jump-6", from: "third-spire", to: "keep-crown", mode: "jump" },
      { id: "jump-7", from: "keep-deck", to: "far-landing", mode: "jump" },
    ],
  },
} satisfies Record<DemoVerticalLayoutKind, DemoLayout>);

export const DEMO_VERTICAL_LAYOUT_KINDS = deepFreeze([
  "ascent",
  "gauntlet",
  "spires",
] as const);

/** Horizontal clearance a jump has to cover between two decks. */
function horizontalGap(from: UpperPlatform, to: UpperPlatform): number {
  if (to.left >= from.right) return to.left - from.right;
  if (to.right <= from.left) return from.left - to.right;
  return 0;
}

/**
 * The support a foot leaving `platform` actually arrives on.
 *
 * Stacked decks make this a real question: dropping off an upper branch lands
 * on the deck below it, not on the ground four tiles further down, and a route
 * graph that always answered "terrain" would overstate every such fall.
 */
function dropDestination(
  platform: UpperPlatform,
  platforms: readonly UpperPlatform[],
  heights: readonly number[],
  tilePixels: number,
  baselineY: number,
): Readonly<{ to: string; surfaceY: number }> {
  const below = platforms
    .filter(
      (candidate) =>
        candidate.id !== platform.id &&
        candidate.deckY > platform.deckY &&
        candidate.left < platform.right &&
        platform.left < candidate.right,
    )
    .sort((left, right) => left.deckY - right.deckY || left.id.localeCompare(right.id));
  const landing = below[0];
  if (landing) return { to: landing.id, surfaceY: landing.deckY };
  const recoverySurfaces = heights
    .slice(platform.sourceColumns.start, platform.sourceColumns.end)
    .map((height) => terrainSurfaceY(height, tilePixels, baselineY));
  if (recoverySurfaces.length === 0) {
    throw new Error(`drop route from ${platform.id} has no recovery terrain`);
  }
  return { to: "terrain", surfaceY: Math.max(...recoverySurfaces) };
}

function createDemoPlatformRoutes(
  layout: DemoLayout,
  lowerSurfaceY: number,
  platforms: readonly UpperPlatform[],
  ladders: readonly LadderZone[],
  heights: readonly number[],
  tilePixels: number,
  baselineY: number,
): readonly PlatformRoute[] {
  const byId = new Map(platforms.map((platform) => [platform.id, platform]));
  const routes: PlatformRoute[] = layout.traversals.map((traversal) => {
    const destination = byId.get(traversal.to);
    if (!destination) throw new Error(`jump destination ${traversal.to} is missing`);
    const source = traversal.from === "terrain" ? null : byId.get(traversal.from);
    if (traversal.from !== "terrain" && !source) {
      throw new Error(`jump source ${traversal.from} is missing`);
    }
    const sourceDeckY = source ? source.deckY : lowerSurfaceY;
    const rise = sourceDeckY - destination.deckY;
    const gap = source ? horizontalGap(source, destination) : 0;
    const grounded = simulatePlatformJump({ rise: Math.max(0, rise), gap });
    const doubled = simulatePlatformJump({
      rise: Math.max(0, rise),
      gap,
      airJumpVelocity: PLATFORMER_AIR_JUMP_VELOCITY,
    });
    // A declared air-jump gate has to be exactly that: out of reach from the
    // ground and in reach with the second impulse. Without the negative half
    // the label drifts into decoration the moment a deck moves a tile.
    if (traversal.mode === "double-jump" && grounded.reachable) {
      throw new Error(`route ${traversal.id} does not require an air jump`);
    }
    const proof = traversal.mode === "double-jump" ? doubled : grounded;
    if (!proof.reachable || proof.landingStep === null || proof.horizontalRange === null) {
      throw new Error(
        `${traversal.mode} route ${traversal.from} to ${traversal.to} is unreachable`,
      );
    }
    return {
      id: traversal.id,
      from: traversal.from,
      to: traversal.to,
      mode: traversal.mode,
      rise,
      gap,
      landingStep: proof.landingStep,
      horizontalRange: proof.horizontalRange,
      ladderId: null,
    };
  });
  for (const platform of platforms) {
    const destination = dropDestination(
      platform,
      platforms,
      heights,
      tilePixels,
      baselineY,
    );
    const fallDistance = destination.surfaceY - platform.deckY;
    const landingStep = platformDropRecoverySteps({ fallDistance });
    if (landingStep === null) {
      throw new Error(`drop route from ${platform.id} cannot recover`);
    }
    routes.push({
      id: `drop-${platform.id}`,
      from: platform.id,
      to: destination.to,
      mode: "drop",
      rise: -fallDistance,
      gap: 0,
      landingStep,
      horizontalRange: null,
      ladderId: null,
    });
  }
  for (const ladder of ladders) {
    routes.push(
      {
        id: `${ladder.id}-up`,
        from: "terrain",
        to: ladder.platformId,
        mode: "ladder",
        rise: ladder.lowerSurfaceY - ladder.upperDeckY,
        gap: 0,
        landingStep: null,
        horizontalRange: null,
        ladderId: ladder.id,
      },
      {
        id: `${ladder.id}-down`,
        from: ladder.platformId,
        to: "terrain",
        mode: "ladder",
        rise: ladder.upperDeckY - ladder.lowerSurfaceY,
        gap: 0,
        landingStep: null,
        horizontalRange: null,
        ladderId: ladder.id,
      },
    );
  }
  const ids = new Set<string>();
  for (const route of routes) {
    assertStableId(route.id, "route id");
    if (ids.has(route.id)) throw new Error("route ids must be unique");
    ids.add(route.id);
  }
  return deepFreeze(routes);
}

/** Columns whose terrain must match the layout's base surface for it to fit. */
function layoutEndpointColumns(layout: DemoLayout): ReadonlySet<number> {
  const columns = new Set<number>([0, 1]);
  for (const ladder of layout.ladders) {
    columns.add(ladder.column);
    columns.add(ladder.column + 1);
  }
  return columns;
}

/** Select a branching platform graph outside caller-owned reservations. */
export function selectDemoVerticalWorld(input: Readonly<{
  heights: readonly number[];
  tilePixels: number;
  baselineY: number;
  worldWidth: number;
  reservedColumns?: ReadonlySet<number>;
  afterColumn?: number;
  maximumColumnExclusive?: number;
  layout?: DemoVerticalLayoutKind;
}>): DemoVerticalSelection | null {
  const layout = DEMO_LAYOUTS[input.layout ?? "ascent"];
  const after = input.afterColumn ?? 8;
  const maximum =
    input.maximumColumnExclusive ?? Math.floor(input.heights.length * 0.5);
  assertFiniteInteger(after, "platform search lower bound");
  assertFiniteInteger(maximum, "platform search upper bound");
  const occupied = input.reservedColumns ?? new Set<number>();
  const footprintWidth = layout.width;
  const endpointColumns = layoutEndpointColumns(layout);
  for (
    let candidate = after + 1;
    candidate + footprintWidth <= maximum &&
    candidate + footprintWidth <= input.heights.length;
    candidate += 1
  ) {
    const expected = input.heights[candidate];
    if (!Number.isSafeInteger(expected) || expected! < 1) continue;
    let eligible = true;
    const end = candidate + footprintWidth - 1;
    for (let column = candidate - 1; column <= end; column += 1) {
      if (occupied.has(column)) {
        eligible = false;
        break;
      }
      if (
        endpointColumns.has(column - candidate) &&
        input.heights[column] !== expected
      ) {
        eligible = false;
        break;
      }
    }
    if (!eligible) continue;
    const start = candidate;
    const lowerSurfaceY = terrainSurfaceY(
      input.heights[start]!,
      input.tilePixels,
      input.baselineY,
    );
    try {
      const world = createVerticalWorld({
        platforms: layout.platforms.map((platform) => ({
          id: platform.id,
          left: (start + platform.start) * input.tilePixels,
          right: (start + platform.end) * input.tilePixels,
          deckY: lowerSurfaceY - input.tilePixels * platform.tiers,
          tier: platform.tiers,
          sourceColumns: {
            start: start + platform.start,
            end: start + platform.end,
          },
        })),
        ladders: layout.ladders.map((ladder) => {
          const platform = layout.platforms.find(
            (candidatePlatform) => candidatePlatform.id === ladder.platformId,
          );
          if (!platform) throw new Error("ladder must name a layout platform");
          if (platform.tiers !== DEMO_LADDER_TIERS) {
            throw new Error("ladder platform must sit four tiles above terrain");
          }
          return {
            id: ladder.id,
            platformId: ladder.platformId,
            centerX:
              (start + ladder.column) * input.tilePixels + input.tilePixels / 2,
            upperDeckY: lowerSurfaceY - input.tilePixels * platform.tiers,
            lowerSurfaceY,
          };
        }),
        heights: input.heights,
        tilePixels: input.tilePixels,
        baselineY: input.baselineY,
        worldWidth: input.worldWidth,
      });
      const routes = createDemoPlatformRoutes(
        layout,
        lowerSurfaceY,
        world.platforms,
        world.ladders,
        input.heights,
        input.tilePixels,
        input.baselineY,
      );
      const reserved = new Set<number>();
      for (let column = start - 1; column <= end; column += 1) {
        if (column >= 0 && column < input.heights.length) reserved.add(column);
      }
      return deepFreeze({
        world,
        routes,
        reservedColumns: [...reserved].sort((a, b) => a - b),
      });
    } catch {
      // Candidate-local geometry can be invalid (for example an odd tile size
      // yields fractional ladder axes, or a deck lands inside the terrain it
      // is supposed to float over). Continue scanning instead of aborting an
      // otherwise playable preview scene.
    }
  }
  return null;
}
export type LadderVisualBounds = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}>;

export function ladderVisualBounds(ladder: LadderZone): LadderVisualBounds {
  if (
    ladder.visualTopOvershoot !== LADDER_VISUAL_OVERSHOOT ||
    ladder.visualBottomOvershoot !== LADDER_VISUAL_OVERSHOOT ||
    ladder.visualWidth !== LADDER_VISUAL_WIDTH
  ) {
    throw new Error("ladder visual contract drifted from its approved raster");
  }
  const halfWidth = ladder.visualWidth / 2;
  const top = ladder.upperDeckY - ladder.visualTopOvershoot;
  const bottom = ladder.lowerSurfaceY + ladder.visualBottomOvershoot;
  return deepFreeze({
    left: ladder.centerX - halfWidth,
    right: ladder.centerX + halfWidth,
    top,
    bottom,
    width: ladder.visualWidth,
    height: bottom - top,
  });
}

export function platformAtX(
  platforms: readonly UpperPlatform[],
  x: number,
): UpperPlatform | undefined {
  return platforms.find((platform) => x >= platform.left && x <= platform.right);
}

export type LandingResolution = Readonly<{
  footY: number;
  vy: number;
  support: Exclude<PlayerSupport, "ladder">;
  supportId: string | null;
}>;

/** Resolve one-way deck crossings before the terminal terrain candidate. */
export function resolveVerticalLanding(input: Readonly<{
  x: number;
  previousFootY: number;
  nextFootY: number;
  vy: number;
  terrainY: number;
  platforms: readonly UpperPlatform[];
  ignoredPlatformId?: string | null;
}>): LandingResolution {
  for (const value of [input.x, input.previousFootY, input.nextFootY, input.vy, input.terrainY]) {
    if (!Number.isFinite(value)) throw new Error("landing coordinates must be finite");
  }
  if (input.vy >= 0) {
    const crossed = input.platforms
      .filter(
        (platform) =>
          platform.id !== input.ignoredPlatformId &&
          input.x >= platform.left &&
          input.x <= platform.right &&
          input.previousFootY <= platform.deckY &&
          input.nextFootY >= platform.deckY,
      )
      .sort((left, right) => left.deckY - right.deckY || left.id.localeCompare(right.id));
    const platform = crossed[0];
    if (platform) {
      return deepFreeze({
        footY: platform.deckY,
        vy: 0,
        support: "platform",
        supportId: platform.id,
      });
    }
    // Terrain is solid rather than one-way. A horizontal step can move an
    // already-falling foot into a raised column, so `previousFootY` may already
    // be below the new surface. Clamp any descending sample at/below terrain.
    if (input.nextFootY >= input.terrainY) {
      return deepFreeze({ footY: input.terrainY, vy: 0, support: "terrain", supportId: null });
    }
  }
  return deepFreeze({
    footY: input.nextFootY,
    vy: input.vy,
    support: "air",
    supportId: null,
  });
}

export type TerrainStepResolution = Readonly<{
  footY: number;
  support: Extract<PlayerSupport, "terrain" | "air">;
}>;

/**
 * Resolve a standing foot against the terrain column under it.
 *
 * A drop past the tolerance is a fall: the foot stays where it is and the
 * caller hands it to gravity. Snapping it down instead teleported the player
 * through every descending step, so a one-tile kerb and a four-tile cliff both
 * read as flat walking.
 *
 * A rise is no longer absorbed either — `resolveTerrainWalk` stops the foot at
 * the column face before it can arrive under a raised surface, so the only way
 * up is a jump. Lifting here is kept solely as a recovery: if a foot ever does
 * end up beneath solid ground, the alternative is a player sealed inside a
 * hill with no input that frees them.
 */
export function resolveTerrainStep(input: Readonly<{
  footY: number;
  surfaceY: number;
  tolerance?: number;
}>): TerrainStepResolution {
  const tolerance = input.tolerance ?? TERRAIN_STEP_DOWN_TOLERANCE;
  for (const value of [input.footY, input.surfaceY, tolerance]) {
    if (!Number.isFinite(value)) throw new Error("terrain step values must be finite");
  }
  if (tolerance < 0) throw new Error("terrain step tolerance must be nonnegative");
  if (input.surfaceY > input.footY + tolerance) {
    return deepFreeze({ footY: input.footY, support: "air" });
  }
  return deepFreeze({ footY: input.surfaceY, support: "terrain" });
}

export type TerrainWalkResolution = Readonly<{
  x: number;
  blocked: boolean;
  /** Column whose face stopped the move, or null when nothing did. */
  blockedColumn: number | null;
}>;

/**
 * Resolve horizontal motion against the terrain columns it crosses.
 *
 * A column whose surface stands above the foot is a wall, whatever the foot is
 * currently supported by, so the same face that refuses a walk also refuses a
 * jump that has not yet cleared it and a drift that would slide into a cliff
 * mid-fall. The foot is left a pixel clear of the face rather than on it, so
 * the column lookup still resolves to the side it is standing on.
 *
 * Descents are not walls: walking off a ledge stays a fall.
 */
export function resolveTerrainWalk(input: Readonly<{
  previousX: number;
  nextX: number;
  footY: number;
  tilePixels: number;
  surfaceAt: (column: number) => number;
  tolerance?: number;
}>): TerrainWalkResolution {
  const tolerance = input.tolerance ?? TERRAIN_STEP_UP_TOLERANCE;
  for (const value of [input.previousX, input.nextX, input.footY, input.tilePixels, tolerance]) {
    if (!Number.isFinite(value)) throw new Error("terrain walk values must be finite");
  }
  if (input.tilePixels <= 0) throw new Error("terrain walk tile size must be positive");
  if (tolerance < 0) throw new Error("terrain walk tolerance must be nonnegative");
  const unblocked: TerrainWalkResolution = deepFreeze({
    x: input.nextX,
    blocked: false,
    blockedColumn: null,
  });
  const from = Math.floor(input.previousX / input.tilePixels);
  const to = Math.floor(input.nextX / input.tilePixels);
  if (from === to) return unblocked;
  const step = to > from ? 1 : -1;
  for (let column = from + step; step > 0 ? column <= to : column >= to; column += step) {
    const surfaceY = input.surfaceAt(column);
    if (!Number.isFinite(surfaceY)) throw new Error("terrain walk surface must be finite");
    if (surfaceY >= input.footY - tolerance) continue;
    return deepFreeze({
      x:
        step > 0
          ? column * input.tilePixels - TERRAIN_WALL_CONTACT_GAP
          : (column + 1) * input.tilePixels,
      blocked: true,
      blockedColumn: column,
    });
  }
  return unblocked;
}

export type CrouchMovementMode = "slow" | "stationary";

/** Resolve grounded horizontal intent under the selected crouch semantics. */
export function resolveCrouchHorizontalVelocity(input: Readonly<{
  velocity: number;
  mode: CrouchMovementMode;
}>): number {
  if (!Number.isFinite(input.velocity)) {
    throw new Error("crouch horizontal velocity must be finite");
  }
  return input.mode === "stationary" ? 0 : input.velocity * 0.4;
}

export type JumpKind = "ground" | "air" | "none";

export type JumpResolution = Readonly<{
  kind: JumpKind;
  /** Signed vertical velocity to assign; negative is upward, 0 when refused. */
  vy: number;
  airJumpsUsed: number;
}>;

/**
 * Decide which jump a press buys.
 *
 * `coyoteExpiresAtMs` is set by the caller only when a support was lost by
 * falling, never by jumping, so the grace window cannot be spent twice or
 * turn one press into a free second grounded launch.
 */
export function resolveJumpRequest(input: Readonly<{
  support: PlayerSupport;
  airJumpsUsed: number;
  nowMs: number;
  coyoteExpiresAtMs: number | null;
  crouching: boolean;
  maximumAirJumps?: number;
  jumpVelocity?: number;
  airJumpVelocity?: number;
}>): JumpResolution {
  const maximumAirJumps = input.maximumAirJumps ?? PLATFORMER_AIR_JUMPS_MAX;
  const jumpVelocity = input.jumpVelocity ?? PLATFORMER_JUMP_VELOCITY;
  const airJumpVelocity = input.airJumpVelocity ?? PLATFORMER_AIR_JUMP_VELOCITY;
  if (!Number.isSafeInteger(input.airJumpsUsed) || input.airJumpsUsed < 0) {
    throw new Error("air jump count must be a nonnegative integer");
  }
  if (!Number.isSafeInteger(maximumAirJumps) || maximumAirJumps < 0) {
    throw new Error("air jump budget must be a nonnegative integer");
  }
  if (!Number.isFinite(input.nowMs)) throw new Error("jump clock must be finite");
  const refused: JumpResolution = deepFreeze({
    kind: "none",
    vy: 0,
    airJumpsUsed: input.airJumpsUsed,
  });
  if (input.support === "ladder") return refused;
  if (input.support !== "air") {
    if (input.crouching) return refused;
    return deepFreeze({ kind: "ground", vy: -jumpVelocity, airJumpsUsed: 0 });
  }
  const coyoteOpen =
    input.coyoteExpiresAtMs !== null && input.nowMs <= input.coyoteExpiresAtMs;
  if (coyoteOpen && input.airJumpsUsed === 0) {
    return deepFreeze({ kind: "ground", vy: -jumpVelocity, airJumpsUsed: 0 });
  }
  if (input.airJumpsUsed >= maximumAirJumps) return refused;
  return deepFreeze({
    kind: "air",
    vy: -airJumpVelocity,
    airJumpsUsed: input.airJumpsUsed + 1,
  });
}

export function ladderEntryAt(input: Readonly<{
  ladders: readonly LadderZone[];
  support: PlayerSupport;
  supportId: string | null;
  x: number;
  footY: number;
  up: boolean;
  down: boolean;
}>): Readonly<{ ladder: LadderZone; direction: "up" | "down" }> | null {
  for (const ladder of input.ladders) {
    if (Math.abs(input.x - ladder.centerX) > ladder.activationHalfWidth) continue;
    if (
      input.support === "terrain" &&
      input.up &&
      !input.down &&
      Math.abs(input.footY - ladder.lowerSurfaceY) <= LADDER_ENDPOINT_TOLERANCE
    ) {
      return deepFreeze({ ladder, direction: "up" });
    }
    if (
      input.support === "platform" &&
      input.supportId === ladder.platformId &&
      input.down &&
      !input.up &&
      input.footY === ladder.upperDeckY
    ) {
      return deepFreeze({ ladder, direction: "down" });
    }
  }
  return null;
}

export type LadderMotion = Readonly<{
  footY: number;
  vy: number;
  exit: "platform" | "terrain" | null;
}>;

/** Advance an attached player with deterministic axis-locked endpoint clamps. */
export function advanceLadderMotion(input: Readonly<{
  ladder: LadderZone;
  footY: number;
  deltaSeconds: number;
  up: boolean;
  down: boolean;
}>): LadderMotion {
  if (!Number.isFinite(input.footY) || !Number.isFinite(input.deltaSeconds)) {
    throw new Error("ladder motion values must be finite");
  }
  if (input.deltaSeconds < 0) throw new Error("ladder delta must be nonnegative");
  const direction = input.up === input.down ? 0 : input.up ? -1 : 1;
  const vy = direction * LADDER_SPEED;
  const next = input.footY + vy * input.deltaSeconds;
  if (next <= input.ladder.upperDeckY) {
    return deepFreeze({ footY: input.ladder.upperDeckY, vy: 0, exit: "platform" });
  }
  if (next >= input.ladder.lowerSurfaceY) {
    return deepFreeze({ footY: input.ladder.lowerSurfaceY, vy: 0, exit: "terrain" });
  }
  return deepFreeze({ footY: next, vy, exit: null });
}

export function ladderJumpOffVelocity(input: Readonly<{
  left: boolean;
  right: boolean;
  facing: "left" | "right";
}>): Readonly<{ vx: number; vy: number }> {
  const direction =
    input.left !== input.right
      ? input.left
        ? -1
        : 1
      : input.facing === "left"
        ? -1
        : 1;
  return deepFreeze({
    vx: direction * LADDER_JUMP_HORIZONTAL_SPEED,
    vy: LADDER_JUMP_VELOCITY,
  });
}

export function platformDropThroughActive(input: Readonly<{
  nowMs: number;
  expiresAtMs: number;
  footY: number;
  deckY: number;
}>): boolean {
  for (const value of [input.nowMs, input.expiresAtMs, input.footY, input.deckY]) {
    if (!Number.isFinite(value)) throw new Error("drop-through values must be finite");
  }
  return (
    input.nowMs <= input.expiresAtMs ||
    input.footY <= input.deckY + PLATFORM_DROP_CLEARANCE
  );
}

export function verticalCameraScrollY(input: Readonly<{
  currentScrollY: number;
  footY: number;
  zoom: number;
  viewportHeight: number;
}>): number {
  for (const value of [
    input.currentScrollY,
    input.footY,
    input.zoom,
    input.viewportHeight,
  ]) {
    if (!Number.isFinite(value)) throw new Error("camera inputs must be finite");
  }
  if (input.zoom <= 0 || input.viewportHeight <= 0) {
    throw new Error("camera zoom and viewport height must be positive");
  }
  const originY = input.viewportHeight / 2;
  const projected =
    originY +
    (input.footY - input.currentScrollY - originY) * input.zoom;
  let next = input.currentScrollY;
  if (projected < VERTICAL_CAMERA_DEADZONE.top) {
    next =
      input.footY -
      originY -
      (VERTICAL_CAMERA_DEADZONE.top - originY) / input.zoom;
  } else if (projected > VERTICAL_CAMERA_DEADZONE.bottom) {
    next =
      input.footY -
      originY -
      (VERTICAL_CAMERA_DEADZONE.bottom - originY) / input.zoom;
  }
  return Math.max(VERTICAL_CAMERA_MIN_SCROLL_Y, Math.min(VERTICAL_CAMERA_MAX_SCROLL_Y, next));
}

export function verticalObjectVisible(input: Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
  cameraLeft: number;
  cameraRight: number;
  cameraTop: number;
  cameraBottom: number;
  overscan: number;
}>): boolean {
  return (
    input.right >= input.cameraLeft - input.overscan &&
    input.left <= input.cameraRight + input.overscan &&
    input.bottom >= input.cameraTop - input.overscan &&
    input.top <= input.cameraBottom + input.overscan
  );
}

export type VerticalViewportWorldBounds = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
}>;

/**
 * Convert Phaser camera scroll coordinates to its zoomed world viewport.
 * Phaser scroll is the unzoomed viewport origin: the world center remains at
 * `scroll + viewport / 2`, while zoom changes the half-extents around it.
 */
export function verticalViewportWorldBounds(input: Readonly<{
  scrollX: number;
  scrollY: number;
  zoom: number;
  viewportWidth: number;
  viewportHeight: number;
}>): VerticalViewportWorldBounds {
  for (const value of [
    input.scrollX,
    input.scrollY,
    input.zoom,
    input.viewportWidth,
    input.viewportHeight,
  ]) {
    if (!Number.isFinite(value)) throw new Error("viewport values must be finite");
  }
  if (input.zoom <= 0 || input.viewportWidth <= 0 || input.viewportHeight <= 0) {
    throw new Error("viewport zoom and dimensions must be positive");
  }
  const centerX = input.scrollX + input.viewportWidth / 2;
  const centerY = input.scrollY + input.viewportHeight / 2;
  const halfWidth = input.viewportWidth / (2 * input.zoom);
  const halfHeight = input.viewportHeight / (2 * input.zoom);
  return deepFreeze({
    left: centerX - halfWidth,
    right: centerX + halfWidth,
    top: centerY - halfHeight,
    bottom: centerY + halfHeight,
  });
}

/** Scene-adapter culling in world coordinates; DPR cannot affect the result. */
export function verticalSceneObjectVisible(input: Readonly<{
  bounds: Readonly<{ left: number; right: number; top: number; bottom: number }>;
  camera: Readonly<{
    scrollX: number;
    scrollY: number;
    zoom: number;
    viewportWidth: number;
    viewportHeight: number;
  }>;
  overscan: number;
  devicePixelRatio: number;
}>): boolean {
  if (
    !Number.isFinite(input.devicePixelRatio) ||
    input.devicePixelRatio < 1 ||
    input.devicePixelRatio > 8
  ) {
    throw new Error("device pixel ratio must be between one and eight");
  }
  if (!Number.isFinite(input.overscan) || input.overscan < 0) {
    throw new Error("viewport overscan must be nonnegative");
  }
  const view = verticalViewportWorldBounds(input.camera);
  return verticalObjectVisible({
    ...input.bounds,
    cameraLeft: view.left,
    cameraRight: view.right,
    cameraTop: view.top,
    cameraBottom: view.bottom,
    overscan: input.overscan,
  });
}

export function buildPlatformRenderPlan(
  platform: UpperPlatform,
  capHeight = 12,
  sideWidth = 12,
): PlatformRenderPlan {
  assertFiniteInteger(capHeight, "platform cap height");
  assertFiniteInteger(sideWidth, "platform side width");
  if (capHeight <= 0 || capHeight > platform.thickness || sideWidth <= 0) {
    throw new Error("platform contour dimensions are invalid");
  }
  const width = platform.right - platform.left;
  return deepFreeze({
    body: {
      x: platform.left,
      y: platform.deckY,
      width,
      height: platform.thickness,
    },
    cap: {
      x: platform.left,
      y: platform.deckY,
      width,
      height: capHeight,
    },
    sides: [
      {
        edge: "left",
        x: platform.left,
        y: platform.deckY,
        width: sideWidth,
        height: platform.thickness,
      },
      {
        edge: "right",
        x: platform.right - sideWidth,
        y: platform.deckY,
        width: sideWidth,
        height: platform.thickness,
      },
    ],
  });
}
