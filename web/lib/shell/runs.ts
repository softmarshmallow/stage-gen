// Server-side run lifecycle helpers.
//
// Spawns `bun run pipeline "<prompt>"` from repo root, redirects stdout +
// stderr to a per-tag `web-run.log` inside out/<tag>/, and tracks live
// processes in an in-process map so the SSE route can tell "still running"
// from "exited".

import { spawn, type ChildProcess } from "node:child_process";
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const OUT_ROOT = path.join(REPO_ROOT, "out");

export function runDirFor(tag: string): string {
  return path.join(OUT_ROOT, tag);
}

export function logPathFor(tag: string): string {
  return path.join(runDirFor(tag), "web-run.log");
}

export function runJsonPathFor(tag: string): string {
  return path.join(runDirFor(tag), "run.json");
}

interface ProcRecord {
  proc: ChildProcess;
  startedAt: number;
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
  if (existsSync(runDirFor(tag))) return { status: "running" };
  return { status: "missing" };
}

/**
 * Start the pipeline as a background subprocess. No-op if a run is already
 * live for this tag. Caller is responsible for not racing two starts at
 * once for the same tag (the picker only fires one).
 */
export async function startRun(opts: {
  prompt: string;
  tag: string;
}): Promise<{ started: boolean }> {
  const { prompt, tag } = opts;
  if (isRunning(tag)) return { started: false };

  const dir = runDirFor(tag);
  await fs.mkdir(dir, { recursive: true });
  const logPath = logPathFor(tag);
  // Truncate the log on a fresh start so SSE clients get a clean replay.
  await fs.writeFile(logPath, "", "utf8");

  // open() the log file as an fs handle and feed it to the spawn stdio.
  const fd = await fs.open(logPath, "a");

  const proc = spawn("bun", ["run", "pipeline", prompt], {
    cwd: REPO_ROOT,
    stdio: ["ignore", fd.fd, fd.fd],
    detached: false,
    env: process.env,
  });

  procs.set(tag, { proc, startedAt: Date.now() });

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
}): Promise<{ ok: boolean; reason?: string }> {
  const { tag, asset } = opts;
  // Look up the prompt from run.json so we can re-spawn the same pipeline.
  try {
    const raw = await fs.readFile(runJsonPathFor(tag), "utf8");
    const data = JSON.parse(raw);
    const prompt: string | undefined = data.prompt;
    if (!prompt) return { ok: false, reason: "no prompt in run.json" };
    // Delete the asset file (and its sidecar) if present so the generator
    // re-creates it on the next run. The orchestrator will skip everything
    // else thanks to the per-stage skip-if-exists guards.
    const target = path.join(runDirFor(tag), asset);
    if (existsSync(target)) await fs.unlink(target).catch(() => {});
    const sidecar = `${target}.meta.json`;
    if (existsSync(sidecar)) await fs.unlink(sidecar).catch(() => {});
    await startRun({ prompt, tag });
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      reason: err instanceof Error ? err.message : String(err),
    };
  }
}
