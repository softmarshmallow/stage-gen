// The case runtime's replay golden: one scripted episode, a digest per action.
//
// The room and the dialogue scene each have one of these and the case did not,
// which left the layer *above* the leaves — the beat order, the facts that cross
// between them, the save it writes and the Continue it offers — with unit tests
// and no per-step reference. A port has nothing to be measured against without
// one, and this is the shape the other two already committed:
//
//   `REPLAY_FRAMES` writes one unchained digest per action, so "which action
//   moved" is a diff rather than a claim; `REPLAY_DUMP` writes the state and the
//   events beside it, so "and why" is a field diff.
//
// The demo document rather than a published episode, deliberately: `out/` is not
// in the repository, and a golden that needed it would be a golden a clone
// cannot reproduce. `episode.test.ts` is the one that plays the published run,
// and it stays where it is.

import { describe, expect, test } from "bun:test";
import {
  DEMO_CASE_TAG,
  demoCaseDocument,
  demoCloseFixture,
  demoSupperFixture,
} from "./case.fixture";
import { initialCaseRuntime, reduceCase, type CaseAction } from "./runtime";
import {
  initialScenarioState,
  reduceScenario,
  scenarioStatementId,
  scenarioView,
  type ScenarioState,
} from "@/lib/scenario/runtime";
import type { ScenarioProgram } from "@/lib/scenario/program";

/** A fixed instant, so the save this episode writes is the same bytes every run. */
const AT = new Date("2026-09-08T04:00:00.000Z");

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

function digest(state: unknown, events: readonly unknown[]): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(JSON.stringify({ state: plain(state), events: plain(events) }));
  return hasher.digest("hex");
}

describe("the case runtime replays to its golden", () => {
  test("a scripted episode hashes to a stable chain", async () => {
    const document = demoCaseDocument();
    let state = initialCaseRuntime(document);
    const steps: string[] = [`opening ${digest(state, [])}`];
    const dumps: string[] = [];
    let index = 0;

    const push = (action: CaseAction): void => {
      const turn = reduceCase(document, DEMO_CASE_TAG, state, action, AT);
      state = turn.state;
      steps.push(`${index} ${digest(state, turn.events)}`);
      dumps.push(
        JSON.stringify({
          step: index,
          action: plain(action),
          state: plain(state),
          events: plain(turn.events),
        }),
      );
      index += 1;
    };

    /**
     * Play one leaf to its outcome, telling the case what it presents.
     *
     * The leaves are played for real rather than stubbed, because the hand-off
     * is the thing under test: the case builds its save out of the scenario
     * state it is handed, so a stub would measure nothing. A choice is answered
     * with its first option — this golden is about the layer above the leaf, so
     * the route only has to be one a player could take and the same one every
     * run.
     */
    const playLeaf = (program: ScenarioProgram, facts: readonly string[]): ScenarioState => {
      let scenario = initialScenarioState(program, facts);
      for (let guard = 0; guard < 200; guard += 1) {
        const view = scenarioView(program, scenario);
        push({
          kind: "presented",
          statementId:
            scenario.outcome === null
              ? scenarioStatementId(scenario.label, scenario.index)
              : null,
          line:
            view !== null && view.kind === "line"
              ? { speaker: view.speakerLabel, text: view.text }
              : null,
          scenario,
          outcome: scenario.outcome,
        });
        if (scenario.outcome !== null) return scenario;
        scenario = reduceScenario(
          program,
          scenario,
          view !== null && view.kind === "choice"
            ? { kind: "choose", option: 0 }
            : { kind: "advance" },
        );
      }
      return scenario;
    };

    push({ kind: "opened", saved: null });
    const supper = playLeaf(demoSupperFixture().scenario, state.progress.facts);
    push({
      kind: "finish",
      beatId: "demo_supper",
      outcome: supper.outcome ?? "",
      flags: supper.flags,
    });
    // The room beat is finished by its declared writes: the room's own reducer
    // has its own golden, and what the case does with the flags it is handed is
    // what this one measures.
    push({
      kind: "finish",
      beatId: "demo_room",
      outcome: "win",
      flags: ["saw_the_card", "asked_about_the_bell", "left_the_room"],
    });
    const close = playLeaf(demoCloseFixture().scenario, state.progress.facts);
    push({
      kind: "finish",
      beatId: "demo_close",
      outcome: close.outcome ?? "",
      flags: close.flags,
    });

    if (process.env.REPLAY_FRAMES) {
      await Bun.write(process.env.REPLAY_FRAMES, `${steps.join("\n")}\n`);
    }
    if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);

    expect(state.phase).toBe("finished");
    expect([...state.carried].sort()).toContain("saw_the_card");
    expect(steps.length).toBeGreaterThan(6);
  });
});
