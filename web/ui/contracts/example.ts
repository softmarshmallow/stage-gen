// Parsers for the example contract (stage_gen.examples): `workflow-example-v1`
// (example.json), the figures ledger beside it (figures.json), and the entry a game
// writes for an example it made (`game-example-entry-v1`, entry.json). Wire fields are
// lower_snake_case; this adapter is the one place they become camelCase runtime shapes.
//
// An example is frozen evidence pinned by digest, so versioning is hard-drop: an unknown
// envelope is refused with a re-export instruction, never migrated. `inputs`, `outputs`,
// node verdicts, checks and pictures stay opaque JSON; the page that shows them owns
// their meaning.

import {
  anyText,
  digest,
  envelope,
  integer,
  integerOrNull,
  jsonObject,
  jsonObjectOrNull,
  json,
  list,
  number,
  numberOrNull,
  object,
  oneOf,
  record,
  text,
  textOrNull,
  type JsonObject,
  type JsonValue,
} from "./wire";

export const EXAMPLE_KIND = "workflow-example-v1";
export const EXAMPLE_SCHEMA_VERSION = 1;
export const EXAMPLE_REFUSAL =
  `unsupported example: expected ${EXAMPLE_KIND} schema_version ${EXAMPLE_SCHEMA_VERSION}; ` +
  "re-export it (scripts/examples.py promote, or the game's example export)";

export const GAME_EXAMPLE_ENTRY_KIND = "game-example-entry-v1";
export const GAME_EXAMPLE_ENTRY_SCHEMA_VERSION = 1;
export const GAME_EXAMPLE_ENTRY_REFUSAL =
  `unsupported game example entry: expected ${GAME_EXAMPLE_ENTRY_KIND} ` +
  `schema_version ${GAME_EXAMPLE_ENTRY_SCHEMA_VERSION}; re-export it with the game's example export`;

/** Whether an example still describes what its maker does today. Derived, never declared. */
export type Currency = "current" | "earlier_version";
export const CURRENCIES: readonly Currency[] = ["current", "earlier_version"];

/** A node an example ran inside a source run's graph, or one its importer composed. */
export type NodeOrigin = "run" | "derived";
const NODE_ORIGINS: readonly NodeOrigin[] = ["run", "derived"];

export interface MadeBy {
  readonly kind: "workflow" | "game";
  readonly id: string;
}

export interface SourceRun {
  readonly path: string;
  /** The run document the digest binds: execution-plan.json, graph.json, ... */
  readonly anchor: string;
  readonly anchorSha256: string;
}

export interface ExampleModel {
  /** A display name, never a route identifier. */
  readonly name: string;
  readonly provider: string | null;
  readonly roles: readonly string[];
  readonly nodes: number;
  readonly calledBy: readonly string[];
}

export interface ExampleNode {
  readonly id: string;
  readonly typeId: string;
  readonly kind: string;
  readonly description: string;
  readonly provider: string | null;
  readonly model: string | null;
  readonly retryOwner: string | null;
  readonly maxAttempts: number | null;
  readonly dependsOn: readonly string[];
  readonly state: string;
  readonly attempts: number | null;
  readonly durationMs: number | null;
  readonly costUsd: number | null;
  readonly providerOperations: number | null;
  readonly cache: string | null;
  readonly notNeeded: string | null;
  readonly verdict: JsonObject | null;
  readonly checks: readonly JsonObject[];
  readonly prompt: string | null;
  readonly rationale: string | null;
  readonly openIssues: readonly JsonValue[];
  readonly recordRef: string | null;
  readonly thumb: JsonObject | null;
  readonly pictures: readonly JsonObject[];
  readonly origin: NodeOrigin;
}

export interface TreeEntry {
  readonly kind: "dir" | "file";
  readonly bytes: number;
  /** Files below a directory; null for a file. */
  readonly files: number | null;
  /** Direct entries of a directory; null for a file. */
  readonly entries: number | null;
}

export interface WorkflowExample {
  readonly exampleId: string;
  readonly madeBy: MadeBy;
  readonly importer: string;
  /** The run folder a consumer receives. */
  readonly deliveredRun: string;
  readonly sourceRuns: readonly SourceRun[];
  /** Every file the importer read, with its digest; null for a converted record. */
  readonly sourceFiles: Readonly<Record<string, string>> | null;
  readonly status: string | null;
  /** The persisted kind of the graph `graphSha256` names; null when no run persisted one. */
  readonly graphKind: string | null;
  readonly graphSha256: string | null;
  readonly inputs: Readonly<Record<string, JsonObject>>;
  readonly outputs: Readonly<Record<string, JsonObject>>;
  readonly metrics: Readonly<Record<string, number>>;
  readonly models: readonly ExampleModel[];
  /** Run-relative path ("" is the run folder itself) to what it held. */
  readonly tree: Readonly<Record<string, TreeEntry>>;
  readonly nodes: Readonly<Record<string, ExampleNode>>;
}

export interface FigureSource {
  readonly path: string;
  readonly sha256: string;
}

export interface FigureEntry {
  /** Example-relative path of the derived file, e.g. "media/input.webp". */
  readonly file: string;
  readonly sha256: string;
  readonly bytes: number;
  readonly size: readonly [number, number] | null;
  readonly sources: readonly FigureSource[];
  readonly transform: string;
}

export interface FiguresLedger {
  readonly run: string;
  readonly files: readonly FigureEntry[];
}

export interface GameExampleStep {
  readonly label: string;
  readonly note: string;
  /** Node ids of the example, titled by the entry's labels. */
  readonly members: readonly string[];
}

export interface ExampleTool {
  readonly name: string;
  readonly role: string;
}

export interface GameExampleEntry {
  readonly madeBy: MadeBy;
  readonly gameTitle: string;
  readonly title: string;
  readonly promise: string;
  /** Position among the landing cards; null when the example is not a card. */
  readonly order: number | null;
  readonly related: readonly string[];
  readonly command: string;
  readonly footer: string | null;
  readonly tools: readonly ExampleTool[];
  readonly labels: Readonly<Record<string, string>>;
  readonly steps: readonly GameExampleStep[];
  readonly currency: Currency;
  readonly exampleSha256: string;
  readonly figuresSha256: string;
}

function texts(value: unknown, label: string): readonly string[] {
  return list(value, label, text);
}

export function parseMadeBy(value: unknown, label: string): MadeBy {
  const fields = object(value, label);
  return Object.freeze({
    kind: oneOf(fields.kind, `${label}.kind`, ["workflow", "game"] as const),
    id: text(fields.id, `${label}.id`),
  });
}

export function parseCurrency(value: unknown, label: string): Currency {
  return oneOf(value, label, CURRENCIES);
}

function sourceRun(value: unknown, label: string): SourceRun {
  const fields = object(value, label);
  return Object.freeze({
    path: text(fields.path, `${label}.path`),
    anchor: text(fields.anchor, `${label}.anchor`),
    anchorSha256: digest(fields.anchor_sha256, `${label}.anchor_sha256`),
  });
}

function model(value: unknown, label: string): ExampleModel {
  const fields = object(value, label);
  return Object.freeze({
    name: text(fields.name, `${label}.name`),
    provider: textOrNull(fields.provider, `${label}.provider`),
    roles: texts(fields.roles, `${label}.roles`),
    nodes: integer(fields.nodes, `${label}.nodes`),
    calledBy: texts(fields.called_by, `${label}.called_by`),
  });
}

function node(value: unknown, label: string): ExampleNode {
  const fields = object(value, label);
  return Object.freeze({
    id: text(fields.id, `${label}.id`),
    typeId: text(fields.type_id, `${label}.type_id`),
    kind: anyText(fields.kind, `${label}.kind`),
    description: anyText(fields.description, `${label}.description`),
    provider: textOrNull(fields.provider, `${label}.provider`),
    model: textOrNull(fields.model, `${label}.model`),
    retryOwner: textOrNull(fields.retry_owner, `${label}.retry_owner`),
    maxAttempts: integerOrNull(fields.max_attempts, `${label}.max_attempts`),
    dependsOn: texts(fields.depends_on, `${label}.depends_on`),
    state: text(fields.state, `${label}.state`),
    attempts: integerOrNull(fields.attempts, `${label}.attempts`),
    durationMs: numberOrNull(fields.duration_ms, `${label}.duration_ms`),
    costUsd: numberOrNull(fields.cost_usd, `${label}.cost_usd`),
    providerOperations: integerOrNull(fields.provider_operations, `${label}.provider_operations`),
    cache: textOrNull(fields.cache, `${label}.cache`),
    notNeeded: textOrNull(fields.not_needed, `${label}.not_needed`),
    verdict: jsonObjectOrNull(fields.verdict, `${label}.verdict`),
    checks: list(fields.checks, `${label}.checks`, jsonObject),
    prompt: textOrNull(fields.prompt, `${label}.prompt`),
    rationale: textOrNull(fields.rationale, `${label}.rationale`),
    openIssues: list(fields.open_issues, `${label}.open_issues`, json),
    recordRef: textOrNull(fields.record_ref, `${label}.record_ref`),
    thumb: jsonObjectOrNull(fields.thumb, `${label}.thumb`),
    pictures: list(fields.pictures, `${label}.pictures`, jsonObject),
    origin: oneOf(fields.origin, `${label}.origin`, NODE_ORIGINS),
  });
}

function treeEntry(value: unknown, label: string): TreeEntry {
  const fields = object(value, label);
  const kind = oneOf(fields.kind, `${label}.kind`, ["dir", "file"] as const);
  return Object.freeze({
    kind,
    bytes: integer(fields.bytes, `${label}.bytes`),
    files: integerOrNull(fields.files, `${label}.files`),
    entries: integerOrNull(fields.entries, `${label}.entries`),
  });
}

export function parseWorkflowExample(value: unknown): WorkflowExample {
  const root = envelope(value, EXAMPLE_KIND, EXAMPLE_SCHEMA_VERSION, EXAMPLE_REFUSAL);
  const sourceRuns = list(root.source_runs, "source_runs", sourceRun);
  if (sourceRuns.length === 0) throw new Error("source_runs must name at least one run");
  const nodes = record(root.nodes, "nodes", node);
  for (const [key, entry] of Object.entries(nodes)) {
    if (entry.id !== key) throw new Error(`nodes.${key}.id must equal its key`);
    for (const dependency of entry.dependsOn) {
      if (!(dependency in nodes)) {
        throw new Error(`nodes.${key} depends on an undeclared node ${dependency}`);
      }
    }
  }
  const sourceFiles = root.source_files ?? null;
  return Object.freeze({
    exampleId: text(root.example_id, "example_id"),
    madeBy: parseMadeBy(root.made_by, "made_by"),
    importer: anyText(root.importer, "importer"),
    deliveredRun: anyText(root.delivered_run, "delivered_run"),
    sourceRuns,
    sourceFiles: sourceFiles === null ? null : record(sourceFiles, "source_files", digest),
    status: textOrNull(root.status, "status"),
    graphKind: textOrNull(root.graph_kind, "graph_kind"),
    graphSha256:
      root.graph_sha256 === null || root.graph_sha256 === undefined
        ? null
        : digest(root.graph_sha256, "graph_sha256"),
    inputs: record(root.inputs, "inputs", jsonObject),
    outputs: record(root.outputs, "outputs", jsonObject),
    metrics: record(root.metrics, "metrics", number),
    models: list(root.models, "models", model),
    tree: record(root.tree, "tree", treeEntry),
    nodes,
  });
}

function figureEntry(value: unknown, label: string): FigureEntry {
  const fields = object(value, label);
  const size = fields.size ?? null;
  let pair: readonly [number, number] | null = null;
  if (size !== null) {
    const values = list(size, `${label}.size`, (entry, at) => integer(entry, at, 1));
    if (values.length !== 2) throw new Error(`${label}.size must be [width, height]`);
    pair = Object.freeze([values[0], values[1]] as const);
  }
  return Object.freeze({
    file: text(fields.file, `${label}.file`),
    sha256: digest(fields.sha256, `${label}.sha256`),
    bytes: integer(fields.bytes, `${label}.bytes`),
    size: pair,
    sources: list(fields.sources, `${label}.sources`, (entry, at) => {
      const source = object(entry, at);
      return Object.freeze({
        path: text(source.path, `${at}.path`),
        sha256: digest(source.sha256, `${at}.sha256`),
      });
    }),
    transform: anyText(fields.transform, `${label}.transform`),
  });
}

export function parseFiguresLedger(value: unknown): FiguresLedger {
  const root = object(value, "figures");
  return Object.freeze({
    run: anyText(root.run, "run"),
    files: list(root.files, "files", figureEntry),
  });
}

/** The last entry for each file: a file written twice keeps its final bytes. */
export function latestFigures(ledger: FiguresLedger): ReadonlyMap<string, FigureEntry> {
  return new Map(ledger.files.map((entry) => [entry.file, entry]));
}

/** One labelled group of an example's node ids, from a game's entry or a workflow.toml entry. */
export function parseExampleStep(value: unknown, label: string): GameExampleStep {
  const fields = object(value, label);
  const members = texts(fields.members, `${label}.members`);
  if (members.length === 0) throw new Error(`${label}.members must not be empty`);
  return Object.freeze({
    label: text(fields.label, `${label}.label`),
    note: anyText(fields.note, `${label}.note`),
    members,
  });
}

export function parseGameExampleEntry(value: unknown): GameExampleEntry {
  const root = envelope(
    value,
    GAME_EXAMPLE_ENTRY_KIND,
    GAME_EXAMPLE_ENTRY_SCHEMA_VERSION,
    GAME_EXAMPLE_ENTRY_REFUSAL,
  );
  const madeBy = parseMadeBy(root.made_by, "made_by");
  if (madeBy.kind !== "game") throw new Error("made_by.kind must be game");
  return Object.freeze({
    madeBy,
    gameTitle: text(root.game_title, "game_title"),
    title: text(root.title, "title"),
    promise: text(root.promise, "promise"),
    order: integerOrNull(root.order, "order", 1),
    related: texts(root.related ?? [], "related"),
    command: text(root.command, "command"),
    footer: textOrNull(root.footer, "footer"),
    tools: list(root.tools ?? [], "tools", (entry, label) => {
      const fields = object(entry, label);
      return Object.freeze({
        name: text(fields.name, `${label}.name`),
        role: text(fields.role, `${label}.role`),
      });
    }),
    labels: record(root.labels ?? {}, "labels", text),
    steps: list(root.steps ?? [], "steps", parseExampleStep),
    currency: parseCurrency(root.currency, "currency"),
    exampleSha256: digest(root.example_sha256, "example_sha256"),
    figuresSha256: digest(root.figures_sha256, "figures_sha256"),
  });
}
