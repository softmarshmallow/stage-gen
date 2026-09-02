import { describe, expect, test } from "bun:test";
import { createEventQueue, type EventQueue } from "@/lib/game-systems/events";
import { sealSystems } from "@/lib/game-systems/systems";
import { CUT_IN_CHOREOGRAPHIES, type CutInFrame } from "./cut-in";
import { beginFxMoment, createFxSystem, type FxEvent, type FxWorld } from "./moment-system";

const beats = CUT_IN_CHOREOGRAPHIES.tear_reveal_v1;

function fakeView() {
  const frames: CutInFrame[] = [];
  let hidden = 0;
  return {
    frames,
    get hidden() {
      return hidden;
    },
    sync(frame: CutInFrame) {
      frames.push(frame);
    },
    hide() {
      hidden += 1;
    },
  };
}

/** A world with nothing but the slice and the queue: the system may read no more. */
function fakeWorld(): FxWorld & { readonly events: EventQueue<FxEvent> } {
  return { fx: null, events: createEventQueue<FxEvent>() };
}

function step(nowSeconds: number) {
  return { dt: 1 / 60, now: nowSeconds, frame: Math.round(nowSeconds * 60) } as const;
}

describe("createFxSystem", () => {
  test("idles and keeps the view hidden when no moment plays", () => {
    const view = fakeView();
    const system = createFxSystem(view);
    const world = fakeWorld();
    system.update(world, step(5));
    expect(view.frames).toHaveLength(0);
    expect(view.hidden).toBe(1);
    expect(world.events.frame).toHaveLength(0);
  });

  test("stamps the start from the step clock, never from zero", () => {
    const view = fakeView();
    const system = createFxSystem(view);
    const world = fakeWorld();
    beginFxMoment(world, "stage_start", "tear_reveal_v1");
    system.update(world, step(42.5));
    expect(world.fx?.startedAt).toBe(42.5);
    expect(view.frames[0]?.ripX).toBe(1);
  });

  test("releases once at the release mark and finishes at the end", () => {
    const view = fakeView();
    const system = createFxSystem(view);
    const world = fakeWorld();
    beginFxMoment(world, "stage_start", "tear_reveal_v1");
    const start = 10;
    system.update(world, step(start));
    world.events.beginFrame();
    system.update(world, step(start + beats.releaseMs / 1000 + 0.001));
    expect(world.events.ofType("fx-released")).toHaveLength(1);
    expect(world.events.ofType("fx-finished")).toHaveLength(0);
    world.events.beginFrame();
    system.update(world, step(start + beats.releaseMs / 1000 + 0.02));
    expect(world.events.ofType("fx-released")).toHaveLength(0);
    world.events.beginFrame();
    system.update(world, step(start + beats.durationMs / 1000 + 0.001));
    expect(world.events.ofType("fx-finished")[0]?.moment).toBe("stage_start");
    expect(world.fx).toBeNull();
    expect(view.hidden).toBeGreaterThan(0);
  });

  test("seals as an emitter with a declared position", () => {
    type QueueWorld = FxWorld & { readonly events: EventQueue<FxEvent> };
    const sealed = sealSystems([createFxSystem<QueueWorld>(fakeView())], {
      events: (world) => world.events,
    });
    expect(sealed.order).toEqual(["fx/moment"]);
    const world = fakeWorld();
    beginFxMoment(world, "stage_start", "tear_reveal_v1");
    sealed.tick(world, step(1));
    expect(world.fx?.startedAt).toBe(1);
  });
});
