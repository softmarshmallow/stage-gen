// Server-side run lifecycle helpers.
//
// Spawns the public Python `stage-gen generate ...` command from repo root,
// redirects stdout + stderr to a per-tag `web-run.log` inside out/<tag>/, and tracks live
// processes in an in-process map so the SSE route can tell "still running"
// from "exited".

import { spawn, type ChildProcess } from "node:child_process";
import { promises as fs } from "node:fs";
import { constants as fsConstants, existsSync } from "node:fs";
import path from "node:path";
import {
  parseRecipeRunSummaryBytes,
  type RecipeRunSummary,
} from "./run-summary";
import {
  DEFAULT_TRANSPARENCY_MODE,
  promptFromRunSummary,
  type TransparencyMode,
} from "./transparency";
import { tagFor } from "./tag";

export { promptFromRunSummary } from "./transparency";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const OUT_ROOT = process.env.STAGE_GEN_OUT_DIR?.trim()
  ? path.resolve(REPO_ROOT, process.env.STAGE_GEN_OUT_DIR.trim())
  : path.join(REPO_ROOT, "out");

// Match the current producer's one-safe-segment contract exactly. Generated prompt tags happen
// to be lower-case, but explicit producer tags may also contain upper-case letters, `_`, or `.`.
const RUN_TAG_MAXIMUM_LENGTH = 128;
const RUN_TAG_PATTERN = new RegExp(
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,${RUN_TAG_MAXIMUM_LENGTH - 1}}$`,
);
const ARTIFACT_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
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
  return isAlreadyDecoded(tag) && tag !== "." && tag !== ".." && RUN_TAG_PATTERN.test(tag);
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

export async function isPreparedRuntimeRun(tag: string): Promise<boolean> {
  const manifestPath = artifactPathFor(tag, "manifest.json");
  try {
    const stat = await fs.lstat(manifestPath);
    if (!stat.isFile() || stat.isSymbolicLink()) return false;
    const parsed = JSON.parse(await fs.readFile(manifestPath, "utf8")) as Record<
      string,
      unknown
    >;
    return (
      parsed["schema_version"] === 9 &&
      parsed["kind"] === "prepared-game-runtime-v9"
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    return false;
  }
}

export function artifactPathFor(tag: string, asset: string): string {
  const segments = asset.split("/");
  if (
    !isAlreadyDecoded(asset) ||
    segments.length === 0 ||
    segments.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        !ARTIFACT_SEGMENT_PATTERN.test(segment),
    )
  ) {
    throw new Error("invalid artifact path");
  }
  const runDir = runDirFor(tag);
  const target = path.resolve(runDir, ...segments);
  if (!target.startsWith(`${runDir}${path.sep}`)) {
    throw new Error("artifact path escapes run directory");
  }
  return target;
}

export interface RunInputSnapshot {
  prompt: string;
  transparencyMode: TransparencyMode;
}

interface ProcRecord {
  proc: ChildProcess;
  startedAt: number;
  input: RunInputSnapshot;
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

async function lstatOrNull(target: string): Promise<Awaited<ReturnType<typeof fs.lstat>> | null> {
  try {
    return await fs.lstat(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function assertRealDirectory(target: string, label: string): Promise<boolean> {
  const stat = await lstatOrNull(target);
  if (!stat) return false;
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a real directory`);
  }
  if ((await fs.realpath(target)) !== path.resolve(target)) {
    throw new Error(`${label} must not traverse a symlink`);
  }
  return true;
}

export async function assertSafeOutRoot(): Promise<boolean> {
  return assertRealDirectory(OUT_ROOT, "run output root");
}

export async function readRunSummary(tag: string): Promise<RecipeRunSummary | null> {
  if (!(await assertSafeOutRoot())) return null;
  const runDir = runDirFor(tag);
  if (!(await assertRealDirectory(runDir, "run directory"))) return null;
  const runJson = path.join(runDir, "run.json");
  const initial = await lstatOrNull(runJson);
  if (!initial) return null;
  if (!initial.isFile() || initial.isSymbolicLink()) {
    throw new Error("run summary file must be a real regular file");
  }
  const handle = await fs.open(runJson, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  let bytes: Buffer;
  let opened: Awaited<ReturnType<typeof handle.stat>>;
  try {
    opened = await handle.stat();
    if (!opened.isFile()) throw new Error("run summary file must be a real regular file");
    bytes = await handle.readFile();
  } finally {
    await handle.close();
  }
  const current = await fs.lstat(runJson);
  if (
    current.isSymbolicLink() ||
    !current.isFile() ||
    current.dev !== opened.dev ||
    current.ino !== opened.ino
  ) {
    throw new Error("run summary file changed while it was being read");
  }
  if ((await fs.realpath(runDir)) !== path.resolve(runDir)) {
    throw new Error("run directory changed while its summary was being read");
  }
  const summary = parseRecipeRunSummaryBytes(bytes);
  if (summary.tag !== tag) {
    throw new Error("run summary tag does not match its run directory");
  }
  if (summary.run_dir !== tag) {
    throw new Error("run summary run_dir does not match its requested run directory");
  }
  return summary;
}

export async function readRunStatus(tag: string): Promise<RunStatus> {
  const summary = await readRunSummary(tag);
  if (summary?.ok === true) return { status: "done", ok: true };
  if (summary?.ok === false) {
    return {
      status: "failed",
      ok: false,
      failedStage: summary.failed_stage,
    };
  }
  if (isRunning(tag)) return { status: "running" };
  if (existsSync(runDirFor(tag))) {
    return { status: "failed", ok: false, failedStage: "interrupted" };
  }
  return { status: "missing" };
}

export async function readRunInput(tag: string): Promise<RunInputSnapshot | null> {
  assertSafeRunTag(tag);
  const summary = await readRunSummary(tag);
  if (summary) {
    const prompt = promptFromRunSummary(summary);
    if (prompt) {
      return { prompt, transparencyMode: summary.input.transparency_mode };
    }
    return null;
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
  // A previous terminal summary must not make a newly spawned retry look
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
    // Read the current headless run summary so the same recipe input can be
    // submitted again after removing the failed artifact.
    const summary = await readRunSummary(tag);
    if (!summary) return { ok: false, reason: "run summary is missing" };
    const prompt = promptFromRunSummary(summary);
    if (!prompt) return { ok: false, reason: "run summary has no input.prompt" };
    const transparencyMode = summary.input.transparency_mode;
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
