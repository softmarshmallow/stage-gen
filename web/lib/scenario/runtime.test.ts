import { describe, expect, test } from "bun:test";

import rawProgram from "./larkfield.fixture.json";
import { parseScenarioProgram } from "./program";
import {
  initialScenarioState,
  reduceScenario,
  scenarioActor,
  scenarioIsFinished,
  scenarioProgress,
  scenarioStatementId,
  scenarioView,
  type ScenarioState,
} from "./runtime";

const program = parseScenarioProgram(rawProgram);

function advance(state: ScenarioState, times = 1): ScenarioState {
  let next = state;
  for (let step = 0; step < times; step += 1) {
    next = reduceScenario(program, next, { kind: "advance" });
  }
  return next;
}

function choose(state: ScenarioState, option: number): ScenarioState {
  return reduceScenario(program, state, { kind: "choose", option });
}

/** Walk to the end, taking `option` at every choice, and collect what was shown. */
function playThrough(option: number): { texts: string[]; final: ScenarioState } {
  let state = initialScenarioState(program);
  const texts: string[] = [];
  for (let step = 0; step < 200 && !scenarioIsFinished(state); step += 1) {
    const view = scenarioView(program, state);
    if (view?.kind === "line") {
      texts.push(view.text);
      state = advance(state);
    } else if (view?.kind === "choice") {
      state = choose(state, option);
    } else {
      break;
    }
  }
  return { texts, final: state };
}

describe("the compiled program", () => {
  test("it validates, and the entry block is the one the author declared", () => {
    expect(program.scenarioId).toBe("last_class");
    expect(program.entry).toBe("arrival");
    expect(program.blocks.map((block) => block.label)).toEqual([
      "arrival",
      "listening",
      "asking",
      "recording",
      "ending_quiet",
      "ending_talked",
    ]);
  });

  test("it refuses a document with a key the contract does not carry", () => {
    expect(() => parseScenarioProgram({ ...rawProgram, extra: 1 })).toThrow(
      "keys must match the schema",
    );
  });

  test("it refuses a block that falls through instead of terminating", () => {
    const blocks = [
      { label: "only", statements: [{ kind: "stage", stage: "classroom_day" }] },
    ];
    expect(() => parseScenarioProgram({ ...rawProgram, blocks })).toThrow(
      "must end with a terminal statement",
    );
  });

  test("it refuses an entry that names no block", () => {
    expect(() => parseScenarioProgram({ ...rawProgram, entry: "nowhere" })).toThrow(
      "does not name a block",
    );
  });
});

describe("walking a scenario", () => {
  test("invisible statements settle before anything is drawn", () => {
    // `stage`, `audio` and `show` come before the first line in `arrival`; the
    // opening state must already have applied them rather than making the view
    // peek ahead to find out what is on screen.
    const state = initialScenarioState(program);
    expect(state.stage).toBe("classroom_day");
    expect(state.tracks).toEqual(["summer_room"]);
    const view = scenarioView(program, state);
    expect(view?.kind).toBe("line");
  });

  test("a shown actor carries the expression the line most recently set", () => {
    let state = initialScenarioState(program);
    state = advance(state); // past the narration, onto Nao's first line
    expect(scenarioActor(state, "nao")).toEqual({
      actorId: "nao",
      expression: "neutral",
      slot: "center",
    });
  });

  test("a speaker is presented by the cast's display name where one is declared", () => {
    let state = initialScenarioState(program);
    state = advance(state);
    const view = scenarioView(program, state);
    expect(view).toMatchObject({ kind: "line", speaker: "nao", speakerLabel: "nao" });
  });

  test("the first choice branches into two different blocks", () => {
    let state = initialScenarioState(program);
    state = advance(state, 2);
    const view = scenarioView(program, state);
    expect(view?.kind).toBe("choice");
    if (view?.kind !== "choice") throw new Error("expected a choice");
    expect(view.options.map((option) => option.text)).toEqual([
      "Say nothing, and listen with her.",
      "Ask what she's recording.",
    ]);
    expect(choose(state, 0).label).toBe("listening");
    expect(choose(state, 1).label).toBe("asking");
  });

  test("each choice reaches its own ending, and the flag is what decides", () => {
    const quiet = playThrough(0);
    const talked = playThrough(1);

    expect(quiet.final.outcome).toBe("listened");
    expect(quiet.final.flags).toEqual(["stayed_quiet"]);
    expect(talked.final.outcome).toBe("talked");
    expect(talked.final.flags).toEqual(["asked_about_recorder"]);

    // The two runs share the middle block and diverge only at the branch.
    expect(quiet.texts).not.toEqual(talked.texts);
    const shared = quiet.texts.filter((line) => talked.texts.includes(line));
    expect(shared.length).toBeGreaterThan(0);
  });

  test("the end card names the authored ending rather than its id", () => {
    const { final } = playThrough(0);
    expect(scenarioView(program, final)).toEqual({
      kind: "end",
      outcome: "listened",
      label: "You listened",
    });
  });

  test("advancing past the end holds, and restart returns to the entry", () => {
    const { final } = playThrough(0);
    expect(reduceScenario(program, final, { kind: "advance" })).toBe(final);
    const restarted = reduceScenario(program, final, { kind: "restart" });
    expect(restarted.label).toBe("arrival");
    expect(restarted.outcome).toBeNull();
    expect(restarted.flags).toEqual([]);
  });

  test("an action the current statement does not accept changes nothing", () => {
    const opening = initialScenarioState(program);
    // A line is not a choice, so choosing does nothing - and the identity is
    // preserved so a consumer can skip the redraw.
    expect(reduceScenario(program, opening, { kind: "choose", option: 0 })).toBe(opening);
    let atChoice = advance(opening, 2);
    expect(scenarioView(program, atChoice)?.kind).toBe("choice");
    expect(reduceScenario(program, atChoice, { kind: "advance" })).toBe(atChoice);
    expect(reduceScenario(program, atChoice, { kind: "choose", option: 9 })).toBe(atChoice);
    atChoice = choose(atChoice, 0);
    expect(atChoice.label).toBe("listening");
  });
});

describe("statement identity", () => {
  test("it names an authored position, not a route through the story", () => {
    expect(scenarioStatementId("arrival", 2)).toBe("arrival#2");
  });

  test("every presented statement is recorded once, in reading order", () => {
    const { final } = playThrough(0);
    expect(final.seen[0]).toBe("arrival#2");
    expect(new Set(final.seen).size).toBe(final.seen.length);
    // Replaying the same route adds nothing new: identity is positional.
    const replayed = playThrough(0);
    expect(replayed.final.seen).toEqual(final.seen);
  });

  test("progress counts read statements against every one the scenario authors", () => {
    const { final } = playThrough(0);
    const progress = scenarioProgress(program, final);
    expect(progress.seen).toBe(final.seen.length);
    expect(progress.total).toBeGreaterThan(progress.seen);
  });
});
