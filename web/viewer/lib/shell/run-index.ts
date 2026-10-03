// The run index: every run under every root, with what it is and how it stands.
//
// This is the viewer's own reader, and it is deliberately shallow. From a run's anchor
// document it takes only the fields that say what wrote it — a workflow run's plan its
// workflow, a delivered package its `kind` and `schema_version` — and from its view only
// the run-level summary. It parses no
// gameplay contract: a run's gameplay belongs to the host that plays it, and a viewer
// that learned to read one would be a second implementation of that genre (decision
// 0061). Which workflow a run belongs to is decided from those fields and the catalog
// (lib/run-groups.ts).
//
// Parsed summaries are kept per file and modification time, so a page that lists
// hundreds of runs re-reads only the ones that changed since the last request.

import { promises as fs } from "node:fs";
import path from "node:path";
import {
  type ExecutionNodeState,
  type ExecutionRunState,
  subjectLabel,
} from "@stage-gen/ui/contracts/run-view";
import type { RunIdentity } from "@/lib/run-groups";
import { readExecutionView, type ViewSource, viewLocation } from "./execution-view";
import { readRunDocument } from "./run-json";
import type { RunRef } from "./run-ref";
import { type FoundRun, discoverRuns, runDirFor } from "./runs";

/** The documents that say what a run is, in the order the index asks them. */
export const ANCHOR_DOCUMENTS = [
  "plan.json",
  "manifest.json",
  "bundle.json",
  "case.json",
  "execution-view.json",
] as const;

/** Files whose change is the run changing: plans, traces, records and views. */
const UPDATE_FILES = [
  "execution-view.json",
  "plan.json",
  "events.jsonl",
  "manifest.json",
  "bundle.json",
  "case.json",
] as const;

/** A gnode workflow run's plan (`plan.json`) declares itself so, and names its workflow. */
const GNODE_PLAN = "graph/v2";
export const GNODE_GRAPH_KIND = "gnode-graph-v2";

/** What a run's view says about the whole run. */
export interface ViewSummary {
  readonly source: ViewSource;
  readonly runState: ExecutionRunState;
  readonly traceModifiedAt: string | null;
  readonly label: string;
  readonly nodeCount: number;
  readonly stateCounts: Readonly<Record<ExecutionNodeState, number>>;
  readonly durationMs: number | null;
  readonly knownCostUsd: number | null;
  readonly kind: string;
  readonly graphKind: string | null;
}

export interface RunIndexEntry {
  readonly run: RunRef;
  readonly rootLabel: string;
  readonly relative: string;
  readonly identity: RunIdentity;
  readonly schemaVersion: number | null;
  /** The view's summary, or null when the run has none in the run folder or the cache. */
  readonly view: ViewSummary | null;
  /** Why the view this build found was refused, so a reader sees the re-derive need. */
  readonly viewRefusal: string | null;
  /** When any of the run's documents last changed, in UTC. */
  readonly updatedAt: string | null;
}

interface Anchor {
  readonly document: string | null;
  readonly kind: string | null;
  readonly schemaVersion: number | null;
  readonly workflowId: string | null;
}

const NO_ANCHOR: Anchor = {
  document: null,
  kind: null,
  schemaVersion: null,
  workflowId: null,
};

/**
 * A file directly inside a run folder. Written as a template rather than path.join: the
 * bundler traces a joined path as if it could reach any file of the project.
 */
function inRun(runDir: string, name: string): string {
  return `${runDir}${path.sep}${name}`;
}

const memo = new Map<string, { readonly stamp: string; readonly value: unknown }>();

async function stampOf(file: string): Promise<string | null> {
  try {
    const stat = await fs.lstat(file);
    return stat.isFile() ? `${stat.mtimeMs}:${stat.size}` : null;
  } catch {
    return null;
  }
}

/** Compute once per file version; the key names both the file and what is taken from it. */
async function remembered<T>(key: string, file: string, compute: () => Promise<T>): Promise<T> {
  const stamp = await stampOf(file);
  const known = memo.get(key);
  if (stamp !== null && known?.stamp === stamp) return known.value as T;
  const value = await compute();
  if (stamp !== null) memo.set(key, { stamp, value });
  return value;
}

function textField(document: Record<string, unknown>, name: string): string | null {
  return typeof document[name] === "string" ? (document[name] as string) : null;
}

async function readAnchor(run: RunRef, runDir: string): Promise<Anchor> {
  for (const name of ANCHOR_DOCUMENTS) {
    const file = inRun(runDir, name);
    if ((await stampOf(file)) === null) continue;
    return remembered(`anchor\0${file}`, file, async () => {
      try {
        const read = await readRunDocument(run, name, { label: "run document", noun: "document" });
        const body = read?.document;
        if (body === null || typeof body !== "object" || Array.isArray(body)) {
          return { ...NO_ANCHOR, document: name };
        }
        const declared = body as Record<string, unknown>;
        if (name === "plan.json" && declared.gnode === GNODE_PLAN) {
          const workflow = declared.workflow;
          const id =
            workflow !== null && typeof workflow === "object" && !Array.isArray(workflow)
              ? textField(workflow as Record<string, unknown>, "id")
              : null;
          return { ...NO_ANCHOR, document: name, kind: GNODE_GRAPH_KIND, workflowId: id };
        }
        return {
          document: name,
          kind: textField(declared, "kind"),
          schemaVersion: typeof declared.schema_version === "number" ? declared.schema_version : null,
          workflowId: null,
        };
      } catch {
        // Unreadable or refused: the run is still listed, with no identity.
        return { ...NO_ANCHOR, document: name };
      }
    });
  }
  return NO_ANCHOR;
}

type ViewRead = { readonly view: ViewSummary | null; readonly refusal: string | null };

async function readViewSummary(run: RunRef): Promise<ViewRead> {
  const location = await viewLocation(run).catch(() => null);
  if (location === null) return { view: null, refusal: null };
  return remembered(`view\0${location.file}`, location.file, async (): Promise<ViewRead> => {
    try {
      const read = await readExecutionView(run);
      if (read === null) return { view: null, refusal: null };
      const { view, source } = read;
      const graphKind = view.subject.fields.graph_kind;
      return {
        view: {
          source,
          runState: view.runState,
          traceModifiedAt: view.traceModifiedAt,
          label: subjectLabel(view.subject),
          nodeCount: view.nodes.length,
          stateCounts: view.stateCounts,
          durationMs: view.durationMs,
          knownCostUsd: view.knownCostUsd,
          kind: view.subject.kind,
          graphKind: typeof graphKind === "string" ? graphKind : null,
        },
        refusal: null,
      };
    } catch (error) {
      return { view: null, refusal: error instanceof Error ? error.message : String(error) };
    }
  });
}

async function updatedAt(runDir: string): Promise<string | null> {
  const stamps = await Promise.all(
    UPDATE_FILES.map(async (name) => {
      try {
        return (await fs.stat(inRun(runDir, name))).mtimeMs;
      } catch {
        return null;
      }
    }),
  );
  const present = stamps.filter((stamp): stamp is number => stamp !== null);
  return present.length ? new Date(Math.max(...present)).toISOString() : null;
}

/** One run's index entry. */
export async function readRunEntry(found: FoundRun): Promise<RunIndexEntry> {
  const runDir = runDirFor(found.run);
  const [anchor, viewRead, updated] = await Promise.all([
    readAnchor(found.run, runDir),
    readViewSummary(found.run),
    updatedAt(runDir),
  ]);
  const view = viewRead.view;
  return {
    run: found.run,
    rootLabel: found.root.label,
    relative: found.relative,
    identity: {
      document: anchor.document,
      kind: anchor.kind,
      viewKind: view?.kind ?? null,
      graphKind: view?.graphKind ?? null,
      workflowId: anchor.workflowId,
    },
    schemaVersion: anchor.schemaVersion,
    view,
    viewRefusal: viewRead.refusal,
    updatedAt: updated,
  };
}

/** Every run under every root, in discovery order. */
export async function listRuns(): Promise<RunIndexEntry[]> {
  const found = await discoverRuns();
  return Promise.all(found.map(readRunEntry));
}
