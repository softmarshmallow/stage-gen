import { describe, expect, test } from "bun:test";
import { createEventQueue, type GameEvent } from "./events";
import { sealSystems, type FixedStep, type GameSystem } from "./systems";

interface World {
  a: number;
  b: number;
  c: number;
}

const STEP: FixedStep = Object.freeze({ dt: 1 / 60, now: 1 / 60, frame: 1 });

function system(
  id: string,
  reads: readonly (keyof World & string)[],
  writes: readonly (keyof World & string)[],
  options: { after?: readonly string[]; onUpdate?: (world: World) => void } = {},
): GameSystem<World> {
  return {
    id,
    contractVersion: `${id}-v1`,
    reads,
    writes,
    after: options.after,
    update(world) {
      options.onUpdate?.(world);
    },
  };
}

describe("sealSystems", () => {
  test("orders every writer of a key before every reader of it", () => {
    const sealed = sealSystems<World>([
      system("reader", ["a", "b"], ["c"]),
      system("writer-b", [], ["b"]),
      system("writer-a", [], ["a"]),
    ]);
    const order = sealed.order;
    expect(order.indexOf("writer-a")).toBeLessThan(order.indexOf("reader"));
    expect(order.indexOf("writer-b")).toBeLessThan(order.indexOf("reader"));
  });

  test("keeps registration order among independent systems, deterministically", () => {
    const systems = [
      system("first", [], ["a"]),
      system("second", [], ["b"]),
      system("third", [], ["c"]),
    ];
    expect(sealSystems<World>(systems).order).toEqual(["first", "second", "third"]);
    // Sealing the same declarations again derives the same order.
    expect(sealSystems<World>(systems).order).toEqual(sealSystems<World>(systems).order);
  });

  test("honors explicit after edges where dataflow is silent", () => {
    const sealed = sealSystems<World>([
      system("late", [], [], { after: ["early"] }),
      system("early", [], []),
    ]);
    expect(sealed.order).toEqual(["early", "late"]);
  });

  test("refuses duplicate ids at seal time", () => {
    expect(() =>
      sealSystems<World>([system("twin", [], ["a"]), system("twin", [], ["b"])]),
    ).toThrow('duplicate system id "twin"');
  });

  test("refuses an after edge naming an unregistered system", () => {
    expect(() =>
      sealSystems<World>([system("orphan", [], [], { after: ["phantom"] })]),
    ).toThrow('after edge names unregistered "phantom"');
  });

  test("refuses a read/write cycle and names it", () => {
    const seal = () =>
      sealSystems<World>([
        system("ping", ["b"], ["a"]),
        system("pong", ["a"], ["b"]),
      ]);
    expect(seal).toThrow("sealSystems refused a dependency cycle");
    expect(seal).toThrow(/ping -> pong -> ping|pong -> ping -> pong/);
  });

  test("refuses a cycle closed by an after edge", () => {
    expect(() =>
      sealSystems<World>([
        system("alpha", [], ["a"], { after: ["beta"] }),
        system("beta", ["a"], []),
      ]),
    ).toThrow("dependency cycle");
  });

  test("tick runs updates in the sealed order", () => {
    const world: World = { a: 0, b: 0, c: 0 };
    const trace: string[] = [];
    const sealed = sealSystems<World>([
      system("consumer", ["a"], ["b"], { onUpdate: () => trace.push("consumer") }),
      system("producer", [], ["a"], { onUpdate: () => trace.push("producer") }),
    ]);
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    expect(trace).toEqual(["producer", "consumer", "producer", "consumer"]);
    expect(sealed.order).toEqual(["producer", "consumer"]);
  });

  test("a system reading its own written key needs no self edge", () => {
    const sealed = sealSystems<World>([system("loner", ["a"], ["a"])]);
    expect(sealed.order).toEqual(["loner"]);
  });
});

// --- The event channel ---------------------------------------------------------------------

interface EventWorld {
  a: number;
  events: ReturnType<typeof createEventQueue<TestEvent>>;
}

type TestEvent =
  | { readonly type: "struck" }
  | { readonly type: "drained" }
  | { readonly type: "unheard" };

function eventWorld(): EventWorld {
  return { a: 0, events: createEventQueue<TestEvent>() };
}

function eventSystem(
  id: string,
  options: {
    emits?: readonly string[];
    consumes?: readonly string[];
    onUpdate?: (world: EventWorld) => void;
  },
): GameSystem<EventWorld> {
  return {
    id,
    contractVersion: `${id}-v1`,
    reads: [],
    writes: [],
    emits: options.emits,
    consumes: options.consumes,
    update(world) {
      options.onUpdate?.(world);
    },
  };
}

const EVENTS = { events: (world: EventWorld) => world.events };

describe("sealSystems event channel", () => {
  test("orders every emitter of a type before every consumer of it", () => {
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("consumer", { consumes: ["struck"] }),
        eventSystem("emitter", { emits: ["struck"] }),
      ],
      EVENTS,
    );
    expect(sealed.order).toEqual(["emitter", "consumer"]);
  });

  test("a consumer sees what an earlier emitter emitted this frame", () => {
    const world = eventWorld();
    const seen: number[] = [];
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("consumer", {
          consumes: ["struck"],
          onUpdate: (w) => seen.push(w.events.ofType("struck").length),
        }),
        eventSystem("emitter", {
          emits: ["struck"],
          onUpdate: (w) => w.events.emit({ type: "struck" }),
        }),
      ],
      EVENTS,
    );
    sealed.tick(world, STEP);
    expect(seen).toEqual([1]);
  });

  test("each tick starts from an empty frame", () => {
    const world = eventWorld();
    const seen: number[] = [];
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("emitter", {
          emits: ["struck"],
          onUpdate: (w) => w.events.emit({ type: "struck" }),
        }),
        eventSystem("consumer", {
          consumes: ["struck"],
          onUpdate: (w) => seen.push(w.events.ofType("struck").length),
        }),
      ],
      EVENTS,
    );
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    // Never 2 or 3: the queue is this frame's occurrences, not the run's.
    expect(seen).toEqual([1, 1, 1]);
  });

  test("refuses a consumer of a type nothing emits", () => {
    expect(() =>
      sealSystems<EventWorld>([eventSystem("listener", { consumes: ["unheard"] })], EVENTS),
    ).toThrow('it consumes "unheard", which no system emits');
  });

  test("refuses an event cycle at seal time, not on some later frame", () => {
    expect(() =>
      sealSystems<EventWorld>(
        [
          eventSystem("ping", { emits: ["struck"], consumes: ["drained"] }),
          eventSystem("pong", { emits: ["drained"], consumes: ["struck"] }),
        ],
        EVENTS,
      ),
    ).toThrow("dependency cycle");
  });

  test("refuses event declarations with no accessor to clear the queue", () => {
    expect(() =>
      sealSystems<EventWorld>([eventSystem("emitter", { emits: ["struck"] })]),
    ).toThrow("no events accessor");
  });

  test("refuses an accessor no system uses", () => {
    expect(() => sealSystems<EventWorld>([eventSystem("quiet", {})], EVENTS)).toThrow(
      "an events accessor no system uses",
    );
  });

  test("a system emitting and consuming its own type needs no self edge", () => {
    const sealed = sealSystems<EventWorld>(
      [eventSystem("loop", { emits: ["struck"], consumes: ["struck"] })],
      EVENTS,
    );
    expect(sealed.order).toEqual(["loop"]);
  });

  test("an event type is an occurrence, not a world key", () => {
    // Two systems both writing state would serialise; both emitting does not.
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("first", { emits: ["struck"] }),
        eventSystem("second", { emits: ["struck"] }),
        eventSystem("reader", { consumes: ["struck"] }),
      ],
      EVENTS,
    );
    expect(sealed.order).toEqual(["first", "second", "reader"]);
  });

  test("the queue accepts any event shape carrying a type", () => {
    const queue = createEventQueue<GameEvent>();
    queue.emit({ type: "anything" });
    expect(queue.frame).toHaveLength(1);
  });
});
