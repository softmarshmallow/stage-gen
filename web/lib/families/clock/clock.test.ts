import { describe, expect, test } from "bun:test";
import { sealSystems, type FixedStep, type GameSystem } from "@/lib/kernel/systems";
import { createClock, createClockSystem, CLOCK_SYSTEM_ID, type ClockState } from "./clock";
import { parseClockBlock } from "./manifest";

const step = (frame: number, dt = 1 / 60): FixedStep => ({ dt, now: dt * frame, frame });

// --- E4: one family file, two worlds that share no field but the clock -------------------

/** A world shaped like the runner's: a moment holds it, and nothing else can. */
interface MomentWorld {
  clock: ClockState;
  fx: { released: boolean } | null;
  distance: number;
}

/** A world shaped like the platformer's: two holders, one of them a feedback read. */
interface HoldWorld {
  clock: ClockState;
  hold: boolean;
  hitstopUntilMs: number;
}

describe("E4: the clock family instantiated into two different worlds", () => {
  test("a runner-shaped world: a moment stops the simulation and its integral", () => {
    const world: MomentWorld = { clock: createClock(), fx: null, distance: 0 };
    const clock = createClockSystem<MomentWorld>({
      slice: "clock",
      holders: [{ name: "moment", held: (w) => w.fx !== null && !w.fx.released }],
    });
    const integrate: GameSystem<MomentWorld, never> = {
      id: "avatar/step",
      contractVersion: "avatar-v1",
      reads: ["clock"],
      writes: ["distance"],
      update: (w) => {
        w.distance += 10 * w.clock.simulationDt;
      },
    };
    const sealed = sealSystems<MomentWorld>([integrate, clock]);
    // Declaration order, not registration order: the clock is registered last.
    expect(sealed.order).toEqual([CLOCK_SYSTEM_ID, "avatar/step"]);

    sealed.tick(world, step(1));
    expect(world.clock.simulationNow).toBeCloseTo(1 / 60, 12);
    expect(world.distance).toBeCloseTo(10 / 60, 12);

    world.fx = { released: false };
    for (let frame = 2; frame <= 61; frame += 1) sealed.tick(world, step(frame));
    // A held second: the frame clock advanced, the simulation did not.
    expect(step(61).now).toBeCloseTo(61 / 60, 12);
    expect(world.clock.held).toBe(true);
    expect(world.clock.heldBy).toBe("moment");
    expect(world.clock.simulationNow).toBeCloseTo(1 / 60, 12);
    expect(world.distance).toBeCloseTo(10 / 60, 12);

    world.fx.released = true;
    sealed.tick(world, step(62));
    expect(world.clock.held).toBe(false);
    expect(world.clock.heldBy).toBe(null);
    expect(world.clock.simulationNow).toBeCloseTo(2 / 60, 12);
  });

  test("a platformer-shaped world: two holders, and the first one in force is named", () => {
    const world: HoldWorld = { clock: createClock(), hold: false, hitstopUntilMs: 0 };
    const clock = createClockSystem<HoldWorld>({
      slice: "clock",
      reads: ["hold"],
      holders: [
        { name: "dialogue", held: (w) => w.hold },
        // Asked against the frame clock, the way a deadline armed from it must be.
        { name: "hitstop", held: (w, s) => s.now < w.hitstopUntilMs },
      ],
    });
    const sealed = sealSystems<HoldWorld>([clock]);

    sealed.tick(world, step(1, 1000 / 30));
    expect(world.clock.simulationDt).toBeCloseTo(1000 / 30, 9);

    world.hitstopUntilMs = 500;
    sealed.tick(world, step(2, 1000 / 30));
    expect(world.clock.heldBy).toBe("hitstop");
    expect(world.clock.simulationDt).toBe(0);

    // Both at once: the list decides which name the frame is reported under.
    world.hold = true;
    sealed.tick(world, step(3, 1000 / 30));
    expect(world.clock.heldBy).toBe("dialogue");

    world.hold = false;
    world.hitstopUntilMs = 0;
    sealed.tick(world, step(4, 1000 / 30));
    expect(world.clock.held).toBe(false);
    // Two of the four frames were held, so the integral is two deltas.
    expect(world.clock.simulationNow).toBeCloseTo((2 * 1000) / 30, 9);
  });
});

describe("what the clock owns, and what a reset means", () => {
  test("a second author of the delta is refused at seal", () => {
    const clock = createClockSystem<HoldWorld>({ slice: "clock", holders: [] });
    const hitstop: GameSystem<HoldWorld, never> = {
      id: "impact/hitstop",
      contractVersion: "impact-v1",
      reads: [],
      writes: ["clock"],
      update: () => undefined,
    };
    expect(() => sealSystems<HoldWorld>([clock, hitstop])).toThrow(
      'it writes "clock", which "clock/step" owns',
    );
  });

  test("a run keeps the integral; a session starts it again", () => {
    const world: HoldWorld = { clock: createClock(), hold: false, hitstopUntilMs: 0 };
    const sealed = sealSystems<HoldWorld>([
      createClockSystem<HoldWorld>({ slice: "clock", holders: [] }),
    ]);
    for (let frame = 1; frame <= 30; frame += 1) sealed.tick(world, step(frame));
    const elapsed = world.clock.simulationNow;
    expect(elapsed).toBeGreaterThan(0);
    sealed.reset(world, "run");
    expect(world.clock.simulationNow).toBe(elapsed);
    expect(world.clock.simulationDt).toBe(0);
    sealed.reset(world, "session");
    expect(world.clock.simulationNow).toBe(0);
  });
});

describe("the block the family gates for itself", () => {
  const blocks = Object.freeze({ fx: "fx-block-v1", gameplay: "platformer-gameplay-block-v1" });

  test("a moved block is refused by name, by the family and not by the genre parser", () => {
    expect(() =>
      parseClockBlock(
        { ...blocks, fx: "fx-block-v2" },
        { block: "fx", version: "fx-block-v1", optional: true },
      ),
    ).toThrow('manifest block "fx" is published as fx-block-v2; this build reads fx-block-v1');
  });

  test("an optional block a package never published leaves the genre with no holder", () => {
    const view = parseClockBlock({ gameplay: "platformer-gameplay-block-v1" }, {
      block: "fx",
      version: "fx-block-v1",
      optional: true,
    });
    expect(view).toEqual({ block: "fx", version: null, published: false });
  });

  test("a required block that is absent is refused by name", () => {
    expect(() =>
      parseClockBlock({}, { block: "gameplay", version: "platformer-gameplay-block-v1" }),
    ).toThrow('manifest block "gameplay" is not published');
  });

  test("the published version is reported back", () => {
    expect(parseClockBlock(blocks, { block: "fx", version: "fx-block-v1", optional: true })).toEqual(
      { block: "fx", version: "fx-block-v1", published: true },
    );
  });
});
