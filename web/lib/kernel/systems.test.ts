import { describe, expect, test } from "bun:test";
import { createEventQueue, type GameEvent } from "./events";
import {
  OwnershipConflictError,
  SystemCycleError,
  UndeclaredWriteError,
  UnemittedEventError,
  UnknownSystemError,
  sealSystems,
  type FixedStep,
  type GameSystem,
  type ResetScope,
} from "./systems";

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
    emits?: readonly TestEvent["type"][];
    consumes?: readonly TestEvent["type"][];
    consumesDeferred?: readonly TestEvent["type"][];
    owns?: readonly (keyof EventWorld & string)[];
    onUpdate?: (world: EventWorld) => void;
  },
): GameSystem<EventWorld> {
  return {
    id,
    contractVersion: `${id}-v1`,
    reads: [],
    writes: [],
    owns: options.owns,
    emits: options.emits,
    consumes: options.consumes,
    consumesDeferred: options.consumesDeferred,
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

  test("a deferred consumer hears an occurrence one frame late", () => {
    const world = eventWorld();
    const heard: number[] = [];
    const sealed = sealSystems<EventWorld>(
      [
        // Sealed FIRST and still hearing the emitter that follows it: the
        // whole point of the deferred channel.
        eventSystem("early", {
          consumesDeferred: ["struck"],
          onUpdate: (w) => heard.push(w.events.previous("struck").length),
        }),
        eventSystem("late", {
          emits: ["struck"],
          onUpdate: (w) => w.events.emit({ type: "struck" }),
        }),
      ],
      EVENTS,
    );
    expect(sealed.order).toEqual(["early", "late"]);
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    sealed.tick(world, STEP);
    expect(heard).toEqual([0, 1, 1]);
  });

  test("a deferred consume cannot close a cycle, because it is not this frame", () => {
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("ping", { emits: ["struck"], consumesDeferred: ["drained"] }),
        eventSystem("pong", { emits: ["drained"], consumes: ["struck"] }),
      ],
      EVENTS,
    );
    expect(sealed.order).toEqual(["ping", "pong"]);
  });

  test("a deferred consume of a type nothing emits is still refused", () => {
    expect(() =>
      sealSystems<EventWorld>([eventSystem("listener", { consumesDeferred: ["unheard"] })], EVENTS),
    ).toThrow(UnemittedEventError);
  });
});

// --- Ownership -----------------------------------------------------------------------------

describe("owns", () => {
  test("refuses two owners of one slice, naming both and the slice", () => {
    const seal = () =>
      sealSystems<World>([
        { ...system("first", [], []), owns: ["a"] },
        { ...system("second", [], []), owns: ["a"] },
      ]);
    expect(seal).toThrow(OwnershipConflictError);
    expect(seal).toThrow('refused two owners of "a"');
    expect(seal).toThrow('"first" and "second"');
  });

  test("refuses another system's write into an owned slice", () => {
    const seal = () =>
      sealSystems<World>([
        { ...system("owner", [], []), owns: ["a"] },
        system("interloper", [], ["a"]),
      ]);
    expect(seal).toThrow(OwnershipConflictError);
    expect(seal).toThrow('it writes "a", which "owner" owns');
  });

  test("an owned slice orders exactly like a written one", () => {
    const sealed = sealSystems<World>([
      system("reader", ["a"], []),
      { ...system("owner", [], []), owns: ["a"] },
    ]);
    expect(sealed.order).toEqual(["owner", "reader"]);
  });

  test("an owner may declare the same slice in writes as well", () => {
    const sealed = sealSystems<World>([{ ...system("owner", [], ["a"]), owns: ["a"] }]);
    expect(sealed.order).toEqual(["owner"]);
  });
});

// --- The dev-mode write trap ---------------------------------------------------------------

interface TrapWorld {
  owned: { value: number };
  shared: { value: number };
  readonlySlice: { value: number };
}

function trapWorld(): TrapWorld {
  return { owned: { value: 0 }, shared: { value: 0 }, readonlySlice: { value: 0 } };
}

function trapSystem(
  id: string,
  declaration: Pick<GameSystem<TrapWorld>, "reads" | "writes" | "owns">,
  onUpdate: (world: TrapWorld) => void,
): GameSystem<TrapWorld> {
  return { id, contractVersion: `${id}-v1`, ...declaration, update: onUpdate };
}

describe("the dev write trap", () => {
  test("refuses a field written inside a slice the system only reads", () => {
    const sealed = sealSystems<TrapWorld>(
      [
        trapSystem("thief", { reads: ["readonlySlice"], writes: ["shared"] }, (world) => {
          world.readonlySlice.value = 1;
        }),
      ],
      { devTrap: true },
    );
    const seal = () => sealed.tick(trapWorld(), STEP);
    expect(seal).toThrow(UndeclaredWriteError);
    expect(seal).toThrow('"thief" wrote "readonlySlice.value"');
  });

  test("refuses a slice replaced on the world", () => {
    const sealed = sealSystems<TrapWorld>(
      [
        trapSystem("thief", { reads: [], writes: ["shared"] }, (world) => {
          world.owned = { value: 9 };
        }),
      ],
      { devTrap: true },
    );
    expect(() => sealed.tick(trapWorld(), STEP)).toThrow('"thief" wrote "owned"');
  });

  test("lets a system write what it declares, owned or shared", () => {
    const world = trapWorld();
    const sealed = sealSystems<TrapWorld>(
      [
        trapSystem("author", { reads: [], writes: ["shared"], owns: ["owned"] }, (w) => {
          w.shared.value += 1;
          w.owned = { value: 7 };
        }),
      ],
      { devTrap: true },
    );
    sealed.tick(world, STEP);
    expect(world.shared.value).toBe(1);
    expect(world.owned).toEqual({ value: 7 });
  });

  test("is off by default, so production does not pay for it", () => {
    const world = trapWorld();
    const sealed = sealSystems<TrapWorld>([
      trapSystem("thief", { reads: ["readonlySlice"], writes: [] }, (w) => {
        w.readonlySlice.value = 1;
      }),
    ]);
    expect(() => sealed.tick(world, STEP)).not.toThrow();
    expect(world.readonlySlice.value).toBe(1);
  });

  test("hands the world through unchanged for reads", () => {
    const world = trapWorld();
    const seen: number[] = [];
    const sealed = sealSystems<TrapWorld>(
      [
        trapSystem("reader", { reads: ["shared"], writes: [] }, (w) => {
          seen.push(w.shared.value);
        }),
      ],
      { devTrap: true },
    );
    world.shared.value = 4;
    sealed.tick(world, STEP);
    expect(seen).toEqual([4]);
  });
});

// --- Reset ---------------------------------------------------------------------------------

describe("composition reset", () => {
  test("resets every system in sealed order, with the scope", () => {
    const world = eventWorld();
    const trace: string[] = [];
    const sealed = sealSystems<EventWorld>([
      {
        ...eventSystem("first", {}),
        reset: (_world: EventWorld, scope: ResetScope) => trace.push(`first:${scope}`),
      },
      {
        ...eventSystem("second", {}),
        reset: (_world: EventWorld, scope: ResetScope) => trace.push(`second:${scope}`),
      },
    ]);
    sealed.reset(world, "run");
    expect(trace).toEqual(["first:run", "second:run"]);
  });

  test("empties the frame queue, and the frame a deferred consumer would hear", () => {
    const world = eventWorld();
    const sealed = sealSystems<EventWorld>(
      [
        eventSystem("emitter", {
          emits: ["struck"],
          onUpdate: (w) => w.events.emit({ type: "struck" }),
        }),
      ],
      EVENTS,
    );
    sealed.tick(world, STEP);
    expect(world.events.frame).toHaveLength(1);
    sealed.reset(world, "run");
    expect(world.events.frame).toHaveLength(0);
    expect(world.events.previous("struck")).toHaveLength(0);
  });

  test("rewinds the clock for a session and leaves it alone for a run", () => {
    let resets = 0;
    const sealed = sealSystems<EventWorld>([eventSystem("quiet", {})], {
      clock: () => ({
        reset: () => {
          resets += 1;
        },
      }),
    });
    sealed.reset(eventWorld(), "run");
    expect(resets).toBe(0);
    sealed.reset(eventWorld(), "session");
    expect(resets).toBe(1);
  });

  test("a declared reset trigger ends the tick it is emitted in", () => {
    const world = eventWorld();
    const seen: number[] = [];
    let restarts = 0;
    const sealed = sealSystems<EventWorld>(
      [
        {
          ...eventSystem("ender", {
            emits: ["drained"],
            onUpdate: (w) => {
              if (w.a === 0) w.events.emit({ type: "drained" });
              w.a += 1;
            },
          }),
          writes: ["a"],
          reset: () => {
            restarts += 1;
          },
        },
        eventSystem("after", {
          onUpdate: (w) => seen.push(w.events.frame.length),
        }),
      ],
      { ...EVENTS, resetOn: ["drained"] },
    );
    sealed.tick(world, STEP);
    // Everything sealed after the ender still saw the occurrence this frame;
    // the reset happens at the frame boundary, not underneath them.
    expect(seen).toEqual([1]);
    expect(restarts).toBe(1);
    // And nothing survives into the next frame.
    expect(world.events.frame).toHaveLength(0);
    sealed.tick(world, STEP);
    expect(restarts).toBe(1);
  });

  test("refuses a reset trigger nothing emits", () => {
    expect(() =>
      sealSystems<EventWorld>([eventSystem("emitter", { emits: ["struck"] })], {
        ...EVENTS,
        resetOn: ["drained"],
      }),
    ).toThrow(UnemittedEventError);
  });
});

// --- The refusals are named ----------------------------------------------------------------

describe("every refusal carries a name a caller can catch", () => {
  test("an unknown after edge", () => {
    expect(() => sealSystems<World>([system("orphan", [], [], { after: ["phantom"] })])).toThrow(
      UnknownSystemError,
    );
  });

  test("a cycle", () => {
    expect(() =>
      sealSystems<World>([system("ping", ["b"], ["a"]), system("pong", ["a"], ["b"])]),
    ).toThrow(SystemCycleError);
  });

  test("a consumed type with no emitter", () => {
    expect(() =>
      sealSystems<EventWorld>([eventSystem("listener", { consumes: ["unheard"] })], EVENTS),
    ).toThrow(UnemittedEventError);
  });
});
