// Parser for the derived execution-view.json a run view is read from: the one a run
// persists, or the one `stage-gen inspect RUN --write-view DIR` and `stage-gen view`
// derive. Wire fields are lower_snake_case; this adapter is the one place they become
// camelCase runtime shapes.
//
// Any `*-execution-view-v1` envelope at schema 3 is read, and so is gnode's own
// `gnode-run-view-v1`, which a view joined from a plain gnode plan carries: the engine
// owns the envelope, so pipeline and game identities are not a registry here. The header
// fields a producer adds beside the envelope become the view's subject. Versioning is
// hard-drop by contract: an unknown envelope is refused with a re-derive instruction,
// never migrated. The view is derived state — the plan, trace, and sidecars stay
// canonical — so a refused document costs one re-derivation, not a migration.

import { artifactReference, parseArtifactPreview, parseLegacyMotion, type ArtifactPreview, type LegacyMotionPreview } from "./artifact-preview";

/** Any authored asset pipeline, independent of the installed workflows. */
export const PIPELINE_EXECUTION_VIEW_KIND = "pipeline-execution-view-v1";

/** gnode's own view kind, carried by a view joined from a plain gnode plan and trace. */
export const GNODE_RUN_VIEW_KIND = "gnode-run-view-v1";

/** Every graph document names its view `<word>-execution-view-v1`. */
const EXECUTION_VIEW_KIND_PATTERN = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*-execution-view-v1$/;

export const EXECUTION_VIEW_SCHEMA_VERSION = 3;

export const EXECUTION_VIEW_REFUSAL =
  "unsupported execution view: expected a *-execution-view-v1 or gnode-run-view-v1 " +
  `document at schema_version ${EXECUTION_VIEW_SCHEMA_VERSION}; derive it again ` +
  "(stage-gen inspect RUN --write-view DIR, or demo-games export-view for a game run)";

export function isExecutionViewKind(value: unknown): value is string {
  return (
    typeof value === "string" &&
    (value === GNODE_RUN_VIEW_KIND || EXECUTION_VIEW_KIND_PATTERN.test(value))
  );
}

// What a run's own records say became of it. "unfinished" deliberately does not
// claim the run is going: a document written once cannot know that. Liveness is
// decided by the reader from traceModifiedAt — see runLiveness below.
export type ExecutionRunState =
  "planned" | "unfinished" | "canceled" | "succeeded" | "failed";

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
  "planned" | "running" | "interrupted" | "canceled" | "succeeded" | "failed";

export function runLiveness(
  run: {
    readonly runState: ExecutionRunState;
    readonly traceModifiedAt: string | null;
  },
  now: number,
): ExecutionRunLiveness {
  if (run.runState !== "unfinished") return run.runState;
  if (run.traceModifiedAt === null) return "interrupted";
  const written = Date.parse(run.traceModifiedAt);
  if (Number.isNaN(written)) return "interrupted";
  return now - written <= RUNNING_TRACE_STALENESS_MS
    ? "running"
    : "interrupted";
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
  "pending" | "running" | "succeeded" | "failed" | "skipped";

export const EXECUTION_NODE_STATES: readonly ExecutionNodeState[] = [
  "pending",
  "running",
  "succeeded",
  "failed",
  "skipped",
];

export type ArtifactDisplay =
  "image" | "audio" | "data" | "text" | "motion_atlas" | "video";

export type ExecutionViewMotion = LegacyMotionPreview;

export interface ExecutionViewArtifact {
  readonly artifactRef: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly mediaType: string;
  readonly present: boolean;
  readonly display: ArtifactDisplay;
  readonly motion: ExecutionViewMotion | null;
  readonly preview: ArtifactPreview | null;
}

/**
 * Which dedicated view a renderer gives a node. A closed engine vocabulary
 * (gnode's ViewArchetype): one view per archetype, and a new archetype is a
 * renderer feature rather than a recipe detail.
 */
export type ViewArchetype =
  | "source"
  | "image"
  | "structured"
  | "judge"
  | "music"
  | "sound"
  | "video"
  | "matte"
  | "transform"
  | "validate"
  | "review"
  | "package";

export const VIEW_ARCHETYPES: readonly ViewArchetype[] = [
  "source",
  "image",
  "structured",
  "judge",
  "music",
  "sound",
  "video",
  "matte",
  "transform",
  "validate",
  "review",
  "package",
] as const;

/** One declared output: an artifact address plus the typed record it carries. */
export interface ExecutionViewPort {
  readonly portId: string;
  readonly artifactRef: string;
  /** The payload contract the artifact satisfies, e.g. "review-verdict-v1". */
  readonly kind: string;
  /** The provenance sidecar paired with this artifact, when one is declared. */
  readonly sidecarRef: string | null;
}

/** An edge endpoint: one named port on one node. */
export interface ExecutionViewPortRef {
  readonly nodeId: string;
  readonly portId: string;
}

/**
 * One input the node consumes that no upstream node produced: a member of the
 * authored package, named and digest-bound, so an input that reaches a
 * provider is never invisible in the plan.
 */
export interface ExecutionViewAuthoredInput {
  readonly label: string;
  readonly ref: string;
  readonly sha256: string;
}

/**
 * The node's definition: what it is told, statically. `prompt` is the text as
 * known at plan time, `templateRef` names a packaged template when composition
 * is runtime-bound, `referenceInputs` point at the derived inputs the node
 * consumes at run time, and `authoredInputs` name the package members it is
 * handed — so the static, derived, and authored halves read side by side.
 */
export interface ExecutionViewCard {
  readonly prompt: string | null;
  readonly templateRef: string | null;
  readonly schemaName: string | null;
  readonly referenceInputs: readonly ExecutionViewPortRef[];
  readonly authoredInputs: readonly ExecutionViewAuthoredInput[];
}

export interface ExecutionViewNode {
  readonly nodeId: string;
  /** Persisted taxonomy path, e.g. "2d/sideview/platformer/motion_atlas.generate". */
  readonly typeId: string;
  /** Joined from the exporter's type registry; null when the type is unregistered. */
  readonly title: string | null;
  readonly archetype: ViewArchetype | null;
  readonly domain: string;
  readonly description: string;
  /** Instance identity: map_id, layer_id, state, actor_id, track_id… */
  readonly params: Readonly<Record<string, string>>;
  readonly dependsOn: readonly string[];
  /** The subset of dependsOn that orders execution without carrying lineage. */
  readonly barrierOnly: readonly string[];
  readonly operation: string;
  readonly resourceId: string;
  readonly provider: string | null;
  readonly model: string | null;
  readonly retryOwner: string;
  readonly maxAttempts: number;
  readonly inputSha256: readonly string[];
  readonly cacheKey: string;
  readonly ports: readonly ExecutionViewPort[];
  readonly card: ExecutionViewCard | null;
  /** Which subgraph-template instance emitted this node, e.g. "catalog-pipeline@v1:props". */
  readonly templateId: string | null;
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

/** A header value a producer added beside the envelope. */
export type SubjectValue = string | number | boolean;

/**
 * Who the run was for. Each producer names its subject with its own header fields —
 * a pipeline its id and title, a graph document its `recipe` literal and its ids, a
 * joined gnode view its graph kind — so they are kept as a map, and the few a reader
 * groups or labels by are lifted out.
 */
export interface ExecutionViewSubject {
  /** The view kind, verbatim. */
  readonly kind: string;
  /** The graph document's persisted `recipe` literal, when the producer has one. */
  readonly recipe: string | null;
  readonly pipelineId: string | null;
  readonly title: string | null;
  /** Every other scalar header field, by its wire name. */
  readonly fields: Readonly<Record<string, SubjectValue>>;
}

/** The one identity a run is labelled by, whichever producer wrote it. */
export function subjectLabel(subject: ExecutionViewSubject): string {
  if (subject.title) return subject.title;
  // A producer's ids are the specific thing the run was for (a universe and its phase,
  // a package and its scope); counts and flags describe it rather than name it.
  const named = Object.values(subject.fields).filter(
    (value): value is string => typeof value === "string" && value.length > 0,
  );
  if (named.length > 0) return named.join(" · ");
  return subject.recipe ?? subject.kind;
}

export interface ExecutionView {
  readonly subject: ExecutionViewSubject;
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
  if (typeof value !== "string")
    throw new Error(`${label} must be a string or null`);
  return value;
}

function count(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative number`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  const result = count(value, label);
  if (!Number.isInteger(result)) throw new Error(`${label} must be an integer`);
  return result;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

function digest(value: unknown, label: string): string {
  const result = text(value, label);
  if (!/^[a-f0-9]{64}$/.test(result)) throw new Error(`${label} must be a SHA-256 digest`);
  return result;
}

function mediaType(value: unknown, label: string): string {
  const result = text(value, label);
  if (!/^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+$/.test(result))
    throw new Error(`${label} must be a bare media type`);
  return result;
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
  return Object.freeze(
    array(value, label).map((entry, index) =>
      text(entry, `${label}[${index}]`),
    ),
  );
}

function nodeState(value: unknown, label: string): ExecutionNodeState {
  if ((EXECUTION_NODE_STATES as readonly unknown[]).includes(value)) {
    return value as ExecutionNodeState;
  }
  throw new Error(
    `${label} must be one of ${EXECUTION_NODE_STATES.join(", ")}`,
  );
}

function artifact(value: unknown, label: string): ExecutionViewArtifact {
  const record = object(value, label);
  let display = record.display;
  if (
    display !== "image" &&
    display !== "audio" &&
    display !== "data" &&
    display !== "text" &&
    display !== "motion_atlas" &&
    display !== "video"
  ) {
    // The engine carries display hints as consumer-owned text; one this renderer has no
    // view for falls back to the ordinary artifact link.
    if (typeof display !== "string" || !display.trim())
      throw new Error(`${label}.display is invalid`);
    display = "data";
  }
  return Object.freeze({
    artifactRef: artifactReference(record.artifact_ref, `${label}.artifact_ref`),
    sha256: digest(record.sha256, `${label}.sha256`),
    bytes: integer(record.bytes, `${label}.bytes`),
    mediaType: mediaType(record.media_type, `${label}.media_type`),
    present: boolean(record.present, `${label}.present`),
    display: display as ArtifactDisplay,
    motion: parseLegacyMotion(record.motion, `${label}.motion`),
    preview: parseArtifactPreview(record.preview, `${label}.preview`),
  });
}

function archetype(value: unknown, label: string): ViewArchetype | null {
  // Null is the exporter admitting it could not join a title and archetype for
  // this type. That is a documented gap, not a broken document: the renderer
  // falls back to the generic view. An unknown *string* is a real disagreement.
  if (value === null || value === undefined) return null;
  if ((VIEW_ARCHETYPES as readonly unknown[]).includes(value))
    return value as ViewArchetype;
  throw new Error(
    `${label} must be null or one of ${VIEW_ARCHETYPES.join(", ")}`,
  );
}

function params(
  value: unknown,
  label: string,
): Readonly<Record<string, string>> {
  const record = object(value ?? {}, label);
  const out: Record<string, string> = {};
  for (const [key, entry] of Object.entries(record)) {
    if (typeof entry !== "string")
      throw new Error(`${label}.${key} must be a string`);
    out[key] = entry;
  }
  return Object.freeze(out);
}

function port(value: unknown, label: string): ExecutionViewPort {
  const record = object(value, label);
  return Object.freeze({
    portId: text(record.port_id, `${label}.port_id`),
    artifactRef: text(record.artifact_ref, `${label}.artifact_ref`),
    kind: text(record.kind, `${label}.kind`),
    sidecarRef: textOrNull(record.sidecar_ref, `${label}.sidecar_ref`),
  });
}

function portRef(value: unknown, label: string): ExecutionViewPortRef {
  const record = object(value, label);
  return Object.freeze({
    nodeId: text(record.node_id, `${label}.node_id`),
    portId: text(record.port_id, `${label}.port_id`),
  });
}

function authoredInput(
  value: unknown,
  label: string,
): ExecutionViewAuthoredInput {
  const record = object(value, label);
  return Object.freeze({
    label: text(record.label, `${label}.label`),
    ref: text(record.ref, `${label}.ref`),
    sha256: text(record.sha256, `${label}.sha256`),
  });
}

function card(value: unknown, label: string): ExecutionViewCard | null {
  if (value === null || value === undefined) return null;
  const record = object(value, label);
  return Object.freeze({
    prompt: textOrNull(record.prompt, `${label}.prompt`),
    templateRef: textOrNull(record.template_ref, `${label}.template_ref`),
    schemaName: textOrNull(record.schema_name, `${label}.schema_name`),
    referenceInputs: Object.freeze(
      array(record.reference_inputs ?? [], `${label}.reference_inputs`).map(
        (entry, index) => portRef(entry, `${label}.reference_inputs[${index}]`),
      ),
    ),
    authoredInputs: Object.freeze(
      array(record.authored_inputs ?? [], `${label}.authored_inputs`).map(
        (entry, index) =>
          authoredInput(entry, `${label}.authored_inputs[${index}]`),
      ),
    ),
  });
}

function node(value: unknown, label: string): ExecutionViewNode {
  const record = object(value, label);
  const cache = record.cache ?? null;
  if (
    cache !== null &&
    cache !== "hit" &&
    cache !== "miss" &&
    cache !== "bypass"
  ) {
    throw new Error(`${label}.cache is invalid`);
  }
  const dependsOn = texts(record.depends_on ?? [], `${label}.depends_on`);
  const barrierOnly = texts(record.barrier_only ?? [], `${label}.barrier_only`);
  for (const barrier of barrierOnly) {
    if (!dependsOn.includes(barrier)) {
      throw new Error(
        `${label}.barrier_only names ${barrier}, which is not a dependency`,
      );
    }
  }
  const ports = Object.freeze(
    array(record.ports ?? [], `${label}.ports`).map((entry, index) =>
      port(entry, `${label}.ports[${index}]`),
    ),
  );
  if (new Set(ports.map((entry) => entry.portId)).size !== ports.length) {
    throw new Error(`${label}.ports must declare unique port ids`);
  }
  return Object.freeze({
    nodeId: text(record.node_id, `${label}.node_id`),
    typeId: text(record.type_id, `${label}.type_id`),
    title: textOrNull(record.title, `${label}.title`),
    archetype: archetype(record.archetype, `${label}.archetype`),
    domain: text(record.domain, `${label}.domain`),
    description: text(record.description, `${label}.description`),
    params: params(record.params, `${label}.params`),
    dependsOn,
    barrierOnly,
    ports,
    card: card(record.card, `${label}.card`),
    templateId: textOrNull(record.template_id, `${label}.template_id`),
    operation: text(record.operation, `${label}.operation`),
    resourceId: text(record.resource_id, `${label}.resource_id`),
    provider: textOrNull(record.provider, `${label}.provider`),
    model: textOrNull(record.model, `${label}.model`),
    retryOwner: text(record.retry_owner, `${label}.retry_owner`),
    maxAttempts: count(record.max_attempts, `${label}.max_attempts`),
    inputSha256: texts(record.input_sha256 ?? [], `${label}.input_sha256`),
    cacheKey: text(record.cache_key, `${label}.cache_key`),
    estimatedDurationSeconds: count(
      record.estimated_duration_seconds,
      `${label}.estimated_duration_seconds`,
    ),
    estimatedCostLowUsd: count(
      record.estimated_cost_low_usd,
      `${label}.estimated_cost_low_usd`,
    ),
    estimatedCostHighUsd: count(
      record.estimated_cost_high_usd,
      `${label}.estimated_cost_high_usd`,
    ),
    state: nodeState(record.state, `${label}.state`),
    startedOffsetMs: countOrNull(
      record.started_offset_ms,
      `${label}.started_offset_ms`,
    ),
    endedOffsetMs: countOrNull(
      record.ended_offset_ms,
      `${label}.ended_offset_ms`,
    ),
    queueMs: countOrNull(record.queue_ms, `${label}.queue_ms`),
    durationMs: countOrNull(record.duration_ms, `${label}.duration_ms`),
    cache,
    attempts: countOrNull(record.attempts, `${label}.attempts`),
    providerOperations: countOrNull(
      record.provider_operations,
      `${label}.provider_operations`,
    ),
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

/** The envelope's own fields; anything else in the header describes the subject. */
const ENVELOPE_FIELDS = new Set([
  "schema_version",
  "kind",
  "graph_sha256",
  "topology_sha256",
  "invocation_id",
  "run_state",
  "trace_modified_at",
  "duration_ms",
  "known_cost_usd",
  "state_counts",
  "resources",
  "nodes",
  "gaps",
  "recipe",
  "pipeline_id",
  "title",
]);

function subject(root: Record<string, unknown>, kind: string): ExecutionViewSubject {
  const fields: Record<string, SubjectValue> = {};
  for (const [name, value] of Object.entries(root)) {
    if (ENVELOPE_FIELDS.has(name)) continue;
    if (typeof value === "string" || typeof value === "boolean") fields[name] = value;
    else if (typeof value === "number" && Number.isFinite(value)) fields[name] = value;
  }
  if (kind === PIPELINE_EXECUTION_VIEW_KIND) {
    const pipelineId = text(root.pipeline_id, "pipeline_id");
    const title = text(root.title, "title");
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(pipelineId))
      throw new Error("pipeline_id must be a safe identifier of at most 128 characters");
    if (!title.trim() || title.trim() !== title || title.length > 256)
      throw new Error("title must be a non-empty string of at most 256 characters");
    return Object.freeze({ kind, recipe: null, pipelineId, title, fields: Object.freeze(fields) });
  }
  return Object.freeze({
    kind,
    recipe: root.recipe === undefined || root.recipe === null ? null : text(root.recipe, "recipe"),
    pipelineId: textOrNull(root.pipeline_id, "pipeline_id"),
    title: textOrNull(root.title, "title"),
    fields: Object.freeze(fields),
  });
}

export function parseExecutionView(value: unknown): ExecutionView {
  const root = object(value, "execution view");
  if (
    root.schema_version !== EXECUTION_VIEW_SCHEMA_VERSION ||
    !isExecutionViewKind(root.kind)
  ) {
    throw new Error(EXECUTION_VIEW_REFUSAL);
  }
  const kind = root.kind;
  const rawCounts = object(root.state_counts, "state_counts");
  const stateCounts = Object.freeze(
    Object.fromEntries(
      EXECUTION_NODE_STATES.map((state) => [
        state,
        integer(rawCounts[state] ?? 0, `state_counts.${state}`),
      ]),
    ),
  ) as Readonly<Record<ExecutionNodeState, number>>;
  const nodes = Object.freeze(
    array(root.nodes, "nodes").map((entry, index) =>
      node(entry, `nodes[${index}]`),
    ),
  );
  const portsByNode = new Map(
    nodes.map((entry) => [
      entry.nodeId,
      new Set(entry.ports.map((declared) => declared.portId)),
    ]),
  );
  if (portsByNode.size !== nodes.length)
    throw new Error("execution view node ids must be unique");
  for (const entry of nodes) {
    for (const dependency of entry.dependsOn) {
      if (!portsByNode.has(dependency)) {
        throw new Error(
          `execution view node ${entry.nodeId} depends on an undeclared node`,
        );
      }
    }
    // A reference input is an edge endpoint, so it is checked like one: a card
    // that points at a port nobody declares would render an input that does not
    // exist, which is worse than refusing the document.
    for (const reference of entry.card?.referenceInputs ?? []) {
      const declared = portsByNode.get(reference.nodeId);
      if (!declared) {
        throw new Error(
          `execution view node ${entry.nodeId} references an undeclared node ${reference.nodeId}`,
        );
      }
      if (!declared.has(reference.portId)) {
        throw new Error(
          `execution view node ${entry.nodeId} references undeclared port ` +
            `${reference.nodeId}/${reference.portId}`,
        );
      }
    }
  }
  return Object.freeze({
    subject: subject(root, kind),
    graphSha256: digest(root.graph_sha256, "graph_sha256"),
    topologySha256: digest(root.topology_sha256, "topology_sha256"),
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
