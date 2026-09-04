// The case's save, as declared scopes over the `persistence` family.
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
//
// What changed at v2, and why the version moved: this file used to be its own
// persistence substrate — one hand-written record, one hand-written parser — and
// it wrote its fields FLAT. That shape cannot say a slice is absent, and "absent"
// is the whole of what a scope is for. `facts` outlives the leaf; the scenario's
// playback, the room's fired interactions and the backlog do not, and the record
// a finished case leaves behind is the game scope with the run scope subtracted.
// v2 is the same fields under `slices`, so the profile can write a subset and the
// reader can say which scopes came back. A v1 save is upgraded on the way in by
// the family's versioned parse rather than discarded, so a player mid-episode
// when this shipped keeps their place.
//
// `facts` is the only `"game"`-scope slice this runtime has. That is not a
// simplification: it is the case contract. A fact is the only thing a scenario
// and a room can both say, and nothing else crosses a beat boundary.
//
// `case_result_v1` below is deliberately NOT a profile. It is what a finished
// case leaves behind, and its lifetime is neither of the two scopes the runtime
// declares: it outlives the case itself, which is why it survives the save being
// cleared and is filed under its own key. Naming that third lifetime is exactly
// what an authored `[save]` table would do — scopes and the triggers that write
// them — and it is a contract change in `src/`. Until there is one, this record
// stays as it is rather than being forced into a scope vocabulary that does not
// yet have a word for it.

import { bagItemIds, bagOfOne } from "@/lib/families/inventory";
import type { ScenarioSlot } from "@/lib/scenario/program";
import { SCENARIO_SLOTS } from "@/lib/scenario/program";
import type { ScenarioState } from "@/lib/scenario/runtime";
import { scenarioStatementId } from "@/lib/scenario/runtime";
import type { RoomPlayState } from "@/lib/pointclick/state";
import {
  parseSave,
  SaveStore,
  serializeSave,
  type PersistenceEvent,
  type SaveProfile,
  type SaveScope,
  type SaveStorage,
} from "@/lib/families/persistence";

export type { SaveStorage };

/**
 * The record's name, which does not move with its version.
 *
 * A version bump that renamed the kind would refuse every save already written,
 * which is the opposite of what a versioned parse is for.
 */
export const CASE_SAVE_KIND = "case_save_v1";
/** v1: the fields written flat. v2: the same fields under declared scopes. */
export const CASE_SAVE_SCHEMA_VERSION = 2;
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
 * The case's own save profile: which slices there are, and how long each lives.
 *
 * `facts` is the only `"game"`-scope slice, because a fact is the only thing that
 * crosses a beat boundary. Everything else belongs to the leaf being played and
 * goes when it does.
 *
 * `run_tag`, `beat_id`, `statement_id` and `updated_at` are meta rather than
 * slices: they say which save this is and where it was taken, not what the
 * player's state is. `statement_id` is derivable from the scenario slice, and it
 * is written anyway so the Continue card can name the line without loading the
 * program the line belongs to.
 */
export const CASE_SAVE_PROFILE: SaveProfile<CaseSave> = {
  kind: CASE_SAVE_KIND,
  version: CASE_SAVE_SCHEMA_VERSION,
  slices: [
    {
      slice: "facts",
      scope: "game",
      serialize: (save) => [...save.facts],
      parse: (value) => Object.freeze(ids(value, "case save facts")),
    },
    {
      slice: "scenario",
      scope: "run",
      serialize: (save) => (save.scenario === null ? undefined : wireScenario(save.scenario)),
      parse: savedScenario,
    },
    {
      slice: "room",
      scope: "run",
      serialize: (save) => (save.room === null ? undefined : wireRoom(save.room)),
      parse: savedRoom,
    },
    {
      slice: "backlog",
      scope: "run",
      serialize: (save) =>
        save.backlog.map((line) => ({ speaker: line.speaker, text: line.text })),
      parse: savedBacklog,
    },
  ],
  serializeMeta: (save) => ({
    run_tag: save.runTag,
    beat_id: save.beatId,
    statement_id: save.statementId,
    updated_at: save.updatedAt,
  }),
  parseMeta: (root) => ({
    runTag: text(root.run_tag, "case save run_tag", 128),
    beatId: text(root.beat_id, "case save beat_id", 128),
    statementId:
      root.statement_id === null || root.statement_id === undefined
        ? null
        : text(root.statement_id, "case save statement_id", 200),
    updatedAt: text(root.updated_at, "case save updated_at", 64),
  }),
  upgrades: [
    {
      // v1 wrote the slices flat beside the meta. Nothing about a v1 save is
      // wrong — the fields are the same fields — so the upgrade is the envelope
      // and nothing else, and a player mid-episode keeps their place.
      from: 1,
      upgrade: (record) => ({
        schema_version: 2,
        kind: record.kind,
        run_tag: record.run_tag,
        beat_id: record.beat_id,
        statement_id: record.statement_id ?? null,
        updated_at: record.updated_at,
        slices: {
          facts: record.facts,
          ...(record.scenario === null || record.scenario === undefined
            ? {}
            : { scenario: record.scenario }),
          ...(record.room === null || record.room === undefined ? {} : { room: record.room }),
          backlog: record.backlog,
        },
      }),
    },
  ],
};

/**
 * Read the save for one case, or null when there is nothing usable there.
 *
 * Never throws. The bytes come from a browser the player owns and a build that
 * may have moved on since they were written; a save that no longer parses means
 * "no save", which is exactly what the shell should offer them. A save written by
 * an EARLIER build is a different matter, and is upgraded rather than discarded.
 */
export function readCaseSave(
  storage: SaveStorage,
  tag: string,
  emit?: (event: PersistenceEvent) => void,
): CaseSave | null {
  const record = new SaveStore(storage, CASE_SAVE_PROFILE, emit).read(caseSaveKey(tag));
  if (record === null) return null;
  try {
    return assembleCaseSave(record.meta, record.slices);
  } catch {
    return null;
  }
}

/**
 * Write one save, in the scopes asked for.
 *
 * The default is everything. A caller that wants only what survives the leaf
 * says `["game"]`, and gets a record carrying the facts and no playback.
 */
export function writeCaseSave(
  storage: SaveStorage,
  save: CaseSave,
  scopes?: readonly SaveScope[],
  emit?: (event: PersistenceEvent) => void,
): void {
  new SaveStore(storage, CASE_SAVE_PROFILE, emit).write(caseSaveKey(save.runTag), save, scopes);
}

export function clearCaseSave(storage: SaveStorage, tag: string): void {
  new SaveStore(storage, CASE_SAVE_PROFILE).clear(caseSaveKey(tag));
}

export function serializeCaseSave(
  save: CaseSave,
  scopes?: readonly SaveScope[],
): Record<string, unknown> {
  return serializeSave(CASE_SAVE_PROFILE, save, scopes);
}

/**
 * Validate one persisted save, upgrading it from whatever version wrote it.
 *
 * Strict about shape, and deliberately not strict about meaning: whether the
 * label still exists, or the flags are still declared, is a question about a
 * program this module has never seen. `restoreScenarioState` answers that with
 * the program in hand and refuses a snapshot that no longer fits.
 */
export function parseCaseSave(value: unknown): CaseSave {
  const record = parseSave(CASE_SAVE_PROFILE, value);
  return assembleCaseSave(record.meta, record.slices);
}

/** The parsed slices and meta, as the one record the shell passes around. */
function assembleCaseSave(
  meta: Readonly<Record<string, unknown>>,
  slices: Readonly<Record<string, unknown>>,
): CaseSave {
  return Object.freeze({
    runTag: meta.runTag as string,
    beatId: meta.beatId as string,
    facts: (slices.facts ?? Object.freeze([])) as readonly string[],
    statementId: (meta.statementId ?? null) as string | null,
    scenario: (slices.scenario ?? null) as ScenarioState | null,
    room: (slices.room ?? null) as RoomPlayState | null,
    backlog: (slices.backlog ?? Object.freeze([])) as readonly BacklogLine[],
    updatedAt: meta.updatedAt as string,
  });
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

/** One scenario slice, as the wire carries it. */
function wireScenario(state: ScenarioState): unknown {
  return {
    label: state.label,
    index: state.index,
    flags: [...state.flags],
    seen: [...state.seen],
    stage: state.stage,
    actors: state.actors.map((actor) => ({
      actor_id: actor.actorId,
      expression: actor.expression,
      slot: actor.slot,
    })),
    tracks: [...state.tracks],
    outcome: state.outcome,
  };
}

/**
 * One room slice, as the wire carries it.
 *
 * The saved form stays a list of item ids: the room's bag is the `inventory`
 * family's counted bag with every quantity 1, so the names are the whole of it.
 */
function wireRoom(state: RoomPlayState): unknown {
  return {
    flags: [...state.flags],
    inventory: bagItemIds(state.inventory),
    revealed: [...state.revealed],
    fired: [...state.fired],
    narration: state.narration,
    solved: state.solved,
  };
}

/** The last fifty lines, trimmed on the way back in as well as on the way out. */
function savedBacklog(value: unknown): readonly BacklogLine[] {
  return Object.freeze(
    list(value, "case save backlog")
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
  );
}

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
    inventory: bagOfOne(ids(raw.inventory, "case save room.inventory")),
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
