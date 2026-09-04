import { describe, expect, test } from "bun:test";
import { sealSystems } from "@/lib/kernel/systems";
import {
  createIntentLatch,
  createIntentSystem,
  defineIntent,
  intentFrom,
  IntentShapeError,
} from "./intent";
import { parseIntentBlock } from "./manifest";

const step = { dt: 1 / 60, now: 1 / 60, frame: 1 } as const;

// --- E4: one latch, two records whose keys mean different things ----------------------------

/** A runner-shaped record: two edges, two levels. */
type RunIntent = Readonly<{ jump: boolean; action: boolean; duck: boolean; thrust: boolean }>;
const RUN_SHAPE = defineIntent<RunIntent>(
  { jump: false, action: false, duck: false, thrust: false },
  ["jump", "action"],
  ["duck", "thrust"],
);

/**
 * A jumper-shaped record: the held axis the runner's consume-on-sample would
 * corrupt, plus a level that is not a boolean.
 */
type JumperIntent = Readonly<{ climb: number; face: "left" | "right" | null; hop: boolean }>;
const JUMPER_SHAPE = defineIntent<JumperIntent>(
  { climb: 0, face: null, hop: false },
  ["hop"],
  ["climb", "face"],
);

describe("E4: one latch, two intent records", () => {
  test("a runner-shaped record: edges are spent by the sample, levels are not", () => {
    const latch = createIntentLatch(RUN_SHAPE);
    latch.request("jump");
    latch.set("duck", true);
    expect(latch.sample()).toEqual({ jump: true, action: false, duck: true, thrust: false });
    // The edge was spent; the level was not.
    expect(latch.sample()).toEqual({ jump: false, action: false, duck: true, thrust: false });
  });

  test("a jumper-shaped record: a held axis sampled twice reads twice", () => {
    // The whole reason edge-vs-level is a parameter. Under the runner's own
    // consume-on-sample rule a held climb would read as one frame of climbing
    // and then nothing at all, which is not a defect in a jumper — it is the
    // runner's edge rule applied to a key that is not an edge.
    const latch = createIntentLatch(JUMPER_SHAPE);
    latch.set("climb", 1);
    latch.set("face", "left");
    latch.request("hop");
    expect(latch.sample()).toEqual({ climb: 1, face: "left", hop: true });
    expect(latch.sample()).toEqual({ climb: 1, face: "left", hop: false });
    expect(latch.sample()).toEqual({ climb: 1, face: "left", hop: false });
    latch.set("climb", 0);
    expect(latch.sample()).toEqual({ climb: 0, face: "left", hop: false });
  });
});

describe("the shape is checked against the record", () => {
  test("a key classified twice is refused where it is declared", () => {
    expect(() =>
      defineIntent<RunIntent>(
        { jump: false, action: false, duck: false, thrust: false },
        ["jump", "duck"],
        ["duck", "thrust"],
      ),
    ).toThrow(IntentShapeError);
  });

  test("a key classified not at all is refused too", () => {
    const seal = () =>
      defineIntent<RunIntent>(
        { jump: false, action: false, duck: false, thrust: false },
        ["jump"],
        ["duck", "thrust"],
      );
    expect(seal).toThrow(IntentShapeError);
    expect(seal).toThrow('intent key "action" is declared as neither an edge nor a level');
  });

  test("a declared key the record does not carry is refused", () => {
    expect(() =>
      defineIntent<RunIntent>(
        { jump: false, action: false, duck: false, thrust: false },
        ["jump", "action", "sprint" as keyof RunIntent & string],
        ["duck", "thrust"],
      ),
    ).toThrow('intent declares "sprint", which the record does not carry');
  });

  test("requesting a level, or setting an edge, is refused at the call", () => {
    const latch = createIntentLatch(RUN_SHAPE);
    expect(() => latch.request("duck")).toThrow('"duck" is a level');
    expect(() => latch.set("jump", true)).toThrow('"jump" is an edge');
  });

  test("an unstated field defaults to not-asked-for and the record is frozen", () => {
    const built = intentFrom(JUMPER_SHAPE, { climb: 1 });
    expect(built).toEqual({ climb: 1, face: null, hop: false });
    expect(Object.isFrozen(built)).toBe(true);
  });
});

describe("the intent system, and what a hold does to it", () => {
  interface World {
    intent: RunIntent;
    clock: { held: boolean };
  }

  test("under a hold the edges are spent and reported unasked; the levels are not", () => {
    const latch = createIntentLatch(RUN_SHAPE);
    const world: World = { intent: RUN_SHAPE.neutral, clock: { held: false } };
    const sealed = sealSystems<World>([
      createIntentSystem<World, RunIntent>({
        slice: "intent",
        latch,
        reads: ["clock"],
        held: (w) => w.clock.held,
      }),
    ]);

    latch.request("jump");
    latch.set("duck", true);
    world.clock.held = true;
    sealed.tick(world, step);
    // Spent, not queued: a latch that kept its edges through a cut-in would
    // fire every one of them the instant the overlay let go.
    expect(world.intent).toEqual({ jump: false, action: false, duck: true, thrust: false });

    world.clock.held = false;
    sealed.tick(world, step);
    expect(world.intent).toEqual({ jump: false, action: false, duck: true, thrust: false });
  });

  test("a reset forgets everything asked for", () => {
    const latch = createIntentLatch(RUN_SHAPE);
    const world: World = { intent: RUN_SHAPE.neutral, clock: { held: false } };
    const sealed = sealSystems<World>([
      createIntentSystem<World, RunIntent>({ slice: "intent", latch, reads: ["clock"] }),
    ]);
    latch.set("duck", true);
    latch.request("jump");
    sealed.reset(world, "run");
    sealed.tick(world, step);
    expect(world.intent).toEqual(RUN_SHAPE.neutral);
  });
});

describe("the block the family gates for itself", () => {
  test("a moved block is refused by name", () => {
    expect(() =>
      parseIntentBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
