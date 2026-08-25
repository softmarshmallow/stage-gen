#!/usr/bin/env bun

import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Page } from "playwright";
import { PNG } from "pngjs";
import {
  GAMEPLAY_AUTOMATION_ENCOUNTER,
  GAMEPLAY_AUTOMATION_MODE,
  GAMEPLAY_AUTOMATION_VIEWPORT,
  type GameplayAutomationSnapshot,
} from "../../lib/runtime/automation";
import type { SceneLayerProbe } from "../../lib/runtime/layers";
import {
  parseImageRepeatManifest,
  parseScrollingManifestEnvelope,
} from "../../lib/runtime/manifest";
import {
  GAMEPLAY_TIMELINE,
  type GameplayFrame,
  type GameplayKey,
} from "../../tests/gameplay/timeline";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const OUTPUT_ROOT = path.join(REPO_ROOT, "output/playwright/image-repeat-proof");
const SAFE_TAG = /^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/;
const DEFAULT_TIMEOUT_MS = 180_000;
const START_FRAME = GAMEPLAY_AUTOMATION_ENCOUNTER.focusEndFrame + 1;
const LAST_PROOF_FRAME = GAMEPLAY_AUTOMATION_ENCOUNTER.finalActiveStartFrame;
const REQUIRED_PERIODS = 2;
const JOIN_BAND = Object.freeze({
  left: GAMEPLAY_AUTOMATION_VIEWPORT.width * 0.4,
  right: GAMEPLAY_AUTOMATION_VIEWPORT.width * 0.6,
});

export const DEFAULT_IMAGE_REPEAT_PROOF_TAG =
  "whimsical-storybook-fantasy-7e5ab98f-game-v1-0034f94ce0-f0440de8-ai";
export const IMAGE_REPEAT_PROOF_USAGE =
  "usage: bun scripts/gameplay/image-repeat-proof.ts " +
  "[--tag <run-tag>] [--base-url http://127.0.0.1:3000] " +
  "[--timeout-ms 180000]";

export type ImageRepeatProofOptions = Readonly<{
  tag: string;
  baseUrl: string;
  timeoutMs: number;
}>;

export type ImageRepeatProofTarget = Readonly<{
  id: string;
  kind: SceneLayerProbe["kind"];
  depthCoefficient: number;
  decision: "admitted" | "repaired";
  sourcePath: string;
  repeatUnitPath: string;
  periodPx: number;
}>;

export type ImageRepeatProofSelection = Readonly<{
  all: readonly ImageRepeatProofTarget[];
  background: ImageRepeatProofTarget;
  foreground: ImageRepeatProofTarget;
}>;

type ManifestPreflight = Readonly<{
  path: string;
  sha256: string;
  bytes: number;
  artifactCount: number;
  buildId: string;
}>;

type PendingCapture = Readonly<{
  role: "start" | "join" | "end";
  bytes: Buffer;
  snapshot: GameplayAutomationSnapshot;
  seamScreenX: number | null;
}>;

type BrowserProof = Readonly<{
  browserVersion: string;
  initial: GameplayAutomationSnapshot;
  selection: ImageRepeatProofSelection;
  captures: readonly [PendingCapture, PendingCapture, PendingCapture];
  browserErrors: readonly string[];
}>;

function valueAfter(args: readonly string[], index: number, flag: string): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

function loopbackBaseUrl(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("image repeat proof base URL is invalid");
  }
  if (
    url.protocol !== "http:" ||
    (url.hostname !== "127.0.0.1" && url.hostname !== "localhost") ||
    url.username !== "" ||
    url.password !== "" ||
    (url.pathname !== "" && url.pathname !== "/") ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new Error("image repeat proof requires one plain loopback HTTP origin");
  }
  return url.origin;
}

export function parseImageRepeatProofArgs(
  args: readonly string[],
): ImageRepeatProofOptions {
  let tag = DEFAULT_IMAGE_REPEAT_PROOF_TAG;
  let baseUrl = "http://127.0.0.1:3000";
  let timeoutMs = DEFAULT_TIMEOUT_MS;
  const seen = new Set<string>();
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index]!;
    if (seen.has(flag)) throw new Error(`duplicate option: ${flag}`);
    seen.add(flag);
    if (flag === "--tag") {
      tag = valueAfter(args, index, flag);
      index += 1;
      continue;
    }
    if (flag === "--base-url") {
      baseUrl = loopbackBaseUrl(valueAfter(args, index, flag));
      index += 1;
      continue;
    }
    if (flag === "--timeout-ms") {
      const value = valueAfter(args, index, flag);
      if (!/^[1-9]\d*$/.test(value)) throw new Error("timeout must be an integer");
      timeoutMs = Number(value);
      if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 10_000 || timeoutMs > 600_000) {
        throw new Error("timeout must be between 10000 and 600000");
      }
      index += 1;
      continue;
    }
    throw new Error(`unknown image repeat proof option: ${flag}`);
  }
  if (!SAFE_TAG.test(tag)) throw new Error("image repeat proof tag is invalid");
  return Object.freeze({ tag, baseUrl: loopbackBaseUrl(baseUrl), timeoutMs });
}

export function assertImageRepeatManifestReady(value: unknown, tag: string): number {
  const manifest = parseScrollingManifestEnvelope(value, tag);
  const imageRepeat = parseImageRepeatManifest(manifest["image_repeat"]);
  if (
    imageRepeat.enabled !== true ||
    imageRepeat.status !== "available" ||
    imageRepeat.artifacts.length === 0
  ) {
    throw new Error("run manifest has no available image_repeat artifacts");
  }
  return imageRepeat.artifacts.length;
}

function stablePngPath(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 768) {
    throw new Error(`${label} must be a bounded portable PNG path`);
  }
  const parts = value.split("/");
  if (
    value.includes("\\") ||
    path.posix.isAbsolute(value) ||
    !value.toLowerCase().endsWith(".png") ||
    parts.some(
      (part) =>
        part === "" ||
        part === "." ||
        part === ".." ||
        part.length > 255 ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(part),
    )
  ) {
    throw new Error(`${label} must be a bounded portable PNG path`);
  }
  return value;
}

function requireVerifiedLayer(layer: SceneLayerProbe): ImageRepeatProofTarget {
  const repeat = layer.imageRepeat;
  if (!repeat) throw new Error(`${layer.id} has no verified-v2 image repeat selection`);
  if (
    layer.repeat !== "repeat-x-verified" ||
    repeat.schemaVersion !== 2 ||
    repeat.axis !== "x" ||
    (repeat.decision !== "admitted" && repeat.decision !== "repaired") ||
    repeat.selected !== "verified-v2" ||
    repeat.unverifiedFallbackApplied !== false ||
    repeat.partnerSpriteCount !== 0 ||
    !Number.isSafeInteger(repeat.periodPx) ||
    repeat.periodPx <= 0 ||
    layer.render.spriteCount !== 1 ||
    layer.render.textureWidth !== repeat.periodPx ||
    !Number.isFinite(layer.depthCoefficient) ||
    layer.depthCoefficient < 0
  ) {
    throw new Error(`${layer.id} does not satisfy the verified-v2 runtime gate`);
  }
  if (
    layer.kind === "near-foreground" &&
    (!layer.foreground ||
      layer.foreground.repeatPeriodSourcePx !== repeat.periodPx ||
      layer.foreground.overlapSourcePx !== 0 ||
      layer.foreground.spriteCount !== 1)
  ) {
    throw new Error(`${layer.id} verified foreground still uses overlap geometry`);
  }
  return Object.freeze({
    id: layer.id,
    kind: layer.kind,
    depthCoefficient: layer.depthCoefficient,
    decision: repeat.decision,
    sourcePath: stablePngPath(repeat.sourcePath, `${layer.id}.sourcePath`),
    repeatUnitPath: stablePngPath(repeat.repeatUnitPath, `${layer.id}.repeatUnitPath`),
    periodPx: repeat.periodPx,
  });
}

function assertCleanSnapshot(snapshot: GameplayAutomationSnapshot): void {
  if (
    snapshot.version !== GAMEPLAY_AUTOMATION_MODE ||
    snapshot.state !== "ready" ||
    snapshot.ready !== true
  ) {
    throw new Error("image repeat proof requires a ready gameplay-v2 snapshot");
  }
  if (snapshot.errors.length > 0 || snapshot.diagnostics.length > 0) {
    throw new Error(
      `gameplay probe is not clean: ${[...snapshot.errors, ...snapshot.diagnostics].join(" | ")}`,
    );
  }
  if (
    !Number.isFinite(snapshot.camera.scrollX) ||
    !Number.isFinite(snapshot.camera.scrollY) ||
    !Number.isFinite(snapshot.camera.zoom) ||
    snapshot.camera.zoom <= 0
  ) {
    throw new Error("gameplay probe camera is invalid");
  }
}

export function selectImageRepeatProofTargets(
  snapshot: GameplayAutomationSnapshot,
): ImageRepeatProofSelection {
  assertCleanSnapshot(snapshot);
  const all = snapshot.layers
    .filter((layer) => layer.imageRepeat !== undefined)
    .map(requireVerifiedLayer);
  const background = [...all]
    .filter(
      (target) =>
        (target.kind === "distant" || target.kind === "midground") &&
        target.depthCoefficient > 0,
    )
    .sort(
      (left, right) =>
        right.depthCoefficient - left.depthCoefficient || left.id.localeCompare(right.id),
    )[0];
  const foreground = [...all]
    .filter(
      (target) => target.kind === "near-foreground" && target.depthCoefficient > 0,
    )
    .sort(
      (left, right) =>
        right.depthCoefficient - left.depthCoefficient || left.id.localeCompare(right.id),
    )[0];
  if (!background || !foreground) {
    throw new Error(
      "image repeat proof requires verified moving background and near-foreground layers",
    );
  }
  return Object.freeze({ all: Object.freeze(all), background, foreground });
}

function targetSignature(target: ImageRepeatProofTarget): string {
  return JSON.stringify(target);
}

function assertSelectionStable(
  expected: ImageRepeatProofSelection,
  current: ImageRepeatProofSelection,
): void {
  const expectedAll = expected.all.map(targetSignature).sort();
  const currentAll = current.all.map(targetSignature).sort();
  if (JSON.stringify(expectedAll) !== JSON.stringify(currentAll)) {
    throw new Error("verified-v2 image repeat selection changed during traversal");
  }
}

export function repeatPeriodsTravelled(
  start: GameplayAutomationSnapshot,
  current: GameplayAutomationSnapshot,
  target: ImageRepeatProofTarget,
): number {
  const startLayer = selectedLayer(start, target);
  const currentLayer = selectedLayer(current, target);
  if (target.kind === "near-foreground") {
    const startForeground = startLayer.foreground;
    const currentForeground = currentLayer.foreground;
    if (
      !startForeground ||
      !currentForeground ||
      !Number.isFinite(startForeground.projectedCameraTravelScreenPx) ||
      !Number.isFinite(currentForeground.projectedCameraTravelScreenPx) ||
      !Number.isFinite(startForeground.seamPeriodScreenPx) ||
      !Number.isFinite(currentForeground.seamPeriodScreenPx) ||
      startForeground.seamPeriodScreenPx <= 0 ||
      Math.abs(
        startForeground.seamPeriodScreenPx - currentForeground.seamPeriodScreenPx,
      ) > 1e-6
    ) {
      throw new Error("foreground repeat travel projection is invalid or changed");
    }
    return Math.max(
      0,
      (currentForeground.projectedCameraTravelScreenPx -
        startForeground.projectedCameraTravelScreenPx) /
        currentForeground.seamPeriodScreenPx,
    );
  }
  const phaseTravel = currentLayer.render.tilePositionX - startLayer.render.tilePositionX;
  if (!Number.isFinite(phaseTravel)) throw new Error("background repeat phase travel is invalid");
  return Math.max(0, phaseTravel / target.periodPx);
}

function selectedLayer(
  snapshot: GameplayAutomationSnapshot,
  target: ImageRepeatProofTarget,
): SceneLayerProbe {
  const layer = snapshot.layers.find((candidate) => candidate.id === target.id);
  if (!layer || targetSignature(requireVerifiedLayer(layer)) !== targetSignature(target)) {
    throw new Error(`${target.id} verified repeat is absent or changed`);
  }
  return layer;
}

export function foregroundJoinScreenX(
  snapshot: GameplayAutomationSnapshot,
  target: ImageRepeatProofTarget,
): number | null {
  const layer = selectedLayer(snapshot, target);
  if (
    target.kind !== "near-foreground" ||
    !snapshot.presentation.foregroundVisible ||
    !layer.render.visible ||
    !layer.foreground ||
    !Number.isFinite(layer.foreground.seamScreenX)
  ) {
    return null;
  }
  return layer.foreground.seamScreenX;
}

export function isCentralJoinFrame(
  start: GameplayAutomationSnapshot,
  current: GameplayAutomationSnapshot,
  target: ImageRepeatProofTarget,
): boolean {
  const seamScreenX = foregroundJoinScreenX(current, target);
  return (
    repeatPeriodsTravelled(start, current, target) >= 0.25 &&
    seamScreenX !== null &&
    seamScreenX >= JOIN_BAND.left &&
    seamScreenX <= JOIN_BAND.right
  );
}

async function manifestPreflight(tag: string): Promise<ManifestPreflight> {
  const runDirectory = path.join(REPO_ROOT, "out", tag);
  const manifestPath = path.join(runDirectory, `manifest_${tag}.json`);
  const buildIdPath = path.join(WEB_ROOT, ".next/BUILD_ID");
  const [runStat, manifestStat, buildStat] = await Promise.all([
    fs.lstat(runDirectory),
    fs.lstat(manifestPath),
    fs.lstat(buildIdPath),
  ]).catch(() => {
    throw new Error(
      "run manifest or production build is missing; wait for the run, then run `bun run build` in web",
    );
  });
  if (
    !runStat.isDirectory() ||
    runStat.isSymbolicLink() ||
    !manifestStat.isFile() ||
    manifestStat.isSymbolicLink() ||
    !buildStat.isFile() ||
    buildStat.isSymbolicLink()
  ) {
    throw new Error("image repeat proof inputs must be real local files and directories");
  }
  const [realRun, realManifest] = await Promise.all([
    fs.realpath(runDirectory),
    fs.realpath(manifestPath),
  ]);
  if (realRun !== runDirectory || realManifest !== manifestPath) {
    throw new Error("image repeat proof inputs escape the generated run directory");
  }
  const [manifestBytes, buildId] = await Promise.all([
    fs.readFile(manifestPath),
    fs.readFile(buildIdPath, "utf8"),
  ]);
  let manifest: unknown;
  try {
    manifest = JSON.parse(manifestBytes.toString("utf8"));
  } catch {
    throw new Error("run manifest is not valid JSON");
  }
  const artifactCount = assertImageRepeatManifestReady(manifest, tag);
  return Object.freeze({
    path: path.relative(REPO_ROOT, manifestPath).split(path.sep).join("/"),
    sha256: createHash("sha256").update(manifestBytes).digest("hex"),
    bytes: manifestBytes.byteLength,
    artifactCount,
    buildId: buildId.trim(),
  });
}

async function readInitialProbe(
  page: Page,
  timeoutMs: number,
): Promise<GameplayAutomationSnapshot> {
  await page.waitForFunction(
    () => {
      const probe = (
        window as typeof window & {
          readonly __stageGenGameplayProbe?: GameplayAutomationSnapshot;
        }
      ).__stageGenGameplayProbe;
      return probe?.ready === true || probe?.state === "error";
    },
    undefined,
    { timeout: timeoutMs },
  );
  return await page.evaluate(() => {
    const probe = (
      window as typeof window & {
        readonly __stageGenGameplayProbe?: GameplayAutomationSnapshot;
      }
    ).__stageGenGameplayProbe;
    if (!probe) throw new Error("public gameplay probe is missing");
    return probe;
  });
}

async function applyFrame(
  page: Page,
  frame: GameplayFrame,
  heldKeys: Set<GameplayKey>,
): Promise<GameplayAutomationSnapshot> {
  for (const action of frame.actions) {
    if (action.type === "down") {
      await page.keyboard.down(action.key);
      heldKeys.add(action.key);
    } else {
      await page.keyboard.up(action.key);
      heldKeys.delete(action.key);
    }
  }
  const snapshot = await page.evaluate(async () => {
    const advance = (
      window as typeof window & {
        readonly __stageGenAdvanceGameplayFrame?: () => Promise<GameplayAutomationSnapshot>;
      }
    ).__stageGenAdvanceGameplayFrame;
    if (!advance) throw new Error("public gameplay frame hook is missing");
    return await advance();
  });
  if (snapshot.frame !== frame.index + 1) {
    throw new Error(`gameplay frame skipped from ${frame.index} to ${snapshot.frame}`);
  }
  return snapshot;
}

function assertNoBrowserErrors(errors: readonly string[]): void {
  if (errors.length > 0) {
    throw new Error(`browser reported errors: ${errors.slice(0, 8).join(" | ")}`);
  }
}

async function canvasPng(page: Page): Promise<Buffer> {
  const canvases = page.locator("canvas");
  if ((await canvases.count()) !== 1) {
    throw new Error("image repeat proof requires exactly one runtime canvas");
  }
  const canvas = canvases.first();
  const geometry = await canvas.evaluate((element) => ({
    width: (element as HTMLCanvasElement).width,
    height: (element as HTMLCanvasElement).height,
    clientWidth: element.clientWidth,
    clientHeight: element.clientHeight,
  }));
  if (
    geometry.width !== GAMEPLAY_AUTOMATION_VIEWPORT.width ||
    geometry.height !== GAMEPLAY_AUTOMATION_VIEWPORT.height ||
    geometry.clientWidth !== GAMEPLAY_AUTOMATION_VIEWPORT.width ||
    geometry.clientHeight !== GAMEPLAY_AUTOMATION_VIEWPORT.height
  ) {
    throw new Error(`runtime canvas geometry is invalid: ${JSON.stringify(geometry)}`);
  }
  return await canvas.screenshot({ type: "png" });
}

async function collectBrowserProof(
  options: ImageRepeatProofOptions,
): Promise<BrowserProof> {
  const browser = await chromium.launch({ headless: true, timeout: options.timeoutMs });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    locale: "en-US",
    timezoneId: "UTC",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(options.timeoutMs);
  const browserErrors: string[] = [];
  const heldKeys = new Set<GameplayKey>();
  page.on("pageerror", (error) => browserErrors.push(`pageerror:${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(`console:${message.text()}`);
  });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText === "net::ERR_ABORTED") return;
    browserErrors.push(
      `request:${new URL(request.url()).pathname}:${request.failure()?.errorText ?? "failed"}`,
    );
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      browserErrors.push(`http:${response.status()}:${new URL(response.url()).pathname}`);
    }
  });

  try {
    const route = `/preview/${options.tag}?automation=${GAMEPLAY_AUTOMATION_MODE}`;
    const response = await page.goto(`${options.baseUrl}${route}`, {
      waitUntil: "domcontentloaded",
      timeout: options.timeoutMs,
    });
    if (!response?.ok()) throw new Error(`preview returned HTTP ${response?.status() ?? 0}`);
    const initial = await readInitialProbe(page, options.timeoutMs);
    if (initial.frame !== 0 || initial.simulationMs !== 0) {
      throw new Error("image repeat proof did not start at frame zero");
    }
    const selection = selectImageRepeatProofTargets(initial);
    assertNoBrowserErrors(browserErrors);

    let start: PendingCapture | null = null;
    let join: PendingCapture | null = null;
    let end: PendingCapture | null = null;
    for (const frame of GAMEPLAY_TIMELINE) {
      if (frame.index + 1 > LAST_PROOF_FRAME) break;
      const snapshot = await applyFrame(page, frame, heldKeys);
      const currentSelection = selectImageRepeatProofTargets(snapshot);
      assertSelectionStable(selection, currentSelection);
      assertNoBrowserErrors(browserErrors);
      if (
        snapshot.stageIndex !== initial.stageIndex ||
        snapshot.stageId !== initial.stageId
      ) {
        throw new Error("image repeat proof cannot combine traversal across stages");
      }
      if (snapshot.player?.defeated) {
        throw new Error("player was defeated before image repeat proof completed");
      }
      if (snapshot.frame === START_FRAME) {
        start = Object.freeze({
          role: "start",
          bytes: await canvasPng(page),
          snapshot,
          seamScreenX: foregroundJoinScreenX(snapshot, selection.foreground),
        });
        continue;
      }
      if (!start) continue;
      if (!join && isCentralJoinFrame(start.snapshot, snapshot, selection.foreground)) {
        join = Object.freeze({
          role: "join",
          bytes: await canvasPng(page),
          snapshot,
          seamScreenX: foregroundJoinScreenX(snapshot, selection.foreground),
        });
      }
      const backgroundPeriods = repeatPeriodsTravelled(
        start.snapshot,
        snapshot,
        selection.background,
      );
      const foregroundPeriods = repeatPeriodsTravelled(
        start.snapshot,
        snapshot,
        selection.foreground,
      );
      if (join && backgroundPeriods >= REQUIRED_PERIODS && foregroundPeriods >= REQUIRED_PERIODS) {
        end = Object.freeze({
          role: "end",
          bytes: await canvasPng(page),
          snapshot,
          seamScreenX: foregroundJoinScreenX(snapshot, selection.foreground),
        });
        break;
      }
    }
    if (!start || !join || !end) {
      throw new Error(
        "gameplay timeline did not show a central join and two full background/foreground periods before the portal window",
      );
    }
    assertNoBrowserErrors(browserErrors);
    return Object.freeze({
      browserVersion: browser.version(),
      initial,
      selection,
      captures: Object.freeze([start, join, end] as const),
      browserErrors: Object.freeze([...browserErrors]),
    });
  } finally {
    for (const key of heldKeys) {
      await page.keyboard.up(key).catch(() => undefined);
    }
    await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
}

function serializeTarget(target: ImageRepeatProofTarget): Readonly<Record<string, unknown>> {
  return Object.freeze({
    id: target.id,
    kind: target.kind,
    depth_coefficient: target.depthCoefficient,
    schema_version: 2,
    axis: "x",
    decision: target.decision,
    source_path: target.sourcePath,
    repeat_unit_path: target.repeatUnitPath,
    period_px: target.periodPx,
    selected: "verified-v2",
    legacy_fallback_applied: false,
    partner_sprite_count: 0,
    sprite_count: 1,
  });
}

function inspectPng(capture: PendingCapture): Readonly<Record<string, unknown>> {
  const png = PNG.sync.read(capture.bytes, { checkCRC: true, skipRescale: false });
  if (
    png.width !== GAMEPLAY_AUTOMATION_VIEWPORT.width ||
    png.height !== GAMEPLAY_AUTOMATION_VIEWPORT.height
  ) {
    throw new Error(`${capture.role} PNG is not exactly 1280x720`);
  }
  return Object.freeze({
    role: capture.role,
    file: `${capture.role}.png`,
    sha256: createHash("sha256").update(capture.bytes).digest("hex"),
    bytes: capture.bytes.byteLength,
    width: png.width,
    height: png.height,
    frame: capture.snapshot.frame,
    simulation_ms: capture.snapshot.simulationMs,
    camera_scroll_x: capture.snapshot.camera.scrollX,
    camera_scroll_y: capture.snapshot.camera.scrollY,
    camera_zoom: capture.snapshot.camera.zoom,
    foreground_join_screen_x: capture.seamScreenX,
  });
}

async function persistBrowserProof(
  options: ImageRepeatProofOptions,
  manifest: ManifestPreflight,
  proof: BrowserProof,
): Promise<Readonly<Record<string, unknown>>> {
  await fs.mkdir(OUTPUT_ROOT, { recursive: true, mode: 0o700 });
  const outputStat = await fs.lstat(OUTPUT_ROOT);
  const outputRealPath = await fs.realpath(OUTPUT_ROOT);
  if (
    !outputStat.isDirectory() ||
    outputStat.isSymbolicLink() ||
    outputRealPath !== OUTPUT_ROOT
  ) {
    throw new Error("image repeat proof output root must be a real local directory");
  }
  const outputDirectory = await fs.mkdtemp(path.join(OUTPUT_ROOT, `${options.tag}-`));
  const captures = proof.captures.map(inspectPng);
  for (const capture of proof.captures) {
    await fs.writeFile(path.join(outputDirectory, `${capture.role}.png`), capture.bytes, {
      flag: "wx",
      mode: 0o600,
    });
  }
  const start = proof.captures[0].snapshot;
  const end = proof.captures[2].snapshot;
  const report = Object.freeze({
    schema_version: 1,
    state: "unreviewed",
    proof_kind: "single-axis-image-repeat-runtime",
    tag: options.tag,
    route: `/preview/${options.tag}?automation=${GAMEPLAY_AUTOMATION_MODE}`,
    capture_target: "phaser-canvas-only",
    shell_included: false,
    seam_mask_or_runtime_mutation_applied: false,
    generated_manifest: Object.freeze({
      path: manifest.path,
      sha256: manifest.sha256,
      bytes: manifest.bytes,
      artifact_count: manifest.artifactCount,
      build_id: manifest.buildId,
    }),
    browser: Object.freeze({ name: "chromium", version: proof.browserVersion }),
    runtime: Object.freeze({
      automation_version: proof.initial.version,
      stage_index: start.stageIndex,
      stage_id: start.stageId,
      start_frame: start.frame,
      end_frame: end.frame,
      camera_start_x: start.camera.scrollX,
      camera_end_x: end.camera.scrollX,
      camera_travel_x: end.camera.scrollX - start.camera.scrollX,
      errors: proof.initial.errors,
      diagnostics: proof.initial.diagnostics,
      browser_errors: proof.browserErrors,
    }),
    assertions: Object.freeze({
      manifest_image_repeat_available: true,
      verified_v2_selected: true,
      exact_repeat_unit_period_used: true,
      one_tile_sprite_per_selected_layer: true,
      legacy_fallback_applied: false,
      partner_sprite_count: 0,
      foreground_overlap_source_px: 0,
      required_periods: REQUIRED_PERIODS,
      background_periods_travelled: repeatPeriodsTravelled(
        start,
        end,
        proof.selection.background,
      ),
      foreground_periods_travelled: repeatPeriodsTravelled(
        start,
        end,
        proof.selection.foreground,
      ),
    }),
    proof_targets: Object.freeze({
      background: serializeTarget(proof.selection.background),
      foreground: serializeTarget(proof.selection.foreground),
    }),
    selected_artifacts: Object.freeze(proof.selection.all.map(serializeTarget)),
    captures: Object.freeze(captures),
  });
  const reportBytes = Buffer.from(`${JSON.stringify(report, null, 2)}\n`, "utf8");
  const reportPath = path.join(outputDirectory, "report.json");
  await fs.writeFile(reportPath, reportBytes, { flag: "wx", mode: 0o600 });
  return Object.freeze({
    output_directory: path.relative(REPO_ROOT, outputDirectory).split(path.sep).join("/"),
    report: path.relative(REPO_ROOT, reportPath).split(path.sep).join("/"),
    report_sha256: createHash("sha256").update(reportBytes).digest("hex"),
    captures,
  });
}

export async function runImageRepeatProof(
  options: ImageRepeatProofOptions,
): Promise<Readonly<Record<string, unknown>>> {
  const manifest = await manifestPreflight(options.tag);
  const proof = await collectBrowserProof(options);
  return await persistBrowserProof(options, manifest, proof);
}

if (import.meta.main) {
  try {
    const args = process.argv.slice(2);
    if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
      process.stdout.write(`${IMAGE_REPEAT_PROOF_USAGE}\n`);
    } else {
      const result = await runImageRepeatProof(parseImageRepeatProofArgs(args));
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    }
  } catch (error) {
    process.stderr.write(
      `image repeat proof failed: ${error instanceof Error ? error.message : String(error)}\n`,
    );
    process.exitCode = 1;
  }
}
