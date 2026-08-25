// Server-side run lifecycle helpers.
//
// Spawns the public Python `stage-gen generate ...` command from repo root,
// redirects stdout + stderr to a per-tag `web-run.log` inside out/<tag>/, and tracks live
// processes in an in-process map so the SSE route can tell "still running"
// from "exited".

import { spawn, type ChildProcess } from "node:child_process";
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  DEFAULT_TRANSPARENCY_MODE,
  promptFromRunManifest,
  transparencyModeFromRunManifest,
  type TransparencyMode,
} from "./transparency";
import { tagFor } from "./tag";

export { promptFromRunManifest } from "./transparency";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const OUT_ROOT = process.env.STAGE_GEN_OUT_DIR?.trim()
  ? path.resolve(REPO_ROOT, process.env.STAGE_GEN_OUT_DIR.trim())
  : path.join(REPO_ROOT, "out");

// Length matches the producer's own bound. Python writes run directories through
// `assert_safe_path_segment`, whose `_SAFE_SEGMENT` allows 128 characters, and this consumer
// capped at 64 - so a tag the generator legitimately produced simply 404'd here, with no error
// naming the length. Two dialogue-scene runs at 65 characters were already unreachable before
// any game contract existed; a bound game adds a 27-character suffix and makes it routine.
//
// The character class stays narrower than the producer's on purpose: run tags are lowercased
// slugs, and `.` in particular must never reach a path segment here. Only the length moved.
const RUN_TAG_MAXIMUM_LENGTH = 128;
const RUN_TAG_PATTERN = new RegExp(
  `^[a-z0-9](?:[a-z0-9-]{0,${RUN_TAG_MAXIMUM_LENGTH - 2}}[a-z0-9])?$`,
);
const ARTIFACT_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
const ALLOWED_EXECUTABLE_NAMES = new Set(["uv", "stage-gen", "stage-gen-py"]);

export interface StageGenCommand {
  executable: string;
  args: string[];
}

export function resolveStageGenExecutable(configured?: string): string {
  if (configured === undefined || configured === "") return "uv";
  if (
    configured !== configured.trim() ||
    /[\s\0]/.test(configured) ||
    (!path.isAbsolute(configured) && path.basename(configured) !== configured) ||
    (path.isAbsolute(configured) && path.normalize(configured) !== configured) ||
    !ALLOWED_EXECUTABLE_NAMES.has(path.basename(configured))
  ) {
    throw new Error(
      "STAGE_GEN_EXECUTABLE must be uv, stage-gen, stage-gen-py, or an absolute path to one",
    );
  }
  return configured;
}

function pythonCliArgsFor(input: {
  prompt: string;
  transparencyMode: TransparencyMode;
}): string[] {
  return [
    "generate",
    "--recipe",
    "scrolling-preview",
    "--transparency",
    input.transparencyMode,
    input.prompt,
  ];
}

export function stageGenCommandFor(
  input: { prompt: string; transparencyMode: TransparencyMode },
  configuredExecutable: string | undefined = process.env.STAGE_GEN_EXECUTABLE,
): StageGenCommand {
  const executable = resolveStageGenExecutable(configuredExecutable);
  const cliArgs = pythonCliArgsFor(input);
  return {
    executable,
    args: path.basename(executable) === "uv" ? ["run", "stage-gen", ...cliArgs] : cliArgs,
  };
}

function isAlreadyDecoded(value: string): boolean {
  try {
    return decodeURIComponent(value) === value;
  } catch {
    return false;
  }
}

export function isSafeRunTag(tag: string): boolean {
  return isAlreadyDecoded(tag) && RUN_TAG_PATTERN.test(tag);
}

export function assertSafeRunTag(tag: string): void {
  if (!isSafeRunTag(tag)) {
    throw new Error("invalid run tag");
  }
}

export function runDirFor(tag: string): string {
  assertSafeRunTag(tag);
  const root = path.resolve(OUT_ROOT);
  const runDir = path.resolve(root, tag);
  if (!runDir.startsWith(`${root}${path.sep}`)) {
    throw new Error("run tag escapes OUT_DIR");
  }
  return runDir;
}

export function logPathFor(tag: string): string {
  return path.join(runDirFor(tag), "web-run.log");
}

export function runJsonPathFor(tag: string): string {
  return path.join(runDirFor(tag), "run.json");
}

export function artifactPathFor(tag: string, asset: string): string {
  if (!isAlreadyDecoded(asset) || !ARTIFACT_NAME_PATTERN.test(asset)) {
    throw new Error("invalid artifact name");
  }
  const runDir = runDirFor(tag);
  const target = path.resolve(runDir, asset);
  if (!target.startsWith(`${runDir}${path.sep}`)) {
    throw new Error("artifact path escapes run directory");
  }
  return target;
}

export interface RunInputSnapshot {
  prompt: string;
  /** Null only for a legacy run manifest that predates explicit strategy metadata. */
  transparencyMode: TransparencyMode | null;
}

interface ProcRecord {
  proc: ChildProcess;
  startedAt: number;
  input: RunInputSnapshot & { transparencyMode: TransparencyMode };
}

// Module-level singleton so multiple SSE clients reuse the same record.
const procs: Map<string, ProcRecord> = new Map();

export function isRunning(tag: string): boolean {
  const r = procs.get(tag);
  return Boolean(r && r.proc.exitCode === null && !r.proc.killed);
}

export interface RunStatus {
  status: "missing" | "running" | "done" | "failed";
  ok?: boolean;
  failedStage?: string | null;
}

export async function readRunStatus(tag: string): Promise<RunStatus> {
  const runJson = runJsonPathFor(tag);
  if (existsSync(runJson)) {
    try {
      const raw = await fs.readFile(runJson, "utf8");
      const data = JSON.parse(raw);
      if (data.ok === true) return { status: "done", ok: true };
      return {
        status: "failed",
        ok: false,
        failedStage: data.failedStage ?? null,
      };
    } catch {
      // fallthrough
    }
  }
  if (isRunning(tag)) return { status: "running" };
  if (existsSync(runDirFor(tag))) {
    return { status: "failed", ok: false, failedStage: "interrupted" };
  }
  return { status: "missing" };
}

export async function readRunInput(tag: string): Promise<RunInputSnapshot | null> {
  assertSafeRunTag(tag);
  const runJson = runJsonPathFor(tag);
  if (existsSync(runJson)) {
    let value: unknown;
    try {
      value = JSON.parse(await fs.readFile(runJson, "utf8"));
    } catch {
      // A live process record can still provide its validated input while the
      // manifest is being published. A terminal malformed manifest fails
      // closed instead of being mistaken for a legacy manifest.
      const inFlight = procs.get(tag)?.input;
      if (inFlight) return inFlight;
      throw new Error("run manifest is not valid JSON");
    }
    const prompt = promptFromRunManifest(value);
    if (prompt) {
      return { prompt, transparencyMode: transparencyModeFromRunManifest(value) };
    }
  }
  return procs.get(tag)?.input ?? null;
}

/**
 * Start the pipeline as a background subprocess. No-op if a run is already
 * live for this tag. Caller is responsible for not racing two starts at
 * once for the same tag (the picker only fires one).
 */
export async function startRun(opts: {
  prompt: string;
  tag: string;
  transparencyMode?: TransparencyMode;
}): Promise<{ started: boolean }> {
  const { prompt, tag } = opts;
  const transparencyMode = opts.transparencyMode ?? DEFAULT_TRANSPARENCY_MODE;
  assertSafeRunTag(tag);
  if (tagFor(prompt, transparencyMode) !== tag) {
    throw new Error("run tag does not match prompt and transparencyMode");
  }
  if (isRunning(tag)) return { started: false };

  const dir = runDirFor(tag);
  await fs.mkdir(dir, { recursive: true });
  // A previous terminal manifest must not make a newly spawned retry look
  // complete or failed while it is running.
  await fs.unlink(runJsonPathFor(tag)).catch((error: NodeJS.ErrnoException) => {
    if (error.code !== "ENOENT") throw error;
  });
  const logPath = logPathFor(tag);
  // Truncate the log on a fresh start so SSE clients get a clean replay.
  await fs.writeFile(logPath, "", "utf8");

  // open() the log file as an fs handle and feed it to the spawn stdio.
  const fd = await fs.open(logPath, "a");

  const command = stageGenCommandFor({ prompt, transparencyMode });
  const proc = spawn(command.executable, command.args, {
    cwd: REPO_ROOT,
    stdio: ["ignore", fd.fd, fd.fd],
    detached: false,
    shell: false,
    env: { ...process.env, STAGE_GEN_OUT_DIR: OUT_ROOT },
  });

  procs.set(tag, {
    proc,
    startedAt: Date.now(),
    input: { prompt, transparencyMode },
  });

  proc.on("exit", () => {
    fd.close().catch(() => {});
    // Keep the record so isRunning returns false but status survives lookup.
  });
  proc.on("error", () => {
    fd.close().catch(() => {});
  });

  return { started: true };
}

/**
 * Spawn the orchestrator for a single stage. The orchestrator's CLI doesn't
 * yet expose stage-targeted reruns, so for now this just kicks off another
 * full pipeline run for the same prompt — the per-asset skip-if-exists
 * checks inside each generator (TC-123) make it effectively a single-asset
 * retry when only one file is missing/broken. Caller passes the original
 * prompt by re-reading run.json.
 */
export async function retryAsset(opts: {
  tag: string;
  asset: string;
}, start: typeof startRun = startRun): Promise<{ ok: boolean; reason?: string }> {
  const { tag, asset } = opts;
  try {
    const target = artifactPathFor(tag, asset);
    // Read the current headless run manifest so the same recipe input can be
    // submitted again after removing the failed artifact.
    const raw = await fs.readFile(runJsonPathFor(tag), "utf8");
    const data = JSON.parse(raw);
    const prompt = promptFromRunManifest(data);
    if (!prompt) return { ok: false, reason: "run manifest has no input.prompt" };
    // A legacy manifest has no reproducible strategy choice. Its artifacts may
    // still be previewed through compatibility keying, but mutating retry must
    // fail rather than silently choose a mode and write into a different tag.
    const transparencyMode = transparencyModeFromRunManifest(data);
    if (!transparencyMode) {
      return {
        ok: false,
        reason: "legacy run has no transparencyMode; restart it from the picker",
      };
    }
    if (tagFor(prompt, transparencyMode) !== tag) {
      return {
        ok: false,
        reason: "run tag does not match its prompt and transparencyMode",
      };
    }
    // Delete the asset file (and its sidecar) if present so the generator
    // re-creates it on the next run. The orchestrator will skip everything
    // else thanks to the per-stage skip-if-exists guards.
    if (existsSync(target)) await fs.unlink(target).catch(() => {});
    const sidecar = `${target}.meta.json`;
    if (existsSync(sidecar)) await fs.unlink(sidecar).catch(() => {});
    await start({ prompt, tag, transparencyMode });
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    };
  }
}

export function stageGenArgsFor(input: {
  prompt: string;
  transparencyMode: TransparencyMode;
}): string[] {
  return stageGenCommandFor(input, "uv").args;
}
