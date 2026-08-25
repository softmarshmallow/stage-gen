/** The one persisted recipe-run summary accepted by the web consumer. */

export const RECIPE_RUN_SCHEMA_VERSION = 3 as const;
export const RECIPE_RUN_KIND = "recipe_run_v3" as const;

export type RunTransparencyMode = "ai" | "chroma";

export interface JsonObject {
  readonly [key: string]: JsonValue;
}

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | readonly JsonValue[]
  | JsonObject;

export type SuccessfulRecipeRunStage = Readonly<{
  stage: string;
  ok: true;
  duration_ms: number;
  artifacts: readonly string[];
}>;

export type FailedRecipeRunStage = Readonly<{
  stage: string;
  ok: false;
  duration_ms: number;
  artifacts: readonly string[];
  error: string;
}>;

export type RecipeRunStage = SuccessfulRecipeRunStage | FailedRecipeRunStage;

type RecipeRunSummaryFields = Readonly<{
  schema_version: typeof RECIPE_RUN_SCHEMA_VERSION;
  kind: typeof RECIPE_RUN_KIND;
  recipe: string;
  input: Readonly<Record<string, JsonValue>> & {
    readonly transparency_mode: RunTransparencyMode;
  };
  tag: string;
  run_dir: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}>;

export type SuccessfulRecipeRunSummary = RecipeRunSummaryFields &
  Readonly<{
    ok: true;
    stages: readonly SuccessfulRecipeRunStage[];
  }>;

export type FailedRecipeRunSummary = RecipeRunSummaryFields &
  Readonly<{
    ok: false;
    stages: readonly RecipeRunStage[];
    failed_stage: string;
  }>;

export type RecipeRunSummary = SuccessfulRecipeRunSummary | FailedRecipeRunSummary;

export type RunCompletionPayload = Readonly<{
  ok: boolean;
  failed_stage: string | null;
}>;

const SUCCESS_RUN_KEYS = [
  "schema_version",
  "kind",
  "recipe",
  "input",
  "tag",
  "run_dir",
  "started_at",
  "ended_at",
  "duration_ms",
  "ok",
  "stages",
] as const;
const FAILED_RUN_KEYS = [...SUCCESS_RUN_KEYS, "failed_stage"] as const;
const SUCCESS_STAGE_KEYS = ["stage", "ok", "duration_ms", "artifacts"] as const;
const FAILED_STAGE_KEYS = [...SUCCESS_STAGE_KEYS, "error"] as const;
const STABLE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const LOWER_SNAKE_FIELD = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const SAFE_TAG = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ARTIFACT_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?Z$/;

function fail(path: string, message: string): never {
  throw new Error(`${path} ${message}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) return fail(path, "must be an object");
  return value;
}

function exactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  path: string,
): void {
  const keys = new Set(expected);
  for (const key of Object.keys(value)) {
    if (!keys.has(key)) fail(`${path}.${key}`, "is not a supported key");
  }
  for (const key of expected) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      fail(`${path}.${key}`, "is required");
    }
  }
}

function literal<const Value extends string | number>(
  value: unknown,
  expected: Value,
  path: string,
): Value {
  if (value !== expected) return fail(path, `must equal ${JSON.stringify(expected)}`);
  return expected;
}

function bool(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") return fail(path, "must be a boolean");
  return value;
}

function stableText(value: unknown, path: string): string {
  if (
    typeof value !== "string" ||
    !value ||
    value !== value.trim() ||
    value.includes("\0")
  ) {
    return fail(path, "must be a non-empty trimmed string");
  }
  return value;
}

function stableId(value: unknown, path: string): string {
  const parsed = stableText(value, path);
  if (!STABLE_ID.test(parsed)) {
    return fail(path, "must be a lower-case hyphenated identifier");
  }
  return parsed;
}

function safeTag(value: unknown, path: string): string {
  const parsed = stableText(value, path);
  if (!SAFE_TAG.test(parsed) || parsed === "." || parsed === "..") {
    return fail(path, "must be one safe path segment");
  }
  return parsed;
}

function nonNegativeInteger(value: unknown, path: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) {
    return fail(path, "must be a non-negative safe integer");
  }
  return value as number;
}

type ParsedTimestamp = Readonly<{
  value: string;
  parts: readonly [number, number, number, number, number, number, string];
}>;

function timestamp(value: unknown, path: string): ParsedTimestamp {
  const parsed = stableText(value, path);
  const match = UTC_TIMESTAMP.exec(parsed);
  if (!match) {
    return fail(path, "must be a valid UTC timestamp ending in Z");
  }
  const parts = [
    Number(parsed.slice(0, 4)),
    Number(parsed.slice(5, 7)),
    Number(parsed.slice(8, 10)),
    Number(parsed.slice(11, 13)),
    Number(parsed.slice(14, 16)),
    Number(parsed.slice(17, 19)),
    match[1] ?? "",
  ] as const;
  const [year, month, day, hour, minute, second] = parts;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthLengths = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > monthLengths[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    return fail(path, "must be a valid UTC timestamp ending in Z");
  }
  return { value: parsed, parts };
}

function timestampPrecedes(left: ParsedTimestamp, right: ParsedTimestamp): boolean {
  for (let index = 0; index < 6; index += 1) {
    const leftPart = left.parts[index] as number;
    const rightPart = right.parts[index] as number;
    if (leftPart !== rightPart) return leftPart < rightPart;
  }
  const leftFraction = left.parts[6];
  const rightFraction = right.parts[6];
  const width = Math.max(leftFraction.length, rightFraction.length);
  return leftFraction.padEnd(width, "0") < rightFraction.padEnd(width, "0");
}

function jsonValue(value: unknown, path: string): JsonValue {
  if (value === null || typeof value === "boolean" || typeof value === "string") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return fail(path, "must be finite JSON data");
    if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
      return fail(path, "must keep integers within the JSON safe-integer range");
    }
    return value;
  }
  if (Array.isArray(value)) {
    return Object.freeze(
      Array.from(value, (entry, index) => jsonValue(entry, `${path}[${index}]`)),
    );
  }
  if (!isRecord(value)) return fail(path, "must be JSON data");
  return Object.freeze(
    Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [
        key,
        jsonValue(entry, `${path}.${key}`),
      ]),
    ),
  );
}

function runInput(value: unknown): RecipeRunSummary["input"] {
  const root = record(value, "run_summary.input");
  if (Object.prototype.hasOwnProperty.call(root, "transparencyMode")) {
    fail(
      "run_summary.input.transparencyMode",
      "is not supported; use transparency_mode",
    );
  }
  for (const key of Object.keys(root)) {
    if (!LOWER_SNAKE_FIELD.test(key)) {
      fail(`run_summary.input.${key}`, "must use lower_snake_case");
    }
  }
  const mode = root["transparency_mode"];
  if (mode !== "ai" && mode !== "chroma") {
    fail("run_summary.input.transparency_mode", "must be ai or chroma");
  }
  return jsonValue(root, "run_summary.input") as RecipeRunSummary["input"];
}

function portableArtifactPath(value: unknown, path: string): string {
  const parsed = stableText(value, path);
  const segments = parsed.split("/");
  if (
    parsed.includes("\0") ||
    parsed.startsWith("/") ||
    segments.some((segment) => !ARTIFACT_SEGMENT.test(segment))
  ) {
    return fail(path, "must be a portable relative POSIX path");
  }
  return parsed;
}

function artifacts(value: unknown, path: string): readonly string[] {
  if (!Array.isArray(value)) return fail(path, "must be an array");
  const parsed = Object.freeze(
    Array.from(value, (entry, index) => portableArtifactPath(entry, `${path}[${index}]`)),
  );
  if (new Set(parsed).size !== parsed.length) {
    fail(path, "must not contain duplicate paths");
  }
  return parsed;
}

function runStage(value: unknown, index: number): RecipeRunStage {
  const path = `run_summary.stages[${index}]`;
  const root = record(value, path);
  const ok = bool(root["ok"], `${path}.ok`);
  exactKeys(root, ok ? SUCCESS_STAGE_KEYS : FAILED_STAGE_KEYS, path);
  const stage = stableId(root["stage"], `${path}.stage`);
  const durationMs = nonNegativeInteger(root["duration_ms"], `${path}.duration_ms`);
  const stageArtifacts = artifacts(root["artifacts"], `${path}.artifacts`);
  if (ok) {
    return Object.freeze({ stage, ok: true, duration_ms: durationMs, artifacts: stageArtifacts });
  }
  if (stageArtifacts.length !== 0) {
    fail(`${path}.artifacts`, "must be empty for a failed stage");
  }
  const error = stableText(root["error"], `${path}.error`);
  return Object.freeze({
    stage,
    ok: false,
    duration_ms: durationMs,
    artifacts: Object.freeze([]),
    error,
  });
}

/** Parse and validate the exact current persisted run-summary contract. */
export function parseRecipeRunSummary(value: unknown): RecipeRunSummary {
  const root = record(value, "run_summary");
  const ok = bool(root["ok"], "run_summary.ok");
  exactKeys(root, ok ? SUCCESS_RUN_KEYS : FAILED_RUN_KEYS, "run_summary");
  const schemaVersion = literal(
    root["schema_version"],
    RECIPE_RUN_SCHEMA_VERSION,
    "run_summary.schema_version",
  );
  const kind = literal(root["kind"], RECIPE_RUN_KIND, "run_summary.kind");
  const recipe = stableId(root["recipe"], "run_summary.recipe");
  const input = runInput(root["input"]);
  const tag = safeTag(root["tag"], "run_summary.tag");
  const runDir = safeTag(root["run_dir"], "run_summary.run_dir");
  if (runDir !== tag) {
    fail("run_summary.run_dir", "must equal run_summary.tag");
  }
  const startedAt = timestamp(root["started_at"], "run_summary.started_at");
  const endedAt = timestamp(root["ended_at"], "run_summary.ended_at");
  if (timestampPrecedes(endedAt, startedAt)) {
    fail("run_summary.ended_at", "must not precede started_at");
  }
  const durationMs = nonNegativeInteger(root["duration_ms"], "run_summary.duration_ms");
  if (!Array.isArray(root["stages"])) {
    fail("run_summary.stages", "must be an array");
  }
  if (root["stages"].length === 0) {
    fail("run_summary.stages", "must contain at least one executed stage");
  }
  const stages = Object.freeze(
    Array.from(root["stages"], (stage, index) => runStage(stage, index)),
  );
  const stageIds = stages.map((stage) => stage.stage);
  if (new Set(stageIds).size !== stageIds.length) {
    fail("run_summary.stages", "must contain unique stage identifiers");
  }
  const failed = stages.filter((stage): stage is FailedRecipeRunStage => !stage.ok);

  const common = {
    schema_version: schemaVersion,
    kind,
    recipe,
    input,
    tag,
    run_dir: runDir,
    started_at: startedAt.value,
    ended_at: endedAt.value,
    duration_ms: durationMs,
  } as const;

  if (ok) {
    if (failed.length !== 0) {
      fail("run_summary.stages", "must all succeed when run_summary.ok is true");
    }
    return Object.freeze({
      ...common,
      ok: true,
      stages: stages as readonly SuccessfulRecipeRunStage[],
    });
  }

  if (failed.length !== 1 || stages.at(-1) !== failed[0]) {
    fail("run_summary.stages", "must end with exactly one failed stage when run_summary.ok is false");
  }
  const failedStage = stableId(root["failed_stage"], "run_summary.failed_stage");
  if (failedStage !== failed[0].stage) {
    fail("run_summary.failed_stage", "must match the final failed stage");
  }
  return Object.freeze({
    ...common,
    ok: false,
    stages,
    failed_stage: failedStage,
  });
}

class DuplicateJsonKeyError extends Error {}

/** JSON.parse discards duplicate object keys, so scan the valid source before accepting it. */
function rejectDuplicateJsonKeys(source: string): void {
  let cursor = 0;

  const skipWhitespace = () => {
    while (
      source[cursor] === " " ||
      source[cursor] === "\t" ||
      source[cursor] === "\n" ||
      source[cursor] === "\r"
    ) {
      cursor += 1;
    }
  };

  const readString = (): string => {
    const start = cursor;
    cursor += 1;
    while (cursor < source.length) {
      const character = source[cursor];
      if (character === '"') {
        cursor += 1;
        return JSON.parse(source.slice(start, cursor)) as string;
      }
      if (character === "\\") {
        cursor += 1;
        cursor += source[cursor] === "u" ? 5 : 1;
      } else {
        cursor += 1;
      }
    }
    throw new SyntaxError("unterminated JSON string");
  };

  const readValue = (): void => {
    skipWhitespace();
    const character = source[cursor];
    if (character === "{") {
      readObject();
      return;
    }
    if (character === "[") {
      readArray();
      return;
    }
    if (character === '"') {
      readString();
      return;
    }
    for (const literalValue of ["true", "false", "null"] as const) {
      if (source.startsWith(literalValue, cursor)) {
        cursor += literalValue.length;
        return;
      }
    }
    const number = source.slice(cursor).match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    if (!number) throw new SyntaxError("invalid JSON value");
    cursor += number[0].length;
  };

  const readObject = (): void => {
    cursor += 1;
    skipWhitespace();
    const keys = new Set<string>();
    if (source[cursor] === "}") {
      cursor += 1;
      return;
    }
    while (cursor < source.length) {
      skipWhitespace();
      if (source[cursor] !== '"') throw new SyntaxError("invalid JSON object key");
      const key = readString();
      if (keys.has(key)) throw new DuplicateJsonKeyError(`duplicate JSON key: ${key}`);
      keys.add(key);
      skipWhitespace();
      if (source[cursor] !== ":") throw new SyntaxError("invalid JSON object entry");
      cursor += 1;
      readValue();
      skipWhitespace();
      if (source[cursor] === "}") {
        cursor += 1;
        return;
      }
      if (source[cursor] !== ",") throw new SyntaxError("invalid JSON object separator");
      cursor += 1;
    }
    throw new SyntaxError("unterminated JSON object");
  };

  const readArray = (): void => {
    cursor += 1;
    skipWhitespace();
    if (source[cursor] === "]") {
      cursor += 1;
      return;
    }
    while (cursor < source.length) {
      readValue();
      skipWhitespace();
      if (source[cursor] === "]") {
        cursor += 1;
        return;
      }
      if (source[cursor] !== ",") throw new SyntaxError("invalid JSON array separator");
      cursor += 1;
    }
    throw new SyntaxError("unterminated JSON array");
  };

  readValue();
  skipWhitespace();
  if (cursor !== source.length) throw new SyntaxError("trailing JSON data");
}

export function parseRecipeRunSummaryText(source: string): RecipeRunSummary {
  let value: unknown;
  try {
    value = JSON.parse(source);
    rejectDuplicateJsonKeys(source);
  } catch (error) {
    if (error instanceof DuplicateJsonKeyError) {
      throw new Error(`run summary is not valid JSON: ${error.message}`);
    }
    throw new Error("run summary must be valid JSON");
  }
  return parseRecipeRunSummary(value);
}

export function parseRecipeRunSummaryBytes(source: Uint8Array): RecipeRunSummary {
  if (source[0] === 0xef && source[1] === 0xbb && source[2] === 0xbf) {
    throw new Error("run summary must be BOM-free UTF-8 JSON");
  }
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(source);
  } catch {
    throw new Error("run summary must be valid UTF-8 JSON");
  }
  return parseRecipeRunSummaryText(text);
}

/** Explicit lower_snake_case projection used by the public pipeline-done SSE event. */
export function runCompletionPayload(summary: RecipeRunSummary): RunCompletionPayload {
  return Object.freeze({
    ok: summary.ok,
    failed_stage: summary.ok ? null : summary.failed_stage,
  });
}
