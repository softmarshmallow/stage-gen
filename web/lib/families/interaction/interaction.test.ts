import { describe, expect, test } from "bun:test";
import { selectAffordance } from "./affordance";
import { openSession, stepSession } from "./session";
import { parseInteractionBlock } from "./manifest";

// --- E4: one pick, two models that shared no line ---------------------------------------------

type Villager = Readonly<{ id: string; x: number; bound: boolean }>;
type RoomRule = Readonly<{ verb: string; hotspot: string; requires: string; fired: boolean }>;

describe("E4: the affordance pick instantiated into two models", () => {
  test("a platformer-shaped model: bound, in range, and the nearest one wins", () => {
    const villagers: readonly Villager[] = [
      { id: "far_baker", x: 300, bound: true },
      { id: "near_smith", x: 120, bound: true },
      { id: "nearest_mute", x: 105, bound: false },
      { id: "out_of_range", x: 1000, bound: true },
    ];
    const at = (playerX: number) =>
      selectAffordance<Villager>({
        candidates: villagers,
        available: (npc) => Math.abs(npc.x - playerX) < 145 && npc.bound,
        distance: (npc) => Math.abs(npc.x - playerX),
      })?.id ?? null;
    // The nearest villager is unbound, so the offer goes to the next one in.
    expect(at(100)).toBe("near_smith");
    // Nobody in range is an ordinary answer, not a failure.
    expect(at(600)).toBe(null);
  });

  test("two villagers at the same distance: the earlier one, which is what a stable sort gave", () => {
    const pair: readonly Villager[] = [
      { id: "left", x: 90, bound: true },
      { id: "right", x: 110, bound: true },
    ];
    expect(
      selectAffordance<Villager>({
        candidates: pair,
        available: () => true,
        distance: (npc) => Math.abs(npc.x - 100),
      })?.id,
    ).toBe("left");
  });

  test("a room-shaped model: no space at all, and the first the author wrote wins", () => {
    // The authored order is a priority — a special case before a general one —
    // so this is a real second shape rather than a degenerate proximity.
    const rules: readonly RoomRule[] = [
      { verb: "use", hotspot: "door", requires: "key_found", fired: false },
      { verb: "use", hotspot: "door", requires: "", fired: false },
    ];
    const pick = (flags: readonly string[]) =>
      selectAffordance<RoomRule>({
        candidates: rules,
        available: (rule) =>
          rule.verb === "use" &&
          rule.hotspot === "door" &&
          !rule.fired &&
          (rule.requires === "" || flags.includes(rule.requires)),
      });
    expect(pick(["key_found"])?.requires).toBe("key_found");
    expect(pick([])?.requires).toBe("");
  });
});

// --- the session --------------------------------------------------------------------------------

type Program = readonly string[];
type State = Readonly<{ index: number; outcome: string | null }>;

const reduce = (program: Program, state: State, action: "advance" | "quit"): State => {
  if (action === "quit") return { index: program.length, outcome: "left" };
  if (state.index >= program.length) return state;
  const index = state.index + 1;
  return { index, outcome: index >= program.length ? "told" : null };
};
const finished = (state: State) => state.outcome !== null;

describe("the interaction session", () => {
  test("a running playback advances and reports nothing", () => {
    const session = openSession("baker_greeting", ["hello", "goodbye"], {
      index: 0,
      outcome: null,
    });
    const step = stepSession({ session, action: "advance", reduce, finished, outcome: (s) => s.outcome });
    expect(step.kind).toBe("running");
    expect(step.session.state).toEqual({ index: 1, outcome: null });
    // The session is a value: the one it was handed is untouched.
    expect(session.state).toEqual({ index: 0, outcome: null });
  });

  test("the ending is reported once, against the interaction the playback belongs to", () => {
    const session = openSession("baker_greeting", ["hello"], { index: 0, outcome: null });
    const step = stepSession({ session, action: "advance", reduce, finished, outcome: (s) => s.outcome });
    expect(step).toMatchObject({
      kind: "finished",
      interactionId: "baker_greeting",
      outcome: "told",
    });
  });

  test("an action the conversation does not answer is unchanged, not an advance", () => {
    // Which is what stops the panel flickering on every key a player presses.
    const ended = openSession("baker_greeting", ["hello"], { index: 1, outcome: null });
    const step = stepSession({ session: ended, action: "advance", reduce, finished, outcome: (s) => s.outcome });
    expect(step.kind).toBe("unchanged");
    expect(step.session).toBe(ended);
  });

  test("a visual-novel-shaped session with no affordance in front of it", () => {
    // Written here with nothing placed in a world, the way the intent family's
    // held axis was: a scenario opened by a beat rather than by walking up to
    // someone still has the same three answers.
    let session = openSession<Program, State>("case_beat_3", ["a", "b", "c"], {
      index: 0,
      outcome: null,
    });
    const kinds: string[] = [];
    for (let turn = 0; turn < 5; turn += 1) {
      const step = stepSession({ session, action: "advance", reduce, finished, outcome: (s) => s.outcome });
      kinds.push(step.kind);
      session = step.session;
    }
    expect(kinds).toEqual(["running", "running", "finished", "unchanged", "unchanged"]);
  });

  test("and a playback abandoned mid-way reports the ending it actually reached", () => {
    const session = openSession("case_beat_3", ["a", "b", "c"], { index: 1, outcome: null });
    expect(
      stepSession({ session, action: "quit", reduce, finished, outcome: (s) => s.outcome }),
    ).toMatchObject({ kind: "finished", outcome: "left" });
  });
});

// --- the block, and the refusal ---------------------------------------------------------------

describe("the block the family gates for itself", () => {
  test("a moved binding table is refused by name", () => {
    expect(() =>
      parseInteractionBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
