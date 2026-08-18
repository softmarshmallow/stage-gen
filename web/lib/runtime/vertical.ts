import { terrainSurfaceY } from "./terrain";

export const UPPER_PLATFORM_THICKNESS = 32 as const;
export const LADDER_ACTIVATION_HALF_WIDTH = 30 as const;
export const LADDER_ENDPOINT_TOLERANCE = 12 as const;
export const LADDER_VISUAL_OVERSHOOT = 32 as const;
export const LADDER_VISUAL_WIDTH = 80 as const;
export const LADDER_SPEED = 180 as const;
export const LADDER_JUMP_VELOCITY = -350 as const;
export const LADDER_JUMP_HORIZONTAL_SPEED = 200 as const;
export const PLATFORMER_WALK_SPEED = 200 as const;
export const PLATFORMER_RUN_SPEED = 540 as const;
export const PLATFORMER_JUMP_VELOCITY = 520 as const;
export const PLATFORMER_GRAVITY = 1500 as const;
export const PLATFORMER_FIXED_STEP_SECONDS = 1 / 30;
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

export type PlatformRouteMode = "jump" | "drop" | "ladder";

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
}>;

/** Semi-implicit Euler proof matching Player.update's fixed-step jump order. */
export function simulatePlatformJump(input: Readonly<{
  rise: number;
  gap: number;
  horizontalSpeed?: number;
  jumpVelocity?: number;
  gravity?: number;
  stepSeconds?: number;
  maximumSteps?: number;
}>): JumpReachability {
  const horizontalSpeed = input.horizontalSpeed ?? PLATFORMER_RUN_SPEED;
  const jumpVelocity = input.jumpVelocity ?? PLATFORMER_JUMP_VELOCITY;
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
  ]) {
    if (!Number.isFinite(value)) throw new Error("jump proof values must be finite");
  }
  if (
    input.rise < 0 ||
    input.gap < 0 ||
    horizontalSpeed < 0 ||
    jumpVelocity <= 0 ||
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
  for (let step = 1; step <= maximumSteps; step += 1) {
    const previousY = y;
    vy += gravity * stepSeconds;
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
  if (!/^[a-z][a-z0-9-]{0,63}$/.test(value)) {
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
  platforms.sort((left, right) => left.left - right.left || left.id.localeCompare(right.id));
  for (let index = 1; index < platforms.length; index += 1) {
    if (platforms[index]!.left < platforms[index - 1]!.right) {
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

function createDemoPlatformRoutes(
  lowerSurfaceY: number,
  platforms: readonly UpperPlatform[],
  ladder: LadderZone,
  heights: readonly number[],
  tilePixels: number,
  baselineY: number,
): readonly PlatformRoute[] {
  const byId = new Map(platforms.map((platform) => [platform.id, platform]));
  const jumpPairs = [
    ["terrain", "tier-1-launch", 0],
    ["tier-1-launch", "tier-2-transfer", 64],
    ["tier-2-transfer", "tier-3-bridge", 64],
    ["tier-3-bridge", "tier-4-summit", 64],
  ] as const;
  const routes: PlatformRoute[] = jumpPairs.map(([from, to, gap], index) => {
    const destination = byId.get(to);
    if (!destination) throw new Error(`jump destination ${to} is missing`);
    const sourceDeckY =
      from === "terrain" ? lowerSurfaceY : byId.get(from)?.deckY;
    if (sourceDeckY === undefined) throw new Error(`jump source ${from} is missing`);
    const rise = sourceDeckY - destination.deckY;
    const proof = simulatePlatformJump({ rise, gap });
    if (!proof.reachable || proof.landingStep === null || proof.horizontalRange === null) {
      throw new Error(`jump route ${from} to ${to} is unreachable`);
    }
    return {
      id: `jump-${index + 1}`,
      from,
      to,
      mode: "jump",
      rise,
      gap,
      landingStep: proof.landingStep,
      horizontalRange: proof.horizontalRange,
      ladderId: null,
    };
  });
  for (const platform of platforms) {
    const recoverySurfaces = heights
      .slice(platform.sourceColumns.start, platform.sourceColumns.end)
      .map((height) => terrainSurfaceY(height, tilePixels, baselineY));
    if (recoverySurfaces.length === 0) {
      throw new Error(`drop route from ${platform.id} has no recovery terrain`);
    }
    const fallDistance = Math.max(...recoverySurfaces) - platform.deckY;
    const landingStep = platformDropRecoverySteps({ fallDistance });
    if (landingStep === null) {
      throw new Error(`drop route from ${platform.id} cannot recover`);
    }
    routes.push({
      id: `drop-${platform.tier}`,
      from: platform.id,
      to: "terrain",
      mode: "drop",
      rise: -fallDistance,
      gap: 0,
      landingStep,
      horizontalRange: null,
      ladderId: null,
    });
  }
  routes.push(
    {
      id: "ladder-up",
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
      id: "ladder-down",
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
  const ids = new Set<string>();
  for (const route of routes) {
    assertStableId(route.id, "route id");
    if (ids.has(route.id)) throw new Error("route ids must be unique");
    ids.add(route.id);
  }
  return deepFreeze(routes);
}

/** Select a four-tier branching graph outside caller-owned reservations. */
export function selectDemoVerticalWorld(input: Readonly<{
  heights: readonly number[];
  tilePixels: number;
  baselineY: number;
  worldWidth: number;
  reservedColumns?: ReadonlySet<number>;
  afterColumn?: number;
  maximumColumnExclusive?: number;
}>): DemoVerticalSelection | null {
  const after = input.afterColumn ?? 8;
  const maximum =
    input.maximumColumnExclusive ?? Math.floor(input.heights.length * 0.35);
  assertFiniteInteger(after, "platform search lower bound");
  assertFiniteInteger(maximum, "platform search upper bound");
  const occupied = input.reservedColumns ?? new Set<number>();
  const footprintWidth = 28;
  for (
    let candidate = after + 1;
    candidate + footprintWidth <= maximum &&
    candidate + footprintWidth <= input.heights.length;
    candidate += 1
  ) {
    const expected = input.heights[candidate];
    if (!Number.isSafeInteger(expected) || expected! < 1) continue;
    let eligible = true;
    const end = candidate + 27;
    const endpointColumns = new Set([
      candidate,
      candidate + 1,
      candidate + 26,
      candidate + 27,
    ]);
    for (let column = candidate - 1; column <= end; column += 1) {
      if (occupied.has(column)) {
        eligible = false;
        break;
      }
      if (endpointColumns.has(column) && input.heights[column] !== expected) {
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
        platforms: [
          {
            id: "tier-1-launch",
            left: start * input.tilePixels,
            right: (start + 6) * input.tilePixels,
            deckY: lowerSurfaceY - input.tilePixels,
            tier: 1,
            sourceColumns: { start, end: start + 6 },
          },
          {
            id: "tier-2-transfer",
            left: (start + 7) * input.tilePixels,
            right: (start + 13) * input.tilePixels,
            deckY: lowerSurfaceY - input.tilePixels * 2,
            tier: 2,
            sourceColumns: { start: start + 7, end: start + 13 },
          },
          {
            id: "tier-3-bridge",
            left: (start + 14) * input.tilePixels,
            right: (start + 20) * input.tilePixels,
            deckY: lowerSurfaceY - input.tilePixels * 3,
            tier: 3,
            sourceColumns: { start: start + 14, end: start + 20 },
          },
          {
            id: "tier-4-summit",
            left: (start + 21) * input.tilePixels,
            right: (start + 27) * input.tilePixels,
            deckY: lowerSurfaceY - input.tilePixels * 4,
            tier: 4,
            sourceColumns: { start: start + 21, end: start + 27 },
          },
        ],
        ladders: [
          {
            id: "ladder-summit",
            platformId: "tier-4-summit",
            centerX: (start + 27) * input.tilePixels - input.tilePixels / 2,
            upperDeckY: lowerSurfaceY - input.tilePixels * 4,
            lowerSurfaceY,
          },
        ],
        heights: input.heights,
        tilePixels: input.tilePixels,
        baselineY: input.baselineY,
        worldWidth: input.worldWidth,
      });
      const routes = createDemoPlatformRoutes(
        lowerSurfaceY,
        world.platforms,
        world.ladders[0]!,
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
      // yields fractional ladder axes). Continue scanning instead of aborting
      // an otherwise playable preview scene.
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
