// Parser for the derived execution-view.json document written by
// `stage-gen export-view`. Wire fields are lower_snake_case; this adapter is
// the one place they become camelCase runtime shapes.
//
// Versioning is hard-drop by contract: an unknown identity is refused with a
// re-export instruction, never migrated. The view is derived state — the plan,
// trace, and sidecars stay canonical — so a refused document costs one
// re-export, not a migration.

export const EXECUTION_VIEW_KIND = "prepared-game-execution-view-v1";
export const EXECUTION_VIEW_SCHEMA_VERSION = 2;

export const EXECUTION_VIEW_REFUSAL =
  `unsupported execution view: expected ${EXECUTION_VIEW_KIND} ` +
  `schema_version ${EXECUTION_VIEW_SCHEMA_VERSION}; re-export this run ` +
  "(stage-gen export-view --run out/<tag>)";

// What a run's own records say became of it. "unfinished" deliberately does not
// claim the run is going: a document written once cannot know that. Liveness is
// decided by the reader from traceModifiedAt — see runLiveness below.
export type ExecutionRunState =
  | "planned"
  | "unfinished"
  | "canceled"
  | "succeeded"
  | "failed";

export const EXECUTION_RUN_STATES: readonly ExecutionRunState[] = [
  "planned",
  "unfinished",
  "canceled",
  "succeeded",
  "failed",
] as const;

// How long an unfinished run may stay silent before a reader stops believing it
// is still going. Nodes are estimated at 120-180s and the scheduler's per-node
// timeout is 1800s, so a live run appends well inside this window; past it, the
// far likelier explanation is that the process is gone. Being wrong is cheap and
// self-correcting in both directions: a genuinely slow run flips back to running
// on its next event, and an abandoned one stops claiming to be alive.
export const RUNNING_TRACE_STALENESS_MS = 15 * 60 * 1000;

// What to tell a reader right now. Unlike ExecutionRunState this is not in the
// document: it folds the run's records together with how long ago they were
// last written, so it can only be decided at read time.
export type ExecutionRunLiveness =
  | "planned"
  | "running"
  | "interrupted"
  | "canceled"
  | "succeeded"
  | "failed";

export function runLiveness(
  run: { readonly runState: ExecutionRunState; readonly traceModifiedAt: string | null },
  now: number,
): ExecutionRunLiveness {
  if (run.runState !== "unfinished") return run.runState;
  if (run.traceModifiedAt === null) return "interrupted";
  const written = Date.parse(run.traceModifiedAt);
  if (Number.isNaN(written)) return "interrupted";
  return now - written <= RUNNING_TRACE_STALENESS_MS ? "running" : "interrupted";
}

// One vocabulary for every surface that names a run's condition.
export const RUN_LIVENESS_LABELS: Record<ExecutionRunLiveness, string> = {
  planned: "planned",
  running: "running",
  interrupted: "interrupted",
  canceled: "canceled",
  succeeded: "ok",
  failed: "failed",
};

// A node in state "running" started and wrote no terminal record. That reads as
// activity only while the run itself is live; otherwise nobody ever finished it.
export function nodeStateLabel(
  state: ExecutionNodeState,
  liveness: ExecutionRunLiveness,
): string {
  return state === "running" && liveness !== "running" ? "abandoned" : state;
}

export type ExecutionNodeState =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped";

export const EXECUTION_NODE_STATES: readonly ExecutionNodeState[] = [
  "pending",
  "running",
  "succeeded",
  "failed",
  "skipped",
];

export type ArtifactDisplay = "image" | "audio" | "data" | "motion_atlas";

export interface ExecutionViewMotion {
  readonly frameCount: number;
  readonly mode: "hold" | "loop" | "once" | "gameplay_driven" | null;
  readonly framesPerSecond: number | null;
  readonly canonicalFrameIndices: readonly number[];
}

export interface ExecutionViewArtifact {
  readonly artifactRef: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly mediaType: string;
  readonly present: boolean;
  readonly display: ArtifactDisplay;
  readonly motion: ExecutionViewMotion | null;
}

export interface ExecutionViewNode {
  readonly nodeId: string;
  readonly domain: string;
  readonly description: string;
  readonly dependsOn: readonly string[];
  readonly operation: string;
  readonly resourceId: string;
  readonly provider: string | null;
  readonly model: string | null;
  readonly retryOwner: string;
  readonly maxAttempts: number;
  readonly inputSha256: readonly string[];
  readonly cacheKey: string;
  readonly outputs: readonly string[];
  readonly estimatedDurationSeconds: number;
  readonly estimatedCostLowUsd: number;
  readonly estimatedCostHighUsd: number;
  readonly state: ExecutionNodeState;
  readonly startedOffsetMs: number | null;
  readonly endedOffsetMs: number | null;
  readonly queueMs: number | null;
  readonly durationMs: number | null;
  readonly cache: "hit" | "miss" | "bypass" | null;
  readonly attempts: number | null;
  readonly providerOperations: number | null;
  readonly knownCostUsd: number | null;
  readonly error: string | null;
  readonly blockedBy: readonly string[];
  readonly artifacts: readonly ExecutionViewArtifact[];
}

export interface ExecutionViewGap {
  readonly gapId: string;
  readonly detail: string;
}

export interface ExecutionView {
  readonly recipe: string;
  readonly gameId: string;
  readonly graphSha256: string;
  readonly topologySha256: string;
  readonly invocationId: string | null;
  readonly runState: ExecutionRunState;
  readonly traceModifiedAt: string | null;
  readonly durationMs: number | null;
  readonly knownCostUsd: number | null;
  readonly stateCounts: Readonly<Record<ExecutionNodeState, number>>;
  readonly nodes: readonly ExecutionViewNode[];
  readonly gaps: readonly ExecutionViewGap[];
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function textOrNull(value: unknown, label: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new Error(`${label} must be a string or null`);
  return value;
}

function count(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative number`);
  }
  return value;
}

function countOrNull(value: unknown, label: string): number | null {
  if (value === null || value === undefined) return null;
  return count(value, label);
}

function runState(value: unknown, label: string): ExecutionRunState {
  if ((EXECUTION_RUN_STATES as readonly unknown[]).includes(value)) {
    return value as ExecutionRunState;
  }
  throw new Error(`${label} must be one of ${EXECUTION_RUN_STATES.join(", ")}`);
}

function texts(value: unknown, label: string): readonly string[] {
  return Object.freeze(array(value, label).map((entry, index) => text(entry, `${label}[${index}]`)));
}

function nodeState(value: unknown, label: string): ExecutionNodeState {
  if ((EXECUTION_NODE_STATES as readonly unknown[]).includes(value)) {
    return value as ExecutionNodeState;
  }
  throw new Error(`${label} must be one of ${EXECUTION_NODE_STATES.join(", ")}`);
}

function motion(value: unknown, label: string): ExecutionViewMotion | null {
  if (value === null || value === undefined) return null;
  const record = object(value, label);
  const mode = record.mode ?? null;
  if (mode !== null && mode !== "hold" && mode !== "loop" && mode !== "once" && mode !== "gameplay_driven") {
    throw new Error(`${label}.mode is invalid`);
  }
  return Object.freeze({
    frameCount: count(record.frame_count, `${label}.frame_count`),
    mode,
    framesPerSecond: countOrNull(record.frames_per_second, `${label}.frames_per_second`),
    canonicalFrameIndices: Object.freeze(
      array(record.canonical_frame_indices ?? [], `${label}.canonical_frame_indices`).map(
        (entry, index) => count(entry, `${label}.canonical_frame_indices[${index}]`),
      ),
    ),
  });
}

function artifact(value: unknown, label: string): ExecutionViewArtifact {
  const record = object(value, label);
  const display = record.display;
  if (display !== "image" && display !== "audio" && display !== "data" && display !== "motion_atlas") {
    throw new Error(`${label}.display is invalid`);
  }
  return Object.freeze({
    artifactRef: text(record.artifact_ref, `${label}.artifact_ref`),
    sha256: text(record.sha256, `${label}.sha256`),
    bytes: count(record.bytes, `${label}.bytes`),
    mediaType: text(record.media_type, `${label}.media_type`),
    present: record.present === true,
    display,
    motion: motion(record.motion, `${label}.motion`),
  });
}

function node(value: unknown, label: string): ExecutionViewNode {
  const record = object(value, label);
  const cache = record.cache ?? null;
  if (cache !== null && cache !== "hit" && cache !== "miss" && cache !== "bypass") {
    throw new Error(`${label}.cache is invalid`);
  }
  return Object.freeze({
    nodeId: text(record.node_id, `${label}.node_id`),
    domain: text(record.domain, `${label}.domain`),
    description: text(record.description, `${label}.description`),
    dependsOn: texts(record.depends_on ?? [], `${label}.depends_on`),
    operation: text(record.operation, `${label}.operation`),
    resourceId: text(record.resource_id, `${label}.resource_id`),
    provider: textOrNull(record.provider, `${label}.provider`),
    model: textOrNull(record.model, `${label}.model`),
    retryOwner: text(record.retry_owner, `${label}.retry_owner`),
    maxAttempts: count(record.max_attempts, `${label}.max_attempts`),
    inputSha256: texts(record.input_sha256 ?? [], `${label}.input_sha256`),
    cacheKey: text(record.cache_key, `${label}.cache_key`),
    outputs: texts(record.outputs ?? [], `${label}.outputs`),
    estimatedDurationSeconds: count(
      record.estimated_duration_seconds,
      `${label}.estimated_duration_seconds`,
    ),
    estimatedCostLowUsd: count(record.estimated_cost_low_usd, `${label}.estimated_cost_low_usd`),
    estimatedCostHighUsd: count(
      record.estimated_cost_high_usd,
      `${label}.estimated_cost_high_usd`,
    ),
    state: nodeState(record.state, `${label}.state`),
    startedOffsetMs: countOrNull(record.started_offset_ms, `${label}.started_offset_ms`),
    endedOffsetMs: countOrNull(record.ended_offset_ms, `${label}.ended_offset_ms`),
    queueMs: countOrNull(record.queue_ms, `${label}.queue_ms`),
    durationMs: countOrNull(record.duration_ms, `${label}.duration_ms`),
    cache,
    attempts: countOrNull(record.attempts, `${label}.attempts`),
    providerOperations: countOrNull(record.provider_operations, `${label}.provider_operations`),
    knownCostUsd: countOrNull(record.known_cost_usd, `${label}.known_cost_usd`),
    error: textOrNull(record.error, `${label}.error`),
    blockedBy: texts(record.blocked_by ?? [], `${label}.blocked_by`),
    artifacts: Object.freeze(
      array(record.artifacts ?? [], `${label}.artifacts`).map((entry, index) =>
        artifact(entry, `${label}.artifacts[${index}]`),
      ),
    ),
  });
}

export function parseExecutionView(value: unknown): ExecutionView {
  const root = object(value, "execution view");
  if (
    root.schema_version !== EXECUTION_VIEW_SCHEMA_VERSION ||
    root.kind !== EXECUTION_VIEW_KIND
  ) {
    throw new Error(EXECUTION_VIEW_REFUSAL);
  }
  const rawCounts = object(root.state_counts, "state_counts");
  const stateCounts = Object.freeze(
    Object.fromEntries(
      EXECUTION_NODE_STATES.map((state) => [
        state,
        count(rawCounts[state] ?? 0, `state_counts.${state}`),
      ]),
    ),
  ) as Readonly<Record<ExecutionNodeState, number>>;
  const nodes = Object.freeze(
    array(root.nodes, "nodes").map((entry, index) => node(entry, `nodes[${index}]`)),
  );
  const nodeIds = new Set(nodes.map((entry) => entry.nodeId));
  if (nodeIds.size !== nodes.length) throw new Error("execution view node ids must be unique");
  for (const entry of nodes) {
    for (const dependency of entry.dependsOn) {
      if (!nodeIds.has(dependency)) {
        throw new Error(`execution view node ${entry.nodeId} depends on an undeclared node`);
      }
    }
  }
  return Object.freeze({
    recipe: text(root.recipe, "recipe"),
    gameId: text(root.game_id, "game_id"),
    graphSha256: text(root.graph_sha256, "graph_sha256"),
    topologySha256: text(root.topology_sha256, "topology_sha256"),
    invocationId: textOrNull(root.invocation_id, "invocation_id"),
    runState: runState(root.run_state, "run_state"),
    traceModifiedAt: textOrNull(root.trace_modified_at, "trace_modified_at"),
    durationMs: countOrNull(root.duration_ms, "duration_ms"),
    knownCostUsd: countOrNull(root.known_cost_usd, "known_cost_usd"),
    stateCounts,
    nodes,
    gaps: Object.freeze(
      array(root.gaps ?? [], "gaps").map((entry, index) => {
        const record = object(entry, `gaps[${index}]`);
        return Object.freeze({
          gapId: text(record.gap_id, `gaps[${index}].gap_id`),
          detail: text(record.detail, `gaps[${index}].detail`),
        });
      }),
    ),
  });
}
