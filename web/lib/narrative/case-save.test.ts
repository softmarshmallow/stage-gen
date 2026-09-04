import { describe, expect, test } from "bun:test";
import {
  appendBacklog,
  BACKLOG_LIMIT,
  beatSave,
  caseResultKey,
  caseSaveKey,
  clearCaseSave,
  parseCaseSave,
  readCaseSave,
  roomSave,
  scenarioSave,
  serializeCaseSave,
  readCaseResult,
  writeCaseResult,
  writeCaseSave,
  type BacklogLine,
  type SaveStorage,
} from "./case-save";
import { initialScenarioState, reduceScenario } from "@/lib/scenario/runtime";
import { parseScenarioProgram } from "@/lib/scenario/program";
import { ferryProgramDocument } from "@/lib/scenario/program.fixture";
import { initialState, interact } from "@/lib/pointclick/state";
import { parseRoomManifest } from "@/lib/pointclick/contract";
import { roomManifestFixture } from "@/lib/pointclick/fixture";

function memoryStorage(): SaveStorage & { readonly entries: Map<string, string> } {
  const entries = new Map<string, string>();
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

const NOW = new Date("2026-09-03T12:00:00.000Z");

describe("appendBacklog", () => {
  test("keeps the newest fifty and forgets the rest", () => {
    let backlog: readonly BacklogLine[] = [];
    for (let index = 0; index < BACKLOG_LIMIT + 12; index += 1) {
      backlog = appendBacklog(backlog, { speaker: "mara", text: `line ${index}` });
    }
    expect(backlog).toHaveLength(BACKLOG_LIMIT);
    expect(backlog[0]!.text).toBe("line 12");
    expect(backlog[BACKLOG_LIMIT - 1]!.text).toBe(`line ${BACKLOG_LIMIT + 11}`);
  });

  test("narration keeps its empty speaker rather than borrowing the last one", () => {
    const backlog = appendBacklog([{ speaker: "mara", text: "hello" }], {
      speaker: null,
      text: "The pier creaks.",
    });
    expect(backlog[1]!.speaker).toBeNull();
  });
});

describe("a scenario save", () => {
  const program = parseScenarioProgram(ferryProgramDocument());

  test("round-trips through the wire, keeping the statement it was written at", () => {
    const state = reduceScenario(program, initialScenarioState(program), { kind: "advance" });
    const save = scenarioSave("case_tag", "beat_one", ["has_token"], state, [], NOW);
    expect(save.statementId).toBe(`${state.label}#${state.index}`);
    const returned = parseCaseSave(serializeCaseSave(save));
    expect(returned).toEqual(save);
  });

  test("the persisted wire is snake_case, because every persisted contract here is", () => {
    const state = initialScenarioState(program);
    const wire = serializeCaseSave(
      scenarioSave("case_tag", "beat_one", [], state, [], NOW),
    ) as Record<string, unknown>;
    // v2: the meta beside the envelope, and the declared slices under `slices`.
    // A scenario beat carries no room, and an absent slice is absent rather than
    // null — which is the whole reason the shape moved.
    expect(Object.keys(wire).sort()).toEqual([
      "beat_id",
      "kind",
      "run_tag",
      "schema_version",
      "slices",
      "statement_id",
      "updated_at",
    ]);
    expect(Object.keys(wire.slices as object).sort()).toEqual(["backlog", "facts", "scenario"]);
    expect(wire.kind).toBe("case_save_v1");
    expect(wire.schema_version).toBe(2);
  });

  test("only the game scope survives the leaf: facts, and nothing that was played", () => {
    const state = reduceScenario(program, initialScenarioState(program), { kind: "advance" });
    const wire = serializeCaseSave(
      scenarioSave("case_tag", "beat_one", ["has_token"], state, [], NOW),
      ["game"],
    ) as Record<string, unknown>;
    expect(wire.slices).toEqual({ facts: ["has_token"] });
    const back = parseCaseSave(wire);
    expect(back.facts).toEqual(["has_token"]);
    expect(back.scenario).toBeNull();
    expect(back.backlog).toEqual([]);
  });

  test("a save written by v1 is restored by v2, under the versioned parse", () => {
    // The bytes a shipped build wrote, flat, exactly as `case_save_v1` had them.
    const state = reduceScenario(program, initialScenarioState(program), { kind: "advance" });
    const v1 = {
      schema_version: 1,
      kind: "case_save_v1",
      run_tag: "the-grain-episode-one",
      beat_id: "b_office",
      facts: ["saw_body"],
      statement_id: `${state.label}#${state.index}`,
      scenario: {
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
      },
      room: null,
      backlog: [{ speaker: "calder", text: "The grain is in the ledger." }],
      updated_at: NOW.toISOString(),
    };
    const restored = parseCaseSave(v1);
    expect(restored.beatId).toBe("b_office");
    expect(restored.facts).toEqual(["saw_body"]);
    expect(restored.statementId).toBe(`${state.label}#${state.index}`);
    expect(restored.scenario).toEqual(state);
    expect(restored.room).toBeNull();
    expect(restored.backlog).toEqual([
      { speaker: "calder", text: "The grain is in the ledger." },
    ]);
    // And the record it came back as is the record this build writes.
    expect(parseCaseSave(serializeCaseSave(restored))).toEqual(restored);
  });

  test("the whole drawn moment is carried, not only the statement id", () => {
    // The reason the record is bigger than "statement id and flags": neither of
    // those says what the backdrop is or who is standing where.
    const state = reduceScenario(program, initialScenarioState(program), { kind: "advance" });
    const save = scenarioSave("case_tag", "beat_one", [], state, [], NOW);
    expect(save.scenario?.stage).not.toBeNull();
    expect(save.scenario?.actors.length).toBeGreaterThan(0);
  });
});

describe("a room save", () => {
  const manifest = parseRoomManifest(roomManifestFixture());

  test("round-trips, and drops the item the player was holding mid-gesture", () => {
    const held = interact(manifest, initialState(manifest), "use", "bench");
    const save = roomSave("case_tag", "beat_two", [], held, [], NOW);
    const returned = parseCaseSave(serializeCaseSave(save));
    expect(returned.room?.inventory).toEqual(held.inventory);
    expect(returned.room?.fired).toEqual(held.fired);
    expect(returned.room?.selectedItem).toBeNull();
  });
});

describe("reading and writing", () => {
  const program = parseScenarioProgram(ferryProgramDocument());

  test("what is written under a tag is what is read back under it", () => {
    const storage = memoryStorage();
    const save = beatSave("case_tag", "beat_one", ["has_token"], [], NOW);
    writeCaseSave(storage, save);
    expect(storage.entries.has(caseSaveKey("case_tag"))).toBe(true);
    expect(readCaseSave(storage, "case_tag")).toEqual(save);
    clearCaseSave(storage, "case_tag");
    expect(readCaseSave(storage, "case_tag")).toBeNull();
  });

  test("one save per tag: a second write replaces the first", () => {
    const storage = memoryStorage();
    writeCaseSave(storage, beatSave("case_tag", "beat_one", [], [], NOW));
    writeCaseSave(storage, beatSave("case_tag", "beat_two", [], [], NOW));
    expect(readCaseSave(storage, "case_tag")?.beatId).toBe("beat_two");
    expect(storage.entries.size).toBe(1);
  });

  test("two cases do not read each other's saves", () => {
    const storage = memoryStorage();
    writeCaseSave(storage, beatSave("one", "beat_one", [], [], NOW));
    writeCaseSave(storage, beatSave("two", "beat_nine", [], [], NOW));
    expect(readCaseSave(storage, "one")?.beatId).toBe("beat_one");
    expect(readCaseSave(storage, "two")?.beatId).toBe("beat_nine");
  });

  test("bytes that no longer parse read as no save, rather than throwing at the player", () => {
    const storage = memoryStorage();
    storage.setItem(caseSaveKey("case_tag"), "{not json");
    expect(readCaseSave(storage, "case_tag")).toBeNull();
    storage.setItem(caseSaveKey("case_tag"), JSON.stringify({ kind: "case_save_v0" }));
    expect(readCaseSave(storage, "case_tag")).toBeNull();
  });

  test("a store that refuses to write loses the save, not the session", () => {
    const failing: SaveStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    const state = initialScenarioState(program);
    expect(() =>
      writeCaseSave(failing, scenarioSave("case_tag", "beat_one", [], state, [], NOW)),
    ).not.toThrow();
    expect(readCaseSave(failing, "case_tag")).toBeNull();
    expect(() => clearCaseSave(failing, "case_tag")).not.toThrow();
  });

  test("a backlog longer than the limit is trimmed on the way back in", () => {
    const storage = memoryStorage();
    const long = Array.from({ length: BACKLOG_LIMIT + 5 }, (_unused, index) => ({
      speaker: null,
      text: `line ${index}`,
    }));
    const wire = serializeCaseSave(beatSave("case_tag", "beat_one", [], [], NOW));
    storage.setItem(
      caseSaveKey("case_tag"),
      JSON.stringify({
        ...wire,
        slices: { ...(wire.slices as object), backlog: long },
      }),
    );
    expect(readCaseSave(storage, "case_tag")?.backlog).toHaveLength(BACKLOG_LIMIT);
  });
});


describe("the record a finished case leaves behind", () => {
  test("survives the save being cleared, because it is the episode's output", () => {
    const storage = memoryStorage();
    writeCaseSave(storage, beatSave("the-grain-episode-one", "b_statements", ["saw_body"], []));
    writeCaseResult(storage, {
      runTag: "the-grain-episode-one",
      outcome: "left_alone",
      facts: ["ward_regard", "saw_body", "told_coffee"],
      finishedAt: "2026-09-03T07:55:00.000Z",
    });
    clearCaseSave(storage, "the-grain-episode-one");

    expect(storage.entries.has(caseSaveKey("the-grain-episode-one"))).toBe(false);
    const result = readCaseResult(storage, "the-grain-episode-one");
    expect(result).not.toBeNull();
    expect(result?.outcome).toBe("left_alone");
    // Sorted, so two runs holding the same board record it identically.
    expect(result?.facts).toEqual(["saw_body", "told_coffee", "ward_regard"]);
  });

  test("a case that was never finished has no record", () => {
    expect(readCaseResult(memoryStorage(), "the-grain-episode-one")).toBeNull();
  });

  test("a record this build cannot read is no record, never a throw", () => {
    const storage = memoryStorage();
    storage.setItem(caseResultKey("t"), "{ not json");
    expect(readCaseResult(storage, "t")).toBeNull();
    storage.setItem(caseResultKey("t"), JSON.stringify({ kind: "something_else" }));
    expect(readCaseResult(storage, "t")).toBeNull();
    storage.setItem(
      caseResultKey("t"),
      JSON.stringify({ kind: "case_result_v1", run_tag: "t", outcome: "x", facts: [1] }),
    );
    expect(readCaseResult(storage, "t")).toBeNull();
  });
});
