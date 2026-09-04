import { describe, expect, test } from "bun:test";
import { createEventQueue, type GameEvent } from "./events";

type TestEvent =
  | { readonly type: "struck"; readonly key: string }
  | { readonly type: "fell" }
  | { readonly type: "drained"; readonly applied: number };

describe("createEventQueue", () => {
  test("keeps emission order within a frame", () => {
    const queue = createEventQueue<TestEvent>();
    queue.emit({ type: "struck", key: "a" });
    queue.emit({ type: "fell" });
    queue.emit({ type: "struck", key: "b" });
    expect(queue.frame.map((event) => event.type)).toEqual(["struck", "fell", "struck"]);
  });

  test("ofType narrows to the events a consumer asked for", () => {
    const queue = createEventQueue<TestEvent>();
    queue.emit({ type: "struck", key: "a" });
    queue.emit({ type: "drained", applied: 1 });
    queue.emit({ type: "struck", key: "b" });
    const struck = queue.ofType("struck");
    expect(struck.map((event) => event.key)).toEqual(["a", "b"]);
    expect(queue.ofType("fell")).toEqual([]);
  });

  test("beginFrame drops the previous frame's occurrences", () => {
    const queue = createEventQueue<TestEvent>();
    queue.emit({ type: "fell" });
    queue.beginFrame();
    expect(queue.frame).toEqual([]);
    expect(queue.ofType("fell")).toEqual([]);
  });

  test("beginFrame leaves a slice a consumer already took alone", () => {
    const queue = createEventQueue<TestEvent>();
    queue.emit({ type: "struck", key: "a" });
    const taken = queue.ofType("struck");
    queue.beginFrame();
    queue.emit({ type: "struck", key: "b" });
    expect(taken.map((event) => event.key)).toEqual(["a"]);
  });

  test("an emitted event is frozen, so a consumer cannot rewrite it for the next one", () => {
    const queue = createEventQueue<TestEvent>();
    queue.emit({ type: "drained", applied: 1 });
    const [event] = queue.ofType("drained");
    expect(Object.isFrozen(event)).toBe(true);
  });

  test("the queue is generic over any event carrying a type", () => {
    interface Custom extends GameEvent {
      readonly type: "custom";
      readonly payload: number;
    }
    const queue = createEventQueue<Custom>();
    queue.emit({ type: "custom", payload: 7 });
    expect(queue.ofType("custom")[0]?.payload).toBe(7);
  });
});
