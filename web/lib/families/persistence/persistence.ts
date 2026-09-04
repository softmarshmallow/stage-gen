// The `persistence` family: what a save is, over the scopes a runtime declares.
//
// The composition table's entry for this family is two sentences of debt.
// "Serializes declared slices" is what it should do; what it does is
// `shell/case-save.ts`, which persists the whole leaf reducer state, fail-soft,
// as one hand-written record with one hand-written parser — and which is the
// only saving anything in this repository does. `facts` is named there as the
// one `"game"`-scope slice, and that word — scope — is the whole ruling: a save
// is not one blob, it is a set of declared slices each of which has a lifetime,
// and the lifetimes are what a resume has to get right.
//
// Two scopes, because the runtime already declares two and no more:
//
//   - "game"  outlives the leaf. The case's `facts` are the only one today: a
//             fact established in one beat is read by the next, which is
//             precisely why it cannot be filed with the beat that set it.
//   - "run"   belongs to the leaf being played. The scenario's playback, the
//             room's fired interactions, the backlog. A save that restored these
//             into a different beat would be restoring somebody else's game.
//
// What is deliberately NOT here: an authored `[save]` table. The composition
// table names one — "to author `[save]`: scope and trigger names" — and it is a
// contract change in `src/`, which this step may not make. So the scopes are the
// ones the runtime already declares in its own types, and the trigger stays the
// host's: the case writes at every statement because the shell decided that, not
// because a package asked for it. What an authored `[save]` would buy is in the
// step's report; nothing here is blocked on it, and nothing here would have to
// move to accept it — a `[save]` table would name scopes and triggers, and this
// module already takes the scopes as data.
//
// This family gates no manifest block, because it reads none. The block-gate
// discipline is a family taking its own dependency on the block it cannot go on
// without; a family with no authored input has no such dependency to take, and
// gating a block it never reads would be the parser-speaking-for-consumers habit
// that discipline exists to end.
//
// Everything below is fail-soft in one direction only. Reading never throws: the
// bytes come from a browser the player owns and a build that may have moved on
// since they were written, and a save that no longer parses means "no save",
// which is what the shell should offer them. Writing never throws either: a full
// or blocked store loses the save, not the session. Serializing DOES throw,
// because a state this runtime cannot describe is a programming error and not a
// player's problem.

import type { GameEvent } from "@/lib/kernel/events";

/**
 * How long a slice lives.
 *
 * Ordered by lifetime, longest first, so a subtraction reads as a prefix: a save
 * restricted to `["game"]` is what survives when the leaf does not.
 */
export const SAVE_SCOPES = Object.freeze(["game", "run"] as const);
export type SaveScope = (typeof SAVE_SCOPES)[number];

/** Only what this family needs of `localStorage`, so a test needs no browser. */
export interface SaveStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/**
 * One declared slice of a save.
 *
 * `serialize` answers `undefined` for a slice this state does not carry — a room
 * beat has no scenario — and an absent slice is written as absent rather than as
 * null, so "this save has no room" and "this save's room is empty" stay different
 * sentences. `parse` is strict and throws on drift; the store catches.
 */
export interface DeclaredSlice<StateT> {
  readonly slice: string;
  readonly scope: SaveScope;
  serialize(state: StateT): unknown;
  parse(value: unknown): unknown;
}

/**
 * One step of the versioned parse.
 *
 * A save written by one version and read by the next arrives here first: the
 * upgrade takes the slice record as it was written and answers it as the next
 * version would have written it. Applied in order from the record's own version
 * up to the profile's, so a save two versions old is upgraded twice rather than
 * refused — which is the difference between a versioned parse and a version check.
 */
export interface SaveUpgrade {
  /** The version this upgrade reads. It produces `from + 1`. */
  readonly from: number;
  upgrade(slices: Readonly<Record<string, unknown>>): Record<string, unknown>;
}

export interface SaveProfile<StateT> {
  /** The record's discriminant, e.g. `case_save_v1`. */
  readonly kind: string;
  /** The version this build writes. Bumped when a slice's shape changes. */
  readonly version: number;
  readonly slices: readonly DeclaredSlice<StateT>[];
  /** Fields outside every scope: who this save belongs to, and when it was written. */
  serializeMeta?(state: StateT): Readonly<Record<string, unknown>>;
  parseMeta?(value: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>>;
  readonly upgrades?: readonly SaveUpgrade[];
}

/** What a read gives back: the meta, and the slices that were actually there. */
export interface SaveRecord {
  readonly kind: string;
  /** The version the bytes were written by, before any upgrade. */
  readonly writtenVersion: number;
  readonly meta: Readonly<Record<string, unknown>>;
  readonly slices: Readonly<Record<string, unknown>>;
  /** Which declared scopes this save actually carries. */
  readonly scopes: readonly SaveScope[];
}

export interface SaveWritten extends GameEvent {
  readonly type: "save/written";
  readonly key: string;
  readonly scopes: readonly SaveScope[];
  readonly slices: readonly string[];
}

export interface SaveLoaded extends GameEvent {
  readonly type: "save/loaded";
  readonly key: string;
  readonly scopes: readonly SaveScope[];
  readonly slices: readonly string[];
  /** The version the bytes carried; below the profile's when it was upgraded. */
  readonly writtenVersion: number;
}

export type PersistenceEvent = SaveWritten | SaveLoaded;

/** Every refusal the serializer makes, so a caller can catch the family. */
export class SaveRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

function scopesOf(slices: readonly string[], profile: SaveProfile<unknown>): readonly SaveScope[] {
  const present = new Set(slices);
  return Object.freeze(
    SAVE_SCOPES.filter((scope) =>
      profile.slices.some((slice) => slice.scope === scope && present.has(slice.slice)),
    ),
  );
}

/**
 * Serialize the declared slices of one state, or only those in `scopes`.
 *
 * The restriction is the family's own subtraction instrument and it is not a
 * test-only affordance: "what survives the leaf" is a real question a case asks
 * at an ending, and it is answered by writing the game scope and nothing else.
 */
export function serializeSave<StateT>(
  profile: SaveProfile<StateT>,
  state: StateT,
  scopes: readonly SaveScope[] = SAVE_SCOPES,
): Record<string, unknown> {
  const wanted = new Set(scopes);
  const slices: Record<string, unknown> = {};
  const seen = new Set<string>();
  for (const declared of profile.slices) {
    if (seen.has(declared.slice)) {
      throw new SaveRefusal(
        `save profile "${profile.kind}" declares "${declared.slice}" twice; one slice, one scope`,
      );
    }
    seen.add(declared.slice);
    if (!wanted.has(declared.scope)) continue;
    const value = declared.serialize(state);
    if (value === undefined) continue;
    slices[declared.slice] = value;
  }
  return {
    schema_version: profile.version,
    kind: profile.kind,
    ...(profile.serializeMeta?.(state) ?? {}),
    slices,
  };
}

/**
 * Validate one persisted save, upgrading it to this build's version first.
 *
 * Strict about shape and deliberately not strict about meaning: whether a label
 * still exists, or a flag is still declared, is a question about a program this
 * module has never seen. The runtime answers that with the program in hand.
 */
export function parseSave<StateT>(
  profile: SaveProfile<StateT>,
  value: unknown,
): SaveRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new SaveRefusal("save must be an object");
  }
  const root = value as Record<string, unknown>;
  if (root.kind !== profile.kind) {
    throw new SaveRefusal(`save kind must be ${JSON.stringify(profile.kind)}`);
  }
  const written = root.schema_version;
  if (!Number.isSafeInteger(written) || (written as number) < 1) {
    throw new SaveRefusal("save schema_version must be a positive integer");
  }
  const writtenVersion = written as number;
  if (writtenVersion > profile.version) {
    // A save from a build that has moved on. Refused rather than guessed at: the
    // upgrades run forwards only, and reading a newer record with an older parser
    // is how a save gets silently truncated on the next write.
    throw new SaveRefusal(
      `save was written by version ${writtenVersion}, which is newer than ${profile.version}`,
    );
  }
  const raw = root.slices;
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new SaveRefusal("save slices must be an object");
  }
  let slices = raw as Readonly<Record<string, unknown>>;
  const upgrades = [...(profile.upgrades ?? [])].sort((a, b) => a.from - b.from);
  for (let version = writtenVersion; version < profile.version; version += 1) {
    const step = upgrades.find((upgrade) => upgrade.from === version);
    if (step === undefined) {
      throw new SaveRefusal(
        `save profile "${profile.kind}" has no upgrade from version ${version}`,
      );
    }
    slices = step.upgrade(slices);
  }
  const parsed: Record<string, unknown> = {};
  for (const declared of profile.slices) {
    const value = slices[declared.slice];
    if (value === undefined) continue;
    parsed[declared.slice] = declared.parse(value);
  }
  const names = Object.keys(parsed);
  return Object.freeze({
    kind: profile.kind,
    writtenVersion,
    meta: Object.freeze(profile.parseMeta?.(root) ?? {}),
    slices: Object.freeze(parsed),
    scopes: scopesOf(names, profile as SaveProfile<unknown>),
  });
}

/**
 * One profile's saves, in one store.
 *
 * A class because it is exactly the lifecycle-bound thing a class is for: it
 * holds the port, the profile and the sink for as long as the game that is
 * saving exists, and every method on it is that triple applied to one key.
 */
export class SaveStore<StateT> {
  constructor(
    private readonly storage: SaveStorage,
    private readonly profile: SaveProfile<StateT>,
    private readonly emit: (event: PersistenceEvent) => void = () => {},
  ) {}

  /** `save/written`, or null when the store refused the bytes. */
  write(
    key: string,
    state: StateT,
    scopes: readonly SaveScope[] = SAVE_SCOPES,
  ): SaveWritten | null {
    const record = serializeSave(this.profile, state, scopes);
    const names = Object.keys(record.slices as Record<string, unknown>);
    try {
      this.storage.setItem(key, JSON.stringify(record));
    } catch {
      // A full or blocked store loses the save, not the session. A player who
      // cannot autosave should still be able to finish what they are playing.
      return null;
    }
    const event = Object.freeze({
      type: "save/written" as const,
      key,
      scopes: scopesOf(names, this.profile as SaveProfile<unknown>),
      slices: Object.freeze([...names]),
    });
    this.emit(event);
    return event;
  }

  /** The save under `key`, or null when there is nothing usable there. */
  read(key: string): SaveRecord | null {
    let raw: string | null;
    try {
      raw = this.storage.getItem(key);
    } catch {
      return null;
    }
    if (raw === null) return null;
    let record: SaveRecord;
    try {
      record = parseSave(this.profile, JSON.parse(raw));
    } catch {
      return null;
    }
    this.emit(
      Object.freeze({
        type: "save/loaded" as const,
        key,
        scopes: record.scopes,
        slices: Object.freeze(Object.keys(record.slices)),
        writtenVersion: record.writtenVersion,
      }),
    );
    return record;
  }

  clear(key: string): void {
    try {
      this.storage.removeItem(key);
    } catch {
      // As above: forgetting a save is not worth ending a play-through over.
    }
  }
}

/** A store with no browser: the test double the family ships with. */
export function memorySaveStorage(
  seed: Readonly<Record<string, string>> = {},
): SaveStorage & { readonly entries: ReadonlyMap<string, string> } {
  const entries = new Map<string, string>(Object.entries(seed));
  return {
    entries,
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => {
      entries.set(key, value);
    },
    removeItem: (key) => {
      entries.delete(key);
    },
  };
}
