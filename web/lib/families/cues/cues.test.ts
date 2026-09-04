import { describe, expect, test } from "bun:test";
import { createEventQueue } from "@/lib/kernel/events";
import { sealSystems, type FixedStep } from "@/lib/kernel/systems";
import { createCueSystem } from "./cues";

const STEP: FixedStep = { dt: 1 / 60, now: 1 / 60, frame: 1 };

function sink() {
  const posts: string[] = [];
  return { posts, play: (cue: string, strength: number) => posts.push(`${cue}:${strength}`) };
}

// --- E4: one family file, two worlds that share no field ----------------------------------------

describe("E4: the cues family sealed into two worlds", () => {
  test("a run's verbs, renamed, graded and guarded", () => {
    // Runner-shaped: a scored run whose package binds `takeoff` and `collect`,
    // and whose cues go quiet once the run has ended.
    type RunEvent =
      | { readonly type: "jumped"; readonly airJump: boolean }
      | { readonly type: "collected" }
      | { readonly type: "ended" };
    type Runnerish = {
      run: { phase: "running" | "dead" };
      score: { chain: number };
      readonly events: ReturnType<typeof createEventQueue<RunEvent>>;
    };
    const effects = sink();
    const world: Runnerish = {
      run: { phase: "running" },
      score: { chain: 15 },
      events: createEventQueue<RunEvent>(),
    };
    const system = createCueSystem<Runnerish, RunEvent["type"], string, "effect">({
      id: "runnerish/cues",
      contractVersion: "cues-v1",
      reads: ["run", "score"],
      sinks: { effect: effects },
      announce: "stage_start",
      table: [
        { on: "jumped", cue: (_w, event: { airJump: boolean }) => (event.airJump ? "air_jump" : "takeoff") },
        {
          on: "collected",
          cue: "collect",
          when: (w: Runnerish) => w.run.phase !== "dead",
          strength: (w: Runnerish) => Math.min(1, w.score.chain / 30),
        },
        { on: "ended", cue: "death" },
      ],
    });
    world.events.emit({ type: "jumped", airJump: true });
    world.events.emit({ type: "collected" });
    system.update(world, STEP);
    expect(effects.posts).toEqual(["stage_start:1", "air_jump:1", "collect:0.5"]);

    world.events.beginFrame();
    world.run.phase = "dead";
    world.events.emit({ type: "collected" });
    world.events.emit({ type: "ended" });
    system.update(world, STEP);
    // The guard is a read of the lifecycle, and the announcement happens once.
    expect(effects.posts).toEqual(["stage_start:1", "air_jump:1", "collect:0.5", "death:1"]);
  });

  test("a stage's verbs, over two sinks, in a world with no run at all", () => {
    // Platformer-shaped: no phase, no score, nothing to guard on — a stage
    // where a blow is heard by an effect sink and a music sink at once. This is
    // the genre that authors no audio today and gets SFX for free when it does.
    type StageEvent = { readonly type: "mob-defeated" } | { readonly type: "map-entered" };
    type Platformerish = { readonly events: ReturnType<typeof createEventQueue<StageEvent>> };
    const effects = sink();
    const music = sink();
    const world: Platformerish = { events: createEventQueue<StageEvent>() };
    const system = createCueSystem<Platformerish, StageEvent["type"], string, "effect" | "music">({
      id: "platformerish/cues",
      contractVersion: "cues-v1",
      channel: "effect",
      sinks: { effect: effects, music },
      table: [
        { on: "mob-defeated", cue: "hit" },
        { on: "map-entered", cue: "arrive" },
        { on: "map-entered", cue: "place", channel: "music" },
      ],
    });
    world.events.emit({ type: "mob-defeated" });
    world.events.emit({ type: "map-entered" });
    system.update(world, STEP);
    expect(effects.posts).toEqual(["hit:1", "arrive:1"]);
    expect(music.posts).toEqual(["place:1"]);
    // No state, so a frame with nothing in it says nothing — there is no level
    // to re-read and no shadow copy to fall out of step.
    world.events.beginFrame();
    system.update(world, STEP);
    expect(effects.posts).toEqual(["hit:1", "arrive:1"]);
  });
});

describe("the cue system's declarations", () => {
  test("the consumes list is derived from the table, so an unemitted cue refuses at seal", () => {
    type E = { readonly type: "hit" };
    type W = { readonly events: ReturnType<typeof createEventQueue<E>> };
    const system = createCueSystem<W, "hit", string, "effect">({
      id: "w/cues",
      contractVersion: "cues-v1",
      sinks: { effect: sink() },
      table: [{ on: "hit", cue: "clang" }],
    });
    expect(system.consumes).toEqual(["hit"]);
    expect(system.writes).toEqual([]);
    // Nothing emits `hit`, so the channel has one end and the sealer says so
    // rather than letting a sound quietly never play.
    expect(() => sealSystems<W>([system], { events: (world) => world.events })).toThrow(
      "hit",
    );
  });

  test("a deferred rule is heard on the frame after, and carries no ordering edge", () => {
    type E = { readonly type: "late" };
    type W = { readonly events: ReturnType<typeof createEventQueue<E>> };
    const posts = sink();
    const world: W = { events: createEventQueue<E>() };
    const system = createCueSystem<W, "late", string, "effect">({
      id: "w/cues",
      contractVersion: "cues-v1",
      sinks: { effect: posts },
      table: [{ on: "late", cue: "echo", deferred: true }],
    });
    expect(system.consumesDeferred).toEqual(["late"]);
    expect(system.consumes).toBeUndefined();
    world.events.emit({ type: "late" });
    system.update(world, STEP);
    expect(posts.posts).toEqual([]);
    world.events.beginFrame();
    system.update(world, STEP);
    expect(posts.posts).toEqual(["echo:1"]);
  });
});
