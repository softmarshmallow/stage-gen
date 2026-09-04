import { describe, expect, test } from "bun:test";
import { sealSystems } from "@/lib/kernel/systems";
import { createEventQueue } from "@/lib/kernel/events";
import { beginFxMoment, createFxSystem, FX_MOMENT_SYSTEM_ID, type FxEvent, type FxState } from "./moment-system";
import { HIDDEN_FX_VIEW } from "./view";
import { KILL_SHAKE_PROFILE, NO_SHAKE, sampleShake, sumShake, type ShakeProfile } from "./shake";
import { parseScreenFxBlock } from "./manifest";

const step = (frame: number) => ({ dt: 1 / 60, now: frame / 60, frame });

// --- E4: one family, two worlds -------------------------------------------------------------

/** A runner-shaped world: a moment over a run. */
interface RunWorld {
  fx: FxState | null;
  run: { phase: string };
  events: ReturnType<typeof createEventQueue<FxEvent>>;
}

/** A stage-shaped world: a moment over a map, with a different neighbour slice. */
interface StageWorld {
  fx: FxState | null;
  map: { id: string };
  events: ReturnType<typeof createEventQueue<FxEvent>>;
}

describe("E4: the moment system instantiated into two different worlds", () => {
  test("a runner-shaped world: the moment holds, releases, and finishes", () => {
    const world: RunWorld = {
      fx: null,
      run: { phase: "intro" },
      events: createEventQueue<FxEvent>(),
    };
    const sealed = sealSystems<RunWorld>([createFxSystem<RunWorld>(HIDDEN_FX_VIEW)], {
      events: (w) => w.events,
    });
    expect(sealed.order).toEqual([FX_MOMENT_SYSTEM_ID]);
    beginFxMoment(world, "stage_start", "tear_reveal_v1");
    let released = 0;
    let finished = 0;
    for (let frame = 1; frame <= 200; frame += 1) {
      sealed.tick(world, step(frame));
      released += world.events.ofType("fx-released").length;
      finished += world.events.ofType("fx-finished").length;
    }
    expect(released).toBe(1);
    expect(finished).toBe(1);
    expect(world.fx).toBe(null);
  });

  test("a stage-shaped world: the same system, a world with nothing in common", () => {
    const world: StageWorld = {
      fx: null,
      map: { id: "crowncrag_road" },
      events: createEventQueue<FxEvent>(),
    };
    const sealed = sealSystems<StageWorld>([createFxSystem<StageWorld>(HIDDEN_FX_VIEW)], {
      events: (w) => w.events,
    });
    // A director asks and the system owns the slice: the request is a deferred
    // consume, heard on the frame after the one it was emitted in, because a
    // director is sealed after this system and could not be heard sooner. The
    // tick that hears it is the one whose `beginFrame` rotated that queue.
    sealed.tick(world, step(1));
    expect(world.fx).toBe(null);
    world.events.emit({ type: "fx-requested", moment: "map_enter", choreography: "tear_reveal_v1" });
    sealed.tick(world, step(2));
    expect(world.fx?.moment).toBe("map_enter");
    // And a moment already in flight is never clobbered by a later ask.
    world.events.emit({ type: "fx-requested", moment: "fever_start", choreography: "tear_reveal_v1" });
    sealed.tick(world, step(3));
    expect(world.fx?.moment).toBe("map_enter");
  });

  test("the silent view carries no engine: it is importable on its own", () => {
    expect(HIDDEN_FX_VIEW.sync({} as never, "anything")).toBeUndefined();
    expect(HIDDEN_FX_VIEW.hide()).toBeUndefined();
  });
});

// --- The shake, which was a private method that mutated a scroll ----------------------------

describe("camera shake", () => {
  test("it decays to nothing over the profile's own duration", () => {
    const source = { seed: 3, elapsedMs: 0, dirSign: 1, scale: 1 };
    const first = sampleShake(source, KILL_SHAKE_PROFILE);
    const late = sampleShake({ ...source, elapsedMs: 120 }, KILL_SHAKE_PROFILE);
    expect(Math.abs(first.x)).toBeGreaterThan(Math.abs(late.x));
    expect(sampleShake({ ...source, elapsedMs: KILL_SHAKE_PROFILE.durationMs }, KILL_SHAKE_PROFILE))
      .toEqual(NO_SHAKE);
  });

  test("the phase is seeded, so two sources of the same age do not move together", () => {
    const a = sampleShake({ seed: 1, elapsedMs: 20, dirSign: 1, scale: 1 }, KILL_SHAKE_PROFILE);
    const b = sampleShake({ seed: 4, elapsedMs: 20, dirSign: 1, scale: 1 }, KILL_SHAKE_PROFILE);
    expect(a).not.toEqual(b);
  });

  test("E4 for the profile: a second genre's shake is a different four numbers", () => {
    const gentle: ShakeProfile = {
      amplitudePx: 12,
      durationMs: 400,
      stepMs: 32,
      pattern: [1, 0, -1, 0],
      verticalFraction: 1,
    };
    const nudge = sampleShake({ seed: 0, elapsedMs: 0, dirSign: 1, scale: 1 }, gentle);
    expect(nudge.x).toBe(12);
    // A profile whose vertical fraction is 1 shakes as hard up as sideways.
    expect(Math.abs(nudge.y)).toBe(12);
  });

  test("three kills in one frame are clamped, not added without bound", () => {
    const many = [
      { x: 4, y: 2 },
      { x: 4, y: 2 },
      { x: 4, y: 2 },
    ];
    expect(sumShake(many, 5)).toEqual({ x: 5, y: 5 });
    // E7, in the smallest form the effect has: with nothing shaking, the
    // offset is exactly zero and every consumer of it is unchanged.
    expect(sumShake([], 5)).toEqual({ x: 0, y: 0 });
  });
});

describe("the block the family gates for itself", () => {
  test("an absent fx block is an answer, not a refusal", () => {
    expect(parseScreenFxBlock({ gameplay: "runner-gameplay-block-v1" })).toEqual({
      block: "fx",
      version: null,
      published: false,
    });
  });

  test("a moved fx block is refused by name", () => {
    expect(() => parseScreenFxBlock({ fx: "fx-block-v2" })).toThrow(
      'manifest block "fx" is published as fx-block-v2; this build reads fx-block-v1',
    );
  });
});
