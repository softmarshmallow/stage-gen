#!/usr/bin/env bun

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { promises as fs } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Browser, type Page } from "playwright";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(SCRIPT_DIR, "../..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..");
const NEXT_CLI = path.join(WEB_ROOT, "node_modules/next/dist/bin/next");
const OUTPUT_ROOT = path.join(WEB_ROOT, "output/playwright/dialogue-overlay");
const MAX_SERVER_LOG_CHARS = 32_000;
const SAFE_TAG = /^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$/;

export const DEFAULT_DIALOGUE_OVERLAY_TAG =
  "whimsical-storybook-fantasy-7e5ab98f-game-v1-0034f94ce0-f0440de8-chroma";
export const DIALOGUE_OVERLAY_USAGE =
  "usage: bun scripts/gameplay/dialogue-overlay.ts " +
  "[--tag <run-tag>] [--timeout-ms 120000]";

export type DialogueOverlayOptions = Readonly<{
  tag: string;
  timeoutMs: number;
}>;

type ExpectedBeat = Readonly<{
  expressionState: "neutral" | "delighted" | "flustered" | "concerned";
  speaker: "Elowen" | "You";
  line: string;
}>;

const EXPECTED_BEATS: readonly ExpectedBeat[] = Object.freeze([
  Object.freeze({
    expressionState: "neutral",
    speaker: "Elowen",
    line: "The sunpetals are ready. I saved the brightest bundle for you.",
  }),
  Object.freeze({
    expressionState: "delighted",
    speaker: "You",
    line: "You remembered which flowers I liked.",
  }),
  Object.freeze({
    expressionState: "flustered",
    speaker: "Elowen",
    line: "Some things are very easy to remember.",
  }),
  Object.freeze({
    expressionState: "concerned",
    speaker: "Elowen",
    line: "But we should hurry—the wind says a summer storm is close.",
  }),
]);

type DialogueProbe = Readonly<{
  open: boolean;
  speaker: string;
  line: string;
  lineIndex: number;
  lineCount: number;
  expressionState: string | null;
  portraitVisible: boolean;
}>;

type VillageProbe = Readonly<{
  name: string;
  npcs: readonly Readonly<{
    slot: number;
    name: string;
    x: number;
    y: number;
    inRange: boolean;
  }>[];
  dialogue: DialogueProbe;
}>;

type SceneProbe = Readonly<{
  stageKind: string;
  consoleErrors: readonly string[];
  diagnostics: readonly string[];
  inventoryVisible?: boolean;
  player?: Readonly<{ x: number }>;
  village?: VillageProbe;
}>;

type CapturedBeat = Readonly<{
  expressionState: ExpectedBeat["expressionState"];
  speaker: string;
  line: string;
  screenshot: string;
}>;

function valueAfter(args: readonly string[], index: number, flag: string): string {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

export function parseDialogueOverlayArgs(args: readonly string[]): DialogueOverlayOptions {
  let tag = DEFAULT_DIALOGUE_OVERLAY_TAG;
  let timeoutMs = 120_000;
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
    throw new Error(`unknown dialogue overlay option: ${flag}`);
  }
  if (!SAFE_TAG.test(tag)) throw new Error("dialogue overlay tag is invalid");
  return Object.freeze({ tag, timeoutMs });
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

async function stopServer(server: ChildProcessWithoutNullStreams): Promise<void> {
  if (!server.pid || server.exitCode !== null || server.signalCode !== null) return;
  server.kill("SIGTERM");
  await Promise.race([
    new Promise<void>((resolve) => server.once("exit", () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 5_000)),
  ]);
  if (server.exitCode === null && server.signalCode === null) server.kill("SIGKILL");
}

async function waitForServer(
  server: ChildProcessWithoutNullStreams,
  baseUrl: string,
  timeoutMs: number,
  serverLog: () => string,
  serverFailure: () => Error | undefined,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const failure = serverFailure();
    if (failure) throw new Error(`production preview failed to start: ${failure.message}`);
    if (server.exitCode !== null || server.signalCode !== null) {
      throw new Error(
        "production preview exited before readiness " +
          `(code ${server.exitCode ?? "none"}, signal ${server.signalCode ?? "none"}): ` +
          serverLog(),
      );
    }
    try {
      const response = await fetch(baseUrl, { redirect: "manual" });
      if (response.status >= 200 && response.status < 500) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`production preview did not become ready: ${serverLog()}`);
}

async function readSceneProbe(page: Page): Promise<SceneProbe> {
  return await page.evaluate(() => {
    const probe = (
      window as typeof window & {
        __sceneProbes?: unknown;
      }
    ).__sceneProbes;
    if (!probe || typeof probe !== "object") throw new Error("scene probe is missing");
    return structuredClone(probe) as SceneProbe;
  });
}

function requireCleanProbe(probe: SceneProbe): void {
  if (probe.consoleErrors.length > 0 || probe.diagnostics.length > 0) {
    throw new Error(
      `scene probe reported errors or diagnostics: ${[
        ...probe.consoleErrors,
        ...probe.diagnostics,
      ].join(" | ")}`,
    );
  }
}

function requireInventoryVisibility(
  probe: SceneProbe,
  expected: boolean,
  context: string,
): void {
  if (probe.inventoryVisible !== expected) {
    throw new Error(
      `inventory HUD must be ${expected ? "visible" : "hidden"} ${context}`,
    );
  }
}

function requireElowenInteractionPrompt(
  probe: SceneProbe,
  expected: boolean,
  context: string,
): void {
  const inRange = probe.village?.npcs.find((npc) => npc.slot === 2)?.inRange;
  if (inRange !== expected) {
    throw new Error(
      `Elowen interaction prompt must be ${expected ? "visible" : "hidden"} ${context}`,
    );
  }
}

function requireVillage(probe: SceneProbe): VillageProbe {
  if (probe.stageKind !== "village" || !probe.village) {
    throw new Error("dialogue overlay verifier requires the opening village stage");
  }
  const elowen = probe.village.npcs.find((npc) => npc.slot === 2);
  if (!elowen || elowen.name !== "Elowen Vale") {
    throw new Error("village probe does not bind Elowen Vale to resident slot 2");
  }
  return probe.village;
}

function requireDialogueProbeShape(dialogue: DialogueProbe): void {
  if (
    typeof dialogue.open !== "boolean" ||
    typeof dialogue.speaker !== "string" ||
    typeof dialogue.line !== "string" ||
    !Number.isSafeInteger(dialogue.lineIndex) ||
    !Number.isSafeInteger(dialogue.lineCount) ||
    (dialogue.expressionState !== null && typeof dialogue.expressionState !== "string") ||
    typeof dialogue.portraitVisible !== "boolean"
  ) {
    throw new Error("dialogue overlay probe does not expose the required camelCase contract");
  }
}

async function waitForElowenRange(page: Page, timeoutMs: number): Promise<void> {
  await page.waitForFunction(
    () => {
      const probe = (
        window as typeof window & {
          __sceneProbes?: SceneProbe;
        }
      ).__sceneProbes;
      return probe?.village?.npcs.some(
        (npc) => npc.slot === 2 && npc.name === "Elowen Vale" && npc.inRange,
      );
    },
    undefined,
    { timeout: timeoutMs },
  );
}

async function waitForBeat(
  page: Page,
  expected: ExpectedBeat,
  index: number,
  timeoutMs: number,
): Promise<DialogueProbe> {
  await page.waitForFunction(
    ({ beat, lineIndex }) => {
      const probe = (
        window as typeof window & {
          __sceneProbes?: SceneProbe;
        }
      ).__sceneProbes;
      const dialogue = probe?.village?.dialogue;
      const elowen = probe?.village?.npcs.find((npc) => npc.slot === 2);
      return (
        dialogue?.open === true &&
        dialogue.lineIndex === lineIndex &&
        dialogue.lineCount === 4 &&
        dialogue.speaker === beat.speaker &&
        dialogue.line === beat.line &&
        dialogue.expressionState === beat.expressionState &&
        dialogue.portraitVisible === true &&
        probe?.inventoryVisible === false &&
        elowen?.inRange === false
      );
    },
    { beat: expected, lineIndex: index },
    { timeout: timeoutMs },
  );
  const dialogue = requireVillage(await readSceneProbe(page)).dialogue;
  requireDialogueProbeShape(dialogue);
  return dialogue;
}

async function playerX(page: Page): Promise<number> {
  const x = (await readSceneProbe(page)).player?.x;
  if (!Number.isFinite(x)) throw new Error("scene probe has no finite player x position");
  return x!;
}

async function captureCanvas(
  page: Page,
  captureDirectory: string,
  filename: string,
): Promise<string> {
  const canvas = page.locator("canvas").first();
  const target = path.join(captureDirectory, filename);
  await canvas.screenshot({ path: target, type: "png" });
  return path
    .relative(WEB_ROOT, target)
    .split(path.sep)
    .join("/");
}

function throwBrowserErrors(errors: readonly string[]): void {
  if (errors.length === 0) return;
  throw new Error(`browser reported ${errors.length} error(s): ${errors.join(" | ")}`);
}

export async function verifyDialogueOverlay(options: DialogueOverlayOptions): Promise<unknown> {
  const runDirectory = path.join(REPO_ROOT, "out", options.tag);
  const [runStat, nextStat, buildId] = await Promise.all([
    fs.lstat(runDirectory),
    fs.lstat(NEXT_CLI),
    fs.readFile(path.join(WEB_ROOT, ".next/BUILD_ID"), "utf8"),
  ]).catch(() => {
    throw new Error("run, dependencies, or production build missing; run `bun run build` first");
  });
  if (
    !runStat.isDirectory() ||
    runStat.isSymbolicLink() ||
    !nextStat.isFile() ||
    nextStat.isSymbolicLink()
  ) {
    throw new Error("dialogue overlay inputs must be regular local files and directories");
  }

  await fs.mkdir(OUTPUT_ROOT, { recursive: true, mode: 0o700 });
  const captureDirectory = await fs.mkdtemp(path.join(OUTPUT_ROOT, `${options.tag}-`));
  const port = await freeLoopbackPort();
  const logs: string[] = [];
  const appendLog = (chunk: Buffer) => {
    logs.push(chunk.toString("utf8"));
    while (logs.join("").length > MAX_SERVER_LOG_CHARS) logs.shift();
  };
  const server = spawn(
    process.execPath,
    [NEXT_CLI, "start", "--hostname", "127.0.0.1", "--port", String(port)],
    {
      cwd: WEB_ROOT,
      env: {
        NODE_ENV: "production",
        NEXT_TELEMETRY_DISABLED: "1",
        STAGE_GEN_OUT_DIR: path.join(REPO_ROOT, "out"),
        PATH: process.env.PATH,
        TMPDIR: process.env.TMPDIR,
      },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let serverFailure: Error | undefined;
  server.once("error", (error) => {
    serverFailure = error;
    appendLog(Buffer.from(`production server error: ${error.message}\n`, "utf8"));
  });
  server.stdout.on("data", appendLog);
  server.stderr.on("data", appendLog);

  let browser: Browser | undefined;
  try {
    browser = await chromium.launch({ headless: true, timeout: options.timeoutMs });
    const baseUrl = `http://127.0.0.1:${port}`;
    await waitForServer(
      server,
      baseUrl,
      options.timeoutMs,
      () => logs.join(""),
      () => serverFailure,
    );
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
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
    page.on("requestfailed", (request) => {
      browserErrors.push(
        `request:${new URL(request.url()).pathname}:${request.failure()?.errorText ?? "failed"}`,
      );
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        browserErrors.push(`http:${response.status()}:${new URL(response.url()).pathname}`);
      }
    });

    const route = `/preview/${options.tag}`;
    const response = await page.goto(`${baseUrl}${route}`, {
      waitUntil: "domcontentloaded",
      timeout: options.timeoutMs,
    });
    if (!response?.ok()) throw new Error(`preview returned HTTP ${response?.status() ?? 0}`);
    await page.waitForFunction(
      () =>
        (window as typeof window & { __sceneReady?: boolean }).__sceneReady === true,
      undefined,
      { timeout: options.timeoutMs },
    );

    const canvases = page.locator("canvas");
    if ((await canvases.count()) !== 1) throw new Error("preview must render exactly one canvas");
    const canvas = canvases.first();
    await canvas.waitFor({ state: "visible", timeout: options.timeoutMs });
    const dimensions = await canvas.evaluate((element) => ({
      width: element.width,
      height: element.height,
    }));
    if (dimensions.width !== 1280 || dimensions.height !== 720) {
      throw new Error(`gameplay canvas is not 1280x720: ${JSON.stringify(dimensions)}`);
    }

    const initialProbe = await readSceneProbe(page);
    requireCleanProbe(initialProbe);
    requireInventoryVisibility(initialProbe, true, "before dialogue opens");
    const initialVillage = requireVillage(initialProbe);
    requireDialogueProbeShape(initialVillage.dialogue);
    if (initialVillage.dialogue.open || initialVillage.dialogue.portraitVisible) {
      throw new Error("dialogue overlay must start closed with its portrait hidden");
    }

    await page.keyboard.down("Shift");
    await page.keyboard.down("d");
    try {
      await waitForElowenRange(page, options.timeoutMs);
    } finally {
      await page.keyboard.up("d");
      await page.keyboard.up("Shift");
    }
    await page.waitForTimeout(100);
    const inRangeProbe = await readSceneProbe(page);
    requireCleanProbe(inRangeProbe);
    const inRangeVillage = requireVillage(inRangeProbe);
    if (!inRangeVillage.npcs.some((npc) => npc.slot === 2 && npc.inRange)) {
      throw new Error("Elowen left interaction range before the movement keys were released");
    }
    requireElowenInteractionPrompt(
      inRangeProbe,
      true,
      "before dialogue opens",
    );
    const captures: string[] = [];
    captures.push(await captureCanvas(page, captureDirectory, "00-in-range.png"));

    const capturedBeats: CapturedBeat[] = [];
    for (let index = 0; index < EXPECTED_BEATS.length; index += 1) {
      const expected = EXPECTED_BEATS[index]!;
      await page.keyboard.press("e");
      const dialogue = await waitForBeat(page, expected, index, options.timeoutMs);
      requireInventoryVisibility(
        await readSceneProbe(page),
        false,
        `during the ${expected.expressionState} beat`,
      );
      requireElowenInteractionPrompt(
        await readSceneProbe(page),
        false,
        `during the ${expected.expressionState} beat`,
      );
      if (index === 0) {
        await page.keyboard.press("i");
        await page.waitForTimeout(100);
        requireInventoryVisibility(
          await readSceneProbe(page),
          false,
          "after an inventory toggle was attempted during dialogue",
        );
      }
      const screenshot = await captureCanvas(
        page,
        captureDirectory,
        `${String(index + 1).padStart(2, "0")}-${expected.expressionState}.png`,
      );
      captures.push(screenshot);
      capturedBeats.push(
        Object.freeze({
          expressionState: expected.expressionState,
          speaker: dialogue.speaker,
          line: dialogue.line,
          screenshot,
        }),
      );

      if (index === 0) {
        const beforeLockedInput = await playerX(page);
        await page.keyboard.down("d");
        try {
          await page.waitForTimeout(400);
        } finally {
          await page.keyboard.up("d");
        }
        const afterLockedInput = await playerX(page);
        if (Math.abs(afterLockedInput - beforeLockedInput) > 0.01) {
          throw new Error("player moved while the dialogue overlay was open");
        }
      }
    }

    await page.keyboard.press("e");
    await page.waitForFunction(
      () => {
        const probe = (
          window as typeof window & {
            __sceneProbes?: SceneProbe;
          }
        ).__sceneProbes;
        const dialogue = probe?.village?.dialogue;
        return (
          dialogue?.open === false &&
          dialogue.portraitVisible === false &&
          dialogue.speaker === "" &&
          dialogue.line === "" &&
          probe?.inventoryVisible === true &&
          probe?.village?.npcs.some((npc) => npc.slot === 2 && npc.inRange)
        );
      },
      undefined,
      { timeout: options.timeoutMs },
    );
    requireInventoryVisibility(
      await readSceneProbe(page),
      true,
      "after dialogue closes",
    );
    requireElowenInteractionPrompt(
      await readSceneProbe(page),
      true,
      "after dialogue closes",
    );
    captures.push(await captureCanvas(page, captureDirectory, "05-closed.png"));

    const beforeResumedInput = await playerX(page);
    await page.keyboard.down("d");
    try {
      await page.waitForTimeout(400);
    } finally {
      await page.keyboard.up("d");
    }
    const afterResumedInput = await playerX(page);
    if (afterResumedInput <= beforeResumedInput + 5) {
      throw new Error("player movement did not resume after the dialogue overlay closed");
    }
    captures.push(await captureCanvas(page, captureDirectory, "06-movement-resumed.png"));

    const finalProbe = await readSceneProbe(page);
    requireCleanProbe(finalProbe);
    requireVillage(finalProbe);
    throwBrowserErrors(browserErrors);

    const relativeCaptureDirectory = path
      .relative(WEB_ROOT, captureDirectory)
      .split(path.sep)
      .join("/");
    const result = Object.freeze({
      schema_version: 1,
      verdict: "pass",
      tag: options.tag,
      route,
      build_id: buildId.trim(),
      viewport: Object.freeze({ width: 1280, height: 720 }),
      resident: Object.freeze({ slot: 2, name: "Elowen Vale" }),
      beats: Object.freeze(capturedBeats),
      portrait_visible_during_each_beat: true,
      inventory_hidden_during_each_beat: true,
      inventory_visibility_restored_after_close: true,
      interaction_prompt_hidden_during_each_beat: true,
      interaction_prompt_restored_after_close: true,
      player_frozen_while_open: true,
      player_movement_resumed_after_close: true,
      browser_errors: Object.freeze([] as string[]),
      chromium_version: browser.version(),
      capture_directory: relativeCaptureDirectory,
      captures: Object.freeze(captures),
    });
    await fs.writeFile(
      path.join(captureDirectory, "verification.json"),
      `${JSON.stringify(result, null, 2)}\n`,
      { flag: "wx", mode: 0o600 },
    );
    await context.close();
    return result;
  } catch (error) {
    const detail = logs.join("").slice(-MAX_SERVER_LOG_CHARS);
    throw new Error(
      `${error instanceof Error ? error.message : String(error)}` +
        (detail ? `\nproduction server log:\n${detail}` : ""),
      { cause: error },
    );
  } finally {
    await browser?.close();
    await stopServer(server);
  }
}

if (import.meta.main) {
  try {
    const args = process.argv.slice(2);
    if (args.length === 1 && (args[0] === "--help" || args[0] === "-h")) {
      process.stdout.write(`${DIALOGUE_OVERLAY_USAGE}\n`);
    } else {
      const result = await verifyDialogueOverlay(parseDialogueOverlayArgs(args));
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    }
  } catch (error) {
    process.stderr.write(
      `dialogue overlay verification failed: ${
        error instanceof Error ? error.message : String(error)
      }\n`,
    );
    process.exitCode = 1;
  }
}
