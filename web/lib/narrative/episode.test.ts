import { describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import path from "node:path";

// The played evidence for step 8: the existing case episode, saved mid-beat and
// resumed, over the runs that are already published.
//
// Nothing is generated here and nothing is drawn. The six scenario leaves are the
// ones `out/the-grain-episode-one` chains, read by the shell's own reader and
// played through the scenario reducer — which is exactly what the Phaser scene
// does inside its canvas. What is under test is the layer above them: the
// episode, its `facts`, its autosave, and whether a player who stops in the
// middle of a beat comes back to the same sentence.
//
// It is one boot: one process, one document read, one store. The resume is a
// second `CaseSession` over that same store, which is exactly the reload the
// shell performs — nothing is relaunched and nothing is read from disk twice.
//
// The save is measured by the family that made it rather than by the bytes it
// left: every `save/written` and `save/loaded` the `persistence` store raised is
// collected, so the cadence, the declared scopes and the version the bytes
// carried are all assertions here. Three things the step's ruling asks for meet
// in this one run — the played episode, the family's scope subtraction over the
// episode's own mid-beat state, and the cross-version restore, which is done by
// writing that same save back in the flat shape version 1 shipped and opening on
// it.
//
// The episode's TWO ROOM BEATS are reported rather than played, and the reason is
// named rather than hidden: every point-and-click room published in this
// repository writes `schema_version: 1` under kind `pointclick-room-runtime-v3`,
// and `b24c224` ("the manifest's schema version says what its kind says") made
// the parser demand 3. No published room can be read by this build without being
// regenerated, and a regeneration is provider spend. So each room beat is driven
// through the seam the case runtime actually has — a leaf reporting its outcome
// and the flags it finished holding, which is all a case ever hears from one —
// with the flags taken from what the published document says that beat writes.
// The room's own click-by-click autosave is covered by `runtime.test.ts` and by
// `case-save.test.ts` over the room fixture.
//
// It skips, loudly, when the episode is not published in this checkout. `out/` is
// not in the repository, and a test that needed it would be a test that fails on
// a clone rather than a test that reads what is there.

import { readCaseDocument } from "./case-io";
import type { CaseDocument } from "./case";
import { readSceneFixture } from "@/lib/shell/dialogue-scene";
import { CaseSession, type CaseEvent } from "./runtime";
import { BACKLOG_LIMIT, CASE_SAVE_PROFILE, caseSaveKey, parseCaseSave } from "./case-save";
import {
  memorySaveStorage,
  serializeSave,
  type PersistenceEvent,
} from "@/lib/families/persistence";
import {
  initialScenarioState,
  reduceScenario,
  restoreScenarioState,
  scenarioStatementId,
  scenarioView,
  type ScenarioState,
} from "@/lib/scenario/runtime";
import type { ScenarioProgram } from "@/lib/scenario/program";


const EPISODE = "the-grain-episode-one";
const OUT = path.resolve(import.meta.dir, "../../..", "out");

async function published(): Promise<boolean> {
  try {
    await fs.access(path.join(OUT, EPISODE, "case.json"));
    return true;
  } catch {
    return false;
  }
}


/** One step of a scenario: advance, or take the first available option. */
function step(program: ScenarioProgram, state: ScenarioState): ScenarioState {
  const view = scenarioView(program, state);
  if (view?.kind === "choice") return reduceScenario(program, state, { kind: "choose", option: 0 });
  return reduceScenario(program, state, { kind: "advance" });
}

const AVAILABLE = await published();

describe.if(AVAILABLE)("the case episode, saved mid-beat and resumed", () => {
  test("eight beats, one save, and the same sentence on the way back in", async () => {
    // The published document, through the shell's own reader.
    const document: CaseDocument = (await readCaseDocument(EPISODE))!;
    expect(document.beats).toHaveLength(8);
    const leaves = new Map<string, ScenarioProgram>();
    for (const beat of document.beats) {
      if (beat.kind !== "scenario") continue;
      const fixture = await readSceneFixture(beat.runTag, beat.scenarioId ?? undefined);
      expect(fixture).not.toBeNull();
      leaves.set(beat.beatId, fixture!.scenario);
    }
    expect(leaves.size).toBe(6);
    const storage = memorySaveStorage();
    const heard: CaseEvent[] = [];
    // Every write and every read the `persistence` family makes, so the save is
    // measured by the family that made it rather than by the bytes it left.
    const saves: PersistenceEvent[] = [];
    const clock = { at: new Date("2026-09-05T09:00:00.000Z") };

    const open = () =>
      new CaseSession(document, EPISODE, storage, {
        onEvent: (event) => heard.push(event),
        onPersistence: (event) => saves.push(event),
        now: () => clock.at,
      });

    // ------------------------------------------------------------ the first run
    const first = open();
    expect(first.open().phase).toBe("playing");
    expect(first.state.progress.beatId).toBe("b_office");

    // The opening scenario, played to its outcome.
    const office = leaves.get("b_office") as ScenarioProgram;
    let scenario = initialScenarioState(office, first.state.progress.facts);
    for (let guard = 0; guard < 500; guard += 1) {
      first.presented({
        kind: "presented",
        statementId:
          scenario.outcome === null
            ? scenarioStatementId(scenario.label, scenario.index)
            : null,
        line: lineOf(office, scenario),
        scenario,
        outcome: scenario.outcome,
      });
      if (scenario.outcome !== null) break;
      scenario = step(office, scenario);
    }
    const officeOutcome = scenario.outcome;
    expect(officeOutcome).toBe("to_tollands");
    first.finish("b_office", officeOutcome!, scenario.flags);
    expect(first.state.progress.beatId).toBe("b_motor_court");

    // The room beat, reporting its win and the flags it finished holding.
    const courtBeat = document.beats.find((beat) => beat.beatId === "b_motor_court")!;
    first.finish("b_motor_court", "win", courtBeat.writes);
    expect(first.state.progress.beatId).toBe("b_way_in");
    // The room's exported flags crossed the boundary as declared facts, and
    // nothing else did: no inventory, no revealed hotspots, no fired indices.
    const carried = first.state.progress.facts;
    expect([...carried]).toEqual([
      "chalk_and_scissors",
      "gallery_open",
      "rang_the_bell",
      "window_before",
    ]);
    expect(carried.every((fact) => document.facts.includes(fact))).toBe(true);

    // ------------------------------------------------- stopping in mid-sentence
    const wayIn = leaves.get("b_way_in") as ScenarioProgram;
    let mid = initialScenarioState(wayIn, carried);
    for (let line = 0; line < 6; line += 1) {
      first.presented({
        kind: "presented",
        statementId: scenarioStatementId(mid.label, mid.index),
        line: lineOf(wayIn, mid),
        scenario: mid,
        outcome: null,
      });
      mid = step(wayIn, mid);
    }
    // Six lines in, the player closes the tab. The last thing autosaved is the
    // sixth statement, and it is what a Continue has to come back to.
    const stoppedAt = first.presented({
      kind: "presented",
      statementId: scenarioStatementId(mid.label, mid.index),
      line: lineOf(wayIn, mid),
      scenario: mid,
      outcome: null,
    });
    const stoppedStatement = scenarioStatementId(mid.label, mid.index);
    // Named, so "the same sentence" below is a sentence and not a variable.
    expect(stoppedStatement).toBe("the_service_door#10");
    const backlogWhenStopped = stoppedAt.backlog.length;
    // The backlog is at its cap by the time they stop, which is the shape a
    // resume has to restore: the last fifty lines, not the first fifty.
    expect(backlogWhenStopped).toBe(BACKLOG_LIMIT);
    expect(backlogWhenStopped).toBeGreaterThan(6);

    // The save is the `persistence` family's, and it says so. One write per line
    // drawn plus one per beat entered — the autosave cadence the shell chose —
    // and the last of them is the sentence the player stopped on.
    const written = saves.filter((event) => event.type === "save/written");
    expect(written).toHaveLength(saves.length);
    // Not a magic number: every line the case drew and every beat it entered, and
    // nothing else, left a save behind. 103 + 2 by the sixth line of `b_way_in`.
    expect(written).toHaveLength(
      heard.filter((event) => event.type === "line/presented").length +
        heard.filter((event) => event.type === "beat/entered").length,
    );
    expect(written.length).toBe(105);
    const last = written[written.length - 1]!;
    expect(last.key).toBe(caseSaveKey(EPISODE));
    // Both declared scopes are in the bytes: `facts` outlives the leaf, the
    // scenario and the backlog belong to it. No `room` slice, because a scenario
    // beat has none to write — absent rather than null, which is the whole point
    // of the v2 envelope.
    expect(last.scopes).toEqual(["game", "run"]);
    expect(last.slices).toEqual(["facts", "scenario", "backlog"]);

    // The bytes as they sit in the store, kept for the cross-version restore
    // further down; this build writes v2.
    const midBytes = storage.entries.get(caseSaveKey(EPISODE))!;
    expect(midBytes).toBeDefined();
    const midWire = JSON.parse(midBytes) as Record<string, unknown>;
    expect(midWire.schema_version).toBe(2);
    expect(midWire.kind).toBe("case_save_v1");
    expect(Object.keys(midWire.slices as object).sort()).toEqual([
      "backlog",
      "facts",
      "scenario",
    ]);

    // E7 for the family, over the episode's own mid-beat state rather than a
    // fixture: restricted to the "game" scope, what survives the leaf is the four
    // facts and nothing else. The leaf's playback and its backlog are a
    // subtraction, not a special case.
    const midSave = parseCaseSave(midWire);
    const gameOnly = serializeSave(CASE_SAVE_PROFILE, midSave, ["game"]);
    expect(Object.keys(gameOnly.slices as object)).toEqual(["facts"]);
    expect((gameOnly.slices as { facts: readonly string[] }).facts).toEqual([...carried]);

    // ------------------------------------------------------------ the resume
    // A second session, on the same store: this is the reload.
    const second = open();
    expect(second.open().phase).toBe("offering_continue");
    const offered = second.state.resume;
    expect(offered?.beatId).toBe("b_way_in");
    expect(offered?.statementId).toBe(stoppedStatement);
    // The `facts` slice — the only one that outlives a leaf — came back whole.
    expect(offered?.facts).toEqual(carried);
    expect(offered?.backlog).toHaveLength(backlogWhenStopped);

    second.continueSaved();
    expect(second.state.progress.beatId).toBe("b_way_in");
    expect(second.state.progress.facts).toEqual(carried);

    // The read is the family's too, and it names the version the bytes carried.
    const loaded = saves.filter((event) => event.type === "save/loaded");
    expect(loaded).toHaveLength(1);
    expect(loaded[0]!.key).toBe(caseSaveKey(EPISODE));
    expect(loaded[0]!.writtenVersion).toBe(2);
    expect(loaded[0]!.scopes).toEqual(["game", "run"]);
    expect(loaded[0]!.slices).toEqual(["facts", "scenario", "backlog"]);

    // And the leaf resumes at the same drawn moment: the saved scenario state is
    // checked against the program it claims to belong to and accepted.
    const resumed = restoreScenarioState(wayIn, offered!.scenario!);
    expect(resumed).not.toBeNull();
    expect(scenarioStatementId(resumed!.label, resumed!.index)).toBe(stoppedStatement);
    expect(scenarioView(wayIn, resumed!)).toEqual(scenarioView(wayIn, mid));

    // Continuing does not double the line the player is looking at.
    second.presented({
      kind: "presented",
      statementId: stoppedStatement,
      line: lineOf(wayIn, resumed!),
      scenario: resumed!,
      outcome: null,
    });
    expect(second.state.backlog).toHaveLength(backlogWhenStopped);

    // ------------------------------------------------------- through to the end
    let at = second.state.progress.beatId;
    let state = resumed!;
    for (let guard = 0; guard < 40 && second.state.phase === "playing"; guard += 1) {
      const beat = document.beats.find((entry) => entry.beatId === at)!;
      if (beat.kind === "room") {
        second.finish(at, "win", beat.writes);
      } else {
        const program = leaves.get(at)!;
        let playing =
          at === "b_way_in" ? state : initialScenarioState(program, second.state.progress.facts);
        for (let inner = 0; inner < 2000 && playing.outcome === null; inner += 1) {
          second.presented({
            kind: "presented",
            statementId: scenarioStatementId(playing.label, playing.index),
            line: lineOf(program, playing),
            scenario: playing,
            outcome: null,
          });
          playing = step(program, playing);
        }
        second.presented({
          kind: "presented",
          statementId: null,
          line: null,
          scenario: playing,
          outcome: playing.outcome,
        });
        second.finish(at, playing.outcome!, playing.flags);
        state = playing;
      }
      at = second.state.progress.beatId;
    }

    expect(second.state.phase).toBe("finished");
    // The episode's own ending, reached on the session that resumed rather than
    // on the one that started, and the four facts that crossed the room boundary
    // are still among the forty-nine it finished holding.
    expect(second.state.ending).toBe("left_alone");
    expect(second.state.carried).toHaveLength(49);
    for (const fact of carried) expect(second.state.carried).toContain(fact);
    // The in-progress save is gone — there is nothing left to resume — and the
    // episode's output is not.
    expect(storage.entries.has("stage_gen.case_save.the-grain-episode-one")).toBe(false);
    expect(storage.entries.has("stage_gen.case_result.the-grain-episode-one")).toBe(true);

    // Every beat this episode declares was entered, in order, once.
    const entered = heard
      .filter((event): event is Extract<CaseEvent, { type: "beat/entered" }> =>
        event.type === "beat/entered",
      )
      .map((event) => event.beatId);
    expect(entered).toEqual(document.beats.slice(1).map((beat) => beat.beatId));
    expect(heard.filter((event) => event.type === "facts/established").length).toBeGreaterThan(0);
    expect(heard.filter((event) => event.type === "case/finished")).toHaveLength(1);

    // --------------------------------- the same stop, written by the last build
    // The machine half of the step's ruling, over the episode's own bytes rather
    // than a hand-built record: take the save the run above wrote, put it back
    // into the flat shape `case_save_v1` shipped as version 1, and open on it.
    // The versioned parse runs the upgrade forward and the player comes back to
    // the same sentence with the same four facts — which is what "a save written
    // by one version is restored by the next" has to mean for a person who was
    // mid-episode when the build changed under them.
    const asV1 = {
      schema_version: 1,
      kind: midWire.kind,
      run_tag: midWire.run_tag,
      beat_id: midWire.beat_id,
      statement_id: midWire.statement_id,
      updated_at: midWire.updated_at,
      ...(midWire.slices as Record<string, unknown>),
    };
    const oldStore = memorySaveStorage({ [caseSaveKey(EPISODE)]: JSON.stringify(asV1) });
    const upgradeSaves: PersistenceEvent[] = [];
    const upgraded = new CaseSession(document, EPISODE, oldStore, {
      onPersistence: (event) => upgradeSaves.push(event),
      now: () => clock.at,
    });
    expect(upgraded.open().phase).toBe("offering_continue");
    expect(upgradeSaves.filter((event) => event.type === "save/loaded")).toHaveLength(1);
    const fromV1 = upgradeSaves.find((event) => event.type === "save/loaded")!;
    expect(fromV1.writtenVersion).toBe(1);
    expect(fromV1.slices).toEqual(["facts", "scenario", "backlog"]);
    const back = upgraded.state.resume;
    expect(back?.beatId).toBe("b_way_in");
    expect(back?.statementId).toBe(stoppedStatement);
    expect(back?.facts).toEqual(carried);
    expect(back?.backlog).toHaveLength(backlogWhenStopped);
    const fromOld = restoreScenarioState(wayIn, back!.scenario!);
    expect(fromOld).not.toBeNull();
    expect(scenarioView(wayIn, fromOld!)).toEqual(scenarioView(wayIn, mid));
  });
});

function lineOf(
  program: ScenarioProgram,
  state: ScenarioState,
): { readonly speaker: string | null; readonly text: string } | null {
  const view = scenarioView(program, state);
  return view?.kind === "line" ? { speaker: view.speakerLabel, text: view.text } : null;
}
