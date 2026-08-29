import { spawn, type ChildProcessByStdio } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Readable } from "node:stream";
import { fileURLToPath } from "node:url";
import { chromium, type Browser, type Page } from "playwright";
import { PNG } from "pngjs";
import {
  GAMEPLAY_AUTOMATION_ENCOUNTER,
  GAMEPLAY_AUTOMATION_VIEWPORT,
  type GameplayAutomationSnapshot,
  type GameplayWorldBoundsProbe,
} from "../../lib/runtime/automation";
import { GAMEPLAY_AUTOMATION_VERSION, type GameplayFixture } from "./contracts";
import {
  GAMEPLAY_REQUIRED_ASSET_KEYS as SYNTHETIC_GAMEPLAY_REQUIRED_ASSET_KEYS,
  generateGameplayFixture,
} from "./fixture";
import {
  GAMEPLAY_MODEL_ASSET_CONTRACTS,
  GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS,
  GAMEPLAY_MODEL_TERRAIN_SEED,
  generateApprovedModelGameplayFixture,
} from "./model-assets";
import {
  PLATFORM_DROP_SETTLE_FRAMES,
  UPPER_PLATFORM_THICKNESS,
  selectDemoVerticalWorld,
} from "../../lib/runtime/vertical";
import { buildHeightmapFromSeed } from "../../lib/runtime/heightmap";
import { STAGE_PLANS, stageTerrainSeed } from "../../lib/runtime/stages";
import { NEAR_FOREGROUND_DEPTH_COEFFICIENT } from "../../lib/runtime/layers";
import {
  GAMEPLAY_DURATION_SECONDS,
  GAMEPLAY_DROP_EVENT_SEQUENCE,
  GAMEPLAY_EVENT_VISIBILITY_WINDOWS,
  GAMEPLAY_FRAME_COUNT,
  GAMEPLAY_POSTER_FRAME,
  GAMEPLAY_PLATFORM_EVENT_SEQUENCE,
  GAMEPLAY_REQUIRED_EVENTS,
  GAMEPLAY_REQUIRED_STATES,
  GAMEPLAY_SELECTED_FRAMES,
  GAMEPLAY_STEP_MS,
  GAMEPLAY_TIMELINE,
  GAMEPLAY_VERTICAL_EVENT_SEQUENCE,
  type GameplayFrame,
} from "./timeline";

const GAMEPLAY_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(GAMEPLAY_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
export const GAMEPLAY_NEXT_CLI_PATH = path.join(
  WEB_ROOT,
  "node_modules",
  "next",
  "dist",
  "bin",
  "next",
);
const CAPTURE_VIDEO_PATH = "docs/media/gameplay-showcase.mp4";
const CAPTURE_POSTER_PATH = "docs/media/gameplay-showcase.poster.png";
const MODEL_ASSET_AGGREGATE_SHA256 =
  "24f02376a8a561333b1f89403649c954a53ffb7c7cc035c3d4495f1127cfe9b8";
/** Gameplay viewport, and with it the ground baseline at its bottom edge. */
const GAMEPLAY_VIEWPORT_HEIGHT = 720;
const GAMEPLAY_WORLD_WIDTH = 12_800;
const GAMEPLAY_TILE_PX = 64;
/**
 * The vertical geometry this capture must find in the live runtime.
 *
 * Derived from the pure selector over the fixture's own terrain seed rather
 * than transcribed. A copy here would only ever prove that two literals in
 * this repository agree with each other; `vertical.test.ts` pins the literal
 * values, and this gate proves the browser built what that module resolves.
 */
/**
 * The vertical geometry this capture must find in the live runtime, per stage.
 *
 * Derived from the pure selector over each stage's own seed and layout rather
 * than transcribed. A copy here would only ever prove that two literals in
 * this repository agree with each other; `vertical.test.ts` pins the literal
 * values, and this gate proves the browser built what those modules resolve.
 * Indexing by stage is what lets the run travel: after the portal fires the
 * probe legitimately describes a different world, and a single fixed
 * expectation would call that a regression.
 */
export const APPROVED_VERTICAL = STAGE_PLANS.map((plan) => {
  const heights = buildHeightmapFromSeed(
    stageTerrainSeed(GAMEPLAY_MODEL_TERRAIN_SEED, plan),
    { cols: 200, minH: 1, maxH: 4 },
  );
  const selected = selectDemoVerticalWorld({
    heights,
    tilePixels: GAMEPLAY_TILE_PX,
    baselineY: GAMEPLAY_VIEWPORT_HEIGHT,
    worldWidth: GAMEPLAY_WORLD_WIDTH,
    reservedColumns: new Set(Array.from({ length: 14 }, (_, column) => column)),
    layout: plan.layout,
  });
  if (!selected) {
    throw new Error(`approved gameplay seed selects no graph for ${plan.id}`);
  }
  return {
    stageId: plan.id,
    reservedColumns: new Set(selected.reservedColumns),
    platforms: selected.world.platforms.map((platform) => ({
      id: platform.id,
      left: platform.left,
      right: platform.right,
      deckY: platform.deckY,
      tier: platform.tier,
      thickness: platform.thickness,
    })),
    routes: selected.routes.map((route) => ({ ...route })),
    climbables: selected.world.climbables.map((ladder) => ({
      id: ladder.id,
      platformId: ladder.platformId,
      centerX: ladder.centerX,
      top: ladder.upperDeckY - ladder.visualTopOvershoot,
      bottom: ladder.lowerSurfaceY + ladder.visualBottomOvershoot,
      activationHalfWidth: ladder.activationHalfWidth,
      visualTopOvershoot: ladder.visualTopOvershoot,
      visualBottomOvershoot: ladder.visualBottomOvershoot,
    })),
  };
});

/** The stage geometry a snapshot claims to be showing. */
function approvedVerticalFor(
  snapshot: Readonly<{ stageIndex: number; stageId: string }>,
): (typeof APPROVED_VERTICAL)[number] {
  const approved = APPROVED_VERTICAL[snapshot.stageIndex];
  if (!approved || approved.stageId !== snapshot.stageId) {
    throw new Error(
      `gameplay probe reports unknown stage ${snapshot.stageIndex}/${snapshot.stageId}`,
    );
  }
  return approved;
}
/**
 * Screen row the near foreground's contact strip lands on. The foreground meets
 * the ground, and the ground baseline is the bottom of the viewport, so this is
 * the viewport height. This read a standalone 704 while the runtime anchored to
 * a matching standalone 704, so the pair agreed with each other and not with
 * the frame: a foreground painted to its own last row ended a quarter-tile
 * short of the screen edge and this gate called it correct.
 */
const FOREGROUND_CONTACT_SCREEN_Y = GAMEPLAY_VIEWPORT_HEIGHT;
const SERVER_TIMEOUT_MS = 30_000;
const PROBE_TIMEOUT_MS = 30_000;
const MAX_SERVER_LOG_CHARS = 64_000;
const MAX_TOOL_OUTPUT_CHARS = 64_000;
const MAX_TOOL_DIAGNOSTIC_CHARS = 4_096;
const TOOL_TERMINATE_GRACE_MS = 2_000;
const FFMPEG_TIMEOUT_MS = 300_000;
const FFPROBE_TIMEOUT_MS = 30_000;
const TOOL_VERSION_TIMEOUT_MS = 10_000;
const MAX_TOOL_TIMEOUT_MS = 600_000;
const MAX_TOOL_TERMINATE_GRACE_MS = 10_000;

export const GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS = Object.freeze({
  tierThree: -37.666666666666686,
  summit: -101.66666666666669,
  recovery: 0,
});

export type GameplayRunEvidence = Readonly<{
  transcript: string;
  transcriptDigest: string;
  selectedFrameHashes: Readonly<Record<string, string>>;
  states: readonly string[];
  finalSnapshot: GameplayAutomationSnapshot;
}>;

export type GameplaySnapshotValidator = (
  snapshot: GameplayAutomationSnapshot,
) => void;

export type GameplayVerification = Readonly<{
  version: typeof GAMEPLAY_AUTOMATION_VERSION;
  verdict: "pass";
  frameCount: number;
  durationSeconds: number;
  fixtureDigest: string;
  transcriptDigest: string;
  selectedFrameHashes: Readonly<Record<string, string>>;
  eventFrames: Readonly<Record<string, number>>;
}>;

type StartedServer = {
  baseUrl: string;
  process: ServerChild;
  stop: () => Promise<void>;
};

type ServerChild = ChildProcessByStdio<null, Readable, Readable>;

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function safeServerEnvironment(outRoot: string): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    NODE_ENV: "production",
    NEXT_TELEMETRY_DISABLED: "1",
    STAGE_GEN_GAMEPLAY_AUTOMATION: "1",
    STAGE_GEN_OUT_DIR: outRoot,
    STAGE_GEN_RUN_LIVE: "0",
  };
  for (const name of ["PATH", "HOME", "TMPDIR"] as const) {
    if (process.env[name]) env[name] = process.env[name];
  }
  return env;
}

async function assertBuiltNextApplication(applicationRoot: string): Promise<void> {
  if (!path.isAbsolute(applicationRoot)) {
    throw new Error("Next application root must be absolute");
  }
  const applicationStat = await fs.lstat(applicationRoot).catch(() => {
    throw new Error("Next application root must be a real directory");
  });
  if (!applicationStat.isDirectory() || applicationStat.isSymbolicLink()) {
    throw new Error("Next application root must be a real directory");
  }
  const [buildId, nextCli] = await Promise.all([
    fs.lstat(path.join(applicationRoot, ".next", "BUILD_ID")),
    fs.lstat(GAMEPLAY_NEXT_CLI_PATH),
  ]).catch(() => {
    throw new Error(
      "built Next application is missing; run `bun run build` in web first",
    );
  });
  if (!buildId.isFile() || buildId.isSymbolicLink() || !nextCli.isFile()) {
    throw new Error(
      "built Next application is unsafe; rebuild it from web/package.json",
    );
  }
  const realCli = await fs.realpath(GAMEPLAY_NEXT_CLI_PATH);
  const dependencyRoot = `${path.join(WEB_ROOT, "node_modules")}${path.sep}`;
  if (!realCli.startsWith(dependencyRoot)) {
    throw new Error("Next launcher escapes the web dependency directory");
  }
}

async function freeLoopbackPort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("could not reserve a loopback port"));
        return;
      }
      server.close((error) => (error ? reject(error) : resolve(address.port)));
    });
  });
}

async function stopChild(child: ServerChild): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill("SIGTERM");
  const exited = new Promise<void>((resolve) =>
    child.once("exit", () => resolve()),
  );
  const deadline = new Promise<"timeout">((resolve) =>
    setTimeout(() => resolve("timeout"), 5_000),
  );
  if (
    (await Promise.race([exited.then(() => "exited" as const), deadline])) ===
    "timeout"
  ) {
    child.kill("SIGKILL");
    await exited;
  }
}

function throwIfAborted(signal: AbortSignal | undefined, label: string): void {
  if (signal?.aborted) throw new Error(`${label} was cancelled`);
}

async function abortable<T>(
  operation: Promise<T>,
  signal: AbortSignal | undefined,
  label: string,
): Promise<T> {
  if (!signal) return await operation;
  throwIfAborted(signal, label);
  let listener: (() => void) | undefined;
  const cancelled = new Promise<never>((_, reject) => {
    listener = () => reject(new Error(`${label} was cancelled`));
    signal.addEventListener("abort", listener, { once: true });
  });
  try {
    return await Promise.race([operation, cancelled]);
  } finally {
    if (listener) signal.removeEventListener("abort", listener);
  }
}

async function rethrowAfterGameplayCleanup(
  primaryError: unknown,
  label: string,
  cleanup: () => Promise<void>,
): Promise<never> {
  try {
    await cleanup();
  } catch (cleanupError) {
    throw new AggregateError(
      [primaryError, cleanupError],
      `${label} failed and cleanup failed`,
      { cause: primaryError },
    );
  }
  throw primaryError;
}

export async function runOwnedGameplayStartup<T>(
  startup: () => Promise<T>,
  cleanup: () => Promise<void>,
  label: string,
): Promise<T> {
  try {
    return await startup();
  } catch (error) {
    return await rethrowAfterGameplayCleanup(error, label, cleanup);
  }
}

export async function acquireAbortableGameplayResource<T>(
  acquisition: Promise<T>,
  signal: AbortSignal | undefined,
  label: string,
  cleanup: (resource: T) => Promise<void>,
): Promise<T> {
  try {
    return await abortable(acquisition, signal, label);
  } catch (error) {
    if (!signal?.aborted) throw error;
    let resource: T;
    try {
      resource = await acquisition;
    } catch {
      throw error;
    }
    return await rethrowAfterGameplayCleanup(
      error,
      label,
      async () => await cleanup(resource),
    );
  }
}

async function startNextServer(
  outRoot: string,
  signal?: AbortSignal,
  applicationRoot = WEB_ROOT,
): Promise<StartedServer> {
  throwIfAborted(signal, "gameplay server startup");
  await assertBuiltNextApplication(applicationRoot);
  const port = await freeLoopbackPort();
  const args = [
    GAMEPLAY_NEXT_CLI_PATH,
    "start",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(port),
  ];
  const child = spawn(process.execPath, args, {
    cwd: applicationRoot,
    env: safeServerEnvironment(outRoot),
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  const remember = (chunk: Buffer) => {
    output = `${output}${chunk.toString("utf8")}`.slice(-MAX_SERVER_LOG_CHARS);
  };
  child.stdout.on("data", remember);
  child.stderr.on("data", remember);
  const baseUrl = `http://127.0.0.1:${port}`;
  return await runOwnedGameplayStartup(
    async () => {
      const startedAt = Date.now();
      while (Date.now() - startedAt < SERVER_TIMEOUT_MS) {
        throwIfAborted(signal, "gameplay server startup");
        if (child.exitCode !== null) {
          throw new Error(
            `Next server exited before readiness (code ${child.exitCode}): ${output}`,
          );
        }
        try {
          const response = await fetch(baseUrl, {
            redirect: "manual",
            signal,
          });
          if (response.status >= 200 && response.status < 500) {
            return { baseUrl, process: child, stop: () => stopChild(child) };
          }
        } catch {
          // Startup races are expected until the loopback listener is ready.
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      throw new Error(
        `Next server did not become ready within ${SERVER_TIMEOUT_MS}ms`,
      );
    },
    async () => await stopChild(child),
    "gameplay server startup",
  );
}

function transcriptLine(snapshot: GameplayAutomationSnapshot): string {
  return JSON.stringify({
    frame: snapshot.frame,
    simulationMs: snapshot.simulationMs,
    stageIndex: snapshot.stageIndex,
    stageId: snapshot.stageId,
    player: snapshot.player,
    camera: snapshot.camera,
    layers: snapshot.layers.filter((layer) => layer.kind === "near-foreground"),
    platforms: snapshot.platforms,
    platformRoutes: snapshot.platformRoutes,
    climbables: snapshot.climbables,
    mobs: snapshot.mobs,
    inventory: snapshot.inventory,
    worldItems: snapshot.worldItems,
    encounter: snapshot.encounter,
    portals: snapshot.portals,
    presentation: snapshot.presentation,
    combatText: snapshot.combatText,
    events: snapshot.events,
  });
}

function firstValueDifference(
  left: unknown,
  right: unknown,
  at = "$",
): string | null {
  if (Object.is(left, right)) return null;
  if (
    left === null ||
    right === null ||
    typeof left !== "object" ||
    typeof right !== "object"
  ) {
    return `${at} (${JSON.stringify(left)} != ${JSON.stringify(right)})`;
  }
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const keys = [
    ...new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)]),
  ].sort();
  for (const key of keys) {
    if (!(key in leftRecord) || !(key in rightRecord))
      return `${at}.${key} (missing)`;
    const difference = firstValueDifference(
      leftRecord[key],
      rightRecord[key],
      `${at}.${key}`,
    );
    if (difference) return difference;
  }
  return null;
}

function transcriptDifference(left: string, right: string): string {
  const leftLines = left.trimEnd().split("\n");
  const rightLines = right.trimEnd().split("\n");
  const length = Math.max(leftLines.length, rightLines.length);
  for (let index = 0; index < length; index += 1) {
    if (leftLines[index] === rightLines[index]) continue;
    if (leftLines[index] === undefined || rightLines[index] === undefined) {
      return `frame ${index + 1} (transcript length differs)`;
    }
    return `frame ${index + 1} at ${firstValueDifference(
      JSON.parse(leftLines[index]),
      JSON.parse(rightLines[index]),
    )}`;
  }
  return "unknown position";
}

function assertSnapshotContract(snapshot: GameplayAutomationSnapshot): void {
  if (snapshot.version !== GAMEPLAY_AUTOMATION_VERSION) {
    throw new Error(
      `unexpected gameplay probe version: ${String(snapshot.version)}`,
    );
  }
  if (snapshot.errors.length > 0) {
    const detail = sanitizedToolDiagnostic(
      snapshot.errors.slice(0, 3).join("\n"),
    );
    throw new Error(
      `gameplay probe reported ${snapshot.errors.length} error(s)` +
        (detail ? `: ${detail}` : ""),
    );
  }
  if (snapshot.diagnostics.length > 0) {
    throw new Error(
      `gameplay probe reported ${snapshot.diagnostics.length} diagnostic(s): ` +
        sanitizedToolDiagnostic(snapshot.diagnostics.slice(0, 3).join("\n")),
    );
  }
  if (!snapshot.ready || snapshot.state !== "ready") {
    throw new Error(`gameplay probe is not ready (${snapshot.state})`);
  }
  if (!snapshot.heightmapDigest?.match(/^[0-9a-f]{64}$/)) {
    throw new Error("gameplay probe has no stable heightmap digest");
  }
  if (
    !snapshot.combatText ||
    !snapshot.combatText.enabled ||
    snapshot.combatText.disposed
  ) {
    throw new Error("gameplay probe has no active default-on combat text system");
  }
  const currentMobHit = snapshot.events.find(
    (event) => event.kind === "mob-hit" && event.frame === snapshot.frame,
  );
  if (currentMobHit) {
    const entry = snapshot.combatText.entries.at(-1);
    if (
      !entry ||
      entry.direction !== "outgoing" ||
      entry.amount !== currentMobHit.data?.damage ||
      entry.text !== String(currentMobHit.data?.damage)
    ) {
      throw new Error("connected mob hit did not publish matching outgoing combat text");
    }
  }
  if (
    snapshot.frame === GAMEPLAY_EVENT_VISIBILITY_WINDOWS.hit.start + 20 &&
    snapshot.combatText.activeCount !== 0
  ) {
    throw new Error("outgoing combat text did not expire on its fixed simulation clock");
  }
  for (const mob of snapshot.mobs) {
    if (
      mob.renderBounds.left < 0 ||
      mob.renderBounds.right > 12_800 ||
      mob.renderBounds.top >= mob.renderBounds.bottom ||
      mob.x < mob.renderBounds.left ||
      mob.x > mob.renderBounds.right
    ) {
      throw new Error("mob full alpha bounds escape the gameplay world");
    }
  }
  if (snapshot.inventory.visible) {
    const bounds = snapshot.inventory.bounds;
    if (
      !bounds ||
      bounds.left < 24 ||
      bounds.right > GAMEPLAY_AUTOMATION_VIEWPORT.width - 24 ||
      bounds.top < 24 ||
      bounds.bottom > GAMEPLAY_AUTOMATION_VIEWPORT.height - 24
    ) {
      throw new Error("inventory HUD escapes the capture-safe viewport");
    }
  }
  const approved = approvedVerticalFor(snapshot);
  assertMatchesApprovedGeometry(
    "platform",
    snapshot.platforms.map(({ visible: _visible, ...platform }) => platform),
    approved.platforms,
  );
  assertMatchesApprovedGeometry(
    "platform route",
    snapshot.platformRoutes.map((route) => ({ ...route })),
    approved.routes,
  );
  assertMatchesApprovedGeometry(
    "climbable",
    snapshot.climbables.map(({ visible: _visible, ...ladder }) => ladder),
    approved.climbables,
  );
  if (snapshot.player) assertPlayerSupportInvariant(snapshot.frame, snapshot.player);
  assertGameplayForegroundProbe(
    snapshot.frame,
    snapshot.layers,
    snapshot.presentation,
    snapshot.camera,
  );
}

/**
 * Compare a live vertical probe against the geometry the pure selector
 * resolves, naming the first row that disagrees.
 *
 * A bare "violates the approved geometry" says nothing about which deck moved,
 * which turned every layout change into a bisect against a browser capture.
 */
function assertMatchesApprovedGeometry(
  label: string,
  actual: readonly unknown[],
  expected: readonly unknown[],
): void {
  if (actual.length !== expected.length) {
    throw new Error(
      `gameplay ${label} probe has ${actual.length} entries, approved geometry has ${expected.length}`,
    );
  }
  for (let index = 0; index < expected.length; index += 1) {
    const left = JSON.stringify(actual[index]);
    const right = JSON.stringify(expected[index]);
    if (left !== right) {
      throw new Error(
        `gameplay ${label} probe violates the approved geometry at ${index}: ${left} !== ${right}`,
      );
    }
  }
}

function assertPlayerSupportInvariant(
  frame: number,
  player: NonNullable<GameplayAutomationSnapshot["player"]>,
): void {
  for (const value of [player.x, player.y, player.vx, player.vy]) {
    if (!Number.isFinite(value)) {
      throw new Error(`player contains a nonfinite value at frame ${frame}`);
    }
  }
  for (const value of Object.values(player.renderBounds)) {
    if (!Number.isFinite(value)) {
      throw new Error(`player render bounds are nonfinite at frame ${frame}`);
    }
  }
  if (
    player.renderBounds.left >= player.renderBounds.right ||
    player.renderBounds.top >= player.renderBounds.bottom ||
    player.x < player.renderBounds.left ||
    player.x > player.renderBounds.right ||
    !approximately(player.renderBounds.bottom, player.y)
  ) {
    throw new Error(`player render bounds are inconsistent at frame ${frame}`);
  }
  if (player.airborne !== (player.support === "air")) {
    throw new Error(`player airborne/support invariant failed at frame ${frame}`);
  }
  if (
    (player.support === "climbable") !== (player.ladderId !== null) ||
    (player.support === "platform") !== (player.platformId !== null) ||
    (player.support === "climbable" && player.supportId !== player.ladderId) ||
    (player.support === "platform" && player.supportId !== player.platformId) ||
    ((player.support === "terrain" || player.support === "air") &&
      player.supportId !== null)
  ) {
    throw new Error(`player support ids are inconsistent at frame ${frame}`);
  }
  if (
    player.dropThroughPlatformId !== null &&
    player.support !== "air"
  ) {
    throw new Error(`player drop-through state is sticky at frame ${frame}`);
  }
  const dropPhase = player.dropTraversalPhase;
  const hasDropOrigin =
    player.dropTraversalPlatformId !== null &&
    Number.isFinite(player.dropTraversalPlatformBottomY);
  if (
    (dropPhase === null) !== !hasDropOrigin ||
    !Number.isSafeInteger(player.dropTraversalStableFrames) ||
    player.dropTraversalStableFrames < 0 ||
    player.dropTraversalStableFrames > PLATFORM_DROP_SETTLE_FRAMES ||
    (dropPhase === null &&
      (player.dropTraversalLowerSupport !== null ||
        player.dropTraversalLowerSupportId !== null ||
        player.dropTraversalLowerSupportY !== null ||
        player.dropTraversalStableFrames !== 0)) ||
    ((dropPhase === "drop-commanded" || dropPhase === "underside-cleared") &&
      (player.dropTraversalLowerSupport !== null ||
        player.dropTraversalLowerSupportId !== null ||
        player.dropTraversalLowerSupportY !== null)) ||
    (dropPhase !== null &&
      dropPhase !== "drop-commanded" &&
      dropPhase !== "underside-cleared" &&
      (player.dropTraversalLowerSupport === null ||
        !Number.isFinite(player.dropTraversalLowerSupportY)))
  ) {
    throw new Error(`player drop traversal probe is inconsistent at frame ${frame}`);
  }
  const climbing = player.support === "climbable";
  if (
    climbing !== (player.state === "climb") ||
    climbing !==
      (player.climbAnimationKey !== null &&
        player.climbAnimationKey.startsWith("player_climb")) ||
    climbing !==
      (player.climbTextureKey !== null &&
        player.climbTextureKey.startsWith("character_climb")) ||
    climbing !== player.rearFacing ||
    (climbing &&
      (!Number.isSafeInteger(player.climbFrame) ||
        player.climbFrame! < 0 ||
        player.climbFrame! > 3 ||
        typeof player.climbAnimationPaused !== "boolean")) ||
    (!climbing &&
      (player.climbFrame !== null || player.climbAnimationPaused !== null))
  ) {
    throw new Error(`player climb presentation is inconsistent at frame ${frame}`);
  }
}

function approximately(left: number, right: number, tolerance = 1e-6): boolean {
  return (
    Number.isFinite(left) &&
    Number.isFinite(right) &&
    Math.abs(left - right) <= tolerance
  );
}

function positiveModulo(value: number, period: number): number {
  return ((value % period) + period) % period;
}

function signedCircularDelta(
  from: number,
  to: number,
  period: number,
): number {
  return positiveModulo(to - from + period / 2, period) - period / 2;
}

function assertGameplayForegroundProbe(
  frame: number,
  layers: GameplayAutomationSnapshot["layers"],
  presentation: GameplayAutomationSnapshot["presentation"],
  camera: GameplayAutomationSnapshot["camera"],
): void {
  const foregrounds = layers.filter(
    (layer) => layer.kind === "near-foreground",
  );
  if (foregrounds.length !== 1) {
    throw new Error(
      `frame ${frame} requires exactly one foreground layer probe`,
    );
  }
  const layer = foregrounds[0]!;
  const foreground = layer.foreground;
  if (!foreground) {
    throw new Error(`frame ${frame} foreground layer has no measured probe`);
  }
  const tolerance = 0.5 / foreground.devicePixelRatio + 1e-6;
  const exactClip =
    foreground.clipBounds.left === 0 &&
    foreground.clipBounds.top === 0 &&
    foreground.clipBounds.right === GAMEPLAY_AUTOMATION_VIEWPORT.width &&
    foreground.clipBounds.bottom === GAMEPLAY_AUTOMATION_VIEWPORT.height;
  const display = layer.render.displayBounds;
  const actualPhaseDevicePixels =
    layer.render.tilePositionX *
    foreground.sourceScaleScreenX *
    foreground.devicePixelRatio;
  const liveSourceScaleScreenX =
    layer.render.tileScaleX * layer.render.scaleX * camera.zoom;
  const liveSourceScaleScreenY =
    layer.render.tileScaleY * layer.render.scaleY * camera.zoom;
  const periodScreenPx =
    foreground.repeatPeriodSourcePx * liveSourceScaleScreenX;
  const projectedCameraTravelScreenPx =
    camera.scrollX * camera.zoom * NEAR_FOREGROUND_DEPTH_COEFFICIENT;
  const rawExpectedPhaseScreenPx = positiveModulo(
    projectedCameraTravelScreenPx,
    periodScreenPx,
  );
  const snappedExpectedPhaseScreenPx =
    Math.round(rawExpectedPhaseScreenPx * foreground.devicePixelRatio) /
    foreground.devicePixelRatio;
  const expectedPhaseScreenPx =
    snappedExpectedPhaseScreenPx >= periodScreenPx
      ? 0
      : snappedExpectedPhaseScreenPx;
  const actualPhaseScreenPx =
    layer.render.tilePositionX * liveSourceScaleScreenX;
  if (
    layer.anchor !== "screen-ground-left" ||
    layer.baseline !== "screen-ground" ||
    layer.repeat !== "repeat-x-overlap-add" ||
    layer.cull !== "never" ||
    layer.renderDepth !== 1200 ||
    layer.render.depth !== layer.renderDepth ||
    layer.depthCoefficient !== NEAR_FOREGROUND_DEPTH_COEFFICIENT ||
    foreground.depthCoefficient !== layer.depthCoefficient ||
    !approximately(layer.cameraScrollX, camera.scrollX) ||
    !approximately(layer.cameraScrollY, camera.scrollY) ||
    layer.render.spriteCount !== 1 ||
    layer.render.scrollFactorX !== 0 ||
    layer.render.scrollFactorY !== 0 ||
    foreground.spriteCount !== 1 ||
    layer.render.visible !== presentation.foregroundVisible ||
    !approximately(layer.cameraZoom, camera.zoom) ||
    !approximately(display.left, layer.screenBounds.left) ||
    !approximately(display.top, layer.screenBounds.top) ||
    !approximately(display.right, layer.screenBounds.right) ||
    !approximately(display.bottom, layer.screenBounds.bottom) ||
    Math.abs(foreground.contactScreenY - FOREGROUND_CONTACT_SCREEN_Y) >
      tolerance ||
    display.bottom < GAMEPLAY_VIEWPORT_HEIGHT - tolerance ||
    foreground.meaningfulContentScreenBounds.top < 540 - tolerance ||
    foreground.sourceScaleScreenX > 0.75 + 1e-6 ||
    foreground.sourceScaleScreenY > 0.75 + 1e-6 ||
    !approximately(
      foreground.sourceScaleScreenX,
      foreground.sourceScaleScreenY,
    ) ||
    !approximately(foreground.sourceScaleScreenX, liveSourceScaleScreenX) ||
    !approximately(foreground.sourceScaleScreenY, liveSourceScaleScreenY) ||
    !exactClip ||
    foreground.repeatPeriodSourcePx !== 1024 ||
    foreground.overlapSourcePx !== 256 ||
    layer.render.textureWidth !== foreground.repeatPeriodSourcePx ||
    layer.render.textureHeight <= 0 ||
    foreground.phaseSourcePx < 0 ||
    foreground.phaseSourcePx >= foreground.repeatPeriodSourcePx ||
    !approximately(layer.tilePositionX, foreground.phaseSourcePx) ||
    !approximately(layer.render.tilePositionX, foreground.phaseSourcePx) ||
    !approximately(foreground.phaseDevicePixels, actualPhaseDevicePixels) ||
    !approximately(
      foreground.observedPhaseScreenPx,
      actualPhaseScreenPx,
    ) ||
    !approximately(
      foreground.projectedCameraTravelScreenPx,
      projectedCameraTravelScreenPx,
    ) ||
    Math.abs(
      signedCircularDelta(
        expectedPhaseScreenPx,
        actualPhaseScreenPx,
        periodScreenPx,
      ),
    ) > tolerance ||
    Math.abs(
      foreground.phaseDevicePixels - Math.round(foreground.phaseDevicePixels),
    ) > 1e-6 ||
    !approximately(
      foreground.seamPeriodScreenPx,
      foreground.repeatPeriodSourcePx * foreground.sourceScaleScreenX,
    ) ||
    !approximately(layer.render.scaleX * camera.zoom, 1) ||
    !approximately(layer.render.scaleY * camera.zoom, 1)
  ) {
    throw new Error(
      `frame ${frame} foreground layer probe violates contract: ${JSON.stringify({
        camera,
        layerCamera: {
          x: layer.cameraScrollX,
          y: layer.cameraScrollY,
          zoom: layer.cameraZoom,
        },
        plannedBounds: layer.screenBounds,
        displayBounds: display,
        visible: layer.render.visible,
        expectedVisible: presentation.foregroundVisible,
        scale: {
          sourceX: foreground.sourceScaleScreenX,
          sourceY: foreground.sourceScaleScreenY,
          liveX: liveSourceScaleScreenX,
          liveY: liveSourceScaleScreenY,
          objectX: layer.render.scaleX,
          objectY: layer.render.scaleY,
        },
        phase: {
          actual: actualPhaseScreenPx,
          expected: expectedPhaseScreenPx,
          source: foreground.phaseSourcePx,
        },
      })}`,
    );
  }
}

function assertGameplayForegroundMotion(
  transcript: readonly Readonly<{
    frame: number;
    camera: GameplayAutomationSnapshot["camera"];
    layers: GameplayAutomationSnapshot["layers"];
    presentation: GameplayAutomationSnapshot["presentation"];
  }>[],
): void {
  let measuredPairs = 0;
  let cumulativeObservedPhaseTravel = 0;
  let cumulativeTerrainScreenTravel = 0;
  let cumulativeTolerance = 0;
  for (let index = 1; index < transcript.length; index += 1) {
    const previous = transcript[index - 1]!;
    const current = transcript[index]!;
    if (
      !previous.presentation.foregroundVisible ||
      !current.presentation.foregroundVisible ||
      previous.camera.zoom !== current.camera.zoom
    ) {
      continue;
    }
    const cameraDelta = current.camera.scrollX - previous.camera.scrollX;
    if (Math.abs(cameraDelta) <= 1e-9) continue;
    const previousForeground = previous.layers[0]?.foreground;
    const currentForeground = current.layers[0]?.foreground;
    if (!previousForeground || !currentForeground) continue;
    const periodScreenPx = currentForeground.seamPeriodScreenPx;
    if (
      !approximately(
        periodScreenPx,
        previousForeground.seamPeriodScreenPx,
      )
    ) {
      continue;
    }
    const observedPhaseTravel = signedCircularDelta(
      previousForeground.observedPhaseScreenPx,
      currentForeground.observedPhaseScreenPx,
      periodScreenPx,
    );
    const terrainScreenTravel = cameraDelta * current.camera.zoom;
    const expectedPhaseTravel =
      terrainScreenTravel * NEAR_FOREGROUND_DEPTH_COEFFICIENT;
    if (Math.abs(expectedPhaseTravel) >= periodScreenPx / 2) continue;
    const tolerance =
      1 / Math.min(
        previousForeground.devicePixelRatio,
        currentForeground.devicePixelRatio,
      ) + 1e-6;
    if (
      Math.abs(observedPhaseTravel - expectedPhaseTravel) > tolerance ||
      Math.sign(observedPhaseTravel) !== Math.sign(terrainScreenTravel) ||
      Math.abs(observedPhaseTravel) + tolerance <=
        Math.abs(terrainScreenTravel) * 1.75
    ) {
      throw new Error(
        `foreground physical displacement violates ${NEAR_FOREGROUND_DEPTH_COEFFICIENT}x motion at frame ${current.frame}`,
      );
    }
    measuredPairs += 1;
    cumulativeObservedPhaseTravel += observedPhaseTravel;
    cumulativeTerrainScreenTravel += terrainScreenTravel;
    cumulativeTolerance = Math.max(cumulativeTolerance, tolerance);
  }
  if (measuredPairs === 0) {
    throw new Error("gameplay transcript has no visible foreground motion pair");
  }
  const cumulativeExpected =
    cumulativeTerrainScreenTravel * NEAR_FOREGROUND_DEPTH_COEFFICIENT;
  if (
    Math.abs(cumulativeObservedPhaseTravel - cumulativeExpected) >
      cumulativeTolerance ||
    Math.abs(cumulativeObservedPhaseTravel) + cumulativeTolerance <=
      Math.abs(cumulativeTerrainScreenTravel) * 1.75
  ) {
    throw new Error(
      `foreground cumulative displacement does not converge to ${NEAR_FOREGROUND_DEPTH_COEFFICIENT}x terrain`,
    );
  }
}

export type GameplayViewportBounds = Readonly<{
  left: number;
  right: number;
  top: number;
  bottom: number;
}>;

export function projectGameplayBoundsToViewport(
  bounds: GameplayWorldBoundsProbe,
  camera: GameplayAutomationSnapshot["camera"],
): GameplayViewportBounds {
  const centerX = GAMEPLAY_AUTOMATION_VIEWPORT.width / 2;
  const centerY = GAMEPLAY_AUTOMATION_VIEWPORT.height / 2;
  const projectX = (worldX: number) =>
    centerX + (worldX - (camera.scrollX + centerX)) * camera.zoom;
  const projectY = (worldY: number) =>
    centerY + (worldY - (camera.scrollY + centerY)) * camera.zoom;
  return Object.freeze({
    left: projectX(bounds.left),
    right: projectX(bounds.right),
    top: projectY(bounds.top),
    bottom: projectY(bounds.bottom),
  });
}

function assertEncounterSubjectVisible(
  frame: number,
  subject: string,
  bounds: GameplayWorldBoundsProbe | null,
  camera: GameplayAutomationSnapshot["camera"],
  margin: number,
): void {
  if (!bounds)
    throw new Error(`${subject} has no encounter bounds at frame ${frame}`);
  const projected = projectGameplayBoundsToViewport(bounds, camera);
  if (
    projected.left < margin ||
    projected.right > GAMEPLAY_AUTOMATION_VIEWPORT.width - margin ||
    projected.top < margin ||
    projected.bottom > GAMEPLAY_AUTOMATION_VIEWPORT.height - margin
  ) {
    throw new Error(
      `${subject} leaves the safe viewport at frame ${frame}: ` +
        `${JSON.stringify(projected)} with margin ${margin}`,
    );
  }
}

export function validateGameplayRun(run: GameplayRunEvidence): void {
  const final = run.finalSnapshot;
  assertSnapshotContract(final);
  if (final.frame !== GAMEPLAY_FRAME_COUNT) {
    throw new Error(
      `expected frame ${GAMEPLAY_FRAME_COUNT}, got ${final.frame}`,
    );
  }
  if (Math.abs(final.simulationMs - GAMEPLAY_DURATION_SECONDS * 1000) > 1e-7) {
    throw new Error(`unexpected simulation duration: ${final.simulationMs}`);
  }
  const actualAssets = [...final.assetKeys].sort();
  if (
    JSON.stringify(actualAssets) !==
    JSON.stringify(GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS)
  ) {
    throw new Error(
      "loaded gameplay asset keys do not match the fixture contract",
    );
  }
  for (const state of GAMEPLAY_REQUIRED_STATES) {
    if (!run.states.includes(state))
      throw new Error(`timeline did not exercise ${state}`);
  }
  for (const kind of GAMEPLAY_REQUIRED_EVENTS) {
    const count = final.events.filter((event) => event.kind === kind).length;
    if (count !== 1) {
      const exit = final.portals.find((portal) => portal.kind === "exit");
      const position =
        kind === "stage-advance"
          ? ` (player x ${String(final.player?.x)}, exit x ${String(exit?.x)})`
          : "";
      throw new Error(
        `expected exactly one ${kind} event, got ${count}${position}`,
      );
    }
  }
  const eventWindows = [
    ["mob-hit", GAMEPLAY_EVENT_VISIBILITY_WINDOWS.hit],
    ["mob-death", GAMEPLAY_EVENT_VISIBILITY_WINDOWS.death],
    ["mob-drop", GAMEPLAY_EVENT_VISIBILITY_WINDOWS.drop],
    ["item-pickup", GAMEPLAY_EVENT_VISIBILITY_WINDOWS.pickup],
    ["stage-advance", GAMEPLAY_EVENT_VISIBILITY_WINDOWS.stageAdvance],
  ] as const;
  for (const [kind, window] of eventWindows) {
    const event = final.events.find((candidate) => candidate.kind === kind)!;
    if (event.frame < window.start || event.frame > window.end) {
      throw new Error(
        `${kind} frame ${event.frame} is outside visible window ${window.start}-${window.end}`,
      );
    }
  }
  const transcript = run.transcript
    .trimEnd()
    .split("\n")
    .map(
      (line) =>
        JSON.parse(line) as {
          frame: number;
          stageIndex: number;
          stageId: string;
          player: GameplayAutomationSnapshot["player"];
          camera: GameplayAutomationSnapshot["camera"];
          layers: GameplayAutomationSnapshot["layers"];
          platforms: GameplayAutomationSnapshot["platforms"];
          platformRoutes: GameplayAutomationSnapshot["platformRoutes"];
          climbables: GameplayAutomationSnapshot["climbables"];
          mobs: GameplayAutomationSnapshot["mobs"];
          worldItems: GameplayAutomationSnapshot["worldItems"];
          encounter: GameplayAutomationSnapshot["encounter"];
          presentation: GameplayAutomationSnapshot["presentation"];
          events: GameplayAutomationSnapshot["events"];
        },
    );
  if (transcript.length !== GAMEPLAY_FRAME_COUNT) {
    throw new Error(
      "gameplay transcript must contain exactly 900 frame snapshots",
    );
  }
  for (const snapshot of transcript) {
    assertGameplayForegroundProbe(
      snapshot.frame,
      snapshot.layers,
      snapshot.presentation,
      snapshot.camera,
    );
    if (snapshot.player) assertPlayerSupportInvariant(snapshot.frame, snapshot.player);
    const stage = approvedVerticalFor(snapshot);
    if (
      snapshot.platforms.length !== stage.platforms.length ||
      snapshot.platformRoutes.length !== stage.routes.length ||
      snapshot.climbables.length !== stage.climbables.length
    ) {
      throw new Error(`vertical probes are incomplete at frame ${snapshot.frame}`);
    }
    if (
      JSON.stringify(snapshot.platformRoutes) !== JSON.stringify(stage.routes)
    ) {
      throw new Error(`platform routes drifted at frame ${snapshot.frame}`);
    }
  }
  assertGameplayForegroundMotion(transcript);
  const byFrame = new Map(
    transcript.map((snapshot) => [snapshot.frame, snapshot]),
  );
  for (const [kind] of eventWindows.slice(0, 4)) {
    const event = final.events.find((candidate) => candidate.kind === kind)!;
    const snapshot = byFrame.get(event.frame);
    if (
      !snapshot?.presentation.encounterFocus ||
      snapshot.presentation.foregroundVisible ||
      !snapshot.presentation.inventorySuppressed ||
      snapshot.camera.zoom !== GAMEPLAY_AUTOMATION_ENCOUNTER.cameraZoom
    ) {
      throw new Error(
        `${kind} is not staged in the unobscured encounter focus`,
      );
    }
  }
  const poster = byFrame.get(GAMEPLAY_POSTER_FRAME);
  if (
    poster?.player?.state !== "attack" ||
    !poster.presentation.encounterFocus ||
    poster.presentation.foregroundVisible ||
    !poster.presentation.inventorySuppressed
  ) {
    throw new Error("poster frame is not an unobscured attack frame");
  }
  const verticalEvents = final.events.filter(
    (event) => event.kind === "ladder-enter" || event.kind === "ladder-exit",
  );
  if (verticalEvents.length !== GAMEPLAY_VERTICAL_EVENT_SEQUENCE.length) {
    throw new Error(
      `vertical traversal event count is incomplete: ${JSON.stringify(verticalEvents)}`,
    );
  }
  for (let index = 0; index < GAMEPLAY_VERTICAL_EVENT_SEQUENCE.length; index += 1) {
    const expected = GAMEPLAY_VERTICAL_EVENT_SEQUENCE[index]!;
    const actual = verticalEvents[index]!;
    const actualEndpoint =
      actual.kind === "ladder-enter" ? actual.data?.from : actual.data?.to;
    if (
      actual.kind !== expected.kind ||
      actual.data?.ladderId !== expected.ladderId ||
      actualEndpoint !== expected.endpoint
    ) {
      throw new Error(`vertical traversal event ${index + 1} violates order or ids`);
    }
  }
  const verticalWindows = [
    [274, 275],
    [319, 320],
  ] as const;
  verticalEvents.forEach((event, index) => {
    const window = verticalWindows[index]!;
    if (event.frame < window[0] || event.frame > window[1]) {
      throw new Error(`${event.kind} frame ${event.frame} is outside traversal window`);
    }
  });
  const platformEvents = final.events.filter(
    (event) => event.kind === "platform-land" || event.kind === "platform-drop",
  );
  if (platformEvents.length !== GAMEPLAY_PLATFORM_EVENT_SEQUENCE.length) {
    throw new Error(
      `platform traversal event count is incomplete: ${JSON.stringify(platformEvents)}`,
    );
  }
  const platformWindows = [
    [145, 146],
    [153, 154],
    [195, 196],
    [210, 211],
    [230, 231],
    [255, 256],
  ] as const;
  platformEvents.forEach((event, index) => {
    const expected = GAMEPLAY_PLATFORM_EVENT_SEQUENCE[index]!;
    const window = platformWindows[index]!;
    if (
      event.kind !== expected.kind ||
      event.data?.platformId !== expected.platformId ||
      event.frame < window[0] ||
      event.frame > window[1]
    ) {
      throw new Error(`platform traversal event ${index + 1} violates graph order`);
    }
  });
  const climbSnapshots = transcript.filter(
    (snapshot) => snapshot.player?.state === "climb",
  );
  if (climbSnapshots.length === 0) throw new Error("timeline did not visibly climb");
  if (!transcript.some((snapshot) => snapshot.player?.support === "platform")) {
    throw new Error("timeline never reached platform support");
  }
  if (!transcript.some((snapshot) => snapshot.camera.scrollY < 0)) {
    throw new Error("vertical camera never followed upward");
  }
  const dropEvents = final.events.filter((event) =>
    GAMEPLAY_DROP_EVENT_SEQUENCE.some(
      (expected) => expected.kind === event.kind,
    ),
  );
  if (dropEvents.length !== GAMEPLAY_DROP_EVENT_SEQUENCE.length) {
    throw new Error(
      `readable drop traversal event count is incomplete: ${JSON.stringify(dropEvents)}`,
    );
  }
  const dropWindows = [154, 162, 165, 171, 175, 196] as const;
  dropEvents.forEach((event, index) => {
    const expected = GAMEPLAY_DROP_EVENT_SEQUENCE[index]!;
    if (
      event.kind !== expected.kind ||
      event.data?.platformId !== expected.platformId ||
      event.frame !== dropWindows[index]
    ) {
      throw new Error(`drop traversal event ${index + 1} violates choreography`);
    }
  });
  const [dropCommand, undersideClear, lowerLand, lowerSettle, recoveryLaunch, recoveryLand] =
    dropEvents;
  if (
    dropCommand!.data?.footY !== 528 ||
    dropCommand!.data?.platformBottomY !== 528 + UPPER_PLATFORM_THICKNESS ||
    undersideClear!.data?.separationAxis !== "horizontal" ||
    Number(undersideClear!.data?.playerLeft) <=
      Number(undersideClear!.data?.platformRight) ||
    Number(undersideClear!.data?.playerBottom) <=
      Number(undersideClear!.data?.playerTop) ||
    lowerLand!.data?.support !== "terrain" ||
    lowerLand!.data?.footY !== 656 ||
    lowerSettle!.data?.support !== "terrain" ||
    lowerSettle!.data?.footY !== 656 ||
    lowerSettle!.data?.stableFrames !== PLATFORM_DROP_SETTLE_FRAMES ||
    recoveryLaunch!.data?.support !== "terrain" ||
    // The recovery leaves from the height it settled at now. It used to walk
    // one column uphill first, which a terrain rise no longer permits.
    recoveryLaunch!.data?.footY !== 656 ||
    recoveryLaunch!.data?.settledFootY !== 656 ||
    recoveryLaunch!.data?.stableFrames !== PLATFORM_DROP_SETTLE_FRAMES ||
    recoveryLand!.data?.support !== "platform" ||
    recoveryLand!.data?.footY !== 528
  ) {
    throw new Error("drop traversal event geometry or support is ambiguous");
  }
  if (
    dropCommand!.frame - platformEvents[0]!.frame < 6 ||
    dropCommand!.frame - platformEvents[0]!.frame > 10 ||
    undersideClear!.frame <= dropCommand!.frame ||
    lowerLand!.frame <= undersideClear!.frame ||
    lowerSettle!.frame - lowerLand!.frame < 6 ||
    lowerSettle!.frame - lowerLand!.frame > 10 ||
    recoveryLaunch!.frame <= lowerSettle!.frame ||
    recoveryLand!.frame - recoveryLaunch!.frame < 10
  ) {
    throw new Error("drop traversal milestones are too compressed to read");
  }
  const preJump = byFrame.get(125);
  if (
    preJump?.player?.support !== "terrain" ||
    preJump.player.column !== 18 ||
    preJump.player.y !== 528
  ) {
    throw new Error("jump route did not establish the exact grounded launch state");
  }
  // Descending terrain is a fall, not a snap. The closing run crosses several
  // downward columns, and each one has to hand the player to gravity: before
  // this, the foot was pinned to whatever column it was over, so a cliff and
  // flat ground were the same walk.
  const stepOffs = final.events.filter(
    (event) => event.kind === "terrain-step-off",
  );
  if (stepOffs.length === 0) {
    throw new Error("timeline never stepped off a terrain ledge");
  }
  for (const stepOff of stepOffs) {
    const at = byFrame.get(stepOff.frame)?.player;
    const next = byFrame.get(stepOff.frame + 1)?.player;
    if (at?.support !== "air" || !next || next.y <= at.y) {
      throw new Error(
        `terrain step-off at frame ${stepOff.frame} did not fall under gravity`,
      );
    }
  }
  // The two-tile walls this route crosses are past the grounded jump's reach,
  // so the run spends real air jumps rather than demonstrating one. Each has
  // to be a genuine extension of an arc that then comes back down: gravity is
  // what separates a double jump from a hover.
  const airJumps = final.events.filter((event) => event.kind === "air-jump");
  if (airJumps.length < 2) {
    throw new Error(`expected the route to need air jumps, got ${airJumps.length}`);
  }
  for (const airJump of airJumps) {
    const before = byFrame.get(airJump.frame - 1)?.player;
    const after = byFrame.get(airJump.frame)?.player;
    // The first support the arc reaches, not a fixed lookahead: the route
    // jumps again soon after some of these, and sampling one frame later
    // would read the next launch as a failure to land.
    let landed = false;
    for (let frame = airJump.frame + 1; frame <= airJump.frame + 45; frame += 1) {
      if (byFrame.get(frame)?.player?.support !== "air") {
        landed = true;
        break;
      }
    }
    if (
      before?.support !== "air" ||
      before.airJumpsUsed !== 0 ||
      after?.support !== "air" ||
      after.airJumpsUsed !== 1 ||
      after.vy >= before.vy ||
      !landed
    ) {
      throw new Error(
        `air jump at frame ${airJump.frame} did not extend one arc and land again`,
      );
    }
  }
  // A rise is a wall the route has to climb, not a step it walks up. The run
  // meets faces it cannot walk through, and every one of them is behind it a
  // second later because a jump cleared it.
  const wallContacts = final.events.filter(
    (event) => event.kind === "terrain-step-block",
  );
  if (wallContacts.length === 0) {
    throw new Error("timeline never met a terrain wall");
  }
  for (const contact of wallContacts) {
    // Only walls the run has time to answer. One met in the closing frames has
    // nowhere to go, and demanding a climb there would pin the assertion to
    // where the capture happens to end rather than to the mechanic.
    const cleared = byFrame.get(contact.frame + 45);
    const at = byFrame.get(contact.frame)?.player;
    if (!cleared?.player || !at) continue;
    if (cleared.player.x === at.x) {
      throw new Error(
        `terrain wall at frame ${contact.frame} was never climbed`,
      );
    }
  }
  if (
    byFrame.get(154)?.player?.dropThroughPlatformId !== "tier-1-launch" ||
    byFrame.get(160)?.player?.dropThroughPlatformId !== null ||
    byFrame.get(196)?.player?.supportId !== "tier-1-launch"
  ) {
    throw new Error("drop-through ignore state did not clear before retry landing");
  }
  for (let frame = 146; frame <= 153; frame += 1) {
    const player = byFrame.get(frame)?.player;
    if (
      player?.support !== "platform" ||
      player.supportId !== "tier-1-launch" ||
      player.y !== 528 ||
      player.vy !== 0
    ) {
      throw new Error(`upper drop support did not visibly settle at frame ${frame}`);
    }
  }
  for (let frame = 165; frame <= 172; frame += 1) {
    const player = byFrame.get(frame)?.player;
    if (
      player?.support !== "terrain" ||
      player.y !== 656 ||
      player.vy !== 0 ||
      player.renderBounds.left <= 1664
    ) {
      throw new Error(`lower drop support did not visibly settle at frame ${frame}`);
    }
  }
  const phaseFrames = [
    [154, "drop-commanded", "air", 529.6666666666666],
    [162, "underside-cleared", "air", 603],
    [165, "lower-support-landed", "terrain", 656],
    [171, "lower-support-settled", "terrain", 656],
    [176, "recovery-airborne", "air", 626.3333333333334],
    [196, "recovered", "platform", 528],
  ] as const;
  for (const [frame, phase, support, footY] of phaseFrames) {
    const player = byFrame.get(frame)?.player;
    if (
      player?.dropTraversalPhase !== phase ||
      player.dropTraversalPlatformId !== "tier-1-launch" ||
      player.dropTraversalPlatformBottomY !== 560 ||
      player.support !== support ||
      !approximately(player.y, footY)
    ) {
      throw new Error(`drop traversal probe is ambiguous at frame ${frame}`);
    }
  }
  const clearPlayer = byFrame.get(162)!.player!;
  // From the opening stage's geometry, not the final snapshot: the run travels
  // through the exit portal, so by frame 900 the probe describes a different
  // world that has never heard of tier-1-launch.
  const clearPlatform = APPROVED_VERTICAL[0]!.platforms.find(
    (platform) => platform.id === "tier-1-launch",
  )!;
  if (
    clearPlayer.renderBounds.left <= clearPlatform.right ||
    clearPlayer.renderBounds.bottom <= clearPlayer.renderBounds.top ||
    byFrame.get(162)!.player!.x <= byFrame.get(161)!.player!.x ||
    (byFrame.get(176)?.player?.vy ?? 0) >= 0 ||
    // The recovery now launches off the wall face the drop left the player
    // under, one tile below the deck it used to walk back onto.
    byFrame.get(174)?.player?.support !== "terrain" ||
    byFrame.get(174)?.player?.y !== 656 ||
    byFrame.get(196)?.player?.supportId !== "tier-1-launch" ||
    byFrame.get(197)?.player?.support !== "air" ||
    byFrame.get(197)?.player?.vx !== 540
  ) {
    throw new Error("drop recovery is clipped or not separate from the jump chain");
  }
  const frame231 = byFrame.get(231);
  const frame256 = byFrame.get(256);
  const frameLadderExit = byFrame.get(320);
  if (
    frame231?.camera.scrollY !==
      GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.tierThree ||
    frame231.player?.support !== "platform" ||
    frame231.player.supportId !== "tier-3-bridge"
  ) {
    throw new Error("jump chain does not reach the exact tier-three state");
  }
  if (
    frame256?.camera.scrollY !== GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.summit ||
    frame256.player?.support !== "platform" ||
    frame256.player.supportId !== "tier-4-summit"
  ) {
    throw new Error("jump-only route does not reach the exact summit state");
  }
  if (
    frameLadderExit?.camera.scrollY !==
      GAMEPLAY_VERTICAL_CAMERA_CHECKPOINTS.recovery ||
    frameLadderExit.player?.support !== "terrain" ||
    frameLadderExit.player.y !== 592 ||
    frameLadderExit.player.climbAnimationKey !== null ||
    frameLadderExit.player.rearFacing
  ) {
    throw new Error("ladder descent does not reset on exact recovery terrain");
  }
  if (
    byFrame.get(297)?.player?.climbAnimationPaused !== true ||
    byFrame.get(300)?.player?.climbAnimationPaused !== false ||
    new Set(climbSnapshots.map((snapshot) => snapshot.player?.climbFrame)).size < 2
  ) {
    throw new Error("climb presentation does not pause and advance deterministically");
  }
  for (let frame = 30; frame <= 76; frame += 1) {
    const snapshot = byFrame.get(frame);
    if (!snapshot)
      throw new Error(`missing encounter snapshot at frame ${frame}`);
    if (
      snapshot.encounter.safeMarginPixels !==
      GAMEPLAY_AUTOMATION_ENCOUNTER.safeMarginPixels
    ) {
      throw new Error(`unexpected encounter margin at frame ${frame}`);
    }
    for (const subject of ["player", "mob", "attack"] as const) {
      assertEncounterSubjectVisible(
        frame,
        subject,
        snapshot.encounter[subject],
        snapshot.camera,
        snapshot.encounter.safeMarginPixels,
      );
    }
    if (frame >= 49 && frame < 67) {
      assertEncounterSubjectVisible(
        frame,
        "drop",
        snapshot.encounter.drop,
        snapshot.camera,
        snapshot.encounter.safeMarginPixels,
      );
    }
    if (frame >= 67) {
      assertEncounterSubjectVisible(
        frame,
        "pickup",
        snapshot.encounter.pickup,
        snapshot.camera,
        snapshot.encounter.safeMarginPixels,
      );
    }
  }
  for (const subject of ["player", "mob", "attack"] as const) {
    assertEncounterSubjectVisible(
      GAMEPLAY_POSTER_FRAME,
      `poster ${subject}`,
      poster.encounter[subject],
      poster.camera,
      poster.encounter.safeMarginPixels,
    );
  }
  const droppedItemDwell = byFrame.get(
    GAMEPLAY_EVENT_VISIBILITY_WINDOWS.drop.end + 6,
  );
  if (!droppedItemDwell || droppedItemDwell.worldItems.length !== 1) {
    throw new Error("dropped item lacks a visible dwell window before pickup");
  }
  for (const frame of [846, 870, 899]) {
    const snapshot = byFrame.get(frame);
    if (
      !snapshot?.presentation.finalActiveWindow ||
      !snapshot.player ||
      Math.abs(snapshot.player.vx) === 0
    ) {
      throw new Error(`final gameplay motion is inactive at frame ${frame}`);
    }
  }
  if (
    byFrame.get(899)?.presentation.portalAlpha ===
    byFrame.get(900)?.presentation.portalAlpha
  ) {
    throw new Error("portal presentation is inactive at the final frame");
  }
  const toggleCount = final.events.filter(
    (event) => event.kind === "inventory-toggle",
  ).length;
  if (toggleCount !== 1 || final.inventory.visible) {
    throw new Error(
      "inventory was not toggled exactly once to the hidden state",
    );
  }
  const inventoryCount = final.inventory.slots.reduce(
    (total, slot) => total + slot.count,
    0,
  );
  if (inventoryCount !== 1)
    throw new Error(`expected one inventory pickup, got ${inventoryCount}`);
  if (
    final.portals.length !== 2 ||
    final.portals[0]?.kind !== "entry" ||
    final.portals[1]?.kind !== "exit"
  ) {
    throw new Error("entry and exit portals were not both active");
  }
  const entryColumn = Math.floor(final.portals[0]!.x / 64);
  const exitColumn = Math.floor(final.portals[1]!.x / 64);
  const finalReservation = approvedVerticalFor(final).reservedColumns;
  if (
    entryColumn !== 3 ||
    exitColumn !== 196 ||
    finalReservation.has(entryColumn) ||
    finalReservation.has(exitColumn)
  ) {
    throw new Error("portal columns violate encounter/vertical reservations");
  }
  // Measured across the run, not at the final frame. Travelling through the
  // exit portal legitimately puts the camera back at the next stage's start,
  // and reading only the last frame would call a completed traversal a
  // camera that never moved.
  const farthestScrollX = Math.max(
    ...transcript.map((snapshot) => snapshot.camera.scrollX),
  );
  if (farthestScrollX <= 0)
    throw new Error("camera did not traverse the stage");
  if (
    Object.keys(run.selectedFrameHashes).length !==
    GAMEPLAY_SELECTED_FRAMES.length
  ) {
    throw new Error("selected frame hash evidence is incomplete");
  }
  for (const digest of Object.values(run.selectedFrameHashes)) {
    if (!digest.match(/^[0-9a-f]{64}$/))
      throw new Error("invalid selected frame digest");
  }
}

async function waitForProbe(
  page: Page,
  signal?: AbortSignal,
): Promise<GameplayAutomationSnapshot> {
  await abortable(
    page.waitForFunction(
      () => {
        const probe = window.__stageGenGameplayProbe;
        return probe?.ready === true || probe?.state === "error";
      },
      undefined,
      { timeout: PROBE_TIMEOUT_MS },
    ),
    signal,
    "gameplay probe wait",
  );
  return await abortable(
    page.evaluate(() => {
      const probe = window.__stageGenGameplayProbe;
      if (!probe) throw new Error("gameplay probe is missing");
      return probe;
    }),
    signal,
    "gameplay probe read",
  );
}

async function runOnce(
  browser: Browser,
  baseUrl: string,
  route: string,
  options: Readonly<{
    timeline: readonly GameplayFrame[];
    selectedFrames: readonly number[];
    frameDirectory?: string;
    validate?: (run: GameplayRunEvidence) => void;
    validateSnapshot?: GameplaySnapshotValidator;
    signal?: AbortSignal;
    deviceScaleFactor?: number;
  }>,
): Promise<GameplayRunEvidence> {
  const {
    timeline,
    selectedFrames,
    frameDirectory,
    validate,
    validateSnapshot = assertSnapshotContract,
    signal,
    deviceScaleFactor = 1,
  } = options;
  if (![1, 2, 3, 4].includes(deviceScaleFactor)) {
    throw new Error("gameplay device scale factor must be 1, 2, 3, or 4");
  }
  throwIfAborted(signal, "gameplay browser run");
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor,
    locale: "en-US",
    timezoneId: "UTC",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const browserErrors: string[] = [];
  page.on("pageerror", (error) =>
    browserErrors.push(`pageerror:${error.message}`),
  );
  page.on("console", (message) => {
    if (message.type() === "error")
      browserErrors.push(`console:${message.text()}`);
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText === "net::ERR_ABORTED") return;
    const pathname = new URL(request.url()).pathname;
    browserErrors.push(
      `request:${pathname}:${request.failure()?.errorText ?? "failed"}`,
    );
  });

  try {
    const response = await abortable(
      page.goto(`${baseUrl}${route}`, {
        waitUntil: "domcontentloaded",
        timeout: PROBE_TIMEOUT_MS,
      }),
      signal,
      "gameplay navigation",
    );
    if (!response?.ok())
      throw new Error(`preview route returned HTTP ${response?.status() ?? 0}`);
    const initial = await waitForProbe(page, signal);
    validateSnapshot(initial);
    if (initial.frame !== 0 || initial.simulationMs !== 0) {
      throw new Error("gameplay probe did not start at frame zero");
    }
    const visiblePlatformElevations = new Set(
      initial.platforms
        .filter((platform) => platform.visible)
        .map((platform) => platform.deckY),
    );
    if (
      visiblePlatformElevations.size < 3 ||
      !initial.climbables.some((ladder) => ladder.visible)
    ) {
      throw new Error(
        "initial gameplay composition must show at least three tiers and one ladder",
      );
    }
    const canvas = page.locator("canvas").first();
    await abortable(
      canvas.waitFor({ state: "visible", timeout: PROBE_TIMEOUT_MS }),
      signal,
      "gameplay canvas wait",
    );
    const bounds = await abortable(
      canvas.boundingBox(),
      signal,
      "gameplay canvas bounds",
    );
    if (!bounds || bounds.width !== 1280 || bounds.height !== 720) {
      throw new Error(
        `gameplay canvas is not 1280x720 (${bounds?.width}x${bounds?.height})`,
      );
    }

    const transcript: string[] = [];
    const states = new Set<string>();
    const selected = new Set<number>(selectedFrames);
    const selectedFrameHashes: Record<string, string> = {};
    let snapshot = initial;
    for (const frame of timeline) {
      throwIfAborted(signal, `gameplay frame ${frame.index + 1}`);
      for (const action of frame.actions) {
        if (action.type === "down") {
          await abortable(
            page.keyboard.down(action.key),
            signal,
            `gameplay frame ${frame.index + 1}`,
          );
        } else {
          await abortable(
            page.keyboard.up(action.key),
            signal,
            `gameplay frame ${frame.index + 1}`,
          );
        }
      }
      snapshot = await abortable(
        page.evaluate(async () => {
          const advance = window.__stageGenAdvanceGameplayFrame;
          if (!advance) throw new Error("gameplay frame hook is missing");
          return await advance();
        }),
        signal,
        `gameplay frame ${frame.index + 1}`,
      );
      if (snapshot.frame !== frame.index + 1) {
        throw new Error(
          `gameplay frame skipped from ${frame.index} to ${snapshot.frame}`,
        );
      }
      validateSnapshot(snapshot);
      if (snapshot.player) states.add(snapshot.player.state);
      transcript.push(transcriptLine(snapshot));
      if (selected.has(snapshot.frame) || frameDirectory) {
        const framePng = await abortable(
          canvas.screenshot({ type: "png" }),
          signal,
          `gameplay frame ${snapshot.frame} screenshot`,
        );
        if (selected.has(snapshot.frame)) {
          selectedFrameHashes[String(snapshot.frame)] = sha256(framePng);
        }
        if (frameDirectory) {
          const frameName = `frame-${String(snapshot.frame).padStart(4, "0")}.png`;
          await fs.writeFile(path.join(frameDirectory, frameName), framePng, {
            flag: "wx",
            mode: 0o600,
          });
        }
      }
    }
    if (browserErrors.length > 0) {
      throw new Error(
        `browser reported ${browserErrors.length} error(s): ${browserErrors.join(" | ")}`,
      );
    }
    const transcriptText = `${transcript.join("\n")}\n`;
    const result = Object.freeze({
      transcript: transcriptText,
      transcriptDigest: sha256(transcriptText),
      selectedFrameHashes: Object.freeze({ ...selectedFrameHashes }),
      states: Object.freeze([...states].sort()),
      finalSnapshot: snapshot,
    });
    if (snapshot.frame !== timeline.length) {
      throw new Error(
        `expected frame ${timeline.length}, got ${snapshot.frame}`,
      );
    }
    if (
      Math.abs(snapshot.simulationMs - timeline.length * GAMEPLAY_STEP_MS) >
      1e-7
    ) {
      throw new Error(
        `unexpected simulation duration: ${snapshot.simulationMs}`,
      );
    }
    if (Object.keys(selectedFrameHashes).length !== selected.size) {
      throw new Error("selected frame hash evidence is incomplete");
    }
    validate?.(result);
    return result;
  } finally {
    await context.close();
  }
}

async function verifyForegroundDprMatrix(
  browser: Browser,
  baseUrl: string,
  route: string,
  timeline: readonly GameplayFrame[],
  signal?: AbortSignal,
): Promise<readonly number[]> {
  const matrix = [1, 2, 3, 4] as const;
  const focusedTimeline = timeline.slice(0, 315);
  for (const deviceScaleFactor of matrix.slice(1)) {
    await runOnce(browser, baseUrl, route, {
      timeline: focusedTimeline,
      selectedFrames: [],
      deviceScaleFactor,
      signal,
      validate: (run) => {
        const snapshots = run.transcript
          .trimEnd()
          .split("\n")
          .map(
            (line) =>
              JSON.parse(line) as {
                frame: number;
                camera: GameplayAutomationSnapshot["camera"];
                layers: GameplayAutomationSnapshot["layers"];
                presentation: GameplayAutomationSnapshot["presentation"];
              },
          );
        assertGameplayForegroundMotion(snapshots);
        for (const snapshot of snapshots) {
          const foreground = snapshot.layers[0]?.foreground;
          if (foreground?.devicePixelRatio !== deviceScaleFactor) {
            throw new Error(
              `foreground DPR ${deviceScaleFactor} live readback is missing at frame ${snapshot.frame}`,
            );
          }
        }
        const byFrame = new Map(
          snapshots.map((snapshot) => [snapshot.frame, snapshot]),
        );
        const visibleStart = byFrame.get(81)!;
        const summit = byFrame.get(256)!;
        const startForeground = visibleStart.layers[0]!.foreground!;
        const summitForeground = summit.layers[0]!.foreground!;
        if (
          !visibleStart.presentation.foregroundVisible ||
          summit.camera.scrollY >= 0 ||
          Math.abs(
            startForeground.contactScreenY - FOREGROUND_CONTACT_SCREEN_Y,
          ) >
            0.5 / deviceScaleFactor + 1e-6 ||
          Math.abs(
            summitForeground.contactScreenY - FOREGROUND_CONTACT_SCREEN_Y,
          ) >
            0.5 / deviceScaleFactor + 1e-6 ||
          Math.abs(
            summitForeground.projectedCameraTravelScreenPx -
              startForeground.projectedCameraTravelScreenPx,
          ) <= summitForeground.seamPeriodScreenPx
        ) {
          throw new Error(
            `foreground DPR ${deviceScaleFactor} did not prove visible motion, vertical anchoring, and repeat re-entry`,
          );
        }
      },
    });
  }
  return Object.freeze([...matrix]);
}

export type GameplaySessionEvidence = Readonly<{
  fixtureDigest: string;
  fixtureTag: string;
  first: GameplayRunEvidence;
  chromiumVersion: string;
  duplicateVerified: boolean;
  foregroundDprVerified: readonly number[];
}>;

function compareRuns(
  first: GameplayRunEvidence,
  second: GameplayRunEvidence,
): void {
  if (first.transcript !== second.transcript) {
    throw new Error(
      `gameplay transcript is nondeterministic at ${transcriptDifference(
        first.transcript,
        second.transcript,
      )} (${first.transcriptDigest} != ${second.transcriptDigest})`,
    );
  }
  if (
    JSON.stringify(first.selectedFrameHashes) !==
    JSON.stringify(second.selectedFrameHashes)
  ) {
    throw new Error("selected gameplay frame hashes are nondeterministic");
  }
}

export type GameplaySessionOptions = Readonly<{
  prepareFixture: (workspace: string) => Promise<GameplayFixture>;
  timeline: readonly GameplayFrame[];
  selectedFrames: readonly number[];
  captureFrames?: boolean;
  verifyDuplicate?: boolean;
  validateRun?: (run: GameplayRunEvidence) => void;
  validateSnapshot?: GameplaySnapshotValidator;
  verifyForegroundDpr?: boolean;
  applicationRoot?: string;
  validateApplication?: () => Promise<void>;
  signal?: AbortSignal;
}>;

export async function withGameplaySession<T>(
  options: GameplaySessionOptions,
  operation: (
    evidence: GameplaySessionEvidence,
    workspace: string,
  ) => Promise<T> | T,
): Promise<T> {
  if (options.timeline.length === 0) {
    throw new Error("gameplay timeline must not be empty");
  }
  for (let index = 0; index < options.timeline.length; index += 1) {
    if (options.timeline[index]?.index !== index) {
      throw new Error("gameplay timeline indices must be contiguous from zero");
    }
  }
  if (
    options.selectedFrames.length === 0 ||
    new Set(options.selectedFrames).size !== options.selectedFrames.length ||
    options.selectedFrames.some(
      (frame) =>
        !Number.isSafeInteger(frame) ||
        frame < 1 ||
        frame > options.timeline.length,
    )
  ) {
    throw new Error("selected gameplay frames must be unique timeline frames");
  }
  throwIfAborted(options.signal, "gameplay session");
  // Resolved, because the server this workspace feeds refuses an output root that traverses a
  // symlink and macOS hands out `/var/folders/...`, where `/var` is one. Without the realpath the
  // run reads as "Next server did not become ready", since every request the readiness poll makes
  // is answered with a confinement error the poll never sees.
  const workspace = await fs.realpath(
    await fs.mkdtemp(path.join(tmpdir(), "stage-gen-gameplay-")),
  );
  let server: StartedServer | undefined;
  let browser: Browser | undefined;
  return await runWithGameplayCleanups(async () => {
    throwIfAborted(options.signal, "gameplay fixture preparation");
    const fixture = await options.prepareFixture(workspace);
    throwIfAborted(options.signal, "gameplay server startup");
    await options.validateApplication?.();
    server = await startNextServer(
      fixture.outRoot,
      options.signal,
      options.applicationRoot,
    );
    browser = await acquireAbortableGameplayResource(
      chromium.launch({ headless: true, timeout: PROBE_TIMEOUT_MS }),
      options.signal,
      "Chromium launch",
      async (launched) => await launched.close(),
    );
    const frameDirectory = options.captureFrames
      ? path.join(workspace, "frames")
      : undefined;
    if (frameDirectory) await fs.mkdir(frameDirectory, { mode: 0o700 });
    const first = await runOnce(browser, server.baseUrl, fixture.route, {
      timeline: options.timeline,
      selectedFrames: options.selectedFrames,
      frameDirectory,
      validate: options.validateRun,
      validateSnapshot: options.validateSnapshot,
      signal: options.signal,
    });
    if (options.verifyDuplicate ?? true) {
      const second = await runOnce(browser, server.baseUrl, fixture.route, {
        timeline: options.timeline,
        selectedFrames: options.selectedFrames,
        validate: options.validateRun,
        validateSnapshot: options.validateSnapshot,
        signal: options.signal,
      });
      compareRuns(first, second);
    }
    const foregroundDprVerified =
      options.verifyForegroundDpr === false
        ? Object.freeze([] as number[])
        : await verifyForegroundDprMatrix(
            browser,
            server.baseUrl,
            fixture.route,
            options.timeline,
            options.signal,
          );
    return await operation(
      Object.freeze({
        fixtureDigest: fixture.digest,
        fixtureTag: fixture.tag,
        first,
        chromiumVersion: browser.version(),
        duplicateVerified: options.verifyDuplicate ?? true,
        foregroundDprVerified,
      }),
      workspace,
    );
  }, [
    { name: "browser", run: async () => await browser?.close() },
    { name: "server", run: async () => await server?.stop() },
    {
      name: "workspace",
      run: async () => await fs.rm(workspace, { recursive: true, force: true }),
    },
  ]);
}

export const PLAYER_HURT_FRAME_COUNT = 40;
export const PLAYER_HURT_EVENT_FRAME = 12;
export const PLAYER_HURT_LAST_REACTION_FRAME = 29;
export const PLAYER_HURT_RECOVERY_FRAME = 30;

const PLAYER_HURT_ACTIONS = new Map<
  number,
  readonly GameplayFrame["actions"][number][]
>([
  // The mob's committed strike lands on frame 12. Hold left two frames later: knockback points
  // right, so a negative velocity during hurt proves that hit feedback does not stun the player.
  [13, Object.freeze([{ type: "down", key: "ArrowLeft" } as const])],
  [34, Object.freeze([{ type: "up", key: "ArrowLeft" } as const])],
]);

export const PLAYER_HURT_TIMELINE: readonly GameplayFrame[] = Object.freeze(
  Array.from({ length: PLAYER_HURT_FRAME_COUNT }, (_, index) =>
    Object.freeze({
      index,
      actions: PLAYER_HURT_ACTIONS.get(index) ?? Object.freeze([]),
    }),
  ),
);

function assertPlayerHurtSnapshotContract(
  snapshot: GameplayAutomationSnapshot,
): void {
  if (!snapshot.ready || snapshot.state !== "ready") {
    throw new Error(`player-hurt probe is not ready (${snapshot.state})`);
  }
  if (snapshot.errors.length > 0 || snapshot.diagnostics.length > 0) {
    throw new Error(
      `player-hurt probe reported errors or diagnostics: ${[
        ...snapshot.errors,
        ...snapshot.diagnostics,
      ].join(" | ")}`,
    );
  }
  if (!snapshot.player) throw new Error("player-hurt probe has no player");
  if (
    !snapshot.combatText ||
    !snapshot.combatText.enabled ||
    snapshot.combatText.disposed
  ) {
    throw new Error("player-hurt probe has no active default-on combat text system");
  }
  const currentHurt = snapshot.events.find(
    (event) => event.kind === "player-hurt" && event.frame === snapshot.frame,
  );
  if (currentHurt) {
    const entry = snapshot.combatText.entries.at(-1);
    if (
      !entry ||
      entry.direction !== "incoming" ||
      entry.amount !== currentHurt.data?.damage ||
      entry.text !== String(currentHurt.data?.damage)
    ) {
      throw new Error("connected player hit did not publish matching incoming combat text");
    }
  }
  if (
    snapshot.frame === PLAYER_HURT_EVENT_FRAME + 20 &&
    snapshot.combatText.activeCount !== 0
  ) {
    throw new Error("incoming combat text did not expire on its fixed simulation clock");
  }
  const actualAssets = [...snapshot.assetKeys].sort();
  if (
    JSON.stringify(actualAssets) !==
    JSON.stringify(SYNTHETIC_GAMEPLAY_REQUIRED_ASSET_KEYS)
  ) {
    throw new Error("player-hurt probe asset keys do not match the synthetic contract");
  }
}

type PlayerHurtTranscriptSnapshot = Readonly<{
  frame: number;
  player: GameplayAutomationSnapshot["player"];
  events: GameplayAutomationSnapshot["events"];
}>;

export function validatePlayerHurtRun(run: GameplayRunEvidence): void {
  const snapshots = run.transcript
    .trimEnd()
    .split("\n")
    .map((line) => JSON.parse(line) as PlayerHurtTranscriptSnapshot);
  const byFrame = new Map(snapshots.map((snapshot) => [snapshot.frame, snapshot]));
  if (
    snapshots.length !== PLAYER_HURT_FRAME_COUNT ||
    run.finalSnapshot.frame !== PLAYER_HURT_FRAME_COUNT
  ) {
    throw new Error("player-hurt transcript has the wrong frame count");
  }
  const hurtEvents = run.finalSnapshot.events.filter(
    (event) => event.kind === "player-hurt",
  );
  const hurtEvent = hurtEvents[0];
  if (
    hurtEvents.length !== 1 ||
    hurtEvent?.frame !== PLAYER_HURT_EVENT_FRAME ||
    hurtEvent.data?.damage !== 1 ||
    hurtEvent.data?.hpLeft !== 5
  ) {
    throw new Error("player-hurt event is not the one deterministic connected blow");
  }
  const hit = byFrame.get(PLAYER_HURT_EVENT_FRAME)?.player;
  if (
    hit?.state !== "hurt" ||
    hit.hp !== 5 ||
    hit.maxHp !== 6 ||
    !hit.invulnerable ||
    hit.facing !== "left" ||
    hit.vx <= 0
  ) {
    throw new Error("connected blow did not synchronously enter player hurt");
  }
  for (
    let frame = PLAYER_HURT_EVENT_FRAME;
    frame <= PLAYER_HURT_LAST_REACTION_FRAME;
    frame += 1
  ) {
    const player = byFrame.get(frame)?.player;
    if (player?.state !== "hurt") {
      throw new Error(`player hurt ended early at frame ${frame}`);
    }
    if (frame >= 14 && player.vx >= 0) {
      throw new Error(`held movement was blocked during player hurt at frame ${frame}`);
    }
  }
  const beforeRecovery = byFrame.get(PLAYER_HURT_LAST_REACTION_FRAME)?.player;
  const recovered = byFrame.get(PLAYER_HURT_RECOVERY_FRAME)?.player;
  if (
    !beforeRecovery ||
    !recovered ||
    recovered.state === "hurt" ||
    recovered.hp !== 5 ||
    recovered.vx >= 0 ||
    recovered.x > beforeRecovery.x
  ) {
    throw new Error("player did not leave hurt while retaining held movement");
  }
  const released = byFrame.get(35)?.player;
  if (!released || released.state !== "idle" || released.vx !== 0) {
    throw new Error("player did not return to idle after the held input was released");
  }
  if (!run.states.includes("hurt")) {
    throw new Error("player-hurt transcript did not publish the hurt state");
  }
}

export type PlayerHurtVerification = Readonly<{
  version: typeof GAMEPLAY_AUTOMATION_VERSION;
  verdict: "pass";
  frameCount: typeof PLAYER_HURT_FRAME_COUNT;
  fixtureDigest: string;
  transcriptDigest: string;
  eventFrame: typeof PLAYER_HURT_EVENT_FRAME;
  recoveryFrame: typeof PLAYER_HURT_RECOVERY_FRAME;
  duplicateVerified: true;
}>;

export async function verifyDeterministicPlayerHurtGameplay(): Promise<PlayerHurtVerification> {
  return await withGameplaySession(
    {
      prepareFixture: async (workspace) =>
        await generateGameplayFixture(path.join(workspace, "out")),
      timeline: PLAYER_HURT_TIMELINE,
      selectedFrames: [12, 14, 24, 30, 35],
      verifyDuplicate: true,
      validateRun: validatePlayerHurtRun,
      validateSnapshot: assertPlayerHurtSnapshotContract,
      verifyForegroundDpr: false,
    },
    (evidence) =>
      Object.freeze({
        version: GAMEPLAY_AUTOMATION_VERSION,
        verdict: "pass" as const,
        frameCount: PLAYER_HURT_FRAME_COUNT,
        fixtureDigest: evidence.fixtureDigest,
        transcriptDigest: evidence.first.transcriptDigest,
        eventFrame: PLAYER_HURT_EVENT_FRAME,
        recoveryFrame: PLAYER_HURT_RECOVERY_FRAME,
        duplicateVerified: true as const,
      }),
  );
}

type VerifiedGameplay = GameplaySessionEvidence;

async function withVerifiedGameplay<T>(
  operation: (evidence: VerifiedGameplay, workspace: string) => Promise<T> | T,
  captureFrames = false,
): Promise<T> {
  return await withGameplaySession(
    {
      prepareFixture: async (workspace) =>
        await generateApprovedModelGameplayFixture(path.join(workspace, "out")),
      timeline: GAMEPLAY_TIMELINE,
      selectedFrames: GAMEPLAY_SELECTED_FRAMES,
      captureFrames,
      verifyDuplicate: true,
      validateRun: validateGameplayRun,
    },
    operation,
  );
}

export type GameplayCleanupStep = Readonly<{
  name: string;
  run: () => Promise<void> | void;
}>;

export async function runWithGameplayCleanups<T>(
  operation: () => Promise<T> | T,
  cleanups: readonly GameplayCleanupStep[],
): Promise<T> {
  let operationSucceeded = false;
  let result!: T;
  let primaryError: unknown;
  try {
    result = await operation();
    operationSucceeded = true;
  } catch (error) {
    primaryError = error;
  }

  const settled = await Promise.allSettled(
    cleanups.map(async (cleanup) => await cleanup.run()),
  );
  const cleanupFailures = settled.flatMap((outcome, index) =>
    outcome.status === "rejected"
      ? [{ name: cleanups[index]!.name, reason: outcome.reason as unknown }]
      : [],
  );
  if (!operationSucceeded) {
    if (cleanupFailures.length > 0) {
      throw new AggregateError(
        [primaryError, ...cleanupFailures.map((failure) => failure.reason)],
        `gameplay operation failed and cleanup failed: ${cleanupFailures
          .map((failure) => failure.name)
          .join(", ")}`,
        { cause: primaryError },
      );
    }
    throw primaryError;
  }
  if (cleanupFailures.length > 0) {
    throw new AggregateError(
      cleanupFailures.map((failure) => failure.reason),
      `gameplay cleanup failed: ${cleanupFailures
        .map((failure) => failure.name)
        .join(", ")}`,
    );
  }
  return result;
}

function verificationFrom(evidence: VerifiedGameplay): GameplayVerification {
  return Object.freeze({
    version: GAMEPLAY_AUTOMATION_VERSION,
    verdict: "pass",
    frameCount: GAMEPLAY_FRAME_COUNT,
    durationSeconds: GAMEPLAY_DURATION_SECONDS,
    fixtureDigest: evidence.fixtureDigest,
    transcriptDigest: evidence.first.transcriptDigest,
    selectedFrameHashes: evidence.first.selectedFrameHashes,
    eventFrames: Object.freeze(
      Object.fromEntries(
        GAMEPLAY_REQUIRED_EVENTS.map((kind) => [
          kind,
          evidence.first.finalSnapshot.events.find(
            (event) => event.kind === kind,
          )!.frame,
        ]),
      ),
    ),
  });
}

export async function verifyDeterministicGameplay(): Promise<GameplayVerification> {
  const verification = await withVerifiedGameplay((evidence) =>
    verificationFrom(evidence),
  );
  await verifyDeterministicPlayerHurtGameplay();
  return verification;
}

type Mp4Probe = Readonly<{
  container: "mp4";
  video_codec: "h264";
  pixel_format: "yuv420p";
  width: 1280;
  height: 720;
  frame_rate: 30;
  duration_seconds: number;
  fast_start: true;
  audio_codec: null;
}>;

type ToolResult = Readonly<{ stdout: string; stderr: string }>;

export type ToolRunOptions = Readonly<{
  timeoutMs?: number;
  terminateGraceMs?: number;
  signal?: AbortSignal;
  cwd?: string;
}>;

type ToolChild = ChildProcessByStdio<null, Readable, Readable>;
type ToolClose = Readonly<{
  code: number | null;
  signal: NodeJS.Signals | null;
}>;
type ToolOutcome =
  | Readonly<{ kind: "close"; close: ToolClose }>
  | Readonly<{ kind: "timeout" }>
  | Readonly<{ kind: "cancelled" }>
  | Readonly<{ kind: "error"; error: Error }>;

function boundedAppend(current: string, chunk: Buffer | string): string {
  return `${current}${chunk.toString()}`.slice(-MAX_TOOL_OUTPUT_CHARS);
}

function sanitizedToolDiagnostic(value: string): string {
  let sanitized = value.replace(
    /\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD))\s*[:=]\s*[^\s]+/gi,
    "$1=<redacted>",
  );
  for (const root of [REPO_ROOT, WEB_ROOT, tmpdir(), process.env.HOME].filter(
    (candidate): candidate is string => Boolean(candidate),
  )) {
    sanitized = sanitized.split(root).join("<path>");
  }
  sanitized = sanitized
    .replace(/(?:[A-Za-z]:\\|\/)(?:[^\s'"`]+[\\/])*[^\s'"`]*/g, "<path>")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "?")
    .trim();
  if (sanitized.length <= MAX_TOOL_DIAGNOSTIC_CHARS) return sanitized;
  return `…${sanitized.slice(-(MAX_TOOL_DIAGNOSTIC_CHARS - 1))}`;
}

function toolDiagnostic(stderr: string, stdout: string, error?: Error): string {
  const detail = sanitizedToolDiagnostic(
    [error?.message, stderr, stdout]
      .filter((value) => Boolean(value))
      .join("\n"),
  );
  return detail ? `: ${detail}` : "";
}

function sendToolSignal(child: ToolChild, signal: NodeJS.Signals): void {
  if (process.platform !== "win32" && child.pid !== undefined) {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ESRCH") {
        child.kill(signal);
        return;
      }
    }
  }
  if (child.exitCode === null && child.signalCode === null) child.kill(signal);
}

async function closesWithin(
  close: Promise<ToolClose>,
  timeoutMs: number,
): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<false>((resolve) => {
    timer = setTimeout(() => resolve(false), timeoutMs);
  });
  const result = await Promise.race([close.then(() => true), deadline]);
  if (timer) clearTimeout(timer);
  return result;
}

async function terminateAndReapTool(
  child: ToolChild,
  close: Promise<ToolClose>,
  terminateGraceMs: number,
): Promise<void> {
  sendToolSignal(child, "SIGTERM");
  if (!(await closesWithin(close, terminateGraceMs))) {
    sendToolSignal(child, "SIGKILL");
  }
  await close;
}

function positiveTimeout(
  value: number | undefined,
  fallback: number,
  maximum: number,
  name: string,
): number {
  const resolved = value ?? fallback;
  if (!Number.isSafeInteger(resolved) || resolved <= 0 || resolved > maximum) {
    throw new Error(
      `${name} must be a positive integer no larger than ${maximum}`,
    );
  }
  return resolved;
}

export async function runTool(
  executable: string,
  args: readonly string[],
  options: ToolRunOptions = {},
): Promise<ToolResult> {
  const name = path.basename(executable) || "media tool";
  const timeoutMs = positiveTimeout(
    options.timeoutMs,
    FFMPEG_TIMEOUT_MS,
    MAX_TOOL_TIMEOUT_MS,
    "tool timeout",
  );
  const terminateGraceMs = positiveTimeout(
    options.terminateGraceMs,
    TOOL_TERMINATE_GRACE_MS,
    MAX_TOOL_TERMINATE_GRACE_MS,
    "tool termination grace",
  );
  if (options.signal?.aborted)
    throw new Error(`${name} was cancelled before launch`);
  const workingDirectory = path.resolve(options.cwd ?? WEB_ROOT);
  const workingDirectoryStat = await fs.lstat(workingDirectory).catch(() => {
    throw new Error(`${name} working directory must be a real directory`);
  });
  if (
    !workingDirectoryStat.isDirectory() ||
    workingDirectoryStat.isSymbolicLink() ||
    (await fs.realpath(workingDirectory)) !== workingDirectory
  ) {
    throw new Error(`${name} working directory must be a real directory`);
  }
  let child: ToolChild;
  try {
    child = spawn(executable, [...args], {
      cwd: workingDirectory,
      env: safeServerEnvironment(path.join(WEB_ROOT, "out")),
      detached: process.platform !== "win32",
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    throw new Error(`${name} failed${toolDiagnostic("", "", error as Error)}`);
  }
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk: Buffer) => {
    stdout = boundedAppend(stdout, chunk);
  });
  child.stderr.on("data", (chunk: Buffer) => {
    stderr = boundedAppend(stderr, chunk);
  });

  const close = new Promise<ToolClose>((resolve) => {
    child.once("close", (code, signal) => resolve({ code, signal }));
  });
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let abortListener: (() => void) | undefined;
  const outcome = await new Promise<ToolOutcome>((resolve) => {
    child.once("close", (code, signal) =>
      resolve({ kind: "close", close: { code, signal } }),
    );
    child.once("error", (error) => resolve({ kind: "error", error }));
    child.stdout.once("error", (error) => resolve({ kind: "error", error }));
    child.stderr.once("error", (error) => resolve({ kind: "error", error }));
    timeout = setTimeout(() => resolve({ kind: "timeout" }), timeoutMs);
    if (options.signal) {
      abortListener = () => resolve({ kind: "cancelled" });
      if (options.signal.aborted) abortListener();
      else
        options.signal.addEventListener("abort", abortListener, { once: true });
    }
  });
  if (timeout) clearTimeout(timeout);
  if (options.signal && abortListener) {
    options.signal.removeEventListener("abort", abortListener);
  }

  if (outcome.kind !== "close") {
    await terminateAndReapTool(child, close, terminateGraceMs);
    if (outcome.kind === "timeout") {
      throw new Error(
        `${name} timed out after ${timeoutMs}ms${toolDiagnostic(stderr, stdout)}`,
      );
    }
    if (outcome.kind === "cancelled") {
      throw new Error(`${name} was cancelled${toolDiagnostic(stderr, stdout)}`);
    }
    throw new Error(
      `${name} failed${toolDiagnostic(stderr, stdout, outcome.error)}`,
    );
  }

  const { code, signal } = outcome.close;
  if (signal) {
    throw new Error(
      `${name} terminated by ${signal}${toolDiagnostic(stderr, stdout)}`,
    );
  }
  if (code !== 0) {
    throw new Error(
      `${name} exited ${code ?? 1}${toolDiagnostic(stderr, stdout)}`,
    );
  }
  return Object.freeze({ stdout, stderr });
}

function canonicalFraction(value: unknown): number {
  if (typeof value !== "string") {
    throw new Error("ffprobe returned an invalid frame rate");
  }
  const match = /^([1-9]\d*)\/([1-9]\d*)$/.exec(value);
  if (!match) throw new Error("ffprobe returned an invalid frame rate");
  const numerator = Number(match[1]);
  const denominator = Number(match[2]);
  if (!Number.isSafeInteger(numerator) || !Number.isSafeInteger(denominator)) {
    throw new Error("ffprobe returned an invalid frame rate");
  }
  const result = numerator / denominator;
  if (!Number.isFinite(result))
    throw new Error("ffprobe returned an invalid frame rate");
  return result;
}

function canonicalDecimal(value: unknown, field: "duration" | "size"): number {
  if (typeof value !== "string") {
    throw new Error(`ffprobe returned an invalid ${field}`);
  }
  const pattern =
    field === "duration" ? /^(?:0|[1-9]\d*)(?:\.\d+)?$/ : /^[1-9]\d*$/;
  if (!pattern.test(value))
    throw new Error(`ffprobe returned an invalid ${field}`);
  const result = Number(value);
  if (
    !Number.isFinite(result) ||
    (field === "size" && !Number.isSafeInteger(result))
  ) {
    throw new Error(`ffprobe returned an invalid ${field}`);
  }
  return result;
}

export function validateGameplayMp4Probe(value: unknown): Mp4Probe {
  if (!value || typeof value !== "object")
    throw new Error("ffprobe result must be an object");
  const record = value as {
    format?: { format_name?: string; duration?: string; size?: string };
    streams?: {
      codec_type?: string;
      codec_name?: string;
      pix_fmt?: string;
      width?: number;
      height?: number;
      avg_frame_rate?: string;
    }[];
  };
  const video = record.streams?.find((stream) => stream.codec_type === "video");
  const audio = record.streams?.find((stream) => stream.codec_type === "audio");
  const duration = canonicalDecimal(record.format?.duration, "duration");
  const size = canonicalDecimal(record.format?.size, "size");
  const frameRate = canonicalFraction(video?.avg_frame_rate);
  if (!record.format?.format_name?.split(",").includes("mp4")) {
    throw new Error("capture container is not MP4");
  }
  if (video?.codec_name !== "h264" || video.pix_fmt !== "yuv420p") {
    throw new Error("capture must use H.264 with yuv420p pixels");
  }
  if (
    video.width !== 1280 ||
    video.height !== 720 ||
    Math.abs(frameRate - 30) > 1e-7
  ) {
    throw new Error("capture must be exactly 1280x720 at 30 fps");
  }
  if (!Number.isFinite(duration) || Math.abs(duration - 30) > 0.05) {
    throw new Error("capture duration must be 30 seconds");
  }
  if (!Number.isSafeInteger(size) || size <= 0 || size > 10_000_000) {
    throw new Error("capture must be nonempty and no larger than 10 MB");
  }
  if (audio) throw new Error("capture must not contain an audio stream");
  return Object.freeze({
    container: "mp4",
    video_codec: "h264",
    pixel_format: "yuv420p",
    width: 1280,
    height: 720,
    frame_rate: 30,
    duration_seconds: duration,
    fast_start: true,
    audio_codec: null,
  });
}

export function resolveGameplayCapturePath(requested: string): string {
  if (!requested || requested.includes("\0"))
    throw new Error("capture path is required");
  if (requested !== CAPTURE_VIDEO_PATH) {
    throw new Error(`capture path must be exactly ${CAPTURE_VIDEO_PATH}`);
  }
  return path.join(REPO_ROOT, ...CAPTURE_VIDEO_PATH.split("/"));
}

async function contentReference(
  repositoryPath: string,
): Promise<{ path: string; sha256: string; bytes: number }> {
  const sourcePath = path.join(REPO_ROOT, ...repositoryPath.split("/"));
  const stat = await fs.lstat(sourcePath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size <= 0) {
    throw new Error(
      `${path.basename(repositoryPath)} must be a nonempty regular file`,
    );
  }
  const bytes = await fs.readFile(sourcePath);
  return {
    path: repositoryPath,
    sha256: sha256(bytes),
    bytes: bytes.byteLength,
  };
}

export async function modelAssetBundleReference(): Promise<{
  count: 20;
  aggregate: { algorithm: string; lineFormat: string; sha256: string };
  assets: readonly {
    id: string;
    path: string;
    sha256: string;
    bytes: number;
  }[];
}> {
  const assets = await Promise.all(
    GAMEPLAY_MODEL_ASSET_CONTRACTS.map(async (contract) => {
      const repositoryPath = `fixtures/gameplay-demo/${contract.path}`;
      const reference = await contentReference(repositoryPath);
      return Object.freeze({ id: contract.id, ...reference });
    }),
  );
  assets.sort((left, right) => left.path.localeCompare(right.path));
  const aggregateBytes = Buffer.from(
    assets.map((asset) => `${asset.sha256}  ${asset.path}\n`).join(""),
    "utf8",
  );
  const aggregateSha256 = sha256(aggregateBytes);
  if (aggregateSha256 !== MODEL_ASSET_AGGREGATE_SHA256) {
    throw new Error(
      "approved model-asset aggregate does not match the frozen producer set",
    );
  }
  return Object.freeze({
    count: 20,
    aggregate: Object.freeze({
      algorithm: "sha256-of-shasum-lines-v1",
      lineFormat:
        "<sha256><two-spaces><repository-relative-path><newline>; filename-sorted",
      sha256: aggregateSha256,
    }),
    assets: Object.freeze(assets),
  });
}

export function validatePosterPng(bytes: Buffer): void {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  if (bytes.byteLength > 5_000_000)
    throw new Error("poster must be no larger than 5 MB");
  if (
    bytes.byteLength < 33 ||
    !bytes.subarray(0, 8).equals(signature) ||
    bytes.readUInt32BE(16) !== 1280 ||
    bytes.readUInt32BE(20) !== 720
  ) {
    throw new Error("poster must be a valid 1280x720 PNG");
  }
  let decoded: ReturnType<typeof PNG.sync.read>;
  try {
    decoded = PNG.sync.read(bytes, { checkCRC: true, skipRescale: false });
  } catch {
    throw new Error("poster must be a complete decodable PNG");
  }
  if (
    decoded.width !== 1280 ||
    decoded.height !== 720 ||
    decoded.depth !== 8 ||
    decoded.colorType !== 2 ||
    decoded.alpha !== false ||
    decoded.palette !== false ||
    decoded.interlace !== false ||
    !Buffer.isBuffer(decoded.data) ||
    decoded.data.byteLength !== 1280 * 720 * 4
  ) {
    throw new Error(
      "poster must decode from exact 1280x720 8-bit RGB to bounded RGBA content",
    );
  }
}

type IsoBmffBox = Readonly<{
  type: string;
  start: number;
  end: number;
  headerBytes: 8 | 16;
}>;

function parseTopLevelIsoBmff(bytes: Buffer): readonly IsoBmffBox[] {
  const boxes: IsoBmffBox[] = [];
  let offset = 0;
  while (offset < bytes.byteLength) {
    const remaining = bytes.byteLength - offset;
    if (remaining < 8)
      throw new Error("capture MP4 has a truncated box header");
    const size32 = bytes.readUInt32BE(offset);
    const type = bytes.toString("latin1", offset + 4, offset + 8);
    if (!/^[\x20-\x7e]{4}$/.test(type)) {
      throw new Error("capture MP4 has an invalid top-level box type");
    }
    let headerBytes: 8 | 16 = 8;
    let boxBytes: bigint;
    if (size32 === 1) {
      if (remaining < 16)
        throw new Error("capture MP4 has a truncated extended box header");
      headerBytes = 16;
      boxBytes = bytes.readBigUInt64BE(offset + 8);
    } else if (size32 === 0) {
      boxBytes = BigInt(remaining);
    } else {
      boxBytes = BigInt(size32);
    }
    if (boxBytes < BigInt(headerBytes)) {
      throw new Error("capture MP4 has an undersized top-level box");
    }
    if (
      boxBytes > BigInt(remaining) ||
      boxBytes > BigInt(Number.MAX_SAFE_INTEGER)
    ) {
      throw new Error(
        "capture MP4 has a truncated or overflowing top-level box",
      );
    }
    const end = offset + Number(boxBytes);
    boxes.push(Object.freeze({ type, start: offset, end, headerBytes }));
    offset = end;
    if (size32 === 0 && offset !== bytes.byteLength) {
      throw new Error("capture MP4 has data after an open-ended box");
    }
  }
  if (offset !== bytes.byteLength)
    throw new Error("capture MP4 box walk is incomplete");
  return Object.freeze(boxes);
}

export function validateFastStartMp4(bytes: Buffer): void {
  const boxes = parseTopLevelIsoBmff(bytes);
  const ftyp = boxes.find((box) => box.type === "ftyp");
  const moov = boxes.find((box) => box.type === "moov");
  const mdat = boxes.find((box) => box.type === "mdat");
  if (!ftyp || ftyp.start !== 0 || ftyp.end - ftyp.start < 16) {
    throw new Error("capture MP4 must begin with a complete ftyp box");
  }
  if (!moov || !mdat || moov.end > mdat.start) {
    throw new Error(
      "capture MP4 does not have a complete moov box before mdat",
    );
  }
}

async function assertReplaceable(targets: readonly string[]): Promise<void> {
  for (const target of targets) {
    try {
      const stat = await fs.lstat(target);
      if (!stat.isFile() || stat.isSymbolicLink()) {
        throw new Error(
          `capture output is not a replaceable regular file: ${path.basename(target)}`,
        );
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

type CaptureInstall = Readonly<{ target: string; bytes: Buffer }>;

type DirectoryComponentIdentity = Readonly<{
  path: string;
  dev: number;
  ino: number;
}>;

export type CaptureDirectoryIdentity = Readonly<{
  requestedPath: string;
  realPath: string;
  components: readonly DirectoryComponentIdentity[];
}>;

export async function bindCaptureDirectoryIdentity(
  directory: string,
): Promise<CaptureDirectoryIdentity> {
  if (!path.isAbsolute(directory) || directory.includes("\0")) {
    throw new Error("capture output directory must be absolute");
  }
  const requestedPath = path.resolve(directory);
  const requestedStat = await fs.lstat(requestedPath).catch(() => {
    throw new Error("capture output directory must be a real directory");
  });
  if (!requestedStat.isDirectory() || requestedStat.isSymbolicLink()) {
    throw new Error("capture output directory must be a real directory");
  }
  const realPath = await fs.realpath(requestedPath);
  const parsed = path.parse(realPath);
  const components: DirectoryComponentIdentity[] = [];
  let current = parsed.root;
  for (const segment of realPath.slice(parsed.root.length).split(path.sep)) {
    if (!segment) continue;
    current = path.join(current, segment);
    const stat = await fs.lstat(current);
    if (!stat.isDirectory() || stat.isSymbolicLink()) {
      throw new Error("capture output ancestry must not contain symlinks");
    }
    components.push(Object.freeze({ path: current, dev: stat.dev, ino: stat.ino }));
  }
  if (components.length === 0) {
    throw new Error("capture output directory must not be a filesystem root");
  }
  return Object.freeze({
    requestedPath,
    realPath,
    components: Object.freeze(components),
  });
}

export async function assertCaptureDirectoryIdentity(
  identity: CaptureDirectoryIdentity,
): Promise<void> {
  const requestedStat = await fs.lstat(identity.requestedPath).catch(() => {
    throw new Error("capture output directory identity changed");
  });
  if (
    !requestedStat.isDirectory() ||
    requestedStat.isSymbolicLink() ||
    (await fs.realpath(identity.requestedPath)) !== identity.realPath
  ) {
    throw new Error("capture output directory identity changed");
  }
  for (const component of identity.components) {
    const stat = await fs.lstat(component.path).catch(() => {
      throw new Error("capture output directory ancestry changed");
    });
    if (
      !stat.isDirectory() ||
      stat.isSymbolicLink() ||
      stat.dev !== component.dev ||
      stat.ino !== component.ino
    ) {
      throw new Error("capture output directory ancestry changed");
    }
  }
}

export type CaptureInstallOperations = Readonly<{
  rename?: (source: string, target: string) => Promise<void>;
  backup?: (source: string, target: string) => Promise<void>;
  signal?: AbortSignal;
  directoryIdentity?: CaptureDirectoryIdentity;
  beforeDirectoryCheck?: (stage: string) => Promise<void>;
  validateBeforeCommit?: () => Promise<void>;
  validateAfterInstall?: () => Promise<void>;
}>;

export async function installCaptureFiles(
  entries: readonly CaptureInstall[],
  operations: CaptureInstallOperations = {},
): Promise<void> {
  const checkCancellation = () => {
    if (operations.signal?.aborted) {
      throw new Error("capture install was cancelled");
    }
  };
  checkCancellation();
  if (entries.length === 0)
    throw new Error("capture install requires output files");
  const captureRoot = path.dirname(path.resolve(entries[0].target));
  if (
    entries.some(
      (entry) => path.dirname(path.resolve(entry.target)) !== captureRoot,
    )
  ) {
    throw new Error("capture install targets must share one directory");
  }
  if (
    new Set(entries.map((entry) => path.basename(entry.target))).size !==
    entries.length
  ) {
    throw new Error("capture install target basenames must be unique");
  }
  const directoryIdentity =
    operations.directoryIdentity ??
    (await bindCaptureDirectoryIdentity(captureRoot));
  if (
    directoryIdentity.requestedPath !== path.resolve(captureRoot) ||
    entries.some(
      (entry) => path.dirname(path.resolve(entry.target)) !== captureRoot,
    )
  ) {
    throw new Error("capture install directory identity does not match targets");
  }
  const assertDirectory = async (stage: string): Promise<void> => {
    await operations.beforeDirectoryCheck?.(stage);
    await assertCaptureDirectoryIdentity(directoryIdentity);
  };
  await assertDirectory("before-staging");
  await assertReplaceable(entries.map((entry) => entry.target));
  await assertDirectory("before-transaction");
  const transactionRoot = await fs.mkdtemp(
    path.join(captureRoot, ".stage-gen-capture-install-"),
  );
  await assertDirectory("after-transaction");
  const payloadRoot = path.join(transactionRoot, "payload");
  const backupRoot = path.join(transactionRoot, "backup");
  await Promise.all([
    fs.mkdir(payloadRoot, { mode: 0o700 }),
    fs.mkdir(backupRoot, { mode: 0o700 }),
  ]);
  const existingTargets = new Set<string>();
  const installedTargets = new Set<string>();
  const rename =
    operations.rename ??
    (async (source, target) => await fs.rename(source, target));
  const backup =
    operations.backup ??
    (async (source, target) => await fs.copyFile(source, target));
  let retainTransaction = false;
  try {
    for (const entry of entries) {
      checkCancellation();
      await assertDirectory(`before-backup:${path.basename(entry.target)}`);
      const basename = path.basename(entry.target);
      await fs.writeFile(path.join(payloadRoot, basename), entry.bytes, {
        flag: "wx",
        mode: 0o644,
      });
      try {
        await backup(entry.target, path.join(backupRoot, basename));
        existingTargets.add(entry.target);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
    }
    checkCancellation();
    await assertDirectory("before-final-validation");
    await operations.validateBeforeCommit?.();
    checkCancellation();
    await assertDirectory("after-final-validation");
    for (const entry of entries) {
      checkCancellation();
      await assertDirectory(`before-rename:${path.basename(entry.target)}`);
      await rename(
        path.join(payloadRoot, path.basename(entry.target)),
        entry.target,
      );
      installedTargets.add(entry.target);
      await assertDirectory(`after-rename:${path.basename(entry.target)}`);
    }
    checkCancellation();
    await assertDirectory("after-install");
    await operations.validateAfterInstall?.();
    checkCancellation();
    await assertDirectory("after-installed-validation");
  } catch (error) {
    const rollbackFailures: string[] = [];
    try {
      await assertCaptureDirectoryIdentity(directoryIdentity);
    } catch {
      retainTransaction = true;
      throw new Error(
        "capture output directory changed; transaction retained without unsafe rollback",
        { cause: error },
      );
    }
    for (const entry of [...entries].reverse()) {
      try {
        if (!installedTargets.has(entry.target)) continue;
        await assertCaptureDirectoryIdentity(directoryIdentity);
        if (existingTargets.has(entry.target)) {
          await fs.rm(entry.target, { force: true });
          await rename(
            path.join(backupRoot, path.basename(entry.target)),
            entry.target,
          );
        } else {
          await fs.rm(entry.target, { force: true });
        }
      } catch {
        rollbackFailures.push(path.basename(entry.target));
      }
    }
    if (rollbackFailures.length > 0) {
      retainTransaction = true;
      throw new Error(
        `capture install rollback failed for ${rollbackFailures.sort().join(", ")}; backups retained`,
        { cause: error },
      );
    }
    throw error;
  } finally {
    if (!retainTransaction) {
      await assertCaptureDirectoryIdentity(directoryIdentity);
      await fs.rm(transactionRoot, { recursive: true, force: true });
    }
  }
}

export type GameplayCaptureEvidence = Readonly<{
  version: typeof GAMEPLAY_AUTOMATION_VERSION;
  verdict: "unreviewed";
  video: Readonly<{
    path: typeof CAPTURE_VIDEO_PATH;
    sha256: string;
    bytes: number;
    durationSeconds: number;
  }>;
  poster: Readonly<{
    path: typeof CAPTURE_POSTER_PATH;
    sha256: string;
    bytes: number;
  }>;
}>;

export async function captureDeterministicGameplay(
  requestedPath: string,
): Promise<GameplayCaptureEvidence> {
  const target = resolveGameplayCapturePath(requestedPath);
  const posterTarget = path.join(REPO_ROOT, ...CAPTURE_POSTER_PATH.split("/"));
  const captureRoot = path.dirname(target);
  await fs.mkdir(captureRoot, { recursive: true, mode: 0o700 });
  const captureRootStat = await fs.lstat(captureRoot);
  if (!captureRootStat.isDirectory() || captureRootStat.isSymbolicLink()) {
    throw new Error("gameplay capture root must be a real directory");
  }
  const realRoot = await fs.realpath(captureRoot);
  if (realRoot !== captureRoot)
    throw new Error("gameplay capture root must not be a symlink");
  // The capture writes no provenance sidecar. `docs/media` is documentation, not a
  // publication root, and determinism is re-established by re-running `--verify`
  // rather than by a record beside the file that nothing reads.
  await assertReplaceable([target, posterTarget]);

  return await withVerifiedGameplay(async (evidence, workspace) => {
    const frames = path.join(workspace, "frames");
    const temporaryTarget = path.join(workspace, "gameplay-showcase.mp4");
    const exactFfmpegArgs = [
      "-hide_banner",
      "-loglevel",
      "error",
      "-framerate",
      "30",
      "-start_number",
      "1",
      "-i",
      path.join(frames, "frame-%04d.png"),
      "-frames:v",
      String(GAMEPLAY_FRAME_COUNT),
      "-an",
      "-c:v",
      "libx264",
      "-preset",
      "slow",
      "-crf",
      "26",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      temporaryTarget,
    ] as const;
    await runTool("ffmpeg", exactFfmpegArgs, { timeoutMs: FFMPEG_TIMEOUT_MS });
    const exactFfprobeArgs = [
      "-v",
      "error",
      "-show_entries",
      "format=format_name,duration,size:stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate",
      "-of",
      "json",
      temporaryTarget,
    ] as const;
    const probe = await runTool("ffprobe", exactFfprobeArgs, {
      timeoutMs: FFPROBE_TIMEOUT_MS,
    });
    const rawProbe = JSON.parse(probe.stdout) as { format?: { size?: string } };
    const mp4 = validateGameplayMp4Probe(rawProbe);
    const videoBytes = await fs.readFile(temporaryTarget);
    if (Number(rawProbe.format?.size) !== videoBytes.byteLength) {
      throw new Error("ffprobe size does not match capture bytes");
    }
    validateFastStartMp4(videoBytes);
    const posterSource = path.join(
      frames,
      `frame-${String(GAMEPLAY_POSTER_FRAME).padStart(4, "0")}.png`,
    );
    const posterBytes = await fs.readFile(posterSource);
    validatePosterPng(posterBytes);
    const videoDigest = sha256(videoBytes);
    const posterDigest = sha256(posterBytes);
    if (
      posterDigest !==
      evidence.first.selectedFrameHashes[String(GAMEPLAY_POSTER_FRAME)]
    ) {
      throw new Error("poster does not match its deterministic checkpoint");
    }
    const packageJson = JSON.parse(
      await fs.readFile(
        path.join(WEB_ROOT, "node_modules", "playwright", "package.json"),
        "utf8",
      ),
    ) as { version?: unknown };
    if (typeof packageJson.version !== "string")
      throw new Error("Playwright version missing");
    const ffmpegVersion = (
      await runTool("ffmpeg", ["-version"], {
        timeoutMs: TOOL_VERSION_TIMEOUT_MS,
      })
    ).stdout
      .split("\n")[0]
      ?.trim();
    if (!ffmpegVersion) throw new Error("ffmpeg version missing");
    const ffprobeVersion = (
      await runTool("ffprobe", ["-version"], {
        timeoutMs: TOOL_VERSION_TIMEOUT_MS,
      })
    ).stdout
      .split("\n")[0]
      ?.trim();
    if (!ffprobeVersion) throw new Error("ffprobe version missing");
    await installCaptureFiles([
      { target, bytes: videoBytes },
      { target: posterTarget, bytes: posterBytes },
    ]);
    return Object.freeze({
      version: GAMEPLAY_AUTOMATION_VERSION,
      verdict: "unreviewed",
      video: Object.freeze({
        path: CAPTURE_VIDEO_PATH,
        sha256: videoDigest,
        bytes: videoBytes.byteLength,
        durationSeconds: mp4.duration_seconds,
      }),
      poster: Object.freeze({
        path: CAPTURE_POSTER_PATH,
        sha256: posterDigest,
        bytes: posterBytes.byteLength,
      }),
    });
  }, true);
}
