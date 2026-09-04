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
import { memorySaveStorage } from "@/lib/families/persistence";
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
    const clock = { at: new Date("2026-09-05T09:00:00.000Z") };

    const open = () =>
      new CaseSession(document, EPISODE, storage, {
        onEvent: (event) => heard.push(event),
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
    expect(carried.length).toBeGreaterThan(0);
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
    const backlogWhenStopped = stoppedAt.backlog.length;
    expect(backlogWhenStopped).toBeGreaterThan(6);

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
    expect(second.state.ending).not.toBeNull();
    expect(second.state.carried.length).toBeGreaterThan(carried.length);
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
  });
});

function lineOf(
  program: ScenarioProgram,
  state: ScenarioState,
): { readonly speaker: string | null; readonly text: string } | null {
  const view = scenarioView(program, state);
  return view?.kind === "line" ? { speaker: view.speakerLabel, text: view.text } : null;
}
