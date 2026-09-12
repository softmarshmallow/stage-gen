// The run index: every run under out/, listed by the document it published.
//
// This is the viewer's own reader, and it is deliberately shallow. It opens
// whichever published document a run carries and takes exactly
// two fields — `kind` and `schema_version` — because those are what say *what*
// the run is. It parses nothing else: a run's gameplay contract belongs to the
// host that plays it, and a viewer that learned to read one would be a second
// implementation of that genre (decision 0061).
//
// The index existed before as four genre readers, one per playable kind, each
// importing that genre's parser to find a title and a cover. That coupled the
// front page to every runtime: adding a genre meant editing the index, and
// removing one broke it. What the index actually needs is a tag, a kind, and
// whether there is anything to open.

import { promises as fs } from "node:fs";
import { readRunDocument } from "./run-json";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT } from "./runs";

/** Historical consumer documents, followed by the generic pipeline view. */
export const RUN_DOCUMENTS = ["manifest.json", "bundle.json", "case.json", "execution-view.json"] as const;
export type RunDocumentName = (typeof RUN_DOCUMENTS)[number];

export const EXECUTION_VIEW_FILENAME = "execution-view.json";

export interface RunIndexEntry {
  readonly tag: string;
  /** Which document the run published, or null when it carries none. */
  readonly document: RunDocumentName | null;
  /** The document's `kind`, verbatim, or null when it declares none. */
  readonly kind: string | null;
  /** The document's `schema_version`, verbatim, or null. */
  readonly schemaVersion: number | null;
  /** Whether the run carries a derived execution view the viewer can render. */
  readonly hasExecutionView: boolean;
}

async function exists(target: string): Promise<boolean> {
  try {
    await fs.stat(target);
    return true;
  } catch {
    return false;
  }
}

/**
 * Read one run's identity: which document it published, and what that document
 * says it is. A document that is unreadable or is not a JSON object leaves the
 * kind null rather than throwing — the index lists the run either way, because
 * a run the viewer cannot identify is exactly the run an operator wants to see.
 */
export async function readRunIdentity(tag: string): Promise<RunIndexEntry> {
  const runDir = `${OUT_ROOT}/${tag}`;
  for (const document of RUN_DOCUMENTS) {
    if (!(await exists(`${runDir}/${document}`))) continue;
    let kind: string | null = null;
    let schemaVersion: number | null = null;
    try {
      const read = await readRunDocument(tag, document, {
        label: "run document",
        noun: "document",
      });
      const body = read?.document;
      if (body !== null && typeof body === "object") {
        const declared = body as { kind?: unknown; schema_version?: unknown };
        if (typeof declared.kind === "string") kind = declared.kind;
        if (typeof declared.schema_version === "number") {
          schemaVersion = declared.schema_version;
        }
      }
    } catch {
      // Unreadable or refused: the run is still listed, with no identity.
    }
    return {
      tag,
      document,
      kind,
      schemaVersion,
      hasExecutionView: await exists(`${runDir}/${EXECUTION_VIEW_FILENAME}`),
    };
  }
  return {
    tag,
    document: null,
    kind: null,
    schemaVersion: null,
    hasExecutionView: await exists(`${runDir}/${EXECUTION_VIEW_FILENAME}`),
  };
}

/**
 * Every run under out/ that published a document or a view, newest tag first.
 *
 * A directory with neither is not a run this viewer has anything to say about —
 * a scratch directory, an interrupted generate — and is skipped.
 */
export async function listRuns(): Promise<RunIndexEntry[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const found = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory() && isSafeRunTag(entry.name))
      .map((entry) => readRunIdentity(entry.name)),
  );
  return found
    .filter((entry) => entry.document !== null || entry.hasExecutionView)
    .sort((a, b) => b.tag.localeCompare(a.tag));
}
