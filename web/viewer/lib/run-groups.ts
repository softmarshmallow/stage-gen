// Which workflow a run belongs to, decided from the catalog and nothing else.
//
// A run's documents say what wrote it: an SDK plan its pipeline id, a graph document its
// `recipe` literal and graph kind, a character run its graph kind, a joined view the graph
// kind it was joined from. The catalog says which
// identities each installed workflow's runs carry, so the match is a lookup and the
// viewer learns no workflow by name. Runs no workflow claims are game runs when a game
// wrote them (a graph document literal no workflow owns, or a consumer document), and
// otherwise other runs: an older build's, a calibration's, a user's own pipeline's.

import type { Catalog, CatalogWorkflow } from "@stage-gen/ui/contracts/catalog";

/** What a run's anchor document and its view declare. */
export interface RunIdentity {
  /** The anchor document's file name, or null when the run carries only a view. */
  readonly document: string | null;
  readonly kind: string | null;
  readonly pipelineId: string | null;
  readonly recipe: string | null;
  readonly viewKind: string | null;
  /** The graph kind a joined gnode view was derived from. */
  readonly graphKind: string | null;
  /** The workflow a gnode workflow run's plan names. */
  readonly workflowId?: string | null;
}

export const SDK_GRAPH_KIND = "pipeline-execution-graph-v1";
export const SDK_VIEW_KIND = "pipeline-execution-view-v1";

/** Documents a game writes for its own host to play. */
const CONSUMER_DOCUMENTS = new Set(["manifest.json", "bundle.json", "case.json"]);

function texts(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === "string") : [];
}

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** The identities one workflow's runs carry, read from its declared identity. */
interface Claims {
  readonly graphKinds: ReadonlySet<string>;
  readonly pipelines: ReadonlySet<string>;
  readonly recipe: string | null;
  readonly viewKind: string | null;
}

function claimsOf(workflow: CatalogWorkflow): Claims {
  const declared = workflow.identity.declared;
  const document = record(declared.graph_document);
  const legacy = Array.isArray(document.legacy_graph_identities)
    ? // Each entry is [schema_version, kind]; the kind is its one string.
      document.legacy_graph_identities.flatMap((pair) => texts(pair))
    : [];
  return {
    graphKinds: new Set([
      ...workflow.identity.graphKinds,
      ...texts(declared.plan_kinds),
      ...legacy,
    ]),
    pipelines: new Set(Object.keys(record(declared.pipelines))),
    recipe: typeof document.recipe === "string" ? document.recipe : null,
    viewKind: typeof document.view_kind === "string" ? document.view_kind : null,
  };
}

function claims(identity: RunIdentity, owned: Claims): boolean {
  const sdk = identity.kind === SDK_GRAPH_KIND || identity.viewKind === SDK_VIEW_KIND;
  if (sdk) return identity.pipelineId !== null && owned.pipelines.has(identity.pipelineId);
  return (
    (identity.kind !== null && owned.graphKinds.has(identity.kind)) ||
    (identity.graphKind !== null && owned.graphKinds.has(identity.graphKind)) ||
    (identity.recipe !== null && identity.recipe === owned.recipe) ||
    (identity.viewKind !== null && identity.viewKind === owned.viewKind)
  );
}

/** The id of the workflow whose runs carry this identity, or null. */
export function workflowOf(identity: RunIdentity, catalog: Catalog): string | null {
  // A gnode workflow run names its workflow, and every one shares the same graph kind, so
  // the name decides: a run of a workflow this catalog lacks belongs to none of them.
  if (identity.workflowId) {
    const named = catalog.workflows.find(
      (workflow) =>
        workflow.id === identity.workflowId &&
        identity.kind !== null &&
        workflow.identity.graphKinds.includes(identity.kind),
    );
    return named?.id ?? null;
  }
  return catalog.workflows.find((workflow) => claims(identity, claimsOf(workflow)))?.id ?? null;
}

/** Whether a run no workflow claims was written by a game. */
export function isGameRun(identity: RunIdentity): boolean {
  return (
    identity.recipe !== null ||
    (identity.document !== null && CONSUMER_DOCUMENTS.has(identity.document))
  );
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
