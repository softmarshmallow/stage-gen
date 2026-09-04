// The scenario runtime: a pure reducer over `{block, index, flags, seen}`.
//
// It owns no drawing, no asset paths, no engine types, and no genre vocabulary.
// Both genres consume it: the visual novel stages a cast against backdrops, and
// the platformer plays the same programs in a portrait panel over its map.
//
// The one rule that has to match the producer exactly: **a branch takes the first
// satisfied edge.** The Python admission proof searched that machine, so a
// runtime that took a different edge would be playing a scenario nobody proved.
// The same goes for statement identity: `seen` is keyed on `<label>#<index>`,
// which is stable across a save because it names authored positions rather than
// how the player got there.

import { SCENARIO_SLOTS } from "./program";
import type {
  ScenarioBlock,
  ScenarioChoiceOption,
  ScenarioCondition,
  ScenarioProgram,
  ScenarioSlot,
  ScenarioStatement,
} from "./program";

export interface ScenarioActor {
  readonly actorId: string;
  readonly expression: string | null;
  readonly slot: ScenarioSlot;
}

/** Everything a consumer needs to draw one moment, and nothing about how. */
export interface ScenarioState {
  readonly label: string;
  /** Index of the presented statement inside its block, or -1 before the first. */
  readonly index: number;
  readonly flags: readonly string[];
  readonly seen: readonly string[];
  readonly stage: string | null;
  readonly actors: readonly ScenarioActor[];
  readonly tracks: readonly string[];
  /** The outcome this run ended through, or null while it is still running. */
  readonly outcome: string | null;
}

export interface ScenarioLineView {
  readonly kind: "line";
  readonly speaker: string | null;
  readonly speakerLabel: string | null;
  readonly text: string;
}

export interface ScenarioChoiceView {
  readonly kind: "choice";
  /** Only the options whose conditions hold; an empty list is impossible by proof. */
  readonly options: readonly ScenarioChoiceOption[];
}

export interface ScenarioEndView {
  readonly kind: "end";
  readonly outcome: string;
  readonly label: string;
}

export type ScenarioView = ScenarioLineView | ScenarioChoiceView | ScenarioEndView;

// ------------------------------------------------------------------- events
//
// The reducer has always known exactly what happened at every step and thrown it
// away: `settle` walks the invisible statements — a stage change, a cast entry, a
// flag, a branch — and answers with a state that says where it ended and nothing
// about how. A consumer that needed an edge had to diff two states and guess,
// which is the failure `kernel/events.ts` was written to end, and it is why this
// reducer had no replay golden: there was nothing per step to hash but a
// position.
//
// Now every transition names itself. The events are the scenario's own — no
// genre vocabulary, no drawing — and they are the second half of what E1 hashes.

import type { GameEvent } from "@/lib/kernel/events";

export interface ScenarioPresented extends GameEvent {
  readonly type: "scenario/presented";
  readonly statementId: string;
  readonly kind: "line" | "choice";
}

export interface ScenarioBranched extends GameEvent {
  readonly type: "scenario/branched";
  readonly from: string;
  readonly to: string;
  /** `jump` is unconditional; `branch` took the first satisfied edge. */
  readonly cause: "jump" | "branch" | "choice";
}

export interface ScenarioFlagChanged extends GameEvent {
  readonly type: "scenario/flag-changed";
  readonly flag: string;
  readonly value: boolean;
}

export interface ScenarioStaged extends GameEvent {
  readonly type: "scenario/staged";
  readonly stage: string;
}

export interface ScenarioActorChanged extends GameEvent {
  readonly type: "scenario/actor-changed";
  readonly actorId: string;
  /** `null` when the actor left the stage. */
  readonly slot: ScenarioSlot | null;
  readonly expression: string | null;
}

export interface ScenarioAudioChanged extends GameEvent {
  readonly type: "scenario/audio-changed";
  readonly track: string;
  readonly action: "play" | "stop";
}

export interface ScenarioEnded extends GameEvent {
  readonly type: "scenario/ended";
  readonly outcome: string;
}

export type ScenarioEvent =
  | ScenarioPresented
  | ScenarioBranched
  | ScenarioFlagChanged
  | ScenarioStaged
  | ScenarioActorChanged
  | ScenarioAudioChanged
  | ScenarioEnded;

/** One transition, and everything that happened inside it. */
export interface ScenarioTurn {
  readonly state: ScenarioState;
  readonly events: readonly ScenarioEvent[];
}

export type ScenarioAction =
  | { readonly kind: "advance" }
  | { readonly kind: "choose"; readonly option: number }
  | { readonly kind: "restart" };

/**
 * The state before the entry block has presented anything.
 *
 * `carried` is how a fact set from an earlier beat of a case arrives, and only
 * the flags this scenario declared as `imported` are seeded from it. A local
 * flag is one this scenario's own `set` statements establish, and seeding it
 * from outside would start the player in a state the admission proof never
 * searched - the proof enumerated every assignment of the imported flags and
 * exactly one starting assignment of the local ones, which is cleared.
 */
export function initialScenarioState(
  program: ScenarioProgram,
  carried: readonly string[] = [],
): ScenarioState {
  return initialScenarioTurn(program, carried).state;
}

/** The opening, with everything the settle did on the way to the first moment. */
export function initialScenarioTurn(
  program: ScenarioProgram,
  carried: readonly string[] = [],
): ScenarioTurn {
  const declared = new Set(program.importedFlags);
  const events: ScenarioEvent[] = [];
  const state = settle(
    program,
    {
      label: program.entry,
      index: -1,
      flags: Object.freeze([...new Set(carried.filter((flag) => declared.has(flag)))].sort()),
      seen: [],
      stage: null,
      actors: [],
      tracks: [],
      outcome: null,
    },
    events,
  );
  return Object.freeze({ state, events: Object.freeze(events) });
}

/**
 * A saved moment, checked against the program it claims to belong to.
 *
 * Returns null rather than throwing when the snapshot does not fit: a save is
 * read back from a browser the player owns, and a scenario that was regenerated
 * under the player's feet should start over, not crash. Everything the drawing
 * depends on is validated - the block, the statement inside it, the stage, the
 * cast, the slots, and the flags - because the runtime is the only thing here
 * that knows what the program actually declares.
 */
export function restoreScenarioState(
  program: ScenarioProgram,
  saved: ScenarioState,
): ScenarioState | null {
  const block = blockOf(program, saved.label);
  if (block === null) return null;
  if (!Number.isSafeInteger(saved.index) || saved.index < 0) return null;
  if (saved.outcome === null && block.statements[saved.index] === undefined) return null;
  if (
    saved.outcome !== null &&
    !program.endings.some((ending) => ending.outcomeId === saved.outcome)
  ) {
    return null;
  }
  const declaredFlags = new Set(program.flags);
  if (saved.flags.some((flag) => !declaredFlags.has(flag))) return null;
  const stages = new Set(program.stages.map((stage) => stage.stageId));
  if (saved.stage !== null && !stages.has(saved.stage)) return null;
  const tracks = new Set(program.tracks.map((track) => track.trackId));
  if (saved.tracks.some((track) => !tracks.has(track))) return null;
  const cast = new Map(program.cast.map((member) => [member.actorId, member]));
  for (const actor of saved.actors) {
    const member = cast.get(actor.actorId);
    if (member === undefined) return null;
    if (!(SCENARIO_SLOTS as readonly string[]).includes(actor.slot)) return null;
    if (actor.expression !== null && !member.expressions.includes(actor.expression)) return null;
  }
  return Object.freeze({
    label: saved.label,
    index: saved.index,
    flags: Object.freeze([...saved.flags].sort()),
    seen: Object.freeze([...saved.seen]),
    stage: saved.stage,
    actors: Object.freeze(saved.actors.map((actor) => Object.freeze({ ...actor }))),
    tracks: Object.freeze([...saved.tracks]),
    outcome: saved.outcome,
  });
}

/**
 * One transition. Returns the same object when nothing moved, so a consumer can
 * skip a redraw by identity the way the existing scene already does.
 */
export function reduceScenario(
  program: ScenarioProgram,
  state: ScenarioState,
  action: ScenarioAction,
): ScenarioState {
  return reduceScenarioTurn(program, state, action).state;
}

/**
 * One transition, and the occurrences inside it.
 *
 * The same reducer; what is added is a record of the invisible statements the
 * settle walked through on the way to the next moment. A turn that moves nothing
 * — a stray key at an ending, a choice that was not offered — reports no events,
 * which is what makes "nothing happened" a checkable answer rather than an
 * unchanged object a caller has to notice by identity.
 */
export function reduceScenarioTurn(
  program: ScenarioProgram,
  state: ScenarioState,
  action: ScenarioAction,
): ScenarioTurn {
  if (action.kind === "restart") return initialScenarioTurn(program);
  const events: ScenarioEvent[] = [];
  const turn = (next: ScenarioState): ScenarioTurn =>
    Object.freeze({ state: next, events: Object.freeze(events) });
  if (state.outcome !== null) return turn(state);

  const statement = statementAt(program, state);
  if (statement === null) return turn(state);

  if (statement.kind === "choice") {
    if (action.kind !== "choose") return turn(state);
    const available = availableOptions(statement.options, state.flags);
    const chosen = available[action.option];
    if (chosen === undefined) return turn(state);
    events.push({
      type: "scenario/branched",
      from: state.label,
      to: chosen.target,
      cause: "choice",
    });
    return turn(settle(program, { ...state, label: chosen.target, index: -1 }, events));
  }
  if (action.kind !== "advance") return turn(state);
  return turn(settle(program, { ...state, index: state.index + 1 }, events));
}

/** What is on screen now: a line, a choice, or the end card. */
export function scenarioView(program: ScenarioProgram, state: ScenarioState): ScenarioView | null {
  if (state.outcome !== null) {
    const ending = program.endings.find((entry) => entry.outcomeId === state.outcome);
    return Object.freeze({
      kind: "end" as const,
      outcome: state.outcome,
      label: ending?.label ?? state.outcome,
    });
  }
  const statement = statementAt(program, state);
  if (statement === null) return null;
  if (statement.kind === "choice") {
    return Object.freeze({
      kind: "choice" as const,
      options: availableOptions(statement.options, state.flags),
    });
  }
  if (statement.kind === "line") {
    return Object.freeze({
      kind: "line" as const,
      speaker: statement.speaker,
      speakerLabel: statement.speaker === null ? null : speakerLabel(program, statement.speaker),
      text: statement.text,
    });
  }
  return null;
}

/** Stable identity for one authored statement, for "already read" and save slots. */
export function scenarioStatementId(label: string, index: number): string {
  return `${label}#${index}`;
}

export function scenarioIsFinished(state: ScenarioState): boolean {
  return state.outcome !== null;
}

/** How many statements the player has read, over how many the scenario authors. */
export function scenarioProgress(
  program: ScenarioProgram,
  state: ScenarioState,
): { readonly seen: number; readonly total: number } {
  const total = program.blocks.reduce(
    (count, block) => count + block.statements.filter(isPresented).length,
    0,
  );
  return { seen: state.seen.length, total };
}

/** The expression an actor is currently shown at, or null when not on stage. */
export function scenarioActor(state: ScenarioState, actorId: string): ScenarioActor | null {
  return state.actors.find((actor) => actor.actorId === actorId) ?? null;
}

// ------------------------------------------------------------------ internals

/**
 * Run forward from `index` until something is on screen or the scenario ends.
 *
 * `show`, `hide`, `stage`, `audio`, `set`, `jump` and `branch` are all invisible:
 * they change the world and hand control straight on. Only a line, a choice, or
 * an ending stops here. Doing this in the reducer rather than the consumer is
 * what keeps "what is drawn" a pure function of the state, instead of something
 * the view has to re-derive by peeking at the next few statements.
 */
function settle(
  program: ScenarioProgram,
  start: ScenarioState,
  events: ScenarioEvent[],
): ScenarioState {
  let state = start;
  // The program is a finite graph whose every block terminates, and the proof
  // refused any that could not reach an `end`. A cycle of invisible statements
  // is still expressible, though, so the walk is bounded rather than trusted.
  const limit = totalStatements(program) + program.blocks.length + 1;
  for (let step = 0; step <= limit; step += 1) {
    const block = blockOf(program, state.label);
    if (block === null) return { ...state, outcome: state.outcome };
    const statement = block.statements[state.index];
    if (statement === undefined) {
      // Before the first statement of a freshly entered block.
      state = { ...state, index: 0 };
      continue;
    }
    if (isPresented(statement)) {
      const settled = markSeen(speak(state, statement, events));
      events.push({
        type: "scenario/presented",
        statementId: scenarioStatementId(settled.label, settled.index),
        kind: statement.kind === "choice" ? "choice" : "line",
      });
      return settled;
    }
    state = apply(program, state, statement, events);
    if (state.outcome !== null) {
      events.push({ type: "scenario/ended", outcome: state.outcome });
      return state;
    }
  }
  throw new Error("scenario runtime exceeded its step bound; the program is not walkable");
}

function apply(
  program: ScenarioProgram,
  state: ScenarioState,
  statement: ScenarioStatement,
  events: ScenarioEvent[],
): ScenarioState {
  switch (statement.kind) {
    case "show": {
      const others = state.actors.filter((actor) => actor.actorId !== statement.actor);
      const previous = scenarioActor(state, statement.actor);
      events.push({
        type: "scenario/actor-changed",
        actorId: statement.actor,
        slot: statement.slot,
        expression: statement.expression ?? previous?.expression ?? null,
      });
      return {
        ...state,
        index: state.index + 1,
        actors: [
          ...others,
          {
            actorId: statement.actor,
            expression: statement.expression ?? previous?.expression ?? null,
            slot: statement.slot,
          },
        ],
      };
    }
    case "hide":
      events.push({
        type: "scenario/actor-changed",
        actorId: statement.actor,
        slot: null,
        expression: null,
      });
      return {
        ...state,
        index: state.index + 1,
        actors: state.actors.filter((actor) => actor.actorId !== statement.actor),
      };
    case "stage":
      events.push({ type: "scenario/staged", stage: statement.stage });
      return { ...state, index: state.index + 1, stage: statement.stage };
    case "audio":
      events.push({
        type: "scenario/audio-changed",
        track: statement.track,
        action: statement.action,
      });
      return {
        ...state,
        index: state.index + 1,
        tracks:
          statement.action === "play"
            ? [...state.tracks.filter((track) => track !== statement.track), statement.track]
            : state.tracks.filter((track) => track !== statement.track),
      };
    case "set":
      events.push({
        type: "scenario/flag-changed",
        flag: statement.flag,
        value: statement.value,
      });
      return {
        ...state,
        index: state.index + 1,
        flags: statement.value
          ? [...state.flags.filter((flag) => flag !== statement.flag), statement.flag].sort()
          : state.flags.filter((flag) => flag !== statement.flag),
      };
    case "jump":
      events.push({
        type: "scenario/branched",
        from: state.label,
        to: statement.target,
        cause: "jump",
      });
      return { ...state, label: statement.target, index: 0 };
    case "branch": {
      // First satisfied edge, exactly as the admission proof searched it.
      const edge = statement.edges.find((entry) => holds(entry.condition, state.flags));
      const target = edge?.target ?? statement.default;
      events.push({ type: "scenario/branched", from: state.label, to: target, cause: "branch" });
      return { ...state, label: target, index: 0 };
    }
    case "end":
      return { ...state, outcome: statement.outcome };
    default:
      return { ...state, index: state.index + 1 };
  }
}

/**
 * A line that names an expression re-dresses its speaker for as long as the
 * line and everything after it, exactly as the script surface reads: `mara
 * delighted "..."` means Mara is delighted from here on, not just staged where
 * `show` last put her. Staging itself stays `show`'s job - a line spoken from
 * off stage changes nothing.
 */
function speak(
  state: ScenarioState,
  statement: ScenarioStatement,
  events: ScenarioEvent[],
): ScenarioState {
  if (statement.kind !== "line" || statement.speaker === null || statement.expression === null) {
    return state;
  }
  const staged = scenarioActor(state, statement.speaker);
  if (staged === null || staged.expression === statement.expression) return state;
  events.push({
    type: "scenario/actor-changed",
    actorId: statement.speaker,
    slot: staged.slot,
    expression: statement.expression,
  });
  return {
    ...state,
    actors: state.actors.map((actor) =>
      actor.actorId === statement.speaker
        ? { ...actor, expression: statement.expression }
        : actor,
    ),
  };
}

function markSeen(state: ScenarioState): ScenarioState {
  const id = scenarioStatementId(state.label, state.index);
  if (state.seen.includes(id)) return state;
  return { ...state, seen: [...state.seen, id] };
}

function statementAt(program: ScenarioProgram, state: ScenarioState): ScenarioStatement | null {
  const block = blockOf(program, state.label);
  return block?.statements[state.index] ?? null;
}

function blockOf(program: ScenarioProgram, label: string): ScenarioBlock | null {
  return program.blocks.find((block) => block.label === label) ?? null;
}

function isPresented(statement: ScenarioStatement): boolean {
  return statement.kind === "line" || statement.kind === "choice";
}

function totalStatements(program: ScenarioProgram): number {
  return program.blocks.reduce((count, block) => count + block.statements.length, 0);
}

function availableOptions(
  options: readonly ScenarioChoiceOption[],
  flags: readonly string[],
): readonly ScenarioChoiceOption[] {
  return Object.freeze(
    options.filter((option) => option.condition === null || holds(option.condition, flags)),
  );
}

function holds(condition: ScenarioCondition, flags: readonly string[]): boolean {
  return (
    condition.requires.every((flag) => flags.includes(flag)) &&
    !condition.forbids.some((flag) => flags.includes(flag))
  );
}

function speakerLabel(program: ScenarioProgram, actorId: string): string {
  const member = program.cast.find((entry) => entry.actorId === actorId);
  return member?.displayName ?? actorId;
}
