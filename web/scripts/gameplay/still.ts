#!/usr/bin/env bun

import { spawn, type ChildProcess } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Page } from "playwright";
import { PNG } from "pngjs";
import {
  GAMEPLAY_AUTOMATION_MODE,
  GAMEPLAY_AUTOMATION_VIEWPORT,
  GAMEPLAY_STILL_MIN_ACTOR_HEIGHT,
  GAMEPLAY_STILL_MIN_PICKUP_HEIGHT,
  GAMEPLAY_STILL_MIN_PICKUP_WIDTH,
  GAMEPLAY_STILL_MIN_PORTAL_HEIGHT,
  GAMEPLAY_STILL_SAFE_MARGIN,
  type GameplayAutomationSnapshot,
  type GameplayWorldBoundsProbe,
} from "../../lib/runtime/automation";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const NEXT_CLI = path.join(WEB_ROOT, "node_modules/next/dist/bin/next");
const OUTPUT_ROOT = path.join(REPO_ROOT, "output/playwright");
const SAFE_TAG = /^[a-z0-9][a-z0-9-]{0,127}$/;
const MAX_LOG_CHARS = 32_000;

export const GAMEPLAY_STILL_USAGE =
  "usage: bun scripts/gameplay/still.ts --tag <run-tag> " +
  "[--output output/playwright/<name>.png] [--timeout-ms 120000]";

export const GAMEPLAY_STILL_REPORT_SCHEMA_VERSION = 1 as const;
export const GAMEPLAY_STILL_REPORT_KIND = "gameplay-still-report-v1" as const;

export type GameplayStillReport = Readonly<{
  schema_version: typeof GAMEPLAY_STILL_REPORT_SCHEMA_VERSION;
  kind: typeof GAMEPLAY_STILL_REPORT_KIND;
  state: "unreviewed";
  capture_target: "phaser-canvas-only";
  shell_included: false;
  development_overlay_included: false;
  route: string;
  tag: string;
  build_id: string;
  output: string;
  sidecar: string;
  width: 1280;
  height: 720;
  sha256: string;
  runtime: Readonly<{
    errors: readonly string[];
    diagnostics: readonly string[];
    loaded_asset_keys: readonly string[];
    visible_tier_count: number;
    visible_ladder_count: number;
  }>;
}>;

export type GameplayStillOptions = Readonly<{
  tag: string;
  output: string;
  timeoutMs: number;
}>;

function requireValue(args: readonly string[], index: number, flag: string): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

function safeOutput(value: string): string {
  if (
    path.isAbsolute(value) ||
    value.includes("\0") ||
    value.split(/[\\/]/).some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new Error("still output must be a stable repository-relative path");
  }
  const normalized = value.split(path.sep).join("/");
  if (
    !normalized.startsWith("output/playwright/") ||
    !/^[a-z0-9][a-z0-9._-]{0,123}\.png$/.test(path.posix.basename(normalized))
  ) {
    throw new Error("still output must be a lowercase PNG below output/playwright");
  }
  return normalized;
}

const GAMEPLAY_STILL_REPORT_KEYS = [
  "schema_version",
  "kind",
  "state",
  "capture_target",
  "shell_included",
  "development_overlay_included",
  "route",
  "tag",
  "build_id",
  "output",
  "sidecar",
  "width",
  "height",
  "sha256",
  "runtime",
] as const;

const GAMEPLAY_STILL_RUNTIME_KEYS = [
  "errors",
  "diagnostics",
  "loaded_asset_keys",
  "visible_tier_count",
  "visible_ladder_count",
] as const;

function reportRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new Error(`${label} must be a plain object`);
  }
  return value as Record<string, unknown>;
}

function exactReportKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  label: string,
): void {
  const allowed = new Set(expected);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new Error(`${label}.${key} is not a supported key`);
  }
  for (const key of expected) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      throw new Error(`${label}.${key} is required`);
    }
  }
}

function reportLiteral<const Value extends string | number | boolean>(
  value: unknown,
  expected: Value,
  label: string,
): Value {
  if (value !== expected) throw new Error(`${label} must equal ${JSON.stringify(expected)}`);
  return expected;
}

function stableReportText(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    !value ||
    value !== value.trim() ||
    value.includes("\0")
  ) {
    throw new Error(`${label} must be a non-empty trimmed string`);
  }
  return value;
}

function reportStringArray(value: unknown, label: string): readonly string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return Object.freeze(
    Array.from(value, (item, index) => stableReportText(item, `${label}[${index}]`)),
  );
}

function reportCount(value: unknown, minimum: number, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    throw new Error(`${label} must be a safe integer greater than or equal to ${minimum}`);
  }
  return value as number;
}

/** Parse the one exact current report persisted beside and returned for a gameplay still. */
export function parseGameplayStillReport(value: unknown): GameplayStillReport {
  const root = reportRecord(value, "gameplay_still_report");
  exactReportKeys(root, GAMEPLAY_STILL_REPORT_KEYS, "gameplay_still_report");
  const schemaVersion = reportLiteral(
    root.schema_version,
    GAMEPLAY_STILL_REPORT_SCHEMA_VERSION,
    "gameplay_still_report.schema_version",
  );
  const kind = reportLiteral(
    root.kind,
    GAMEPLAY_STILL_REPORT_KIND,
    "gameplay_still_report.kind",
  );
  const state = reportLiteral(root.state, "unreviewed", "gameplay_still_report.state");
  const captureTarget = reportLiteral(
    root.capture_target,
    "phaser-canvas-only",
    "gameplay_still_report.capture_target",
  );
  const shellIncluded = reportLiteral(
    root.shell_included,
    false,
    "gameplay_still_report.shell_included",
  );
  const developmentOverlayIncluded = reportLiteral(
    root.development_overlay_included,
    false,
    "gameplay_still_report.development_overlay_included",
  );
  const tag = stableReportText(root.tag, "gameplay_still_report.tag");
  if (!SAFE_TAG.test(tag)) throw new Error("gameplay_still_report.tag is invalid");
  const route = reportLiteral(
    root.route,
    `/preview/${tag}?automation=${GAMEPLAY_AUTOMATION_MODE}`,
    "gameplay_still_report.route",
  );
  const buildId = stableReportText(root.build_id, "gameplay_still_report.build_id");
  const output = safeOutput(stableReportText(root.output, "gameplay_still_report.output"));
  const sidecar = reportLiteral(
    root.sidecar,
    `${output}.capture.json`,
    "gameplay_still_report.sidecar",
  );
  const width = reportLiteral(root.width, 1280, "gameplay_still_report.width");
  const height = reportLiteral(root.height, 720, "gameplay_still_report.height");
  const sha256 = stableReportText(root.sha256, "gameplay_still_report.sha256");
  if (!/^[a-f0-9]{64}$/.test(sha256)) {
    throw new Error("gameplay_still_report.sha256 must be a lowercase SHA-256 digest");
  }

  const runtimeRoot = reportRecord(root.runtime, "gameplay_still_report.runtime");
  exactReportKeys(runtimeRoot, GAMEPLAY_STILL_RUNTIME_KEYS, "gameplay_still_report.runtime");
  const errors = reportStringArray(runtimeRoot.errors, "gameplay_still_report.runtime.errors");
  const diagnostics = reportStringArray(
    runtimeRoot.diagnostics,
    "gameplay_still_report.runtime.diagnostics",
  );
  if (errors.length !== 0 || diagnostics.length !== 0) {
    throw new Error("gameplay_still_report.runtime must record a clean capture");
  }
  const loadedAssetKeys = reportStringArray(
    runtimeRoot.loaded_asset_keys,
    "gameplay_still_report.runtime.loaded_asset_keys",
  );
  if (loadedAssetKeys.length === 0 || new Set(loadedAssetKeys).size !== loadedAssetKeys.length) {
    throw new Error("gameplay_still_report.runtime.loaded_asset_keys must be non-empty and unique");
  }
  const visibleTierCount = reportCount(
    runtimeRoot.visible_tier_count,
    3,
    "gameplay_still_report.runtime.visible_tier_count",
  );
  const visibleLadderCount = reportCount(
    runtimeRoot.visible_ladder_count,
    1,
    "gameplay_still_report.runtime.visible_ladder_count",
  );

  return Object.freeze({
    schema_version: schemaVersion,
    kind,
    state,
    capture_target: captureTarget,
    shell_included: shellIncluded,
    development_overlay_included: developmentOverlayIncluded,
    route,
    tag,
    build_id: buildId,
    output,
    sidecar,
    width,
    height,
    sha256,
    runtime: Object.freeze({
      errors,
      diagnostics,
      loaded_asset_keys: loadedAssetKeys,
      visible_tier_count: visibleTierCount,
      visible_ladder_count: visibleLadderCount,
    }),
  });
}

export function parseGameplayStillArgs(args: readonly string[]): GameplayStillOptions {
  let tag: string | undefined;
  let output: string | undefined;
  let timeoutMs = 120_000;
  const seen = new Set<string>();
  for (let index = 0; index < args.length; index += 1) {
    const flag = args[index]!;
    if (seen.has(flag)) throw new Error(`duplicate option: ${flag}`);
    seen.add(flag);
    if (flag === "--tag") {
      tag = requireValue(args, index, flag);
      index += 1;
    } else if (flag === "--output") {
      output = safeOutput(requireValue(args, index, flag));
      index += 1;
    } else if (flag === "--timeout-ms") {
      const value = requireValue(args, index, flag);
      if (!/^[1-9]\d*$/.test(value)) throw new Error("timeout must be an integer");
      timeoutMs = Number(value);
      if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 10_000 || timeoutMs > 600_000) {
        throw new Error("timeout must be between 10000 and 600000");
      }
      index += 1;
    } else {
      throw new Error(`unknown gameplay still option: ${flag}`);
    }
  }
  if (!tag || !SAFE_TAG.test(tag)) throw new Error("a valid --tag is required");
  return Object.freeze({
    tag,
    output: output ?? `output/playwright/${tag}.canvas.png`,
    timeoutMs,
  });
}

function projectBounds(
  bounds: GameplayWorldBoundsProbe,
  camera: GameplayAutomationSnapshot["camera"],
): GameplayWorldBoundsProbe {
  const centerX = GAMEPLAY_AUTOMATION_VIEWPORT.width / 2;
  const centerY = GAMEPLAY_AUTOMATION_VIEWPORT.height / 2;
  const x = (world: number) =>
    centerX + (world - (camera.scrollX + centerX)) * camera.zoom;
  const y = (world: number) =>
    centerY + (world - (camera.scrollY + centerY)) * camera.zoom;
  return Object.freeze({
    left: x(bounds.left),
    right: x(bounds.right),
    top: y(bounds.top),
    bottom: y(bounds.bottom),
  });
}

function assertNotPartiallyVisible(
  label: string,
  bounds: GameplayWorldBoundsProbe,
  camera: GameplayAutomationSnapshot["camera"],
  margin: number,
): GameplayWorldBoundsProbe | null {
  const projected = projectBounds(bounds, camera);
  const intersects =
    projected.right > 0 &&
    projected.left < GAMEPLAY_AUTOMATION_VIEWPORT.width &&
    projected.bottom > 0 &&
    projected.top < GAMEPLAY_AUTOMATION_VIEWPORT.height;
  if (
    intersects &&
    (projected.left < margin ||
      projected.right > GAMEPLAY_AUTOMATION_VIEWPORT.width - margin ||
      projected.top < margin ||
      projected.bottom > GAMEPLAY_AUTOMATION_VIEWPORT.height - margin)
  ) {
    throw new Error(`${label} is partially visible outside the capture-safe viewport`);
  }
  return intersects ? projected : null;
}

function assertRequiredVisible(
  label: string,
  bounds: GameplayWorldBoundsProbe,
  camera: GameplayAutomationSnapshot["camera"],
  margin: number,
  minimumSize: Readonly<{ width?: number; height?: number }>,
): void {
  const projected = assertNotPartiallyVisible(label, bounds, camera, margin);
  if (!projected) {
    throw new Error(`${label} must be fully visible in the capture-safe viewport`);
  }
  if (!meetsMinimumProjectedSize(projected, minimumSize)) {
    throw new Error(`${label} is too small to identify in the capture`);
  }
}

function meetsMinimumProjectedSize(
  projected: GameplayWorldBoundsProbe,
  minimum: Readonly<{ width?: number; height?: number }>,
): boolean {
  return (
    projected.right - projected.left >= (minimum.width ?? 0) &&
    projected.bottom - projected.top >= (minimum.height ?? 0)
  );
}

export function validateGameplayStillProbe(snapshot: GameplayAutomationSnapshot): void {
  if (!snapshot.ready || snapshot.state !== "ready" || snapshot.frame !== 0) {
    throw new Error("still capture requires a ready frame-zero gameplay probe");
  }
  if (snapshot.errors.length > 0 || snapshot.diagnostics.length > 0) {
    throw new Error("still capture requires zero runtime errors and diagnostics");
  }
  const requiredKeys = [
    "tileset",
    "ladder",
    "character_climb",
    "character_idle",
    "character_walk",
    "character_run",
    "character_jump",
    "character_crawl",
    "character_attack",
    "items",
    "inventory",
    "portal",
  ];
  for (const key of requiredKeys) {
    if (!snapshot.assetKeys.includes(key)) {
      throw new Error(`still capture is missing required loaded key: ${key}`);
    }
  }
  if (
    !snapshot.assetKeys.some((key) => key.startsWith("spec:")) ||
    !snapshot.layers.some(
      (layer) => layer.kind === "sky" && layer.render.visible,
    ) ||
    !snapshot.assetKeys.some((key) => key.startsWith("mob_") && key.endsWith("_idle"))
  ) {
    throw new Error("still capture is missing required spec, sky-layer, or mob roles");
  }
  const visiblePlatforms = snapshot.platforms.filter((platform) => platform.visible);
  if (
    new Set(visiblePlatforms.map((platform) => platform.deckY)).size < 3 ||
    !snapshot.ladders.some((ladder) => ladder.visible)
  ) {
    throw new Error("still capture must visibly include three tiers and a ladder");
  }
  const foregrounds = snapshot.layers.filter(
    (layer) => layer.kind === "near-foreground" && layer.render.visible,
  );
  if (
    foregrounds.length !== 1 ||
    !foregrounds[0]!.foreground ||
    foregrounds[0]!.foreground!.meaningfulContentScreenBounds.top <
      foregrounds[0]!.safeBounds.top ||
    foregrounds[0]!.render.spriteCount !== 1
  ) {
    throw new Error("still capture foreground is outside its actor-safe band");
  }
  if (!snapshot.inventory.visible || !snapshot.inventory.bounds) {
    throw new Error("still capture HUD must be visible");
  }
  const hud = snapshot.inventory.bounds;
  if (
    hud.left < 24 ||
    hud.right > GAMEPLAY_AUTOMATION_VIEWPORT.width - 24 ||
    hud.top < 24 ||
    hud.bottom > GAMEPLAY_AUTOMATION_VIEWPORT.height - 24
  ) {
    throw new Error("still capture HUD escapes its 24px safe margin");
  }
  if (!snapshot.player) {
    throw new Error("still capture requires one fully visible player");
  }
  assertRequiredVisible(
    "player",
    snapshot.player.renderBounds,
    snapshot.camera,
    GAMEPLAY_STILL_SAFE_MARGIN,
    { height: GAMEPLAY_STILL_MIN_ACTOR_HEIGHT },
  );

  const visibleLiveMobs = snapshot.mobs.filter((mob, index) => {
    if (!mob.visible) return false;
    const projected = assertNotPartiallyVisible(
      `mob ${index}`,
      mob.renderBounds,
      snapshot.camera,
      GAMEPLAY_STILL_SAFE_MARGIN,
    );
    return (
      mob.alive &&
      projected !== null &&
      meetsMinimumProjectedSize(projected, {
        height: GAMEPLAY_STILL_MIN_ACTOR_HEIGHT,
      })
    );
  });
  if (visibleLiveMobs.length === 0) {
    throw new Error("still capture requires one fully visible identifiable live mob");
  }

  const visiblePortals = snapshot.portals.filter((portal) => {
    const projected = assertNotPartiallyVisible(
      `${portal.kind} portal`,
      {
        left: portal.x - portal.w / 2,
        right: portal.x + portal.w / 2,
        top: portal.y - portal.h,
        bottom: portal.y,
      },
      snapshot.camera,
      GAMEPLAY_STILL_SAFE_MARGIN,
    );
    return (
      projected !== null &&
      meetsMinimumProjectedSize(projected, {
        height: GAMEPLAY_STILL_MIN_PORTAL_HEIGHT,
      })
    );
  });
  if (visiblePortals.length === 0) {
    throw new Error("still capture requires one fully visible identifiable portal");
  }

  const visiblePickups = snapshot.worldItems.filter((item, index) => {
    const projected = assertNotPartiallyVisible(
      `pickup ${index}`,
      item.renderBounds,
      snapshot.camera,
      GAMEPLAY_STILL_SAFE_MARGIN,
    );
    return (
      projected !== null &&
      meetsMinimumProjectedSize(projected, {
        width: GAMEPLAY_STILL_MIN_PICKUP_WIDTH,
        height: GAMEPLAY_STILL_MIN_PICKUP_HEIGHT,
      })
    );
  });
  if (visiblePickups.length === 0) {
    throw new Error("still capture requires one fully visible identifiable pickup");
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

async function stopServer(server: ChildProcess): Promise<void> {
  if (server.exitCode !== null || server.signalCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise<void>((resolve) => server.once("exit", () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (server.exitCode === null && server.signalCode === null) server.kill("SIGKILL");
}

async function waitForServer(baseUrl: string, deadline: number): Promise<void> {
  while (Date.now() < deadline) {
    try {
      const response = await fetch(baseUrl, { redirect: "manual" });
      if (response.status > 0) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("production preview server did not become ready");
}

async function readProbe(page: Page, timeoutMs: number): Promise<GameplayAutomationSnapshot> {
  await page.waitForFunction(
    () => {
      const probe = (
        window as Window & {
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
      window as Window & {
        readonly __stageGenGameplayProbe?: GameplayAutomationSnapshot;
      }
    ).__stageGenGameplayProbe;
    if (!probe) throw new Error("gameplay probe is missing");
    return probe;
  });
}

export async function captureGameplayStill(
  options: GameplayStillOptions,
): Promise<GameplayStillReport> {
  const runDirectory = path.join(REPO_ROOT, "out", options.tag);
  const [runStat, buildId, nextStat] = await Promise.all([
    fs.lstat(runDirectory),
    fs.readFile(path.join(WEB_ROOT, ".next/BUILD_ID"), "utf8"),
    fs.lstat(NEXT_CLI),
  ]).catch(() => {
    throw new Error("run, dependencies, or production build missing; run `bun run build` first");
  });
  if (!runStat.isDirectory() || runStat.isSymbolicLink() || !nextStat.isFile()) {
    throw new Error("still capture inputs must be real local files and directories");
  }
  const output = path.join(REPO_ROOT, ...options.output.split("/"));
  if (!output.startsWith(`${OUTPUT_ROOT}${path.sep}`)) {
    throw new Error("still capture output escapes output/playwright");
  }
  await fs.mkdir(path.dirname(output), { recursive: true, mode: 0o700 });
  const port = await freeLoopbackPort();
  const logs: string[] = [];
  const appendLog = (chunk: Buffer) => {
    logs.push(chunk.toString("utf8"));
    while (logs.join("").length > MAX_LOG_CHARS) logs.shift();
  };
  const server = spawn(
    process.execPath,
    [NEXT_CLI, "start", "-H", "127.0.0.1", "-p", String(port)],
    {
      cwd: WEB_ROOT,
      env: {
        NODE_ENV: "production",
        NEXT_TELEMETRY_DISABLED: "1",
        STAGE_GEN_GAMEPLAY_AUTOMATION: "1",
        STAGE_GEN_OUT_DIR: path.join(REPO_ROOT, "out"),
        PATH: process.env.PATH,
        TMPDIR: process.env.TMPDIR,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  server.stdout.on("data", appendLog);
  server.stderr.on("data", appendLog);
  const browser = await chromium.launch({ headless: true, timeout: options.timeoutMs });
  try {
    const baseUrl = `http://127.0.0.1:${port}`;
    await waitForServer(baseUrl, Date.now() + options.timeoutMs);
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 1,
      locale: "en-US",
      timezoneId: "UTC",
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const browserErrors: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(`pageerror:${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(`console:${message.text()}`);
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        browserErrors.push(`http:${response.status()}:${new URL(response.url()).pathname}`);
      }
    });
    const response = await page.goto(
      `${baseUrl}/preview/${options.tag}?automation=${GAMEPLAY_AUTOMATION_MODE}`,
      { waitUntil: "domcontentloaded", timeout: options.timeoutMs },
    );
    if (!response?.ok()) throw new Error(`preview returned HTTP ${response?.status() ?? 0}`);
    const probe = await readProbe(page, options.timeoutMs);
    validateGameplayStillProbe(probe);
    if (browserErrors.length > 0) {
      throw new Error(`browser reported errors: ${browserErrors.slice(0, 5).join(" | ")}`);
    }
    const canvases = page.locator("canvas");
    if ((await canvases.count()) !== 1) throw new Error("capture requires exactly one canvas");
    const canvas = canvases.first();
    const geometry = await canvas.evaluate((element) => {
      const canvasElement = element as HTMLCanvasElement;
      return {
        width: canvasElement.width,
        height: canvasElement.height,
        clientWidth: canvasElement.clientWidth,
        clientHeight: canvasElement.clientHeight,
      };
    });
    if (
      geometry.width !== 1280 ||
      geometry.height !== 720 ||
      geometry.clientWidth !== 1280 ||
      geometry.clientHeight !== 720
    ) {
      throw new Error(`canvas geometry is not 1280x720: ${JSON.stringify(geometry)}`);
    }
    const bytes = await canvas.screenshot({ type: "png" });
    const png = PNG.sync.read(bytes, { checkCRC: true, skipRescale: false });
    if (png.width !== 1280 || png.height !== 720) {
      throw new Error("canvas-only PNG is not exactly 1280x720");
    }
    const digest = createHash("sha256").update(bytes).digest("hex");
    const sidecar = `${output}.capture.json`;
    const relativeSidecar = path.relative(REPO_ROOT, sidecar).split(path.sep).join("/");
    const report = parseGameplayStillReport({
      schema_version: GAMEPLAY_STILL_REPORT_SCHEMA_VERSION,
      kind: GAMEPLAY_STILL_REPORT_KIND,
      state: "unreviewed",
      capture_target: "phaser-canvas-only",
      shell_included: false,
      development_overlay_included: false,
      route: `/preview/${options.tag}?automation=${GAMEPLAY_AUTOMATION_MODE}`,
      tag: options.tag,
      build_id: buildId.trim(),
      output: options.output,
      sidecar: relativeSidecar,
      width: png.width,
      height: png.height,
      sha256: digest,
      runtime: {
        errors: probe.errors,
        diagnostics: probe.diagnostics,
        loaded_asset_keys: probe.assetKeys,
        visible_tier_count: new Set(
          probe.platforms.filter((platform) => platform.visible).map((platform) => platform.deckY),
        ).size,
        visible_ladder_count: probe.ladders.filter((ladder) => ladder.visible).length,
      },
    });
    const metadata = Buffer.from(
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
    await fs.writeFile(output, bytes, { flag: "wx", mode: 0o600 });
    try {
      await fs.writeFile(sidecar, metadata, { flag: "wx", mode: 0o600 });
    } catch (error) {
      await fs.unlink(output);
      throw error;
    }
    await context.close();
    return report;
  } catch (error) {
    const detail = logs.join("").slice(-MAX_LOG_CHARS);
    throw new Error(
      `${error instanceof Error ? error.message : String(error)}` +
        (detail ? `\nproduction server log:\n${detail}` : ""),
      { cause: error },
    );
  } finally {
    await browser.close();
    await stopServer(server);
  }
}

if (import.meta.main) {
  try {
    const args = process.argv.slice(2);
    if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
      process.stdout.write(`${GAMEPLAY_STILL_USAGE}\n`);
    } else {
      const result = await captureGameplayStill(parseGameplayStillArgs(args));
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    }
  } catch (error) {
    process.stderr.write(
      `gameplay still capture failed: ${error instanceof Error ? error.message : String(error)}\n`,
    );
    process.exitCode = 1;
  }
}
