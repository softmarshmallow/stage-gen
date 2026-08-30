import type { SceneLayerProbe } from "./layers";
import type { MobAggression } from "./combat";
import type { PlayerState } from "./player-state";
import type { CombatTextSystemSnapshot } from "./combat-text";
import { PLATFORMER_FIXED_STEP_SECONDS } from "./vertical";

export const GAMEPLAY_AUTOMATION_MODE = "gameplay-v2" as const;
export type GameplayAutomationMode = typeof GAMEPLAY_AUTOMATION_MODE;

export const GAMEPLAY_AUTOMATION_FPS = 1 / PLATFORMER_FIXED_STEP_SECONDS;
export const GAMEPLAY_AUTOMATION_FRAME_MS =
  PLATFORMER_FIXED_STEP_SECONDS * 1000;
export const GAMEPLAY_AUTOMATION_VIEWPORT = Object.freeze({
  width: 1280,
  height: 720,
});

export type GameplayOverviewCamera = Readonly<{
  scrollX: number;
  scrollY: number;
  zoom: number;
}>;

export const GAMEPLAY_STILL_SAFE_MARGIN = 32;
export const GAMEPLAY_STILL_MIN_ACTOR_HEIGHT = 64;
export const GAMEPLAY_STILL_MIN_PORTAL_HEIGHT = 96;
export const GAMEPLAY_STILL_MIN_PICKUP_WIDTH = 24;
export const GAMEPLAY_STILL_MIN_PICKUP_HEIGHT = 28;

export type GameplayStillAnchor = Readonly<{ x: number; y: number }>;
export type GameplayStillComposition = Readonly<{
  camera: GameplayOverviewCamera;
  player: GameplayStillAnchor;
  mob: GameplayStillAnchor;
  portal: GameplayStillAnchor;
  pickup: GameplayStillAnchor;
}>;

/**
 * Fit the complete platform-and-ladder route into the initial canvas. The
 * first fixed gameplay step resumes actor-follow choreography, so this camera
 * is a deterministic still/composition surface rather than gameplay state.
 */
export function gameplayOverviewCamera(input: Readonly<{
  platforms: readonly Readonly<{
    left: number;
    right: number;
    deckY: number;
    thickness: number;
  }>[];
  climbables: readonly Readonly<{
    left: number;
    right: number;
    top: number;
    bottom: number;
  }>[];
  viewport?: Readonly<{ width: number; height: number }>;
  marginPixels?: number;
  maximumZoom?: number;
}>): GameplayOverviewCamera | null {
  if (input.platforms.length < 3 || input.climbables.length === 0) return null;
  const viewport = input.viewport ?? GAMEPLAY_AUTOMATION_VIEWPORT;
  const margin = input.marginPixels ?? 48;
  const maximumZoom = input.maximumZoom ?? 0.72;
  if (
    !Number.isFinite(viewport.width) ||
    !Number.isFinite(viewport.height) ||
    viewport.width <= margin * 2 ||
    viewport.height <= margin * 2 ||
    !Number.isFinite(maximumZoom) ||
    maximumZoom <= 0 ||
    maximumZoom > 1 ||
    !Number.isFinite(margin) ||
    margin < 0
  ) {
    throw new Error("gameplay overview camera inputs are invalid");
  }
  const bounds = [
    ...input.platforms.map((platform) => ({
      left: platform.left,
      right: platform.right,
      top: platform.deckY,
      bottom: platform.deckY + platform.thickness,
    })),
    ...input.climbables,
  ];
  for (const bound of bounds) {
    if (
      ![bound.left, bound.right, bound.top, bound.bottom].every(Number.isFinite) ||
      bound.right <= bound.left ||
      bound.bottom <= bound.top
    ) {
      throw new Error("gameplay overview bounds are invalid");
    }
  }
  const left = Math.min(...bounds.map((bound) => bound.left));
  const right = Math.max(...bounds.map((bound) => bound.right));
  const top = Math.min(...bounds.map((bound) => bound.top));
  const bottom = Math.max(...bounds.map((bound) => bound.bottom));
  const zoom = Math.min(
    maximumZoom,
    (viewport.width - margin * 2) / (right - left),
    (viewport.height - margin * 2) / (bottom - top),
  );
  if (!Number.isFinite(zoom) || zoom <= 0) {
    throw new Error("gameplay overview route cannot fit the viewport");
  }
  return Object.freeze({
    scrollX: (left + right) / 2 - viewport.width / 2,
    // Keep the gameplay baseline stable; zoom owns vertical fitting and zero
    // scroll avoids exposing below-world space in a still capture.
    scrollY: 0,
    zoom,
  });
}

/**
 * Place real runtime subjects on three successive platform elevations for the
 * frame-zero production still. The scene restores their gameplay spawns before
 * frame one, so the checkpoint is presentation-only and cannot alter the run.
 */
export function gameplayStillComposition(input: Readonly<{
  platforms: readonly Readonly<{
    left: number;
    right: number;
    deckY: number;
    thickness: number;
    tier: number;
  }>[];
  climbables: readonly Readonly<{
    left: number;
    right: number;
    top: number;
    bottom: number;
  }>[];
}>): GameplayStillComposition | null {
  const elevations = [...input.platforms]
    .sort(
      (left, right) =>
        left.tier - right.tier ||
        left.deckY - right.deckY ||
        left.left - right.left,
    )
    .filter(
      (platform, index, all) =>
        all.findIndex((candidate) => candidate.deckY === platform.deckY) ===
        index,
    );
  if (elevations.length < 3) return null;
  // Frame the decks the still actually stages subjects on, plus the ladder,
  // rather than every deck in the world. A branching graph can run far above
  // and past its route; fitting all of it would shrink the three subjects
  // this still exists to show until none of them read.
  const staged = elevations.slice(0, 3);
  const camera = gameplayOverviewCamera({
    platforms: staged,
    climbables: input.climbables,
  });
  if (!camera) return null;
  // The fixed runtime route fits at >= 0.56 zoom. Reject future layouts that
  // would make the 1.8-tile mob smaller than the locked 64px still contract.
  if (camera.zoom * 64 * 1.8 < GAMEPLAY_STILL_MIN_ACTOR_HEIGHT) {
    throw new Error("gameplay still route makes runtime actors too small");
  }
  const at = (platform: (typeof elevations)[number], fraction: number) =>
    Object.freeze({
      x: platform.left + (platform.right - platform.left) * fraction,
      y: platform.deckY,
    });
  return Object.freeze({
    camera,
    player: at(elevations[0]!, 0.22),
    portal: at(elevations[0]!, 0.78),
    mob: at(elevations[1]!, 0.5),
    pickup: at(elevations[2]!, 0.5),
  });
}

export const GAMEPLAY_AUTOMATION_ENCOUNTER = Object.freeze({
  focusStartFrame: 1,
  focusEndFrame: 80,
  cameraZoom: 1.2,
  safeMarginPixels: 64,
  deathDelayFrames: 9,
  dropDelayFrames: 15,
  pickupDelayFrames: 33,
  finalActiveStartFrame: 846,
});

export type GameplayAutomationLoop = Readonly<{
  running: boolean;
  sleep: () => void;
}>;

/**
 * Stop Phaser's normal rAF loop immediately after `Game.start()` starts it.
 * Phaser invokes `postBoot` before `TimeStep.start`, so calling `sleep()`
 * synchronously there is a no-op. A microtask runs after `start()` returns but
 * before the browser can dispatch the first animation frame.
 */
export function sleepGameplayAutomationLoopAfterBoot(
  loop: GameplayAutomationLoop,
): void {
  queueMicrotask(() => {
    if (loop.running) loop.sleep();
  });
}

export type GameplayAutomationPresentation = Readonly<{
  encounterFocus: boolean;
  foregroundVisible: boolean;
  inventorySuppressed: boolean;
  finalActiveWindow: boolean;
  cameraZoom: number;
  portalScale: number;
  portalAlpha: number;
}>;

/** Pure fixed-frame presentation policy; it cannot mutate gameplay state. */
export function gameplayAutomationPresentation(
  frame: number,
): GameplayAutomationPresentation {
  if (!Number.isSafeInteger(frame) || frame < 0) {
    throw new Error(
      "gameplay automation presentation frame must be a nonnegative integer",
    );
  }
  const encounterFocus =
    frame >= GAMEPLAY_AUTOMATION_ENCOUNTER.focusStartFrame &&
    frame <= GAMEPLAY_AUTOMATION_ENCOUNTER.focusEndFrame;
  const pulse = Math.sin((frame * Math.PI) / 12);
  return Object.freeze({
    encounterFocus,
    foregroundVisible: !encounterFocus,
    inventorySuppressed: encounterFocus,
    finalActiveWindow:
      frame >= GAMEPLAY_AUTOMATION_ENCOUNTER.finalActiveStartFrame,
    cameraZoom: encounterFocus ? GAMEPLAY_AUTOMATION_ENCOUNTER.cameraZoom : 1,
    portalScale: 1,
    portalAlpha: 0.985 + pulse * 0.015,
  });
}

export class GameplayAutomationRequestError extends Error {
  constructor() {
    super("gameplay automation is not available");
    this.name = "GameplayAutomationRequestError";
  }
}

/** Resolve the query at the server boundary; clients never inspect the env. */
export function resolveGameplayAutomationMode(
  requested: string | readonly string[] | undefined,
  serverFlag: string | undefined,
): GameplayAutomationMode | null {
  if (requested === undefined) return null;
  if (requested !== GAMEPLAY_AUTOMATION_MODE || serverFlag !== "1") {
    throw new GameplayAutomationRequestError();
  }
  return GAMEPLAY_AUTOMATION_MODE;
}

export type GameplayAutomationState = "loading" | "ready" | "error";

export type GameplayFrame = Readonly<{
  frame: number;
  simulationMs: number;
  deltaMs: number;
}>;

/** A monotonic fixed-step clock that cannot advance before asset readiness. */
export class GameplayAutomationClock {
  private currentFrame = 0;
  private currentState: GameplayAutomationState = "loading";

  get frame(): number {
    return this.currentFrame;
  }

  get simulationMs(): number {
    return this.currentFrame * GAMEPLAY_AUTOMATION_FRAME_MS;
  }

  get state(): GameplayAutomationState {
    return this.currentState;
  }

  markReady(): void {
    if (this.currentState !== "loading") {
      throw new Error("gameplay automation readiness is already settled");
    }
    this.currentState = "ready";
  }

  markFailed(): void {
    if (this.currentState === "loading") this.currentState = "error";
  }

  advance(): GameplayFrame {
    if (this.currentState !== "ready") {
      throw new Error("gameplay automation is not ready");
    }
    this.currentFrame += 1;
    return Object.freeze({
      frame: this.currentFrame,
      simulationMs: this.simulationMs,
      deltaMs: GAMEPLAY_AUTOMATION_FRAME_MS,
    });
  }
}

export type GameplayTranscriptEvent = Readonly<{
  kind: string;
  frame: number;
  simulationMs: number;
  data: Readonly<Record<string, string | number | boolean>> | null;
}>;

export type GameplayPlayerProbe = Readonly<{
  // Deliberately the controller's own union rather than a copy of it. A transcribed list stays
  // type-valid when the controller gains a state, so the probe would go on publishing a contract
  // the runtime had stopped honouring, with nothing failing to compile.
  state: PlayerState;
  facing: "left" | "right";
  x: number;
  y: number;
  column: number;
  vx: number;
  vy: number;
  airborne: boolean;
  /** Mid-air jumps spent since the last support. */
  airJumpsUsed: number;
  attackActive: boolean;
  hp: number;
  maxHp: number;
  invulnerable: boolean;
  defeated: boolean;
  support: "terrain" | "platform" | "climbable" | "air";
  supportId: string | null;
  ladderId: string | null;
  platformId: string | null;
  dropThroughPlatformId: string | null;
  dropTraversalPhase:
    | "drop-commanded"
    | "underside-cleared"
    | "lower-support-landed"
    | "lower-support-settled"
    | "recovery-airborne"
    | "recovered"
    | null;
  dropTraversalPlatformId: string | null;
  dropTraversalPlatformBottomY: number | null;
  dropTraversalLowerSupport: "terrain" | "platform" | null;
  dropTraversalLowerSupportId: string | null;
  dropTraversalLowerSupportY: number | null;
  dropTraversalStableFrames: number;
  renderBounds: Readonly<{
    left: number;
    top: number;
    right: number;
    bottom: number;
  }>;
  /** Names the strip for the climbable being held, so it varies with the authored role. */
  climbAnimationKey: string | null;
  climbTextureKey: string | null;
  climbFrame: number | null;
  climbAnimationPaused: boolean | null;
  rearFacing: boolean;
}>;

export type GameplayPlatformProbe = Readonly<{
  id: string;
  left: number;
  right: number;
  deckY: number;
  tier: number;
  thickness: number;
  visible: boolean;
}>;

export type GameplayPlatformRouteProbe = Readonly<{
  id: string;
  from: string;
  to: string;
  mode: "jump" | "double-jump" | "drop" | "climbable";
  rise: number;
  gap: number;
  landingStep: number | null;
  horizontalRange: number | null;
  ladderId: string | null;
}>;

export type GameplayClimbableProbe = Readonly<{
  id: string;
  platformId: string;
  centerX: number;
  top: number;
  bottom: number;
  activationHalfWidth: number;
  visualTopOvershoot: number;
  visualBottomOvershoot: number;
  visible: boolean;
}>;

export type GameplayMobProbe = Readonly<{
  ladderIndex: number;
  hp: number;
  state:
    | "wander"
    | "chase"
    | "return_home"
    | "attack_recovery"
    | "windup"
    | "hurt"
    | "dead";
  /** Aggression archetype the generator published, or null when the optional profile is absent. */
  aggression: MobAggression | null;
  x: number;
  y: number;
  alive: boolean;
  visible: boolean;
  /** Conservative alpha bounds across every idle and hurt animation frame. */
  renderBounds: GameplayWorldBoundsProbe;
}>;

export type GameplayInventoryProbe = Readonly<{
  kindIndex: number;
  slotIndex: number;
  count: number;
  x: number;
  y: number;
  expectedPanelX: number;
  expectedPanelY: number;
}>;

export type GameplayWorldItemProbe = Readonly<{
  kindIndex: number;
  x: number;
  y: number;
  settled: boolean;
  renderBounds: GameplayWorldBoundsProbe;
}>;

export type GameplayWorldBoundsProbe = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
}>;

export type GameplayEncounterProbe = Readonly<{
  safeMarginPixels: number;
  focusX: number | null;
  focusY: number | null;
  player: GameplayWorldBoundsProbe | null;
  mob: GameplayWorldBoundsProbe | null;
  attack: GameplayWorldBoundsProbe | null;
  drop: GameplayWorldBoundsProbe | null;
  pickup: GameplayWorldBoundsProbe | null;
}>;

export type GameplayPortalProbe = Readonly<{
  kind: "entry" | "exit";
  x: number;
  y: number;
  w: number;
  h: number;
}>;

export type GameplayAutomationSnapshot = Readonly<{
  version: GameplayAutomationMode;
  state: GameplayAutomationState;
  ready: boolean;
  errors: readonly string[];
  /** Non-fatal bounded diagnostics, including unavailable optional traversal. */
  diagnostics: readonly string[];
  assetKeys: readonly string[];
  /** Position in the stage plan this frame's world belongs to. */
  stageIndex: number;
  stageId: string;
  frame: number;
  simulationMs: number;
  player: GameplayPlayerProbe | null;
  camera: Readonly<{ scrollX: number; scrollY: number; zoom: number }>;
  layers: readonly SceneLayerProbe[];
  platforms: readonly GameplayPlatformProbe[];
  platformRoutes: readonly GameplayPlatformRouteProbe[];
  climbables: readonly GameplayClimbableProbe[];
  mobs: readonly GameplayMobProbe[];
  inventory: Readonly<{
    visible: boolean;
    bounds: GameplayWorldBoundsProbe | null;
    slots: readonly GameplayInventoryProbe[];
  }>;
  worldItems: readonly GameplayWorldItemProbe[];
  encounter: GameplayEncounterProbe;
  portals: readonly GameplayPortalProbe[];
  presentation: GameplayAutomationPresentation;
  /** Stage-scoped FCT state; absent before stage construction and during teardown. */
  combatText?: CombatTextSystemSnapshot;
  events: readonly GameplayTranscriptEvent[];
  heightmapDigest: string | null;
}>;

declare global {
  interface Window {
    __sceneReady?: boolean;
    readonly __stageGenGameplayProbe?: GameplayAutomationSnapshot;
    readonly __stageGenAdvanceGameplayFrame?: () => Promise<GameplayAutomationSnapshot>;
  }
}

function deepFreeze(value: unknown): void {
  if (value === null || typeof value !== "object" || Object.isFrozen(value))
    return;
  for (const child of Object.values(value)) deepFreeze(child);
  Object.freeze(value);
}

/** Return a detached, deeply frozen and JSON-serializable public snapshot. */
export function readonlyGameplaySnapshot(
  snapshot: GameplayAutomationSnapshot,
): GameplayAutomationSnapshot {
  const detached = structuredClone({
    ...snapshot,
    assetKeys: [...new Set(snapshot.assetKeys)].sort(),
  });
  deepFreeze(detached);
  return detached;
}

/** Stable lowercase SHA-256 over signed 32-bit big-endian height values. */
export async function heightmapSha256(
  heights: readonly number[],
): Promise<string> {
  const bytes = new Uint8Array(heights.length * 4);
  const view = new DataView(bytes.buffer);
  heights.forEach((height, index) => view.setInt32(index * 4, height, false));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}
