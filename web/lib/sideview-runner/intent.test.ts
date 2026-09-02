import { describe, expect, test } from "bun:test";
import {
  attachKeyboardIntentSource,
  attachPointerIntentSource,
  createIntentLatch,
  createIntentSystem,
  NEUTRAL_RUNNER_INTENT,
  runnerIntent,
} from "./intent";
import { parseRunnerRuntimeManifest } from "./contract";
import { runnerManifestFixture } from "./fixture";
import { createRunnerWorld } from "./world";

describe("runnerIntent", () => {
  test("defaults every unstated field to not asked for", () => {
    expect(runnerIntent()).toEqual(NEUTRAL_RUNNER_INTENT);
    expect(runnerIntent({ jump: true })).toEqual({
      jump: true,
      duck: false,
      thrust: false,
      action: false,
    });
    expect(Object.isFrozen(runnerIntent({ jump: true }))).toBe(true);
  });
});

describe("createIntentLatch", () => {
  test("an edge is seen by exactly one sample", () => {
    const latch = createIntentLatch();
    latch.requestJump();
    expect(latch.sample().jump).toBe(true);
    expect(latch.sample().jump).toBe(false);
  });

  test("edges latched between samples are not lost", () => {
    const latch = createIntentLatch();
    latch.sample();
    latch.requestAction();
    latch.requestJump();
    const sampled = latch.sample();
    expect(sampled.action).toBe(true);
    expect(sampled.jump).toBe(true);
  });

  test("duck is held state, surviving samples until released", () => {
    const latch = createIntentLatch();
    latch.setDuck(true);
    expect(latch.sample().duck).toBe(true);
    expect(latch.sample().duck).toBe(true);
    latch.setDuck(false);
    expect(latch.sample().duck).toBe(false);
  });
});

type Listener = (event: KeyboardEvent) => void;

function fakeWindow() {
  const listeners = new Map<string, Set<Listener>>();
  return {
    addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
      const set = listeners.get(type) ?? new Set<Listener>();
      set.add(listener as Listener);
      listeners.set(type, set);
    },
    removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
      listeners.get(type)?.delete(listener as Listener);
    },
    dispatch(type: string, event: Partial<KeyboardEvent>) {
      for (const listener of listeners.get(type) ?? []) {
        listener({ preventDefault: () => undefined, repeat: false, ...event } as KeyboardEvent);
      }
    },
    count(type: string): number {
      return listeners.get(type)?.size ?? 0;
    },
  };
}

describe("attachKeyboardIntentSource", () => {
  test("maps Space and ArrowUp to jump, R to action, and ignores repeats", () => {
    const latch = createIntentLatch();
    const target = fakeWindow();
    attachKeyboardIntentSource(latch, target);
    target.dispatch("keydown", { code: "Space" });
    expect(latch.sample().jump).toBe(true);
    target.dispatch("keydown", { code: "ArrowUp" });
    expect(latch.sample().jump).toBe(true);
    target.dispatch("keydown", { code: "KeyR" });
    expect(latch.sample().action).toBe(true);
    target.dispatch("keydown", { code: "Space", repeat: true });
    expect(latch.sample().jump).toBe(false);
  });

  test("holds duck while ArrowDown is down and disposes cleanly", () => {
    const latch = createIntentLatch();
    const target = fakeWindow();
    const dispose = attachKeyboardIntentSource(latch, target);
    target.dispatch("keydown", { code: "ArrowDown" });
    expect(latch.sample().duck).toBe(true);
    target.dispatch("keyup", { code: "ArrowDown" });
    expect(latch.sample().duck).toBe(false);
    dispose();
    expect(target.count("keydown")).toBe(0);
    expect(target.count("keyup")).toBe(0);
  });
});

type PointerListener = (event: PointerEvent) => void;

function fakePointerTarget() {
  const listeners = new Map<string, Set<PointerListener>>();
  const captured: number[] = [];
  let prevented = 0;
  return {
    addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
      const set = listeners.get(type) ?? new Set<PointerListener>();
      set.add(listener as PointerListener);
      listeners.set(type, set);
    },
    removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
      listeners.get(type)?.delete(listener as PointerListener);
    },
    getBoundingClientRect() {
      return { top: 100, height: 500 } as DOMRect;
    },
    setPointerCapture(pointerId: number) {
      captured.push(pointerId);
    },
    dispatch(type: string, event: Pick<PointerEvent, "clientY" | "pointerId">) {
      for (const listener of listeners.get(type) ?? []) {
        listener({
          ...event,
          preventDefault: () => {
            prevented += 1;
          },
        } as PointerEvent);
      }
    },
    count(type: string): number {
      return listeners.get(type)?.size ?? 0;
    },
    get captured(): readonly number[] {
      return captured;
    },
    get prevented(): number {
      return prevented;
    },
  };
}

describe("attachPointerIntentSource", () => {
  test("maps the upper zone to one immediate jump", () => {
    const latch = createIntentLatch();
    const target = fakePointerTarget();
    attachPointerIntentSource(latch, target);

    target.dispatch("pointerdown", { clientY: 200, pointerId: 1 });

    expect(latch.sample().jump).toBe(true);
    expect(latch.sample().jump).toBe(false);
    expect(latch.sample().duck).toBe(false);
    expect(target.prevented).toBe(1);
  });

  test("holds the lower zone as duck through capture until every pointer releases", () => {
    const latch = createIntentLatch();
    const target = fakePointerTarget();
    attachPointerIntentSource(latch, target);

    target.dispatch("pointerdown", { clientY: 500, pointerId: 7 });
    target.dispatch("pointerdown", { clientY: 510, pointerId: 8 });
    expect(latch.sample()).toEqual({ jump: false, duck: true, thrust: false, action: false });
    expect(target.captured).toEqual([7, 8]);
    target.dispatch("pointerup", { clientY: 700, pointerId: 7 });
    expect(latch.sample().duck).toBe(true);
    target.dispatch("pointercancel", { clientY: 700, pointerId: 8 });
    expect(latch.sample().duck).toBe(false);
  });

  test("disposal removes every pointer listener and cannot leave duck held", () => {
    const latch = createIntentLatch();
    const target = fakePointerTarget();
    const dispose = attachPointerIntentSource(latch, target);
    target.dispatch("pointerdown", { clientY: 500, pointerId: 3 });
    expect(latch.sample().duck).toBe(true);

    dispose();

    expect(latch.sample().duck).toBe(false);
    for (const type of ["pointerdown", "pointerup", "pointercancel", "lostpointercapture"]) {
      expect(target.count(type)).toBe(0);
    }
  });
});

describe("createIntentSystem", () => {
  test("publishes the latch's sample as world data once per tick", () => {
    const world = createRunnerWorld(parseRunnerRuntimeManifest(runnerManifestFixture()), 1);
    const latch = createIntentLatch();
    const system = createIntentSystem(latch);
    latch.requestJump();
    system.update(world, { dt: 1 / 60, now: 1 / 60, frame: 1 });
    expect(world.intent.jump).toBe(true);
    system.update(world, { dt: 1 / 60, now: 2 / 60, frame: 2 });
    expect(world.intent.jump).toBe(false);
  });
});

describe("thrust rides the jump key as a held level", () => {
  test("a keydown edges the jump once and holds thrust until the key comes up", () => {
    const latch = createIntentLatch();
    const target = fakeWindow();
    attachKeyboardIntentSource(latch, target);

    target.dispatch("keydown", { code: "Space" });
    const first = latch.sample();
    expect(first.jump).toBe(true);
    expect(first.thrust).toBe(true);

    // The edge is spent; the level is not.
    const second = latch.sample();
    expect(second.jump).toBe(false);
    expect(second.thrust).toBe(true);

    target.dispatch("keyup", { code: "Space" });
    expect(latch.sample().thrust).toBe(false);
  });

  test("an auto-repeating key neither re-edges the jump nor re-asserts thrust", () => {
    const latch = createIntentLatch();
    const target = fakeWindow();
    attachKeyboardIntentSource(latch, target);

    target.dispatch("keydown", { code: "ArrowUp" });
    expect(latch.sample().jump).toBe(true);
    target.dispatch("keydown", { code: "ArrowUp", repeat: true });
    const repeated = latch.sample();
    expect(repeated.jump).toBe(false);
    expect(repeated.thrust).toBe(true);
  });

  test("ducking does not thrust", () => {
    const latch = createIntentLatch();
    const target = fakeWindow();
    attachKeyboardIntentSource(latch, target);

    target.dispatch("keydown", { code: "ArrowDown" });

    const sampled = latch.sample();
    expect(sampled.duck).toBe(true);
    expect(sampled.thrust).toBe(false);
  });

  test("the pointer's upper zone holds thrust until every upper pointer lifts", () => {
    const latch = createIntentLatch();
    const target = fakePointerTarget();
    attachPointerIntentSource(latch, target);

    target.dispatch("pointerdown", { clientY: 100, pointerId: 1 });
    target.dispatch("pointerdown", { clientY: 120, pointerId: 2 });
    expect(latch.sample().thrust).toBe(true);
    expect(target.captured).toEqual([1, 2]);

    target.dispatch("pointerup", { clientY: 100, pointerId: 1 });
    expect(latch.sample().thrust).toBe(true);
    target.dispatch("lostpointercapture", { clientY: 120, pointerId: 2 });
    expect(latch.sample().thrust).toBe(false);
  });

  test("disposal cannot leave thrust held", () => {
    const latch = createIntentLatch();
    const target = fakePointerTarget();
    const dispose = attachPointerIntentSource(latch, target);
    target.dispatch("pointerdown", { clientY: 100, pointerId: 5 });
    expect(latch.sample().thrust).toBe(true);

    dispose();

    expect(latch.sample().thrust).toBe(false);
  });
});
