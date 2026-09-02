// The pilot's whole persistence substrate: one autosave per case, in the browser.
//
// This is the shell, not Scenario. The scenario contract's only obligation was to
// make a save possible, and it met it: statement identity is `<label>#<index>`,
// an authored position that does not depend on the route the player took, so a
// save keyed on it survives a reload and, unlike a raw statement counter, still
// means something after the player branched.
//
// What is deliberately not here, and is debt rather than design: save slots,
// skip-already-read, auto-advance, and preferences. One autosave per case, a
// Continue, and a backlog of the last fifty lines is the whole pilot minimum.
//
// One thing the brief's "statement id and the flag set" cannot do on its own, and
// the reason this record is larger than that: a statement id says which line to
// show, and the flags say what the reducer will do next, but neither says what
// the backdrop is or who is standing where. Those are settled by having walked
// the invisible statements before the line, and a save that dropped them would
// resume the right sentence in an empty room. So the record carries the runtime's
// own presented state, with the statement id as its identity.

import type { ScenarioSlot } from "@/lib/scenario/program";
import { SCENARIO_SLOTS } from "@/lib/scenario/program";
import type { ScenarioState } from "@/lib/scenario/runtime";
import { scenarioStatementId } from "@/lib/scenario/runtime";
import type { RoomPlayState } from "@/lib/pointclick/state";

export const CASE_SAVE_KIND = "case_save_v1";
export const CASE_SAVE_SCHEMA_VERSION = 1;
export const CASE_RESULT_KIND = "case_result_v1";
export const BACKLOG_LIMIT = 50;

const SAVE_KEY_PREFIX = "stage_gen.case_save.";
const RESULT_KEY_PREFIX = "stage_gen.case_result.";
const TEXT_MAX = 600;

/** One line the player has already been shown, as the backlog remembers it. */
export interface BacklogLine {
  readonly speaker: string | null;
  readonly text: string;
}

export interface CaseSave {
  readonly runTag: string;
  readonly beatId: string;
  /** The case's shared facts as of the last completed beat. */
  readonly facts: readonly string[];
  /** `<label>#<index>` of the line in progress, or null in a room. */
  readonly statementId: string | null;
  readonly scenario: ScenarioState | null;
  readonly room: RoomPlayState | null;
  readonly backlog: readonly BacklogLine[];
  readonly updatedAt: string;
}

/**
 * What a finished case leaves behind.
 *
 * The in-progress save is cleared at the ending, correctly — there is nothing
 * left to resume. But the facts a player finished holding ARE the episode's
 * output: an episodic story opens the next case on the board the last one
 * produced, and a player who reached an ending should be able to see what they
 * carried. Clearing the save without writing this discarded the verdict at the
 * exact moment it was computed.
 *
 * Kept under its own key so it survives replays of the same case being started
 * again, and so nothing that reads a save can mistake a finished run for a
 * resumable one.
 */
export interface CaseResult {
  readonly runTag: string;
  /** The `end <outcome>` the case terminated through. */
  readonly outcome: string;
  /** Every fact the player finished holding, sorted. */
  readonly facts: readonly string[];
  readonly finishedAt: string;
}

/** Only what this module needs of `localStorage`, so a test needs no browser. */
export interface SaveStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function caseSaveKey(tag: string): string {
  return `${SAVE_KEY_PREFIX}${tag}`;
}

/** The last fifty lines, oldest first, with the newest appended. */
export function appendBacklog(
  backlog: readonly BacklogLine[],
  line: BacklogLine,
): readonly BacklogLine[] {
  const next = [...backlog, Object.freeze({ speaker: line.speaker, text: line.text })];
  return Object.freeze(next.slice(Math.max(0, next.length - BACKLOG_LIMIT)));
}

/**
 * Read the save for one case, or null when there is nothing usable there.
 *
 * Never throws. The bytes come from a browser the player owns and a build that
 * may have moved on since they were written; a save that no longer parses means
 * "no save", which is exactly what the shell should offer them.
 */
export function readCaseSave(storage: SaveStorage, tag: string): CaseSave | null {
  let raw: string | null;
  try {
    raw = storage.getItem(caseSaveKey(tag));
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    return parseCaseSave(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function writeCaseSave(storage: SaveStorage, save: CaseSave): void {
  try {
    storage.setItem(caseSaveKey(save.runTag), JSON.stringify(serializeCaseSave(save)));
  } catch {
    // A full or blocked store loses the save, not the session. A player who
    // cannot autosave should still be able to finish the case they are playing.
  }
}

export function caseResultKey(tag: string): string {
  return `${RESULT_KEY_PREFIX}${tag}`;
}

/** Record what a finished case produced. Never throws, for the same reason. */
export function writeCaseResult(storage: SaveStorage, result: CaseResult): void {
  try {
    storage.setItem(
      caseResultKey(result.runTag),
      JSON.stringify({
        schema_version: CASE_SAVE_SCHEMA_VERSION,
        kind: CASE_RESULT_KIND,
        run_tag: result.runTag,
        outcome: result.outcome,
        facts: [...result.facts].sort(),
        finished_at: result.finishedAt,
      }),
    );
  } catch {
    // A full or blocked store loses the record, not the ending the player reached.
  }
}

/** Read what a finished case produced, or null when it has not been finished. */
export function readCaseResult(storage: SaveStorage, tag: string): CaseResult | null {
  let raw: string | null;
  try {
    raw = storage.getItem(caseResultKey(tag));
  } catch {
    return null;
  }
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const record = value as Record<string, unknown>;
    if (record.kind !== CASE_RESULT_KIND) return null;
    const facts = record.facts;
    if (typeof record.run_tag !== "string") return null;
    if (typeof record.outcome !== "string") return null;
    if (typeof record.finished_at !== "string") return null;
    if (!Array.isArray(facts) || facts.some((f) => typeof f !== "string")) return null;
    return Object.freeze({
      runTag: record.run_tag,
      outcome: record.outcome,
      facts: Object.freeze([...(facts as string[])]),
      finishedAt: record.finished_at,
    });
  } catch {
    return null;
  }
}

export function clearCaseSave(storage: SaveStorage, tag: string): void {
  try {
    storage.removeItem(caseSaveKey(tag));
  } catch {
    // As above: forgetting a save is not worth ending a play-through over.
  }
}

export function serializeCaseSave(save: CaseSave): unknown {
  return {
    schema_version: CASE_SAVE_SCHEMA_VERSION,
    kind: CASE_SAVE_KIND,
    run_tag: save.runTag,
    beat_id: save.beatId,
    facts: [...save.facts],
    statement_id: save.statementId,
    scenario:
      save.scenario === null
        ? null
        : {
            label: save.scenario.label,
            index: save.scenario.index,
            flags: [...save.scenario.flags],
            seen: [...save.scenario.seen],
            stage: save.scenario.stage,
            actors: save.scenario.actors.map((actor) => ({
              actor_id: actor.actorId,
              expression: actor.expression,
              slot: actor.slot,
            })),
            tracks: [...save.scenario.tracks],
            outcome: save.scenario.outcome,
          },
    room:
      save.room === null
        ? null
        : {
            flags: [...save.room.flags],
            inventory: [...save.room.inventory],
            revealed: [...save.room.revealed],
            fired: [...save.room.fired],
            narration: save.room.narration,
            solved: save.room.solved,
          },
    backlog: save.backlog.map((line) => ({ speaker: line.speaker, text: line.text })),
    updated_at: save.updatedAt,
  };
}

/**
 * Validate one persisted save.
 *
 * Strict about shape, and deliberately not strict about meaning: whether the
 * label still exists, or the flags are still declared, is a question about a
 * program this module has never seen. `restoreScenarioState` answers that with
 * the program in hand and refuses a snapshot that no longer fits.
 */
export function parseCaseSave(value: unknown): CaseSave {
  const root = record(value, "case save");
  exact(root.schema_version, CASE_SAVE_SCHEMA_VERSION, "case save schema_version");
  exact(root.kind, CASE_SAVE_KIND, "case save kind");
  const scenarioRaw = root.scenario;
  const roomRaw = root.room;
  return Object.freeze({
    runTag: text(root.run_tag, "case save run_tag", 128),
    beatId: text(root.beat_id, "case save beat_id", 128),
    facts: Object.freeze(ids(root.facts, "case save facts")),
    statementId:
      root.statement_id === null || root.statement_id === undefined
        ? null
        : text(root.statement_id, "case save statement_id", 200),
    scenario:
      scenarioRaw === null || scenarioRaw === undefined ? null : savedScenario(scenarioRaw),
    room: roomRaw === null || roomRaw === undefined ? null : savedRoom(roomRaw),
    backlog: Object.freeze(
      list(root.backlog, "case save backlog")
        .slice(-BACKLOG_LIMIT)
        .map((entry, index) => {
          const line = record(entry, `case save backlog[${index}]`);
          return Object.freeze({
            speaker:
              line.speaker === null || line.speaker === undefined
                ? null
                : text(line.speaker, `case save backlog[${index}].speaker`, 96),
            text: text(line.text, `case save backlog[${index}].text`, TEXT_MAX),
          });
        }),
    ),
    updatedAt: text(root.updated_at, "case save updated_at", 64),
  });
}

/**
 * The record written the moment a beat is entered, before it has drawn anything.
 *
 * Without it, a player who reloads in the first second of a beat would resume at
 * the previous one and replay a scene they finished.
 */
export function beatSave(
  runTag: string,
  beatId: string,
  facts: readonly string[],
  backlog: readonly BacklogLine[],
  now: Date = new Date(),
): CaseSave {
  return Object.freeze({
    runTag,
    beatId,
    facts: Object.freeze([...facts]),
    statementId: null,
    scenario: null,
    room: null,
    backlog: Object.freeze([...backlog]),
    updatedAt: now.toISOString(),
  });
}

/** The record a scenario beat writes at every statement it presents. */
export function scenarioSave(
  runTag: string,
  beatId: string,
  facts: readonly string[],
  state: ScenarioState,
  backlog: readonly BacklogLine[],
  now: Date = new Date(),
): CaseSave {
  return Object.freeze({
    runTag,
    beatId,
    facts: Object.freeze([...facts]),
    statementId: scenarioStatementId(state.label, state.index),
    scenario: state,
    room: null,
    backlog: Object.freeze([...backlog]),
    updatedAt: now.toISOString(),
  });
}

/** The record a room beat writes at every click. */
export function roomSave(
  runTag: string,
  beatId: string,
  facts: readonly string[],
  state: RoomPlayState,
  backlog: readonly BacklogLine[],
  now: Date = new Date(),
): CaseSave {
  return Object.freeze({
    runTag,
    beatId,
    facts: Object.freeze([...facts]),
    statementId: null,
    scenario: null,
    room: state,
    backlog: Object.freeze([...backlog]),
    updatedAt: now.toISOString(),
  });
}

// ------------------------------------------------------------------ scalars

function savedScenario(value: unknown): ScenarioState {
  const raw = record(value, "case save scenario");
  return Object.freeze({
    label: text(raw.label, "case save scenario.label", 128),
    index: integer(raw.index, "case save scenario.index"),
    flags: Object.freeze(ids(raw.flags, "case save scenario.flags")),
    seen: Object.freeze(
      list(raw.seen, "case save scenario.seen").map((entry, index) =>
        text(entry, `case save scenario.seen[${index}]`, 200),
      ),
    ),
    stage:
      raw.stage === null || raw.stage === undefined
        ? null
        : text(raw.stage, "case save scenario.stage", 128),
    actors: Object.freeze(
      list(raw.actors, "case save scenario.actors").map((entry, index) => {
        const actor = record(entry, `case save scenario.actors[${index}]`);
        return Object.freeze({
          actorId: text(actor.actor_id, `case save scenario.actors[${index}].actor_id`, 128),
          expression:
            actor.expression === null || actor.expression === undefined
              ? null
              : text(actor.expression, `case save scenario.actors[${index}].expression`, 128),
          slot: slot(actor.slot, `case save scenario.actors[${index}].slot`),
        });
      }),
    ),
    tracks: Object.freeze(ids(raw.tracks, "case save scenario.tracks")),
    outcome:
      raw.outcome === null || raw.outcome === undefined
        ? null
        : text(raw.outcome, "case save scenario.outcome", 128),
  });
}

function savedRoom(value: unknown): RoomPlayState {
  const raw = record(value, "case save room");
  return Object.freeze({
    flags: Object.freeze(ids(raw.flags, "case save room.flags")),
    inventory: Object.freeze(ids(raw.inventory, "case save room.inventory")),
    revealed: Object.freeze(ids(raw.revealed, "case save room.revealed")),
    fired: Object.freeze(
      list(raw.fired, "case save room.fired").map((entry, index) =>
        integer(entry, `case save room.fired[${index}]`),
      ),
    ),
    // A held item is a gesture in progress, not a place in the room. Resuming
    // with something invisibly "in hand" would make the next click a mystery.
    selectedItem: null,
    narration: text(raw.narration, "case save room.narration", TEXT_MAX),
    solved: boolean(raw.solved, "case save room.solved"),
  });
}

function slot(value: unknown, label: string): ScenarioSlot {
  if (typeof value !== "string" || !(SCENARIO_SLOTS as readonly string[]).includes(value)) {
    throw new Error(`${label} must be one of ${SCENARIO_SLOTS.join(", ")}`);
  }
  return value as ScenarioSlot;
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function list(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function ids(value: unknown, label: string): string[] {
  return list(value, label).map((entry, index) => text(entry, `${label}[${index}]`, 128));
}

function text(value: unknown, label: string, maxLength: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maxLength) {
    throw new Error(`${label} must be a non-empty string of at most ${maxLength} characters`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value)) throw new Error(`${label} must be an integer`);
  return value as number;
}

function boolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

function exact<ValueT>(value: unknown, expected: ValueT, label: string): void {
  if (value !== expected) throw new Error(`${label} must be ${JSON.stringify(expected)}`);
}
