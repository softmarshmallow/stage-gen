// Server-side reader for the derived execution-view.json a run may carry.
//
// Absent is null; present-but-refused throws — the page turns that into the
// re-export message rather than a crash, per the view's hard-drop versioning.

import { promises as fs } from "node:fs";
import {
  type ExecutionRunState,
  type ExecutionView,
  isExecutionViewKind,
  parseExecutionView,
  subjectLabel,
} from "@/lib/run-viewer/execution-view";
import { readRunDocument } from "./run-json";
import { artifactPathFor, assertSafeOutRoot, isSafeRunTag, OUT_ROOT } from "./runs";

export const EXECUTION_VIEW_FILENAME = "execution-view.json";

/**
 * Read and parse one run's execution view. Returns null when the run or the
 * document is absent; throws when the file exists but is not a document this
 * build renders (unknown version, tampered read, invalid shape).
 */
export async function readExecutionView(tag: string): Promise<ExecutionView | null> {
  const read = await readRunDocument(tag, EXECUTION_VIEW_FILENAME, {
    label: "execution view",
    noun: "view",
  });
  if (read === null) return null;
  return parseExecutionView(read.document);
}

async function isRenderableExecutionView(tag: string): Promise<boolean> {
  try {
    const raw = await fs.readFile(artifactPathFor(tag, EXECUTION_VIEW_FILENAME), "utf8");
    const kind = (JSON.parse(raw) as { kind?: unknown }).kind;
    return typeof kind !== "string" || isExecutionViewKind(kind);
  } catch {
    return true;
  }
}

export interface ExecutionViewRunListEntry {
  readonly tag: string;
  /** What the run's records say; null for a document this build refuses. */
  readonly runState: ExecutionRunState | null;
  /** When the trace was last appended, so a reader can judge liveness. */
  readonly traceModifiedAt: string | null;
  /** true when execution-view.json exists but this build refuses it. */
  readonly unreadable: boolean;
  /** What the run was for: a game id or a scene id, whichever its header carries. */
  readonly label: string | null;
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
        // A run belonging to a recipe this build does not carry declares a view
        // kind outside the list. It is a valid document this viewer does not
        // render, not a stale one, so it is skipped rather than reported as
        // needing re-export.
        if (!(await isRenderableExecutionView(tag))) return;
        const view = await readExecutionView(tag);
        if (!view) return;
        out.push({
          tag,
          runState: view.runState,
          traceModifiedAt: view.traceModifiedAt,
          unreadable: false,
          label: subjectLabel(view.subject),
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
          runState: null,
          traceModifiedAt: null,
          unreadable: true,
          label: null,
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
