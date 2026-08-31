import { describe, expect, test } from "bun:test";

import { ferryProgramDocument } from "./program.fixture";
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

const program = parseScenarioProgram(ferryProgramDocument());

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

/**
 * Walk to the end, picking one option index at every choice (clamped to the
 * last offered), and collect what was shown. Index 0 is the committed route;
 * a large index refuses at every turn.
 */
function playThrough(option: number): { texts: string[]; final: ScenarioState } {
  let state = initialScenarioState(program);
  const texts: string[] = [];
  for (let step = 0; step < 200 && !scenarioIsFinished(state); step += 1) {
    const view = scenarioView(program, state);
    if (view?.kind === "line") {
      texts.push(view.text);
      state = advance(state);
    } else if (view?.kind === "choice") {
      state = choose(state, Math.min(option, view.options.length - 1));
    } else {
      break;
    }
  }
  return { texts, final: state };
}

describe("the compiled program", () => {
  test("it validates, and the entry block is the one the author declared", () => {
    expect(program.scenarioId).toBe("ferry_bell");
    expect(program.entry).toBe("opening");
    expect(program.blocks.map((block) => block.label)).toContain("opening");
    expect(program.blocks.length).toBe(11);
    expect(program.endings.map((ending) => ending.outcomeId)).toEqual([
      "crossed",
      "stayed",
      "stranded",
    ]);
  });

  test("it refuses a document with a key the contract does not carry", () => {
    expect(() => parseScenarioProgram({ ...ferryProgramDocument(), extra: 1 })).toThrow(
      "keys must match the schema",
    );
  });

  test("it refuses a block that falls through instead of terminating", () => {
    const blocks = [{ label: "only", statements: [{ kind: "stage", stage: "pier_dusk" }] }];
    expect(() => parseScenarioProgram({ ...ferryProgramDocument(), blocks })).toThrow(
      "must end with a terminal statement",
    );
  });

  test("it refuses an entry that names no block", () => {
    expect(() => parseScenarioProgram({ ...ferryProgramDocument(), entry: "nowhere" })).toThrow(
      "does not name a block",
    );
  });
});

describe("walking a scenario", () => {
  test("invisible statements settle before anything is drawn", () => {
    // `stage` and `audio` come before the first line in `opening`; the opening
    // state must already have applied them rather than making the view peek
    // ahead to find out what is on screen.
    const state = initialScenarioState(program);
    expect(state.stage).toBe("pier_dusk");
    expect(state.tracks).toEqual(["harbor_wind"]);
    const view = scenarioView(program, state);
    expect(view?.kind).toBe("line");
  });

  test("a shown actor wears the expression its staging named", () => {
    let state = initialScenarioState(program);
    state = advance(state); // past the narration, onto Mara's first line
    expect(scenarioActor(state, "mara")).toEqual({
      actorId: "mara",
      expression: "neutral",
      slot: "center",
    });
  });

  test("a line that names an expression re-dresses its staged speaker", () => {
    // `mara delighted "..."` changes what Mara's plate shows for as long as
    // the line and everything after it, without a `show` re-staging her.
    let state = initialScenarioState(program);
    state = choose(advance(state, 2), 0); // ring the bell
    expect(scenarioView(program, state)).toMatchObject({ kind: "line" });
    expect(scenarioActor(state, "mara")?.expression).toBe("delighted");
    // The re-staging at the boathouse door names no expression, so she keeps it.
    state = advance(state);
    expect(scenarioActor(state, "mara")).toEqual({
      actorId: "mara",
      expression: "delighted",
      slot: "left",
    });
  });

  test("a line spoken from off stage re-dresses nobody", () => {
    // The refusing route hides Mara on the hill, and her parting line is
    // spoken unstaged: expressions ride on lines, staging stays `show`'s job.
    const { final } = playThrough(9);
    expect(final.outcome).toBe("stranded");
    expect(scenarioActor(final, "mara")).toBeNull();
  });

  test("a speaker is presented by the cast's display name where one is declared", () => {
    let state = initialScenarioState(program);
    state = advance(state);
    const view = scenarioView(program, state);
    expect(view).toMatchObject({ kind: "line", speaker: "mara", speakerLabel: "Mara" });
  });

  test("the first choice branches into two different blocks", () => {
    let state = initialScenarioState(program);
    state = advance(state, 2);
    const view = scenarioView(program, state);
    expect(view?.kind).toBe("choice");
    if (view?.kind !== "choice") throw new Error("expected a choice");
    expect(view.options.map((option) => option.text)).toEqual([
      "Ring the bell.",
      "Ask what the crossing costs.",
    ]);
    expect(choose(state, 0).label).toBe("ringing");
    expect(choose(state, 1).label).toBe("asking");
  });

  test("each route reaches its own ending, and the flags are what decide", () => {
    // Committing at every turn earns both flags; refusing at every turn earns
    // neither and the branch falls through to its default.
    const forward = playThrough(0);
    const refusing = playThrough(9);

    expect(forward.final.outcome).toBe("crossed");
    expect(forward.final.flags).toEqual(["has_token", "rang_the_bell"]);
    expect(refusing.final.outcome).toBe("stranded");
    expect(refusing.final.flags).toEqual(["asked_the_fare"]);

    // The two runs share the opening and diverge at the first choice.
    expect(forward.texts).not.toEqual(refusing.texts);
    const shared = forward.texts.filter((line) => refusing.texts.includes(line));
    expect(shared.length).toBeGreaterThan(0);
  });

  test("a branch takes the first satisfied edge even when a later one also holds", () => {
    // The committed route sets both `has_token` and `rang_the_bell`; both
    // departure edges hold, and the first one wins - the same ordered dispatch
    // the Python admission proof searched.
    const forward = playThrough(0);
    expect(forward.final.outcome).toBe("crossed");
    // Ring the bell but keep the coin: the first edge fails, the second fires.
    let state = choose(advance(initialScenarioState(program), 2), 0);
    state = choose(advance(state, 2), 1); // wait by the door
    while (!scenarioIsFinished(state)) state = advance(state);
    expect(state.outcome).toBe("stayed");
    expect(scenarioActor(state, "teo")?.expression).toBe("delighted");
  });

  test("a conditional option is hidden until its flag is set", () => {
    // Trading for a token is gated on having rung the bell, so the refusing
    // route is never offered it.
    let state = initialScenarioState(program);
    const seen: number[] = [];
    for (let step = 0; step < 60 && !scenarioIsFinished(state); step += 1) {
      const view = scenarioView(program, state);
      if (view?.kind === "choice") {
        seen.push(view.options.length);
        state = choose(state, view.options.length - 1);
      } else if (view?.kind === "line") {
        state = advance(state);
      } else break;
    }
    // The three-option menu at the booth is offered as two when the flag is clear.
    expect(seen).toContain(2);
    expect(seen).not.toContain(3);
  });

  test("the end card names the authored ending rather than its id", () => {
    const { final } = playThrough(0);
    expect(scenarioView(program, final)).toEqual({
      kind: "end",
      outcome: "crossed",
      label: "You crossed at dusk",
    });
  });

  test("advancing past the end holds, and restart returns to the entry", () => {
    const { final } = playThrough(0);
    expect(reduceScenario(program, final, { kind: "advance" })).toBe(final);
    const restarted = reduceScenario(program, final, { kind: "restart" });
    expect(restarted.label).toBe("opening");
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
    expect(atChoice.label).toBe("ringing");
  });
});

describe("statement identity", () => {
  test("it names an authored position, not a route through the story", () => {
    expect(scenarioStatementId("opening", 2)).toBe("opening#2");
  });

  test("every presented statement is recorded once, in reading order", () => {
    const { final } = playThrough(0);
    expect(final.seen[0]).toBe("opening#2");
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
