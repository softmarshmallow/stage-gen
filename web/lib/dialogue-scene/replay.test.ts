import { describe, expect, test } from "bun:test";

// E1 for the dialogue scene: one program, one scripted action track, one hash
// per step, and the events each step raised.
//
// Same instrument as the runner's and the platformer's goldens, with the same
// difference the room's has: a visual novel has no clock, so the "step" is the
// action — advance, choose, restart — and the script is a list of them.
//
// Everything a consumer of this genre draws is settled by the invisible
// statements the reducer walks BEFORE the line it stops on: the backdrop, who is
// on stage, in which slot, wearing what, and which track is playing. Until this
// step none of that was reported, so the only thing a refactor could compare was
// where the walk ended. The events are what make the walk itself measurable, and
// the digest chain is what makes it one assertion.
//
// `REPLAY_FRAMES` writes one unchained digest per step; `REPLAY_DUMP` writes the
// state and the events.

import { parseScenarioProgram } from "@/lib/scenario/program";
import { ferryProgramDocument } from "@/lib/scenario/program.fixture";
import {
  initialScenarioTurn,
  reduceScenarioTurn,
  scenarioView,
  type ScenarioAction,
  type ScenarioState,
} from "@/lib/scenario/runtime";

/**
 * The scripted run: the ferry, taken twice.
 *
 * Both branches of the opening choice and both of the boathouse door, a restart
 * in the middle, and two actions the reducer must refuse — a `choose` where a
 * line is on screen, and an `advance` past the ending card. A golden that only
 * walked forward would never hash a refusal, and a refusal that silently became
 * a transition is exactly the regression this file exists to catch.
 */
const SCRIPT: readonly ScenarioAction[] = [
  // Run one: ring the bell, take the token, cross.
  { kind: "advance" },
  { kind: "choose", option: 0 },
  { kind: "advance" },
  { kind: "choose", option: 0 },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "choose", option: 0 },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  // Run two, from the top: ask the fare, wait by the door, and find out what
  // the branch does when neither flag holds.
  { kind: "restart" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "choose", option: 1 },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "choose", option: 1 },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
  { kind: "advance" },
];

function plain(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(plain);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = plain((value as Record<string, unknown>)[key]);
    }
    return out;
  }
  return value;
}

function digest(state: ScenarioState, events: readonly unknown[], view: unknown): string {
  const hasher = new Bun.CryptoHasher("sha256");
  // The view is hashed as well as the state: what is drawn is a pure function of
  // the state, and a change that moved one without the other would be a change
  // in this genre's whole contract with its consumers.
  hasher.update(JSON.stringify({ state: plain(state), events: plain(events), view: plain(view) }));
  return hasher.digest("hex");
}

describe("the dialogue scene replays to its golden", () => {
  test("twenty-five scripted actions hash to the pinned chain", async () => {
    const program = parseScenarioProgram(ferryProgramDocument());
    const opening = initialScenarioTurn(program);
    let state = opening.state;
    let chain = digest(state, opening.events, scenarioView(program, state));
    const steps: string[] = [`opening ${chain}`];
    const dumps: string[] = [];

    for (const [index, action] of SCRIPT.entries()) {
      const turn = reduceScenarioTurn(program, state, action);
      state = turn.state;
      const view = scenarioView(program, state);
      const step = digest(state, turn.events, view);
      steps.push(`${index} ${step}`);
      if (process.env.REPLAY_DUMP) {
        dumps.push(JSON.stringify({ step: index, action, state, events: turn.events, view }));
      }
      const hasher = new Bun.CryptoHasher("sha256");
      hasher.update(`${chain}${step}`);
      chain = hasher.digest("hex");
    }

    if (process.env.REPLAY_FRAMES) {
      await Bun.write(process.env.REPLAY_FRAMES, `${steps.join("\n")}\n`);
    }
    if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);

    // Pinned at the step it was baked. A refactor that must preserve behaviour
    // shows this exact chain; one that intends a change shows a diff at the
    // documented step and nowhere else, and re-pins with a sentence saying why.
    expect(chain).toBe("68aec044ca05c39d7531062072579e0ea7ff89f54c1eec6b665274446c8b67d2");
    // Both endings the two runs reach, and the two the branch could have taken
    // instead: `crossed` at step 9 with the token, `stranded` at step 22 with
    // neither flag, through the branch's default.
    expect(state.outcome).toBe("stranded");
  });

  test("the settle reports every invisible statement it walked", () => {
    const program = parseScenarioProgram(ferryProgramDocument());
    const opening = initialScenarioTurn(program);
    // The backdrop, the track and the first line, in authored order — the three
    // facts a resumed scene needs and a state alone cannot say happened.
    expect(opening.events).toEqual([
      { type: "scenario/staged", stage: "pier_dusk" },
      { type: "scenario/audio-changed", track: "harbor_wind", action: "play" },
      { type: "scenario/presented", statementId: "opening#2", kind: "line" },
    ]);
  });

  test("an action the moment does not take moves nothing and says nothing", () => {
    const program = parseScenarioProgram(ferryProgramDocument());
    const opening = initialScenarioTurn(program).state;
    const refused = reduceScenarioTurn(program, opening, { kind: "choose", option: 0 });
    expect(refused.state).toBe(opening);
    expect(refused.events).toEqual([]);
  });
});
