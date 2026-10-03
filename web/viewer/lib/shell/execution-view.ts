// Server-side reader for a run's execution view: the one the run persists, or the one
// `stage-gen view` derived for it into the user cache.
//
// The run folder's own view is read when it is at least as new as the cached one;
// otherwise the cache's, which `stage-gen view` keeps fresh while the run's trace grows.
// A run is never written to: a view the viewer needs and the run lacks lives only in the
// cache. Absent is null; present-but-refused throws — the page turns that into the
// re-derive message rather than a crash, per the view's hard-drop versioning.

import { promises as fs } from "node:fs";
import path from "node:path";
import { type ExecutionView, parseExecutionView } from "@stage-gen/ui/contracts/run-view";
import { parseViewContexts, type ViewContexts } from "@stage-gen/ui/contracts/view-context";
import { readRunDocument } from "./run-json";
import type { RunRef } from "./run-ref";
import { isRealRunDirectory, runDirFor, viewCacheDir, viewKey } from "./runs";

export const EXECUTION_VIEW_FILENAME = "execution-view.json";
/** Beside a gnode run's view: the context each of its step views is shown with. */
export const VIEW_CONTEXTS_FILENAME = "view-contexts.json";

/** Where a view came from: the run folder, or the cache `stage-gen view` keeps. */
export type ViewSource = "run" | "cache";

export interface ReadView {
  readonly view: ExecutionView;
  readonly source: ViewSource;
}

async function modifiedMs(target: string): Promise<number | null> {
  try {
    const stat = await fs.lstat(target);
    return stat.isFile() ? stat.mtimeMs : null;
  } catch {
    return null;
  }
}

/** The cached view of a run, or null when the viewer runs without a view cache. */
export function cachedViewPath(runDir: string): string | null {
  const cache = viewCacheDir();
  return cache === null ? null : path.join(cache, viewKey(runDir), EXECUTION_VIEW_FILENAME);
}

async function readCachedView(file: string): Promise<unknown> {
  const stat = await fs.lstat(file);
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("cached execution view must be a real regular file");
  }
  return JSON.parse(await fs.readFile(file, "utf8")) as unknown;
}

/** Which view to read, without reading it: the newer of the run's and the cache's. */
export async function viewLocation(
  run: RunRef,
): Promise<{ readonly source: ViewSource; readonly file: string; readonly mtimeMs: number } | null> {
  if (!(await isRealRunDirectory(run))) return null;
  const runDir = runDirFor(run);
  const own = path.join(runDir, EXECUTION_VIEW_FILENAME);
  const cached = cachedViewPath(runDir);
  const ownMs = await modifiedMs(own);
  const cachedMs = cached === null ? null : await modifiedMs(cached);
  if (cached !== null && cachedMs !== null && (ownMs === null || cachedMs > ownMs)) {
    return { source: "cache", file: cached, mtimeMs: cachedMs };
  }
  return ownMs === null ? null : { source: "run", file: own, mtimeMs: ownMs };
}

/**
 * Read and parse one run's execution view. Returns null when the run has no view in
 * either place; throws when the chosen file is not a document this build renders
 * (unknown version, tampered read, invalid shape).
 */
export async function readExecutionView(run: RunRef): Promise<ReadView | null> {
  const location = await viewLocation(run);
  if (location === null) return null;
  if (location.source === "cache") {
    return { view: parseExecutionView(await readCachedView(location.file)), source: "cache" };
  }
  const read = await readRunDocument(run, EXECUTION_VIEW_FILENAME, {
    label: "execution view",
    noun: "view",
  });
  if (read === null) return null;
  return { view: parseExecutionView(read.document), source: "run" };
}

/**
 * The step views of a run, read from beside its execution view; null when it keeps none.
 * Throws when the file is not a document this build renders.
 */
export async function readViewContexts(run: RunRef): Promise<ViewContexts | null> {
  const location = await viewLocation(run);
  if (location === null) return null;
  if (location.source === "cache") {
    const file = path.join(path.dirname(location.file), VIEW_CONTEXTS_FILENAME);
    if ((await modifiedMs(file)) === null) return null;
    return parseViewContexts(await readCachedView(file));
  }
  const read = await readRunDocument(run, VIEW_CONTEXTS_FILENAME, {
    label: "view contexts",
    noun: "view contexts",
  });
  return read === null ? null : parseViewContexts(read.document);
}
