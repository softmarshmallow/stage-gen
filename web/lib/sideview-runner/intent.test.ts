import { describe, expect, test } from "bun:test";
import {
  attachKeyboardIntentSource,
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
    expect(runnerIntent({ jump: true })).toEqual({ jump: true, duck: false, action: false });
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
