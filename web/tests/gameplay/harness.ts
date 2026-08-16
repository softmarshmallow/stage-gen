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
import { GAMEPLAY_AUTOMATION_VERSION } from "./contracts";
import {
  GAMEPLAY_DEMO_APPROVAL_MANIFEST,
  GAMEPLAY_DEMO_ASSET_MANIFEST,
  GAMEPLAY_MODEL_ASSET_CONTRACTS,
  GAMEPLAY_MODEL_REQUIRED_ASSET_KEYS,
  generateApprovedModelGameplayFixture,
} from "./model-assets";
import {
  GAMEPLAY_DURATION_SECONDS,
  GAMEPLAY_EVENT_VISIBILITY_WINDOWS,
  GAMEPLAY_FRAME_COUNT,
  GAMEPLAY_POSTER_FRAME,
  GAMEPLAY_REQUIRED_EVENTS,
  GAMEPLAY_REQUIRED_STATES,
  GAMEPLAY_SELECTED_FRAMES,
  GAMEPLAY_STEP_MS,
  GAMEPLAY_TIMELINE,
} from "./timeline";

const GAMEPLAY_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(GAMEPLAY_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const NEXT_CLI = path.join(
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
  "6bb9d428aead88df25e91dfe7761382e23673a77c5a1d2a1622019554184d30a";
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

export type GameplayRunEvidence = Readonly<{
  transcript: string;
  transcriptDigest: string;
  selectedFrameHashes: Readonly<Record<string, string>>;
  states: readonly string[];
  finalSnapshot: GameplayAutomationSnapshot;
}>;

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

async function assertBuiltNextApplication(): Promise<void> {
  const [buildId, nextCli] = await Promise.all([
    fs.lstat(path.join(WEB_ROOT, ".next", "BUILD_ID")),
    fs.lstat(NEXT_CLI),
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
  const realCli = await fs.realpath(NEXT_CLI);
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

async function startNextServer(outRoot: string): Promise<StartedServer> {
  await assertBuiltNextApplication();
  const port = await freeLoopbackPort();
  const args = [
    NEXT_CLI,
    "start",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(port),
  ];
  const child = spawn(process.execPath, args, {
    cwd: WEB_ROOT,
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
  const startedAt = Date.now();
  while (Date.now() - startedAt < SERVER_TIMEOUT_MS) {
    if (child.exitCode !== null) {
      throw new Error(
        `Next server exited before readiness (code ${child.exitCode}): ${output}`,
      );
    }
    try {
      const response = await fetch(baseUrl, { redirect: "manual" });
      if (response.status >= 200 && response.status < 500) {
        return { baseUrl, process: child, stop: () => stopChild(child) };
      }
    } catch {
      // Startup races are expected until the loopback listener is ready.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  await stopChild(child);
  throw new Error(
    `Next server did not become ready within ${SERVER_TIMEOUT_MS}ms`,
  );
}

function transcriptLine(snapshot: GameplayAutomationSnapshot): string {
  return JSON.stringify({
    frame: snapshot.frame,
    simulationMs: snapshot.simulationMs,
    player: snapshot.player,
    camera: snapshot.camera,
    mobs: snapshot.mobs,
    inventory: snapshot.inventory,
    worldItems: snapshot.worldItems,
    encounter: snapshot.encounter,
    portals: snapshot.portals,
    presentation: snapshot.presentation,
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
  if (!snapshot.ready || snapshot.state !== "ready") {
    throw new Error(`gameplay probe is not ready (${snapshot.state})`);
  }
  if (snapshot.errors.length > 0) {
    throw new Error(
      `gameplay probe reported ${snapshot.errors.length} error(s)`,
    );
  }
  if (!snapshot.heightmapDigest?.match(/^[0-9a-f]{64}$/)) {
    throw new Error("gameplay probe has no stable heightmap digest");
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
          player: GameplayAutomationSnapshot["player"];
          camera: GameplayAutomationSnapshot["camera"];
          mobs: GameplayAutomationSnapshot["mobs"];
          worldItems: GameplayAutomationSnapshot["worldItems"];
          encounter: GameplayAutomationSnapshot["encounter"];
          presentation: GameplayAutomationSnapshot["presentation"];
        },
    );
  if (transcript.length !== GAMEPLAY_FRAME_COUNT) {
    throw new Error(
      "gameplay transcript must contain exactly 900 frame snapshots",
    );
  }
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
    byFrame.get(899)?.presentation.portalScale ===
    byFrame.get(900)?.presentation.portalScale
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
  if (final.camera.scrollX <= 0)
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

async function waitForProbe(page: Page): Promise<GameplayAutomationSnapshot> {
  await page.waitForFunction(
    () => {
      const probe = window.__stageGenGameplayProbe;
      return probe?.ready === true || probe?.state === "error";
    },
    undefined,
    { timeout: PROBE_TIMEOUT_MS },
  );
  return await page.evaluate(() => {
    const probe = window.__stageGenGameplayProbe;
    if (!probe) throw new Error("gameplay probe is missing");
    return probe;
  });
}

async function runOnce(
  browser: Browser,
  baseUrl: string,
  route: string,
  frameDirectory?: string,
): Promise<GameplayRunEvidence> {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
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
    const response = await page.goto(`${baseUrl}${route}`, {
      waitUntil: "domcontentloaded",
      timeout: PROBE_TIMEOUT_MS,
    });
    if (!response?.ok())
      throw new Error(`preview route returned HTTP ${response?.status() ?? 0}`);
    const initial = await waitForProbe(page);
    assertSnapshotContract(initial);
    if (initial.frame !== 0 || initial.simulationMs !== 0) {
      throw new Error("gameplay probe did not start at frame zero");
    }
    const canvas = page.locator("canvas").first();
    await canvas.waitFor({ state: "visible", timeout: PROBE_TIMEOUT_MS });
    const bounds = await canvas.boundingBox();
    if (!bounds || bounds.width !== 1280 || bounds.height !== 720) {
      throw new Error(
        `gameplay canvas is not 1280x720 (${bounds?.width}x${bounds?.height})`,
      );
    }

    const transcript: string[] = [];
    const states = new Set<string>();
    const selected = new Set<number>(GAMEPLAY_SELECTED_FRAMES);
    const selectedFrameHashes: Record<string, string> = {};
    let snapshot = initial;
    for (const frame of GAMEPLAY_TIMELINE) {
      for (const action of frame.actions) {
        if (action.type === "down") await page.keyboard.down(action.key);
        else await page.keyboard.up(action.key);
      }
      snapshot = await page.evaluate(async () => {
        const advance = window.__stageGenAdvanceGameplayFrame;
        if (!advance) throw new Error("gameplay frame hook is missing");
        return await advance();
      });
      if (snapshot.frame !== frame.index + 1) {
        throw new Error(
          `gameplay frame skipped from ${frame.index} to ${snapshot.frame}`,
        );
      }
      assertSnapshotContract(snapshot);
      if (snapshot.player) states.add(snapshot.player.state);
      transcript.push(transcriptLine(snapshot));
      if (selected.has(snapshot.frame) || frameDirectory) {
        const framePng = await canvas.screenshot({ type: "png" });
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
    validateGameplayRun(result);
    return result;
  } finally {
    await context.close();
  }
}

type VerifiedGameplay = Readonly<{
  fixtureDigest: string;
  first: GameplayRunEvidence;
  chromiumVersion: string;
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

async function withVerifiedGameplay<T>(
  operation: (evidence: VerifiedGameplay, workspace: string) => Promise<T> | T,
  captureFrames = false,
): Promise<T> {
  const workspace = await fs.mkdtemp(
    path.join(tmpdir(), "stage-gen-gameplay-"),
  );
  let server: StartedServer | undefined;
  let browser: Browser | undefined;
  return await runWithGameplayCleanups(async () => {
    const fixture = await generateApprovedModelGameplayFixture(
      path.join(workspace, "out"),
    );
    server = await startNextServer(fixture.outRoot);
    browser = await chromium.launch({ headless: true });
    const frameDirectory = captureFrames
      ? path.join(workspace, "frames")
      : undefined;
    if (frameDirectory) await fs.mkdir(frameDirectory, { mode: 0o700 });
    const first = await runOnce(
      browser,
      server.baseUrl,
      fixture.route,
      frameDirectory,
    );
    const second = await runOnce(browser, server.baseUrl, fixture.route);
    compareRuns(first, second);
    return await operation(
      Object.freeze({
        fixtureDigest: fixture.digest,
        first,
        chromiumVersion: browser.version(),
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
  return await withVerifiedGameplay((evidence) => verificationFrom(evidence));
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
  let child: ToolChild;
  try {
    child = spawn(executable, [...args], {
      cwd: WEB_ROOT,
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

async function sourceReference(
  repositoryPath: string,
): Promise<{ path: string; sha256: string }> {
  const sourcePath = path.join(REPO_ROOT, ...repositoryPath.split("/"));
  return {
    path: repositoryPath,
    sha256: sha256(await fs.readFile(sourcePath)),
  };
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

async function modelAssetBundleReference(): Promise<{
  count: 18;
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
    count: 18,
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

function assertPortableMetadata(value: unknown): void {
  const rendered = JSON.stringify(value);
  if (/\/(?:private\/tmp|tmp|Users|var\/folders)\//.test(rendered)) {
    throw new Error("capture metadata contains an unstable absolute path");
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

export type CaptureInstallOperations = Readonly<{
  rename?: (source: string, target: string) => Promise<void>;
}>;

export async function installCaptureFiles(
  entries: readonly CaptureInstall[],
  operations: CaptureInstallOperations = {},
): Promise<void> {
  if (entries.length === 0)
    throw new Error("capture install requires output files");
  const captureRoot = path.dirname(entries[0].target);
  if (entries.some((entry) => path.dirname(entry.target) !== captureRoot)) {
    throw new Error("capture install targets must share one directory");
  }
  if (
    new Set(entries.map((entry) => path.basename(entry.target))).size !==
    entries.length
  ) {
    throw new Error("capture install target basenames must be unique");
  }
  await assertReplaceable(entries.map((entry) => entry.target));
  const transactionRoot = await fs.mkdtemp(
    path.join(captureRoot, ".stage-gen-capture-install-"),
  );
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
  let retainTransaction = false;
  try {
    for (const entry of entries) {
      const basename = path.basename(entry.target);
      await fs.writeFile(path.join(payloadRoot, basename), entry.bytes, {
        flag: "wx",
        mode: 0o644,
      });
      try {
        await fs.copyFile(entry.target, path.join(backupRoot, basename));
        existingTargets.add(entry.target);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
    }
    for (const entry of entries) {
      await rename(
        path.join(payloadRoot, path.basename(entry.target)),
        entry.target,
      );
      installedTargets.add(entry.target);
    }
  } catch (error) {
    const rollbackFailures: string[] = [];
    for (const entry of [...entries].reverse()) {
      try {
        if (existingTargets.has(entry.target)) {
          await fs.rm(entry.target, { force: true });
          await rename(
            path.join(backupRoot, path.basename(entry.target)),
            entry.target,
          );
        } else if (installedTargets.has(entry.target)) {
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
    if (!retainTransaction)
      await fs.rm(transactionRoot, { recursive: true, force: true });
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
  const targetMetadata = `${target}.meta.json`;
  const posterMetadata = `${posterTarget}.meta.json`;
  await assertReplaceable([
    target,
    posterTarget,
    targetMetadata,
    posterMetadata,
  ]);

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
    const captureVersion =
      `Playwright ${packageJson.version}; Chromium ${evidence.chromiumVersion}; ` +
      `${ffmpegVersion}; ${ffprobeVersion}`;
    const sharedParams = {
      automation_mode: GAMEPLAY_AUTOMATION_VERSION,
      browser: "chromium",
      playwright_version: packageJson.version,
      chromium_version: evidence.chromiumVersion,
      ffmpeg_version: ffmpegVersion,
      ffprobe_version: ffprobeVersion,
      viewport: { width: 1280, height: 720 },
      device_scale_factor: 1,
      frame_count: GAMEPLAY_FRAME_COUNT,
      frame_rate: 30,
      clock: { mode: "manual-fixed-step", step_ms: GAMEPLAY_STEP_MS },
      fixture_sha256: evidence.fixtureDigest,
      transcript_sha256: evidence.first.transcriptDigest,
      checkpoint_sha256: evidence.first.selectedFrameHashes,
      event_frames: verificationFrom(evidence).eventFrames,
    };
    const source = await sourceReference("web/scripts/gameplay/showcase.ts");
    const verifier = await sourceReference("web/tests/gameplay/harness.ts");
    const generator = Object.freeze({
      pathAtCapture: verifier.path,
      ref: `sha256:${verifier.sha256}`,
      sha256: verifier.sha256,
    });
    const fixture = await sourceReference("web/tests/gameplay/model-assets.ts");
    const fixtureGenerator = Object.freeze({
      pathAtCapture: fixture.path,
      ref: `sha256:${fixture.sha256}`,
      sha256: fixture.sha256,
    });
    const timeline = await sourceReference("web/tests/gameplay/timeline.ts");
    const producerManifest = await contentReference(
      `fixtures/gameplay-demo/${GAMEPLAY_DEMO_ASSET_MANIFEST}`,
    );
    const approvalManifest = await contentReference(
      `fixtures/gameplay-demo/${GAMEPLAY_DEMO_APPROVAL_MANIFEST}`,
    );
    const assetSet = await modelAssetBundleReference();
    const videoSidecar = {
      schema_version: 1,
      state: "unreviewed",
      visualReview: { status: "pending", independent: false },
      artifact: {
        path: CAPTURE_VIDEO_PATH,
        media_type: "video/mp4",
        sha256: videoDigest,
        bytes: videoBytes.byteLength,
      },
      capture: {
        tool: "Playwright canvas frames and ffmpeg libx264",
        version: captureVersion,
        params: {
          ...sharedParams,
          ffmpeg_args: [
            "-framerate",
            "30",
            "-start_number",
            "1",
            "-i",
            "frame-%04d.png",
            "-frames:v",
            "900",
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
            "gameplay-showcase.mp4",
          ],
          ffprobe_args: [
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration,size:stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate",
            "-of",
            "json",
            "gameplay-showcase.mp4",
          ],
        },
        source,
        generator,
        verifier,
        fixture,
        fixtureGenerator,
        timeline,
        producerManifest,
        approvalManifest,
        assetSet,
        mp4,
      },
    };
    const posterSidecar = {
      schema_version: 1,
      state: "unreviewed",
      visualReview: { status: "pending", independent: false },
      artifact: {
        path: CAPTURE_POSTER_PATH,
        media_type: "image/png",
        sha256: posterDigest,
        bytes: posterBytes.byteLength,
      },
      capture: {
        tool: "Playwright deterministic canvas checkpoint",
        version: captureVersion,
        params: {
          ...sharedParams,
          representative_frame: GAMEPLAY_POSTER_FRAME,
          representative_frame_sha256: posterDigest,
        },
        source,
        generator,
        verifier,
        fixture,
        fixtureGenerator,
        timeline,
        producerManifest,
        approvalManifest,
        assetSet,
      },
    };
    assertPortableMetadata(videoSidecar);
    assertPortableMetadata(posterSidecar);
    await installCaptureFiles([
      { target, bytes: videoBytes },
      { target: posterTarget, bytes: posterBytes },
      {
        target: targetMetadata,
        bytes: Buffer.from(`${JSON.stringify(videoSidecar, null, 2)}\n`),
      },
      {
        target: posterMetadata,
        bytes: Buffer.from(`${JSON.stringify(posterSidecar, null, 2)}\n`),
      },
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
