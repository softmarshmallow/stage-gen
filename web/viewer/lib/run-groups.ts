// Which workflow a run belongs to, decided from the catalog and nothing else.
//
// A workflow run's plan names its workflow and its graph kind; a run that carries only a
// view says the graph kind it was joined from. The catalog says which graph kinds each
// installed workflow's runs carry, so the match is a lookup and the viewer learns no
// workflow by name. Runs no workflow claims are game runs when a game wrote them (a
// delivered package's document), and otherwise other runs.

import type { Catalog, CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";

/** What a run's anchor document and its view declare. */
export interface RunIdentity {
  /** The anchor document's file name, or null when the run carries only a view. */
  readonly document: string | null;
  readonly kind: string | null;
  readonly viewKind: string | null;
  /** The graph kind a joined view was derived from. */
  readonly graphKind: string | null;
  /** The workflow a workflow run's plan names. */
  readonly workflowId?: string | null;
}

/** Documents a game writes for its own host to play. */
const CONSUMER_DOCUMENTS = new Set(["manifest.json", "bundle.json", "case.json"]);

function claims(identity: RunIdentity, workflow: CatalogWorkflow): boolean {
  const kinds = new Set(workflow.identity.graphKinds);
  return (
    (identity.kind !== null && kinds.has(identity.kind)) ||
    (identity.graphKind !== null && kinds.has(identity.graphKind))
  );
}

/** The id of the workflow whose runs carry this identity, or null. */
export function workflowOf(identity: RunIdentity, catalog: Catalog): string | null {
  // A workflow run names its workflow, and every one shares the same graph kind, so the
  // name decides: a run of a workflow this catalog lacks belongs to none of them.
  if (identity.workflowId) {
    const named = catalog.workflows.find(
      (workflow) =>
        workflow.id === identity.workflowId &&
        identity.kind !== null &&
        workflow.identity.graphKinds.includes(identity.kind),
    );
    return named?.id ?? null;
  }
  return catalog.workflows.find((workflow) => claims(identity, workflow))?.id ?? null;
}

/** Whether a run no workflow claims was written by a game. */
export function isGameRun(identity: RunIdentity): boolean {
  return identity.document !== null && CONSUMER_DOCUMENTS.has(identity.document);
}

export interface RunGroups<T> {
  /** Every installed workflow in catalog order, with its runs (perhaps none). */
  readonly workflows: readonly { readonly workflow: CatalogWorkflow; readonly runs: readonly T[] }[];
  readonly game: readonly T[];
  readonly other: readonly T[];
}

/** Newest first: the run touched last is the one a reader came to look at. */
function byUpdate<T extends { readonly updatedAt: string | null }>(a: T, b: T): number {
  return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
}

export function groupRuns<T extends { readonly identity: RunIdentity; readonly updatedAt: string | null }>(
  entries: readonly T[],
  catalog: Catalog | null,
): RunGroups<T> {
  const byWorkflow = new Map<string, T[]>();
  const game: T[] = [];
  const other: T[] = [];
  for (const entry of entries) {
    const workflow = catalog === null ? null : workflowOf(entry.identity, catalog);
    if (workflow !== null) {
      byWorkflow.set(workflow, [...(byWorkflow.get(workflow) ?? []), entry]);
    } else if (isGameRun(entry.identity)) {
      game.push(entry);
    } else {
      other.push(entry);
    }
  }
  return {
    workflows: (catalog?.workflows ?? []).map((workflow) => ({
      workflow,
      runs: (byWorkflow.get(workflow.id) ?? []).sort(byUpdate),
    })),
    game: game.sort(byUpdate),
    other: other.sort(byUpdate),
  };
}
