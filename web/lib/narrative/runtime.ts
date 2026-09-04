// The case runtime: the episode above the leaves, as a reducer and a session.
//
// It was a React component. `CasePlayer.tsx` held every rule about where the
// player is, what they are carrying, what they have already read, whether there
// is a save to offer and what a finished beat does next — in `useState`, in
// `useRef` mirrors written during a Phaser render, and in callbacks. The
// composition table's entry for it says the whole thing in one line: "pure rules
// (`advanceCase`, `mergeFacts`) whose only runtime is a 544-line React
// component". So the rules had no test that did not need a browser, and the one
// thing the pilot most needed to be sure of — that a player can stop in the
// middle and come back — could only be checked by hand.
//
// Two pieces, and the split is the point:
//
//   - `reduceCase` is pure. One action in, one turn out: the next state, the
//     occurrences it raised, and what the host should persist. It never reaches
//     a store, a clock or a window, so the episode can be played end to end in a
//     test at the speed of a function call.
//   - `CaseSession` is the lifecycle-bound half: it holds the document, the tag,
//     the `persistence` store and the current state for as long as the case is
//     being played, applies actions, does the writes the turn asked for, and
//     tells its subscribers. A class because that is what a class is for.
//
// What stays in the component: the chrome. A backlog and a Continue are not part
// of either genre's game — they belong to the person holding the device, they
// have to work identically over a scene and over a room, and they are the two
// places in a pilot where a keyboard and a screen reader should just work.

import type { GameEvent } from "@/lib/kernel/events";
import type { SaveScope } from "@/lib/families/persistence";
import type { RoomPlayState } from "@/lib/pointclick/state";
import type { ScenarioState } from "@/lib/scenario/runtime";
import { SaveStore, type PersistenceEvent, type SaveStorage } from "@/lib/families/persistence";
import {
  advanceCase,
  caseBeat,
  initialCaseProgress,
  mergeFacts,
  ROOM_WIN_OUTCOME,
  type CaseDocument,
  type CaseProgress,
} from "./case";
import {
  appendBacklog,
  beatSave,
  CASE_SAVE_PROFILE,
  caseSaveKey,
  readCaseSave,
  roomSave,
  scenarioSave,
  writeCaseResult,
  type BacklogLine,
  type CaseResult,
  type CaseSave,
} from "./case-save";

/** Where the shell is, which is not the same question as where the player is. */
export type CasePhase = "reading_save" | "offering_continue" | "playing" | "finished";

/** An outcome a leaf has reported and the player has not yet accepted. */
export interface PendingOutcome {
  readonly beatId: string;
  readonly outcome: string;
  readonly flags: readonly string[];
}

export interface CaseRuntimeState {
  readonly phase: CasePhase;
  /** The beat, and the `facts` slice: the one thing that crosses a leaf boundary. */
  readonly progress: CaseProgress;
  /** A save waiting to be accepted or thrown away; null once it has been. */
  readonly resume: CaseSave | null;
  readonly backlog: readonly BacklogLine[];
  readonly pending: PendingOutcome | null;
  /** The `end <outcome>` the episode terminated through, or null. */
  readonly ending: string | null;
  /** What the player finished holding. The episode's output, not a statistic. */
  readonly carried: readonly string[];
  /** Which beat has produced its first moment, so the shell can drop its label. */
  readonly drawn: string | null;
  /**
   * The last line remembered, as a key.
   *
   * A leaf redraws the moment it was saved at and reports it like any other, so
   * without this a Continue would append the line the player is looking at to a
   * backlog that already ends with it.
   */
  readonly lastLine: string | null;
}

export type CaseAction =
  | { readonly kind: "opened"; readonly saved: CaseSave | null }
  | { readonly kind: "continue" }
  | { readonly kind: "start-over" }
  | {
      readonly kind: "presented";
      readonly statementId: string | null;
      readonly line: BacklogLine | null;
      readonly scenario: ScenarioState;
      readonly outcome: string | null;
    }
  | { readonly kind: "room-changed"; readonly room: RoomPlayState }
  | {
      readonly kind: "finish";
      readonly beatId: string;
      readonly outcome: string;
      readonly flags: readonly string[];
    };

// ------------------------------------------------------------------- events

export interface BeatEntered extends GameEvent {
  readonly type: "beat/entered";
  readonly beatId: string;
  readonly facts: readonly string[];
}

export interface LinePresented extends GameEvent {
  readonly type: "line/presented";
  readonly beatId: string;
  /** `<label>#<index>` for a scenario; null in a room, which narrates on a click. */
  readonly statementId: string | null;
}

/**
 * Facts crossed a leaf boundary.
 *
 * The `facts` family's own occurrence, and the reason it is not `effects`: this
 * is a declared boolean namespace crossing a boundary neither leaf can see over,
 * filtered by what the case declares. No fact reaches a leaf's own effect
 * vocabulary and no leaf's quest state leaves it.
 */
export interface FactsEstablished extends GameEvent {
  readonly type: "facts/established";
  readonly beatId: string;
  /** Only the newly established ones, sorted. */
  readonly facts: readonly string[];
}

export interface CaseFinished extends GameEvent {
  readonly type: "case/finished";
  readonly outcome: string;
  readonly facts: readonly string[];
}

export type CaseEvent = BeatEntered | LinePresented | FactsEstablished | CaseFinished;

/** What the host should persist as a result of one turn. */
export interface CaseWrite {
  readonly save: CaseSave;
  /** Absent means every scope. `["game"]` is what survives the leaf. */
  readonly scopes?: readonly SaveScope[];
}

export interface CaseTurn {
  readonly state: CaseRuntimeState;
  readonly events: readonly CaseEvent[];
  readonly write: CaseWrite | null;
  /** The in-progress save should go: there is nothing left to resume. */
  readonly clear: boolean;
  /** What a finished case leaves behind, at the one turn that computes it. */
  readonly result: CaseResult | null;
}

export function initialCaseRuntime(document: CaseDocument): CaseRuntimeState {
  return Object.freeze({
    phase: "reading_save" as const,
    progress: initialCaseProgress(document),
    resume: null,
    backlog: Object.freeze([]),
    pending: null,
    ending: null,
    carried: Object.freeze([]),
    drawn: null,
    lastLine: null,
  });
}

/**
 * What "the same line, again" means, per leaf kind.
 *
 * A scenario has statement identity and needs nothing else. A room has no such
 * thing — it narrates in response to a click — so its line is identified by the
 * beat, the interactions that have fired, and the words themselves, which is
 * exactly enough to tell a redraw from a new click.
 */
export function scenarioLineKey(beatId: string, statementId: string | null): string {
  return `${beatId}:${statementId ?? "end"}`;
}

export function roomLineKey(
  beatId: string,
  fired: readonly number[],
  narration: string,
): string {
  return `${beatId}:${fired.join(",")}:${narration}`;
}

const NOTHING: CaseTurn["events"] = Object.freeze([]);

function still(state: CaseRuntimeState): CaseTurn {
  return { state, events: NOTHING, write: null, clear: false, result: null };
}

/**
 * One transition of the episode.
 *
 * `at` is the wall clock, handed in rather than read, because a save's
 * `updated_at` is the one field here that is not a function of the game.
 */
export function reduceCase(
  document: CaseDocument,
  tag: string,
  state: CaseRuntimeState,
  action: CaseAction,
  at: Date = new Date(),
): CaseTurn {
  switch (action.kind) {
    case "opened": {
      const saved = action.saved;
      // A save whose beat this build no longer carries is not a save. The player
      // is offered a fresh episode rather than a Continue that goes nowhere.
      if (saved === null || caseBeat(document, saved.beatId) === null) {
        return still({ ...state, phase: "playing" });
      }
      return still({
        ...state,
        phase: "offering_continue",
        resume: saved,
        backlog: saved.backlog,
      });
    }

    case "continue": {
      const saved = state.resume;
      if (saved === null) return still(state);
      return still({
        ...state,
        phase: "playing",
        progress: Object.freeze({ beatId: saved.beatId, facts: saved.facts }),
        pending: null,
        lastLine:
          saved.room === null
            ? scenarioLineKey(saved.beatId, saved.statementId)
            : roomLineKey(saved.beatId, saved.room.fired, saved.room.narration),
      });
    }

    case "start-over": {
      const fresh = initialCaseRuntime(document);
      return { ...still({ ...fresh, phase: "playing" }), clear: true };
    }

    case "presented": {
      if (state.phase !== "playing") return still(state);
      const beatId = state.progress.beatId;
      const key = scenarioLineKey(beatId, action.statementId);
      const remembered = remember(state, key, action.line);
      const next: CaseRuntimeState = {
        ...state,
        ...remembered,
        drawn: beatId,
        pending:
          action.outcome === null
            ? state.pending
            : { beatId, outcome: action.outcome, flags: action.scenario.flags },
      };
      return {
        state: next,
        events: Object.freeze([
          { type: "line/presented" as const, beatId, statementId: action.statementId },
        ]),
        write: {
          save: scenarioSave(
            tag,
            beatId,
            state.progress.facts,
            action.scenario,
            remembered.backlog,
            at,
          ),
        },
        clear: false,
        result: null,
      };
    }

    case "room-changed": {
      if (state.phase !== "playing") return still(state);
      const beatId = state.progress.beatId;
      const key = roomLineKey(beatId, action.room.fired, action.room.narration);
      const remembered = remember(state, key, {
        speaker: null,
        text: action.room.narration,
      });
      const next: CaseRuntimeState = {
        ...state,
        ...remembered,
        drawn: beatId,
        pending: action.room.solved
          ? { beatId, outcome: ROOM_WIN_OUTCOME, flags: action.room.flags }
          : state.pending,
      };
      return {
        state: next,
        events: Object.freeze([
          { type: "line/presented" as const, beatId, statementId: null },
        ]),
        write: {
          save: roomSave(tag, beatId, state.progress.facts, action.room, remembered.backlog, at),
        },
        clear: false,
        result: null,
      };
    }

    case "finish": {
      if (state.progress.beatId !== action.beatId) return still(state);
      const before = new Set(state.progress.facts);
      const merged = mergeFacts(document, state.progress.facts, action.flags);
      const established = Object.freeze(merged.filter((fact) => !before.has(fact)));
      const advanced = advanceCase(document, state.progress, action.outcome, action.flags);
      if (advanced === null) {
        // Terminal, or an outcome the case declares no edge for. Either way the
        // episode is over here. The in-progress save goes — there is nothing left
        // to resume — but what the player finished holding IS the episode's
        // output, and the next case opens on it.
        const events: CaseEvent[] = [];
        if (established.length > 0) {
          events.push({
            type: "facts/established",
            beatId: action.beatId,
            facts: established,
          });
        }
        events.push({ type: "case/finished", outcome: action.outcome, facts: merged });
        return {
          state: {
            ...state,
            phase: "finished",
            carried: merged,
            ending: action.outcome,
            pending: null,
          },
          events: Object.freeze(events),
          write: null,
          clear: true,
          result: Object.freeze({
            runTag: tag,
            outcome: action.outcome,
            facts: merged,
            finishedAt: at.toISOString(),
          }),
        };
      }
      const events: CaseEvent[] = [];
      if (established.length > 0) {
        events.push({ type: "facts/established", beatId: action.beatId, facts: established });
      }
      events.push({
        type: "beat/entered",
        beatId: advanced.beatId,
        facts: advanced.facts,
      });
      return {
        state: {
          ...state,
          progress: advanced,
          resume: null,
          pending: null,
          lastLine: null,
        },
        events: Object.freeze(events),
        // Written the moment a beat is entered, before it has drawn anything:
        // without it a player who reloads in the first second of a beat would
        // resume at the previous one and replay a scene they finished.
        write: {
          save: beatSave(tag, advanced.beatId, advanced.facts, state.backlog, at),
        },
        clear: false,
        result: null,
      };
    }
  }
}

function remember(
  state: CaseRuntimeState,
  key: string,
  line: BacklogLine | null,
): { readonly backlog: readonly BacklogLine[]; readonly lastLine: string } {
  if (line === null || state.lastLine === key) {
    return { backlog: state.backlog, lastLine: key };
  }
  return { backlog: appendBacklog(state.backlog, line), lastLine: key };
}

// ------------------------------------------------------------------ session

export interface CaseSessionOptions {
  /** Where the two occurrences the `persistence` family raises are heard. */
  readonly onPersistence?: (event: PersistenceEvent) => void;
  readonly onEvent?: (event: CaseEvent) => void;
  readonly now?: () => Date;
}

/**
 * One case being played, with its save.
 *
 * Holds the store and the state for as long as the episode is on screen; every
 * method is one action through `reduceCase` followed by whatever writing the
 * turn asked for. The tag is the session's, not the reducer's — the reducer has
 * no business knowing which localStorage key it is filed under.
 */
export class CaseSession {
  private current: CaseRuntimeState;
  private readonly store: SaveStore<CaseSave>;
  private readonly listeners = new Set<(state: CaseRuntimeState) => void>();
  private readonly now: () => Date;

  constructor(
    private readonly document: CaseDocument,
    private readonly tag: string,
    private readonly storage: SaveStorage,
    private readonly options: CaseSessionOptions = {},
  ) {
    this.current = initialCaseRuntime(document);
    this.store = new SaveStore(storage, CASE_SAVE_PROFILE, options.onPersistence);
    this.now = options.now ?? (() => new Date());
  }

  get state(): CaseRuntimeState {
    return this.current;
  }

  subscribe(listener: (state: CaseRuntimeState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** Read the save, if there is one, and offer it. The episode's first act. */
  open(): CaseRuntimeState {
    return this.apply({
      kind: "opened",
      saved: readCaseSave(this.storage, this.tag, this.options.onPersistence),
    });
  }

  continueSaved(): CaseRuntimeState {
    return this.apply({ kind: "continue" });
  }

  startOver(): CaseRuntimeState {
    return this.apply({ kind: "start-over" });
  }

  presented(action: Extract<CaseAction, { kind: "presented" }>): CaseRuntimeState {
    return this.apply(action);
  }

  roomChanged(room: RoomPlayState): CaseRuntimeState {
    return this.apply({ kind: "room-changed", room });
  }

  finish(beatId: string, outcome: string, flags: readonly string[]): CaseRuntimeState {
    return this.apply({ kind: "finish", beatId, outcome, flags });
  }

  private apply(action: CaseAction): CaseRuntimeState {
    const turn = reduceCase(this.document, this.tag, this.current, action, this.now());
    this.current = turn.state;
    if (turn.write !== null) {
      this.store.write(caseSaveKey(this.tag), turn.write.save, turn.write.scopes);
    }
    if (turn.clear) this.store.clear(caseSaveKey(this.tag));
    if (turn.result !== null) writeCaseResult(this.storage, turn.result);
    for (const event of turn.events) this.options.onEvent?.(event);
    for (const listener of this.listeners) listener(this.current);
    return this.current;
  }
}
