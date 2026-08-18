import type { SceneLayerProbe } from "./layers";
import { PLATFORMER_FIXED_STEP_SECONDS } from "./vertical";

export const GAMEPLAY_AUTOMATION_MODE = "gameplay-v1" as const;
export type GameplayAutomationMode = typeof GAMEPLAY_AUTOMATION_MODE;

export const GAMEPLAY_AUTOMATION_FPS = 1 / PLATFORMER_FIXED_STEP_SECONDS;
export const GAMEPLAY_AUTOMATION_FRAME_MS =
  PLATFORMER_FIXED_STEP_SECONDS * 1000;
export const GAMEPLAY_AUTOMATION_VIEWPORT = Object.freeze({
  width: 1280,
  height: 720,
});

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
    portalScale: 1 + pulse * 0.08,
    portalAlpha: 0.875 + pulse * 0.125,
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
  state: "idle" | "walk" | "run" | "jump" | "crouch" | "attack" | "climb";
  facing: "left" | "right";
  x: number;
  y: number;
  column: number;
  vx: number;
  vy: number;
  airborne: boolean;
  attackActive: boolean;
  support: "terrain" | "platform" | "ladder" | "air";
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
  climbAnimationKey: "player_climb" | null;
  climbTextureKey: "character_climb" | null;
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
  mode: "jump" | "drop" | "ladder";
  rise: number;
  gap: number;
  landingStep: number | null;
  horizontalRange: number | null;
  ladderId: string | null;
}>;

export type GameplayLadderProbe = Readonly<{
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
  state: "wander" | "hurt" | "dead";
  x: number;
  y: number;
  alive: boolean;
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
  assetKeys: readonly string[];
  frame: number;
  simulationMs: number;
  player: GameplayPlayerProbe | null;
  camera: Readonly<{ scrollX: number; scrollY: number; zoom: number }>;
  layers: readonly SceneLayerProbe[];
  platforms: readonly GameplayPlatformProbe[];
  platformRoutes: readonly GameplayPlatformRouteProbe[];
  ladders: readonly GameplayLadderProbe[];
  mobs: readonly GameplayMobProbe[];
  inventory: Readonly<{
    visible: boolean;
    slots: readonly GameplayInventoryProbe[];
  }>;
  worldItems: readonly GameplayWorldItemProbe[];
  encounter: GameplayEncounterProbe;
  portals: readonly GameplayPortalProbe[];
  presentation: GameplayAutomationPresentation;
  events: readonly GameplayTranscriptEvent[];
  heightmapDigest: string | null;
}>;

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
