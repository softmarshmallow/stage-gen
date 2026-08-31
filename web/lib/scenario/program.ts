// The `scenario-program-v1` document, validated the way this repository
// validates every persisted contract: by hand, strictly, refusing unknown and
// missing keys alike rather than trusting a shape because it parsed.
//
// This is the producer's compiled narrative, not a second authoring format. The
// Python side parsed the script, folded it into these statements, and proved the
// whole graph reachable before any art was paid for. Nothing here re-derives any
// of that; the runtime's job is to walk what was already admitted.

export const SCENARIO_PROGRAM_KIND = "scenario-program-v1";

const SNAKE_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const TEXT_MAX = 600;

export type ScenarioSlot = "left" | "center" | "right";

export interface ScenarioCondition {
  readonly requires: readonly string[];
  readonly forbids: readonly string[];
}

export interface ScenarioLine {
  readonly kind: "line";
  readonly speaker: string | null;
  readonly expression: string | null;
  readonly text: string;
}

export interface ScenarioShow {
  readonly kind: "show";
  readonly actor: string;
  readonly expression: string | null;
  readonly slot: ScenarioSlot;
}

export interface ScenarioHide {
  readonly kind: "hide";
  readonly actor: string;
}

export interface ScenarioStage {
  readonly kind: "stage";
  readonly stage: string;
}

export interface ScenarioAudio {
  readonly kind: "audio";
  readonly action: "play" | "stop";
  readonly track: string;
}

export interface ScenarioSet {
  readonly kind: "set";
  readonly flag: string;
  readonly value: boolean;
}

export interface ScenarioChoiceOption {
  readonly text: string;
  readonly target: string;
  readonly condition: ScenarioCondition | null;
}

export interface ScenarioChoice {
  readonly kind: "choice";
  readonly options: readonly ScenarioChoiceOption[];
}

export interface ScenarioBranchEdge {
  readonly condition: ScenarioCondition;
  readonly target: string;
}

export interface ScenarioBranch {
  readonly kind: "branch";
  readonly edges: readonly ScenarioBranchEdge[];
  readonly default: string;
}

export interface ScenarioJump {
  readonly kind: "jump";
  readonly target: string;
}

export interface ScenarioEnd {
  readonly kind: "end";
  readonly outcome: string;
}

export type ScenarioStatement =
  | ScenarioLine
  | ScenarioShow
  | ScenarioHide
  | ScenarioStage
  | ScenarioAudio
  | ScenarioSet
  | ScenarioChoice
  | ScenarioBranch
  | ScenarioJump
  | ScenarioEnd;

export interface ScenarioBlock {
  readonly label: string;
  readonly statements: readonly ScenarioStatement[];
}

export interface ScenarioCastMember {
  readonly actorId: string;
  readonly displayName: string | null;
  /** An actor that declares expressions can be shown; one that declares none speaks only. */
  readonly expressions: readonly string[];
}

export interface ScenarioStageDeclaration {
  readonly stageId: string;
  readonly brief: string;
}

/**
 * How the producer was asked to make this track.
 *
 * Production metadata the runtime never reads, carried because the compiled
 * program is what the generator fans out over and the wire must round-trip
 * whole. Parsed strictly all the same: an unknown key here is drift.
 */
export interface ScenarioTrackGeneration {
  readonly intent: "generate";
  readonly instrumental: boolean;
  readonly seamlessLoop: boolean;
  readonly targetDurationSeconds: number;
}

export interface ScenarioTrackDeclaration {
  readonly trackId: string;
  readonly brief: string;
  readonly generation: ScenarioTrackGeneration;
}

export interface ScenarioEnding {
  readonly outcomeId: string;
  readonly label: string;
}

export interface ScenarioProgram {
  readonly gameId: string;
  readonly scenarioId: string;
  readonly displayName: string;
  readonly revision: number;
  readonly scriptSha256: string;
  readonly entry: string;
  readonly cast: readonly ScenarioCastMember[];
  readonly stages: readonly ScenarioStageDeclaration[];
  readonly tracks: readonly ScenarioTrackDeclaration[];
  readonly flags: readonly string[];
  readonly endings: readonly ScenarioEnding[];
  readonly blocks: readonly ScenarioBlock[];
}

/**
 * Validate one compiled scenario program.
 *
 * Structural only, deliberately. Whether a label resolves or an ending is
 * reachable was settled by the admission proof offline; re-deciding it here
 * would be a second opinion about a question that already has an answer, and a
 * consumer that disagreed with the proof would be the bug.
 */
export function parseScenarioProgram(value: unknown): ScenarioProgram {
  const root = strictRecord(
    value,
    [
      "schema_version",
      "kind",
      "game_id",
      "scenario_id",
      "display_name",
      "revision",
      "script_sha256",
      "entry",
      "cast",
      "stages",
      "endings",
      "blocks",
    ],
    "scenario program",
    ["tracks", "flags"],
  );
  exact(root.schema_version, 1, "scenario program schema_version");
  exact(root.kind, SCENARIO_PROGRAM_KIND, "scenario program kind");

  const program: ScenarioProgram = {
    gameId: text(root.game_id, "scenario game_id", 96),
    scenarioId: snakeId(root.scenario_id, "scenario_id"),
    displayName: text(root.display_name, "scenario display_name", 96),
    revision: positiveInteger(root.revision, "scenario revision"),
    scriptSha256: sha256(root.script_sha256, "scenario script_sha256"),
    entry: snakeId(root.entry, "scenario entry"),
    cast: Object.freeze(list(root.cast, "scenario cast", 1).map(castMember)),
    stages: Object.freeze(list(root.stages, "scenario stages", 1).map(stageDeclaration)),
    tracks: Object.freeze(list(root.tracks ?? [], "scenario tracks", 0).map(trackDeclaration)),
    flags: Object.freeze(list(root.flags ?? [], "scenario flags", 0).map(flagDeclaration)),
    endings: Object.freeze(list(root.endings, "scenario endings", 1).map(ending)),
    blocks: Object.freeze(list(root.blocks, "scenario blocks", 1).map(block)),
  };

  const labels = new Set(program.blocks.map((entry) => entry.label));
  if (labels.size !== program.blocks.length) {
    throw new Error("scenario block labels must be unique");
  }
  if (!labels.has(program.entry)) {
    throw new Error(`scenario entry ${program.entry} does not name a block`);
  }
  return Object.freeze(program);
}

// ------------------------------------------------------------------ members

function castMember(value: unknown, index: number): ScenarioCastMember {
  const record = strictRecord(
    value,
    ["actor_id", "expressions"],
    `scenario cast[${index}]`,
    ["display_name"],
  );
  return Object.freeze({
    actorId: snakeId(record.actor_id, `scenario cast[${index}].actor_id`),
    displayName: optionalText(
      record.display_name ?? null,
      `scenario cast[${index}].display_name`,
      96,
    ),
    expressions: Object.freeze(
      list(record.expressions, `scenario cast[${index}].expressions`, 0).map((entry, at) =>
        snakeId(entry, `scenario cast[${index}].expressions[${at}]`),
      ),
    ),
  });
}

function stageDeclaration(value: unknown, index: number): ScenarioStageDeclaration {
  const record = strictRecord(value, ["stage_id", "brief"], `scenario stages[${index}]`);
  return Object.freeze({
    stageId: snakeId(record.stage_id, `scenario stages[${index}].stage_id`),
    brief: text(record.brief, `scenario stages[${index}].brief`, TEXT_MAX),
  });
}

function trackDeclaration(value: unknown, index: number): ScenarioTrackDeclaration {
  const record = strictRecord(
    value,
    ["track_id", "brief", "generation"],
    `scenario tracks[${index}]`,
  );
  const generation = strictRecord(
    record.generation,
    ["intent", "instrumental", "seamless_loop", "target_duration_seconds"],
    `scenario tracks[${index}].generation`,
  );
  exact(generation.intent, "generate", `scenario tracks[${index}].generation.intent`);
  return Object.freeze({
    trackId: snakeId(record.track_id, `scenario tracks[${index}].track_id`),
    brief: text(record.brief, `scenario tracks[${index}].brief`, TEXT_MAX),
    generation: Object.freeze({
      intent: "generate" as const,
      instrumental: boolean(
        generation.instrumental,
        `scenario tracks[${index}].generation.instrumental`,
      ),
      seamlessLoop: boolean(
        generation.seamless_loop,
        `scenario tracks[${index}].generation.seamless_loop`,
      ),
      targetDurationSeconds: positiveInteger(
        generation.target_duration_seconds,
        `scenario tracks[${index}].generation.target_duration_seconds`,
      ),
    }),
  });
}

function flagDeclaration(value: unknown, index: number): string {
  const record = strictRecord(value, ["flag_id"], `scenario flags[${index}]`);
  return snakeId(record.flag_id, `scenario flags[${index}].flag_id`);
}

function ending(value: unknown, index: number): ScenarioEnding {
  const record = strictRecord(value, ["outcome_id", "label"], `scenario endings[${index}]`);
  return Object.freeze({
    outcomeId: snakeId(record.outcome_id, `scenario endings[${index}].outcome_id`),
    label: text(record.label, `scenario endings[${index}].label`, 96),
  });
}

function block(value: unknown, index: number): ScenarioBlock {
  const record = strictRecord(value, ["label", "statements"], `scenario blocks[${index}]`);
  const label = snakeId(record.label, `scenario blocks[${index}].label`);
  const statements = list(record.statements, `block ${label} statements`, 1).map((entry, at) =>
    statement(entry, `block ${label} statement ${at}`),
  );
  const terminal = statements[statements.length - 1];
  if (!isTerminal(terminal)) {
    throw new Error(`block ${label} must end with a terminal statement`);
  }
  if (statements.slice(0, -1).some(isTerminal)) {
    throw new Error(`block ${label} continues past a terminal statement`);
  }
  return Object.freeze({ label, statements: Object.freeze(statements) });
}

/** A block never falls through, which is what makes the runtime a walk of a graph. */
export function isTerminal(value: ScenarioStatement | undefined): boolean {
  return (
    value !== undefined &&
    (value.kind === "choice" ||
      value.kind === "branch" ||
      value.kind === "jump" ||
      value.kind === "end")
  );
}

// --------------------------------------------------------------- statements

function statement(value: unknown, label: string): ScenarioStatement {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const kind = (value as Record<string, unknown>).kind;
  switch (kind) {
    case "line":
      return lineStatement(value, label);
    case "show":
      return showStatement(value, label);
    case "hide":
      return Object.freeze({
        kind: "hide",
        actor: snakeId(strictRecord(value, ["kind", "actor"], label).actor, `${label} actor`),
      });
    case "stage":
      return Object.freeze({
        kind: "stage",
        stage: snakeId(strictRecord(value, ["kind", "stage"], label).stage, `${label} stage`),
      });
    case "audio":
      return audioStatement(value, label);
    case "set":
      return setStatement(value, label);
    case "choice":
      return choiceStatement(value, label);
    case "branch":
      return branchStatement(value, label);
    case "jump":
      return Object.freeze({
        kind: "jump",
        target: snakeId(strictRecord(value, ["kind", "target"], label).target, `${label} target`),
      });
    case "end":
      return Object.freeze({
        kind: "end",
        outcome: snakeId(
          strictRecord(value, ["kind", "outcome"], label).outcome,
          `${label} outcome`,
        ),
      });
    default:
      throw new Error(`${label} has an unsupported kind: ${String(kind)}`);
  }
}

function lineStatement(value: unknown, label: string): ScenarioLine {
  const record = strictRecord(value, ["kind", "text"], label, ["speaker", "expression"]);
  const speaker =
    record.speaker == null ? null : snakeId(record.speaker, `${label} speaker`);
  const expression =
    record.expression == null ? null : snakeId(record.expression, `${label} expression`);
  if (expression !== null && speaker === null) {
    throw new Error(`${label} is narration and cannot carry an expression`);
  }
  return Object.freeze({
    kind: "line",
    speaker,
    expression,
    text: text(record.text, `${label} text`, TEXT_MAX),
  });
}

function showStatement(value: unknown, label: string): ScenarioShow {
  const record = strictRecord(value, ["kind", "actor", "slot"], label, ["expression"]);
  return Object.freeze({
    kind: "show",
    actor: snakeId(record.actor, `${label} actor`),
    expression:
      record.expression == null ? null : snakeId(record.expression, `${label} expression`),
    slot: slot(record.slot, `${label} slot`),
  });
}

function audioStatement(value: unknown, label: string): ScenarioAudio {
  const record = strictRecord(value, ["kind", "action", "track"], label);
  if (record.action !== "play" && record.action !== "stop") {
    throw new Error(`${label} action must be play or stop`);
  }
  return Object.freeze({
    kind: "audio",
    action: record.action,
    track: snakeId(record.track, `${label} track`),
  });
}

function setStatement(value: unknown, label: string): ScenarioSet {
  const record = strictRecord(value, ["kind", "flag"], label, ["value"]);
  // `set <flag>` compiles to value true, and the canonical form omits a default.
  const raw = record.value ?? true;
  if (typeof raw !== "boolean") throw new Error(`${label} value must be a boolean`);
  return Object.freeze({
    kind: "set",
    flag: snakeId(record.flag, `${label} flag`),
    value: raw,
  });
}

function choiceStatement(value: unknown, label: string): ScenarioChoice {
  const record = strictRecord(value, ["kind", "options"], label);
  const options = list(record.options, `${label} options`, 2).map((entry, index) => {
    const option = strictRecord(
      entry,
      ["text", "target"],
      `${label} option ${index}`,
      ["condition"],
    );
    return Object.freeze({
      text: text(option.text, `${label} option ${index} text`, TEXT_MAX),
      target: snakeId(option.target, `${label} option ${index} target`),
      condition:
        option.condition == null
          ? null
          : condition(option.condition, `${label} option ${index} condition`),
    });
  });
  return Object.freeze({ kind: "choice", options: Object.freeze(options) });
}

function branchStatement(value: unknown, label: string): ScenarioBranch {
  const record = strictRecord(value, ["kind", "edges", "default"], label);
  const edges = list(record.edges, `${label} edges`, 1).map((entry, index) => {
    const edge = strictRecord(entry, ["condition", "target"], `${label} edge ${index}`);
    return Object.freeze({
      condition: condition(edge.condition, `${label} edge ${index} condition`),
      target: snakeId(edge.target, `${label} edge ${index} target`),
    });
  });
  return Object.freeze({
    kind: "branch",
    edges: Object.freeze(edges),
    default: snakeId(record.default, `${label} default`),
  });
}

function condition(value: unknown, label: string): ScenarioCondition {
  const record = strictRecord(value, [], label, ["requires", "forbids"]);
  const requires = list(record.requires ?? [], `${label} requires`, 0).map((entry, index) =>
    snakeId(entry, `${label} requires[${index}]`),
  );
  const forbids = list(record.forbids ?? [], `${label} forbids`, 0).map((entry, index) =>
    snakeId(entry, `${label} forbids[${index}]`),
  );
  if (requires.length === 0 && forbids.length === 0) {
    throw new Error(`${label} must test at least one flag`);
  }
  return Object.freeze({ requires: Object.freeze(requires), forbids: Object.freeze(forbids) });
}

// ------------------------------------------------------------------ scalars

/**
 * Refuse unknown keys and missing REQUIRED keys; allow optional ones to be absent.
 *
 * Absent and null mean the same thing on this wire. The producer's canonical
 * form omits nulls, so `speaker: null` on a narration line simply is not there -
 * demanding the key would refuse every document the producer actually writes.
 * Unknown keys are still refused, which is the half of strictness that catches
 * drift.
 */
function strictRecord(
  value: unknown,
  requiredKeys: readonly string[],
  label: string,
  optionalKeys: readonly string[] = [],
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const known = new Set([...requiredKeys, ...optionalKeys]);
  const missing = requiredKeys.filter(
    (key) => !Object.prototype.hasOwnProperty.call(record, key),
  );
  const extra = Object.keys(record).filter((key) => !known.has(key));
  if (missing.length > 0 || extra.length > 0) {
    throw new Error(
      `${label} keys must match the schema` +
        `${missing.length > 0 ? `; missing ${missing.join(", ")}` : ""}` +
        `${extra.length > 0 ? `; unexpected ${extra.join(", ")}` : ""}`,
    );
  }
  return record;
}

function list(value: unknown, label: string, minimum: number): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  if (value.length < minimum) {
    throw new Error(`${label} must contain at least ${minimum} entries`);
  }
  return value;
}

function text(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) {
    throw new Error(`${label} must be a trimmed non-empty string`);
  }
  if (value.length > maxLength) throw new Error(`${label} must be at most ${maxLength} characters`);
  return value;
}

function optionalText(value: unknown, label: string, maxLength: number): string | null {
  return value === null ? null : text(value, label, maxLength);
}

function snakeId(value: unknown, label: string): string {
  if (typeof value !== "string" || !SNAKE_ID.test(value)) {
    throw new Error(`${label} must be a lower_snake_case identifier`);
  }
  return value;
}

function sha256(value: unknown, label: string): string {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) {
    throw new Error(`${label} must be a sha256 digest`);
  }
  return value;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

function positiveInteger(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 1) {
    throw new Error(`${label} must be a positive integer`);
  }
  return value as number;
}

function slot(value: unknown, label: string): ScenarioSlot {
  if (value !== "left" && value !== "center" && value !== "right") {
    throw new Error(`${label} must be left, center, or right`);
  }
  return value;
}

function exact<ValueT>(value: unknown, expected: ValueT, label: string): void {
  if (value !== expected) {
    throw new Error(`${label} must be ${JSON.stringify(expected)}`);
  }
}

/**
 * The inverse of `parseScenarioProgram`: back to the persisted snake_case wire.
 *
 * Needed because the runtime shape is camelCase and every persisted contract in
 * this repository is snake_case, so anything that forwards a program into a
 * fixture file or a bundle projection has to convert rather than hand its
 * in-memory shape straight through. Round-tripping is what keeps the two from
 * quietly diverging.
 */
export function serializeScenarioProgram(program: ScenarioProgram): unknown {
  return {
    schema_version: 1,
    kind: SCENARIO_PROGRAM_KIND,
    game_id: program.gameId,
    scenario_id: program.scenarioId,
    display_name: program.displayName,
    revision: program.revision,
    script_sha256: program.scriptSha256,
    entry: program.entry,
    cast: program.cast.map((member) => ({
      actor_id: member.actorId,
      display_name: member.displayName,
      expressions: [...member.expressions],
    })),
    stages: program.stages.map((stage) => ({
      stage_id: stage.stageId,
      brief: stage.brief,
    })),
    tracks: program.tracks.map((track) => ({
      track_id: track.trackId,
      brief: track.brief,
      generation: {
        intent: track.generation.intent,
        instrumental: track.generation.instrumental,
        seamless_loop: track.generation.seamlessLoop,
        target_duration_seconds: track.generation.targetDurationSeconds,
      },
    })),
    flags: program.flags.map((flag) => ({ flag_id: flag })),
    endings: program.endings.map((ending) => ({
      outcome_id: ending.outcomeId,
      label: ending.label,
    })),
    blocks: program.blocks.map((block) => ({
      label: block.label,
      statements: block.statements.map(serializeStatement),
    })),
  };
}

function serializeStatement(statement: ScenarioStatement): unknown {
  switch (statement.kind) {
    case "choice":
      return {
        kind: "choice",
        options: statement.options.map((option) => ({
          text: option.text,
          target: option.target,
          condition: option.condition === null ? null : { ...option.condition },
        })),
      };
    case "branch":
      return {
        kind: "branch",
        edges: statement.edges.map((edge) => ({
          condition: { ...edge.condition },
          target: edge.target,
        })),
        default: statement.default,
      };
    default:
      return { ...statement };
  }
}
