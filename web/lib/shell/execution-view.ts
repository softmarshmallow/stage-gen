// Server-side reader for the derived execution-view.json a run may carry.
//
// Absent is null; present-but-refused throws — the page turns that into the
// re-export message rather than a crash, per the view's hard-drop versioning.

import { constants as fsConstants, promises as fs } from "node:fs";
import path from "node:path";
import {
  type ExecutionView,
  parseExecutionView,
} from "@/lib/runtime/execution-view";
import { artifactPathFor, assertSafeOutRoot, isSafeRunTag, OUT_ROOT, runDirFor } from "./runs";

export const EXECUTION_VIEW_FILENAME = "execution-view.json";

async function lstatOrNull(
  target: string,
): Promise<Awaited<ReturnType<typeof fs.lstat>> | null> {
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

/**
 * Read and parse one run's execution view. Returns null when the run or the
 * document is absent; throws when the file exists but is not a document this
 * build renders (unknown version, tampered read, invalid shape).
 */
export async function readExecutionView(tag: string): Promise<ExecutionView | null> {
  if (!(await assertSafeOutRoot())) return null;

  const runDir = runDirFor(tag);
  if (!(await assertRealDirectory(runDir, "run directory"))) return null;

  const viewPath = artifactPathFor(tag, EXECUTION_VIEW_FILENAME);
  const initial = await lstatOrNull(viewPath);
  if (!initial) return null;
  if (!initial.isFile() || initial.isSymbolicLink()) {
    throw new Error("execution view must be a real regular file");
  }

  const handle = await fs.open(viewPath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  let bytes: Buffer;
  let opened: Awaited<ReturnType<typeof handle.stat>>;
  try {
    opened = await handle.stat();
    if (!opened.isFile()) throw new Error("execution view must be a real regular file");
    bytes = await handle.readFile();
  } finally {
    await handle.close();
  }

  const current = await fs.lstat(viewPath);
  if (
    opened.dev !== initial.dev ||
    opened.ino !== initial.ino ||
    current.isSymbolicLink() ||
    !current.isFile() ||
    current.dev !== opened.dev ||
    current.ino !== opened.ino
  ) {
    throw new Error("execution view changed while it was being read");
  }
  if ((await fs.realpath(runDir)) !== path.resolve(runDir)) {
    throw new Error("run directory changed while its view was being read");
  }

  return parseExecutionView(JSON.parse(bytes.toString("utf8")));
}

export interface ExecutionViewRunListEntry {
  readonly tag: string;
  /** null while the run is in flight; also null for an unreadable document. */
  readonly ok: boolean | null;
  /** true when execution-view.json exists but this build refuses it. */
  readonly unreadable: boolean;
  readonly gameId: string | null;
  readonly nodeCount: number;
  readonly stateCounts: Readonly<Record<string, number>> | null;
  readonly durationMs: number | null;
  readonly knownCostUsd: number | null;
}

/** Enumerate runs under out/ that carry an execution view, newest tag first. */
export async function listExecutionViewRuns(): Promise<ExecutionViewRunListEntry[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ExecutionViewRunListEntry[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory()) return;
      const tag = entry.name;
      if (!isSafeRunTag(tag)) return;
      try {
        const view = await readExecutionView(tag);
        if (!view) return;
        out.push({
          tag,
          ok: view.ok,
          unreadable: false,
          gameId: view.gameId,
          nodeCount: view.nodes.length,
          stateCounts: view.stateCounts,
          durationMs: view.durationMs,
          knownCostUsd: view.knownCostUsd,
        });
      } catch {
        // The document exists but this build refuses it (stale version or
        // invalid shape). List it so the operator sees the re-export need.
        out.push({
          tag,
          ok: null,
          unreadable: true,
          gameId: null,
          nodeCount: 0,
          stateCounts: null,
          durationMs: null,
          knownCostUsd: null,
        });
      }
    }),
  );
  out.sort((a, b) => b.tag.localeCompare(a.tag));
  return out;
}
