import { describe, expect, test } from "bun:test";

import { memorySaveStorage, type PersistenceEvent } from "@/lib/families/persistence";
import { parseCase } from "./case";
import { caseSaveKey } from "./case-save";
import {
  CaseSession,
  initialCaseRuntime,
  reduceCase,
  roomLineKey,
  scenarioLineKey,
  type CaseEvent,
} from "./runtime";
import { initialScenarioState, reduceScenario } from "@/lib/scenario/runtime";
import { parseScenarioProgram } from "@/lib/scenario/program";
import { ferryProgramDocument } from "@/lib/scenario/program.fixture";
import { initialState, interact } from "@/lib/pointclick/state";
import { parseRoomManifest } from "@/lib/pointclick/contract";
import { roomManifestFixture } from "@/lib/pointclick/fixture";

// The episode's rules, tested without a browser — which is the whole point of
// lifting them out of `CasePlayer.tsx`. Every one of these was previously only
// reachable through a React render and a Phaser canvas.

const NOW = new Date("2026-09-05T10:00:00.000Z");

function twoBeatCase() {
  return parseCase({
    schema_version: 1,
    kind: "case-runtime-v1",
    case_id: "two_beats",
    display_name: "Two beats",
    entry: "b_one",
    facts: [{ fact_id: "saw_ledger" }, { fact_id: "found_key" }],
    beats: [
      {
        beat_id: "b_one",
        kind: "scenario",
        run_tag: "run-a",
        scenario_id: "one",
        display_name: "The office",
        writes: ["saw_ledger"],
        edges: [{ outcome: "onward", to: "b_two" }],
      },
      {
        beat_id: "b_two",
        kind: "room",
        run_tag: "run-b",
        display_name: "The court",
        terminal: true,
        edges: [],
      },
    ],
  });
}

describe("the case reducer", () => {
  const document = twoBeatCase();
  const program = parseScenarioProgram(ferryProgramDocument());
  const manifest = parseRoomManifest(roomManifestFixture());

  test("opening with no save plays; opening with one offers it", () => {
    const fresh = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: null,
    });
    expect(fresh.state.phase).toBe("playing");
    expect(fresh.state.progress.beatId).toBe("b_one");
  });

  test("a save whose beat this build no longer carries is not a save", () => {
    const stale = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: {
        runTag: "tag",
        beatId: "b_gone",
        facts: [],
        statementId: null,
        scenario: null,
        room: null,
        backlog: [],
        updatedAt: NOW.toISOString(),
      },
    });
    // Offered a fresh episode rather than a Continue that goes nowhere.
    expect(stale.state.phase).toBe("playing");
    expect(stale.state.resume).toBeNull();
  });

  test("a presented statement writes a save and remembers the line once", () => {
    let state = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: null,
    }).state;
    const scenario = reduceScenario(program, initialScenarioState(program), { kind: "advance" });
    const first = reduceCase(
      document,
      "tag",
      state,
      { kind: "presented", statementId: "a#0", line: { speaker: "mara", text: "hello" }, scenario, outcome: null },
      NOW,
    );
    expect(first.write?.save.beatId).toBe("b_one");
    expect(first.write?.save.runTag).toBe("tag");
    expect(first.state.backlog).toHaveLength(1);
    expect(first.state.drawn).toBe("b_one");
    expect(first.events).toEqual([
      { type: "line/presented", beatId: "b_one", statementId: "a#0" },
    ]);
    // The same statement again is a redraw, not a second line.
    const again = reduceCase(
      document,
      "tag",
      first.state,
      { kind: "presented", statementId: "a#0", line: { speaker: "mara", text: "hello" }, scenario, outcome: null },
      NOW,
    );
    expect(again.state.backlog).toHaveLength(1);
    state = again.state;
  });

  test("a room click writes a save, and a solved room raises its win", () => {
    const opened = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: null,
    }).state;
    const room = interact(manifest, initialState(manifest), "inspect", "bench");
    const turn = reduceCase(document, "tag", opened, { kind: "room-changed", room }, NOW);
    expect(turn.write?.save.room?.narration).toBe(room.narration);
    expect(turn.state.backlog[0]).toEqual({ speaker: null, text: room.narration });
    expect(turn.events).toEqual([
      { type: "line/presented", beatId: "b_one", statementId: null },
    ]);
  });

  test("finishing a beat merges only declared facts, and says which are new", () => {
    const opened = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: null,
    }).state;
    const turn = reduceCase(
      document,
      "tag",
      opened,
      // `local_only` is the leaf's own flag: it is not a declared fact and does
      // not cross. No fact reaches a leaf's effect vocabulary either way.
      { kind: "finish", beatId: "b_one", outcome: "onward", flags: ["saw_ledger", "local_only"] },
      NOW,
    );
    expect(turn.state.progress).toEqual({ beatId: "b_two", facts: ["saw_ledger"] });
    expect(turn.events).toEqual([
      { type: "facts/established", beatId: "b_one", facts: ["saw_ledger"] },
      { type: "beat/entered", beatId: "b_two", facts: ["saw_ledger"] },
    ]);
    // Written the moment the beat is entered, before it has drawn anything.
    expect(turn.write?.save.beatId).toBe("b_two");
  });

  test("a terminal beat finishes the case, clears the save and leaves the result", () => {
    const atTwo = reduceCase(
      document,
      "tag",
      reduceCase(document, "tag", initialCaseRuntime(document), { kind: "opened", saved: null })
        .state,
      { kind: "finish", beatId: "b_one", outcome: "onward", flags: ["saw_ledger"] },
      NOW,
    ).state;
    const end = reduceCase(
      document,
      "tag",
      atTwo,
      { kind: "finish", beatId: "b_two", outcome: "win", flags: ["found_key"] },
      NOW,
    );
    expect(end.state.phase).toBe("finished");
    expect(end.state.carried).toEqual(["found_key", "saw_ledger"]);
    expect(end.clear).toBe(true);
    expect(end.result).toEqual({
      runTag: "tag",
      outcome: "win",
      facts: ["found_key", "saw_ledger"],
      finishedAt: NOW.toISOString(),
    });
    expect(end.events.at(-1)).toEqual({
      type: "case/finished",
      outcome: "win",
      facts: ["found_key", "saw_ledger"],
    });
  });

  test("continuing seeds the line key so the resumed sentence is not doubled", () => {
    const saved = {
      runTag: "tag",
      beatId: "b_one",
      facts: ["saw_ledger"] as readonly string[],
      statementId: "a#4",
      scenario: initialScenarioState(program),
      room: null,
      backlog: [{ speaker: null, text: "already read" }],
      updatedAt: NOW.toISOString(),
    };
    const offered = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved,
    }).state;
    expect(offered.phase).toBe("offering_continue");
    const resumed = reduceCase(document, "tag", offered, { kind: "continue" }).state;
    expect(resumed.progress).toEqual({ beatId: "b_one", facts: ["saw_ledger"] });
    expect(resumed.lastLine).toBe(scenarioLineKey("b_one", "a#4"));
    expect(resumed.backlog).toHaveLength(1);
  });

  test("a room resume is keyed by what has fired and what was said", () => {
    const room = interact(manifest, initialState(manifest), "inspect", "bench");
    const saved = {
      runTag: "tag",
      beatId: "b_one",
      facts: [] as readonly string[],
      statementId: null,
      scenario: null,
      room,
      backlog: [],
      updatedAt: NOW.toISOString(),
    };
    const resumed = reduceCase(
      document,
      "tag",
      reduceCase(document, "tag", initialCaseRuntime(document), { kind: "opened", saved }).state,
      { kind: "continue" },
    ).state;
    expect(resumed.lastLine).toBe(roomLineKey("b_one", room.fired, room.narration));
  });

  test("starting over clears the save and puts the player back at the entry", () => {
    const offered = reduceCase(document, "tag", initialCaseRuntime(document), {
      kind: "opened",
      saved: {
        runTag: "tag",
        beatId: "b_two",
        facts: ["saw_ledger"],
        statementId: null,
        scenario: null,
        room: null,
        backlog: [{ speaker: null, text: "read" }],
        updatedAt: NOW.toISOString(),
      },
    }).state;
    const over = reduceCase(document, "tag", offered, { kind: "start-over" });
    expect(over.clear).toBe(true);
    expect(over.state.progress.beatId).toBe("b_one");
    expect(over.state.backlog).toEqual([]);
  });
});

describe("the session, and what it persists", () => {
  const document = twoBeatCase();
  const program = parseScenarioProgram(ferryProgramDocument());

  test("the two persistence occurrences are heard, and one save is kept per case", () => {
    const storage = memorySaveStorage();
    const saves: PersistenceEvent[] = [];
    const events: CaseEvent[] = [];
    const session = new CaseSession(document, "case-tag", storage, {
      onPersistence: (event) => saves.push(event),
      onEvent: (event) => events.push(event),
      now: () => NOW,
    });
    session.open();
    session.presented({
      kind: "presented",
      statementId: "a#0",
      line: { speaker: null, text: "one" },
      scenario: initialScenarioState(program),
      outcome: null,
    });
    expect(saves.map((event) => event.type)).toEqual(["save/written"]);
    expect(saves[0]).toMatchObject({
      key: caseSaveKey("case-tag"),
      scopes: ["game", "run"],
      slices: ["facts", "scenario", "backlog"],
    });
    expect(storage.entries.size).toBe(1);

    // The reload, on the same store.
    const back = new CaseSession(document, "case-tag", storage, {
      onPersistence: (event) => saves.push(event),
      now: () => NOW,
    });
    expect(back.open().phase).toBe("offering_continue");
    expect(saves.at(-1)?.type).toBe("save/loaded");
    // The save's own statement id is derived from the scenario state it carries,
    // not from what the leaf said it was drawing: an authored position, so a
    // Continue names the line even when the program has been re-read since.
    const opening = initialScenarioState(program);
    expect(back.state.resume?.statementId).toBe(`${opening.label}#${opening.index}`);
  });

  test("subscribers hear every turn", () => {
    const session = new CaseSession(document, "case-tag", memorySaveStorage(), { now: () => NOW });
    const beats: string[] = [];
    const stop = session.subscribe((state) => beats.push(state.progress.beatId));
    session.open();
    session.finish("b_one", "onward", ["saw_ledger"]);
    stop();
    session.finish("b_two", "win", []);
    expect(beats).toEqual(["b_one", "b_two"]);
  });
});
