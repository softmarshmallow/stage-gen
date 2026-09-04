import { describe, expect, test } from "bun:test";

import {
  memorySaveStorage,
  parseSave,
  SaveRefusal,
  SaveStore,
  serializeSave,
  type DeclaredSlice,
  type PersistenceEvent,
  type SaveProfile,
} from "./persistence";

// ------------------------------------------------------------------ world one

/** A leaf-shaped state: one game-scope slice and two run-scope ones. */
interface LeafState {
  readonly facts: readonly string[];
  readonly beat: string;
  readonly line: number;
}

const strings = (value: unknown): readonly string[] => {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw new SaveRefusal("must be a list of strings");
  }
  return Object.freeze([...(value as string[])]);
};

const LEAF: SaveProfile<LeafState> = {
  kind: "leaf_save",
  version: 1,
  slices: [
    { slice: "facts", scope: "game", serialize: (s) => [...s.facts], parse: strings },
    { slice: "beat", scope: "run", serialize: (s) => s.beat, parse: (v) => String(v) },
    { slice: "line", scope: "run", serialize: (s) => s.line, parse: (v) => Number(v) },
  ],
  serializeMeta: (s) => ({ beat_id: s.beat }),
  parseMeta: (root) => ({ beatId: root.beat_id }),
};

// ------------------------------------------------------------------ world two

/**
 * E4, dual instantiation: the same family sealed over a world whose type shares
 * nothing with the first. A score board has no beats, no facts and no leaf; what
 * it has is a lifetime distinction, which is the only thing this family knows.
 */
interface BoardState {
  readonly best: number;
  readonly attempt: number;
}

const BOARD: SaveProfile<BoardState> = {
  kind: "board_save",
  version: 1,
  slices: [
    { slice: "best", scope: "game", serialize: (s) => s.best, parse: (v) => Number(v) },
    { slice: "attempt", scope: "run", serialize: (s) => s.attempt, parse: (v) => Number(v) },
  ],
};

describe("persistence serializes the scopes a runtime declares", () => {
  test("a whole save carries every declared slice, and says which scopes it has", () => {
    const record = serializeSave(LEAF, { facts: ["saw_ledger"], beat: "study", line: 4 });
    expect(record).toEqual({
      schema_version: 1,
      kind: "leaf_save",
      beat_id: "study",
      slices: { facts: ["saw_ledger"], beat: "study", line: 4 },
    });
    const parsed = parseSave(LEAF, record);
    expect(parsed.scopes).toEqual(["game", "run"]);
    expect(parsed.meta).toEqual({ beatId: "study" });
  });

  test("E7 (subtraction): the game scope alone restores identically, minus the run", () => {
    const state = { facts: ["saw_ledger"], beat: "study", line: 4 };
    const whole = parseSave(LEAF, serializeSave(LEAF, state));
    const carried = parseSave(LEAF, serializeSave(LEAF, state, ["game"]));
    // What the family promises: dropping a scope drops exactly its slices and
    // changes nothing about the ones that remain. This is what a case does at an
    // ending — the facts the player finished holding survive the leaf that set
    // them, and the leaf's own playback does not.
    expect(carried.scopes).toEqual(["game"]);
    expect(carried.slices).toEqual({ facts: ["saw_ledger"] });
    expect(carried.slices.facts).toEqual(whole.slices.facts);
  });

  test("a slice the state does not carry is absent, not null", () => {
    const sparse: SaveProfile<LeafState> = {
      ...LEAF,
      slices: [
        LEAF.slices[0]!,
        {
          slice: "room",
          scope: "run",
          serialize: () => undefined,
          parse: (v) => v,
        } satisfies DeclaredSlice<LeafState>,
      ],
    };
    const record = serializeSave(sparse, { facts: [], beat: "study", line: 0 });
    expect(Object.keys(record.slices as object)).toEqual(["facts"]);
  });

  test("one slice, one scope: a profile that declares a name twice is refused", () => {
    const doubled: SaveProfile<LeafState> = {
      ...LEAF,
      slices: [LEAF.slices[0]!, { ...LEAF.slices[0]!, scope: "run" }],
    };
    expect(() => serializeSave(doubled, { facts: [], beat: "a", line: 0 })).toThrow(SaveRefusal);
  });
});

describe("the versioned parse", () => {
  /**
   * The next version of `LEAF`: `line` became `{ label, index }`, which is a
   * slice shape change and therefore a version bump.
   */
  const LEAF_V2: SaveProfile<LeafState> = {
    ...LEAF,
    version: 2,
    slices: [
      LEAF.slices[0]!,
      LEAF.slices[1]!,
      {
        slice: "line",
        scope: "run",
        serialize: (s) => ({ label: s.beat, index: s.line }),
        parse: (value) => {
          const record = value as Record<string, unknown>;
          if (typeof record?.label !== "string" || !Number.isSafeInteger(record.index)) {
            throw new SaveRefusal("line must be {label, index}");
          }
          return { label: record.label, index: record.index };
        },
      },
    ],
    upgrades: [
      {
        from: 1,
        upgrade: (record) => {
          const slices = record.slices as Record<string, unknown>;
          return {
            ...record,
            slices: {
              ...slices,
              line: { label: String(slices.beat), index: Number(slices.line) },
            },
          };
        },
      },
    ],
  };

  test("a save written by one version is restored by the next", () => {
    // Written by the build that shipped v1, byte for byte.
    const written = serializeSave(LEAF, { facts: ["saw_ledger"], beat: "study", line: 4 });
    expect(written.schema_version).toBe(1);

    const restored = parseSave(LEAF_V2, written);
    expect(restored.writtenVersion).toBe(1);
    expect(restored.slices).toEqual({
      facts: ["saw_ledger"],
      beat: "study",
      line: { label: "study", index: 4 },
    });
    // And the same build reads its own writes without the upgrade running.
    const native = parseSave(LEAF_V2, serializeSave(LEAF_V2, { facts: [], beat: "hall", line: 1 }));
    expect(native.writtenVersion).toBe(2);
    expect(native.slices.line).toEqual({ label: "hall", index: 1 });
  });

  test("a version with no upgrade is refused rather than guessed at", () => {
    const orphan: SaveProfile<LeafState> = { ...LEAF_V2, upgrades: [] };
    expect(() => parseSave(orphan, serializeSave(LEAF, { facts: [], beat: "a", line: 0 }))).toThrow(
      /no upgrade from version 1/,
    );
  });

  test("a save from a newer build is refused, not truncated", () => {
    const future = serializeSave(LEAF_V2, { facts: [], beat: "a", line: 0 });
    expect(() => parseSave(LEAF, future)).toThrow(/newer than 1/);
  });

  test("drift in one slice refuses the save, naming the family", () => {
    expect(() => parseSave(LEAF, { schema_version: 1, kind: "leaf_save", slices: { facts: 3 } }))
      .toThrow(SaveRefusal);
    expect(() => parseSave(LEAF, { schema_version: 1, kind: "board_save", slices: {} })).toThrow(
      /kind must be/,
    );
  });
});

describe("the store, and the two occurrences it reports", () => {
  test("save/written and save/loaded name the key, the scopes and the slices", () => {
    const heard: PersistenceEvent[] = [];
    const store = new SaveStore(memorySaveStorage(), LEAF, (event) => heard.push(event));
    store.write("slot", { facts: ["saw_ledger"], beat: "study", line: 4 });
    const read = store.read("slot");
    expect(read?.slices.beat).toBe("study");
    expect(heard).toEqual([
      { type: "save/written", key: "slot", scopes: ["game", "run"], slices: ["facts", "beat", "line"] },
      {
        type: "save/loaded",
        key: "slot",
        scopes: ["game", "run"],
        slices: ["facts", "beat", "line"],
        writtenVersion: 1,
      },
    ]);
  });

  test("reading is fail-soft: junk, a missing key and a hostile store are all `no save`", () => {
    const heard: PersistenceEvent[] = [];
    const storage = memorySaveStorage({ junk: "{not json", wrong: '{"kind":"other"}' });
    const store = new SaveStore(storage, LEAF, (event) => heard.push(event));
    expect(store.read("absent")).toBeNull();
    expect(store.read("junk")).toBeNull();
    expect(store.read("wrong")).toBeNull();
    // Nothing was loaded, so nothing said it was.
    expect(heard).toEqual([]);
  });

  test("writing is fail-soft: a full store loses the save, not the session", () => {
    const blocked = {
      getItem: () => null,
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: () => {
        throw new Error("QuotaExceededError");
      },
    };
    const store = new SaveStore(blocked, LEAF);
    expect(store.write("slot", { facts: [], beat: "a", line: 0 })).toBeNull();
    expect(() => store.clear("slot")).not.toThrow();
  });

  test("E4 (dual instantiation): the same family over a world with no leaf in it", () => {
    const heard: PersistenceEvent[] = [];
    const store = new SaveStore(memorySaveStorage(), BOARD, (event) => heard.push(event));
    store.write("board", { best: 9100, attempt: 3 });
    expect(store.read("board")?.slices).toEqual({ best: 9100, attempt: 3 });
    // And the same subtraction, on a world that shares no field with the first:
    // the record survives the attempt.
    store.write("board", { best: 9100, attempt: 3 }, ["game"]);
    expect(store.read("board")?.slices).toEqual({ best: 9100 });
    expect(heard.map((event) => event.type)).toEqual([
      "save/written",
      "save/loaded",
      "save/written",
      "save/loaded",
    ]);
  });
});
