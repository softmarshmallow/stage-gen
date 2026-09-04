// The GameSystem protocol: gameplay as declared, sealable units of work.
//
// This is the runtime analogue of the generation graph. A generation node
// declares its inputs and outputs and the planner refuses an impossible graph
// before any spend; a game system declares which world keys it reads and
// writes and `sealSystems` refuses an impossible frame before any tick. The
// sealed order is data — inspectable, testable, and derived rather than
// implied by registration accident.
//
// `reads` and `writes` describe same-frame dataflow: a system that consumes a
// key another system produced *this frame* declares the read, and sealing
// orders every writer of a key before every reader of it. A feedback read —
// consuming last frame's value, the way a difficulty ramp samples the
// distance the avatar wrote a frame ago — is deliberately not declared,
// because declaring it would assert an ordering the game loop cannot satisfy.
// Where feedback or presentation still needs a definite position, `after`
// carries the explicit edge. `reads` is for reads: a read declared to buy an
// ordering edge is a lie the next reader of the file believes.
//
// `owns` is the authority channel. A slice with an owner has exactly one
// author, refused at seal rather than discovered when two systems disagree
// about what is in it. `writes` without `owns` is the weaker claim — this
// system writes here, and so may others — and every write, owned or shared,
// is checked against the declaration at tick time when `devTrap` is on.
//
// `emits` and `consumes` are the third channel, and they carry occurrences
// rather than state — see `events.ts` for why state keys cannot. They order
// exactly the way reads and writes do (every emitter of an event type before
// every consumer of it) and refuse exactly the way they do, so a queue is not
// an escape hatch from sealing: an event loop is still a cycle, and still
// fails at seal time rather than on some later frame. Both are typed against
// the world's own event union, so a misspelled occurrence is a compile error
// rather than a system that never hears anything.
//
// `consumesDeferred` is the event channel's feedback read: the occurrence is
// heard on the frame after it is emitted, and therefore carries no ordering
// edge and cannot close a cycle. It is how a system sealed *before* an
// emitter hears it at all — the case that used to be written as an
// undeclared direct write into the earlier system's slice.

import type { EventQueue, EventQueueControl, GameEvent } from "./events";

export interface FixedStep {
  readonly dt: number;
  readonly now: number;
  readonly frame: number;
}

/**
 * The event union a world carries, or `string` for a world with no queue.
 *
 * This is what types `emits`/`consumes` against the genre's own events: the
 * runner's systems can only declare occurrences `RunnerEvent` actually has.
 */
export type EventTypeOf<W> = W extends { readonly events: EventQueue<infer E> }
  ? E["type"] & string
  : string;

/**
 * Why a composition is being reset.
 *
 * `run` is a new run inside the same session: the world starts over, the
 * frame queue is emptied, and the step clock keeps counting — a moment
 * playing over the restart is timed from a clock that never rewinds.
 * `session` is the whole composition starting again, clock included.
 */
export type ResetScope = "run" | "session";

export interface GameSystem<W, E extends string = EventTypeOf<W>> {
  /** Stable identity, e.g. "runner/avatar". */
  readonly id: string;
  /** The version of this system's world contract, e.g. "avatar-system-v1". */
  readonly contractVersion: string;
  readonly reads: readonly (keyof W & string)[];
  readonly writes: readonly (keyof W & string)[];
  /**
   * World slices this system is the sole author of.
   *
   * An owned slice orders exactly like a written one; what ownership adds is
   * the refusal — two owners, or any other system declaring a write of it, is
   * a seal-time error naming both systems and the slice.
   */
  readonly owns?: readonly (keyof W & string)[];
  /** Event types this system may append to the frame queue. */
  readonly emits?: readonly E[];
  /** Event types this system reads out of the frame queue, this frame. */
  readonly consumes?: readonly E[];
  /** Event types this system reads out of the *previous* frame's queue. */
  readonly consumesDeferred?: readonly E[];
  /** Explicit edges where reads/writes underdetermine the order. */
  readonly after?: readonly string[];
  update(world: W, step: FixedStep): void;
  /**
   * Forget whatever this system remembers between frames.
   *
   * Called by the composition's own reset, in sealed order, with the world
   * unguarded: a reset is not a tick, and the system that owns a lifecycle is
   * allowed to rebuild the world that lifecycle covers.
   */
  reset?(world: W, scope: ResetScope): void;
}

export interface SealOptions<W> {
  /**
   * How to reach this world's frame event queue.
   *
   * Required as soon as any system declares `emits` or `consumes`, and refused
   * when none does — a queue nothing uses would be cleared every frame for no
   * reader, and an event channel with nothing to clear it would leak the whole
   * run into one unbounded array.
   */
  readonly events?: (world: W) => EventQueueControl;
  /**
   * How to reach the fixed-step clock, so a session reset can rewind it.
   *
   * Optional because a composition may be driven by a clock it does not own;
   * without it, `reset(world, "session")` resets the systems and the queue and
   * says nothing about time.
   */
  readonly clock?: () => { reset(): void };
  /**
   * Occurrences that end the run they are emitted in.
   *
   * The tick that sees one finishes its sealed order and then resets the
   * composition, so a restart is a declared frame boundary rather than eleven
   * slices rewritten mid-tick underneath the systems still to run — which is
   * what left a dead run's occurrences in the queue for everything sealed
   * after the system that restarted it.
   */
  readonly resetOn?: readonly EventTypeOf<W>[];
  /**
   * Refuse, at tick time, any write to a slice the writing system did not
   * declare. Off by default: the guard is a proxy per system per slice, and
   * production should not pay for a check that the tests can make for it.
   */
  readonly devTrap?: boolean;
}

export interface SealedSystems<W> {
  /** The derived tick order, exposed so it can be asserted rather than trusted. */
  readonly order: readonly string[];
  tick(world: W, step: FixedStep): void;
  /**
   * Reset the whole composition: every system's own `reset`, then the frame
   * queue, and — for a session — the step clock. The queue is emptied last so
   * that nothing outlives the reset, and so that no system sealed after a
   * restart is handed the dead run's occurrences.
   */
  reset(world: W, scope: ResetScope): void;
}

/** Every refusal this module makes, so a caller can catch the family. */
export class SealRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** Two systems registered under one id. */
export class DuplicateSystemError extends SealRefusal {}

/** Two owners of one slice, or a write into a slice another system owns. */
export class OwnershipConflictError extends SealRefusal {}

/** A consumed occurrence no system emits — a channel with no other end. */
export class UnemittedEventError extends SealRefusal {}

/** An `after` edge naming something that is not registered. */
export class UnknownSystemError extends SealRefusal {}

/** A dependency cycle: no order satisfies the declarations. */
export class SystemCycleError extends SealRefusal {}

/** An event channel with no accessor, or an accessor with no channel. */
export class EventAccessorError extends SealRefusal {}

/** A system writing a slice it did not declare, caught by the dev trap. */
export class UndeclaredWriteError extends Error {
  constructor(
    readonly systemId: string,
    readonly slice: string,
    message: string,
  ) {
    super(message);
    this.name = "UndeclaredWriteError";
  }
}

/** Depth-first search for one cycle among the given edges, returned as a path. */
function findCycle(
  ids: readonly string[],
  edges: ReadonlyMap<string, ReadonlySet<string>>,
): readonly string[] {
  const state = new Map<string, "visiting" | "done">();
  const stack: string[] = [];
  const walk = (id: string): readonly string[] | null => {
    state.set(id, "visiting");
    stack.push(id);
    for (const next of edges.get(id) ?? []) {
      const seen = state.get(next);
      if (seen === "done") continue;
      if (seen === "visiting") {
        return [...stack.slice(stack.indexOf(next)), next];
      }
      const found = walk(next);
      if (found) return found;
    }
    stack.pop();
    state.set(id, "done");
    return null;
  };
  for (const id of ids) {
    if (!state.has(id)) {
      const found = walk(id);
      if (found) return found;
    }
  }
  // Callers only ask after Kahn's algorithm stalled, so a cycle exists.
  throw new SystemCycleError("sealSystems detected a cycle it could not reconstruct");
}

/** Everything a system may write: what it owns, plus what it shares. */
function authority<W>(system: GameSystem<W, string>): ReadonlySet<string> {
  return new Set<string>([...system.writes, ...(system.owns ?? [])]);
}

/**
 * A world view that refuses writes the system did not declare.
 *
 * Two levels deep, which is where the undeclared writes actually were: a
 * slice replaced on the world (`world.run = ...`) and a field written inside
 * a slice the system only reads (`world.avatar.motion = "death"`). Deeper
 * containers — a Set of collected ids, an array of shots — are handed over
 * raw, because wrapping them would break the internal slots of the system
 * that legitimately owns them, and because the declaration is per slice.
 */
function trapped<W extends object>(
  world: W,
  system: GameSystem<W, string>,
  exempt: (value: unknown) => boolean,
): W {
  const declared = authority(system);
  const guards = new WeakMap<object, object>();
  const refuse = (slice: string, field: string | symbol): never => {
    const at = typeof field === "symbol" ? String(field) : field;
    throw new UndeclaredWriteError(
      system.id,
      slice,
      `"${system.id}" wrote "${slice}${slice === at ? "" : `.${at}`}", ` +
        `which it does not declare: add "${slice}" to its writes or owns, ` +
        `or ask a system that does declare it, through an event it consumes`,
    );
  };
  const guard = (slice: string, value: unknown): unknown => {
    if (value === null || typeof value !== "object") return value;
    if (exempt(value)) return value;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && !Array.isArray(value)) return value;
    const existing = guards.get(value as object);
    if (existing) return existing;
    const created = new Proxy(value as object, {
      set: (_target, field) => refuse(slice, field),
      defineProperty: (_target, field) => refuse(slice, field),
      deleteProperty: (_target, field) => refuse(slice, field),
    });
    guards.set(value as object, created);
    return created;
  };
  return new Proxy(world, {
    get(target, key, receiver) {
      const value = Reflect.get(target, key, receiver);
      if (typeof key !== "string" || declared.has(key)) return value;
      return guard(key, value);
    },
    set(target, key, value, receiver) {
      if (typeof key === "string" && !declared.has(key)) refuse(key, key);
      return Reflect.set(target, key, value, receiver);
    },
    deleteProperty(target, key) {
      if (typeof key === "string" && !declared.has(key)) refuse(key, key);
      return Reflect.deleteProperty(target, key);
    },
  }) as W;
}

/**
 * Seal a set of systems into one deterministic tick order.
 *
 * Refusals happen here, at seal time, exactly the way the generation graph
 * refuses at plan time: a duplicate id, two owners of one slice, an `after`
 * edge naming a system that is not registered, a consumed occurrence nothing
 * emits, and a dependency cycle are all programming errors that no amount of
 * ticking can recover from, so none of them is allowed to reach the first
 * frame.
 *
 * The order is Kahn's algorithm over writes-before-reads plus `after` edges,
 * with registration order breaking every tie — so the result is total,
 * deterministic, and stable under edits that do not change the declarations.
 */
export function sealSystems<W>(
  systems: readonly GameSystem<W, EventTypeOf<W>>[],
  options: SealOptions<W> = {},
): SealedSystems<W> {
  const declared = systems as readonly GameSystem<W, string>[];
  const byId = new Map<string, GameSystem<W, string>>();
  for (const system of declared) {
    if (byId.has(system.id)) {
      throw new DuplicateSystemError(
        `sealSystems refused duplicate system id "${system.id}"`,
      );
    }
    byId.set(system.id, system);
  }
  const ids = declared.map((system) => system.id);

  const usesEvents = declared.some(
    (system) =>
      (system.emits?.length ?? 0) > 0 ||
      (system.consumes?.length ?? 0) > 0 ||
      (system.consumesDeferred?.length ?? 0) > 0,
  );
  if (usesEvents && !options.events) {
    throw new EventAccessorError(
      "sealSystems refused an event-declaring set with no events accessor: " +
        "pass { events } so the frame queue can be cleared each tick",
    );
  }
  if (!usesEvents && options.events) {
    throw new EventAccessorError(
      "sealSystems refused an events accessor no system uses: " +
        "declare emits/consumes or drop the accessor",
    );
  }

  // Ownership first: it is the claim every other declaration is checked
  // against, and a slice with two authors has no order worth deriving.
  const ownerByKey = new Map<string, string>();
  for (const system of declared) {
    for (const key of system.owns ?? []) {
      const owner = ownerByKey.get(key);
      if (owner !== undefined) {
        throw new OwnershipConflictError(
          `sealSystems refused two owners of "${key}": ` +
            `"${owner}" and "${system.id}" both declare it. One slice, one author — ` +
            `the second asks the first for the change through an event`,
        );
      }
      ownerByKey.set(key, system.id);
    }
  }
  for (const system of declared) {
    for (const key of system.writes) {
      const owner = ownerByKey.get(key);
      if (owner !== undefined && owner !== system.id) {
        throw new OwnershipConflictError(
          `sealSystems refused "${system.id}": it writes "${key}", which "${owner}" owns. ` +
            `Ask the owner for the change through an event it consumes`,
        );
      }
    }
  }

  const edges = new Map<string, Set<string>>(ids.map((id) => [id, new Set<string>()]));
  const writersByKey = new Map<string, string[]>();
  const emittersByType = new Map<string, string[]>();
  for (const system of declared) {
    for (const key of authority(system)) {
      const writers = writersByKey.get(key) ?? [];
      writers.push(system.id);
      writersByKey.set(key, writers);
    }
    for (const type of system.emits ?? []) {
      const emitters = emittersByType.get(type) ?? [];
      emitters.push(system.id);
      emittersByType.set(type, emitters);
    }
  }
  const requireEmitter = (type: string, blame: string): void => {
    if (!emittersByType.has(type)) {
      throw new UnemittedEventError(
        `sealSystems refused "${blame}": it consumes "${type}", which no system emits`,
      );
    }
  };
  for (const system of declared) {
    for (const key of system.reads) {
      for (const writer of writersByKey.get(key) ?? []) {
        if (writer !== system.id) edges.get(writer)?.add(system.id);
      }
    }
    for (const type of system.consumes ?? []) {
      requireEmitter(type, system.id);
      for (const emitter of emittersByType.get(type) ?? []) {
        if (emitter !== system.id) edges.get(emitter)?.add(system.id);
      }
    }
    // A deferred consume is last frame's occurrence: it constrains nothing
    // about this frame's order, which is exactly why it cannot close a cycle.
    // Nor does it require an emitter. An in-frame consume with no emitter is a
    // channel with no other end — a defect. A deferred one is a mailbox: the
    // fx system listens for asks in a roster whose genre may have no director
    // to make them, and an empty mailbox is not a defect. What would have been
    // a typo is caught by the type instead, against the world's own union.
    for (const dependency of system.after ?? []) {
      if (!byId.has(dependency)) {
        throw new UnknownSystemError(
          `sealSystems refused "${system.id}": its after edge names unregistered "${dependency}"`,
        );
      }
      if (dependency !== system.id) edges.get(dependency)?.add(system.id);
    }
  }
  for (const type of options.resetOn ?? []) {
    if (!emittersByType.has(type)) {
      throw new UnemittedEventError(
        `sealSystems refused the reset trigger "${type}", which no system emits`,
      );
    }
  }

  const indegree = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const targets of edges.values()) {
    for (const target of targets) {
      indegree.set(target, (indegree.get(target) ?? 0) + 1);
    }
  }

  const order: string[] = [];
  const emitted = new Set<string>();
  while (order.length < ids.length) {
    // Registration order breaks ties: scan for the first ready system.
    const ready = ids.find((id) => !emitted.has(id) && indegree.get(id) === 0);
    if (ready === undefined) {
      const remaining = ids.filter((id) => !emitted.has(id));
      const cycle = findCycle(remaining, edges);
      throw new SystemCycleError(
        `sealSystems refused a dependency cycle: ${cycle.join(" -> ")} ` +
          `(break it with an explicit "after" edge or a narrower reads/writes declaration)`,
      );
    }
    emitted.add(ready);
    order.push(ready);
    for (const target of edges.get(ready) ?? []) {
      indegree.set(target, (indegree.get(target) ?? 0) - 1);
    }
  }

  const sequence = order.map((id) => {
    const system = byId.get(id);
    if (!system) throw new UnknownSystemError(`sealSystems lost system "${id}"`);
    return system;
  });
  const events = options.events;
  const resetOn = options.resetOn ?? [];
  // One view per system, built once: the guard is a per-slice proxy, and
  // rebuilding it every frame would make the trap cost more than it measures.
  const views = new Map<string, W>();
  const viewFor = (world: W, system: GameSystem<W, string>): W => {
    if (!options.devTrap || world === null || typeof world !== "object") return world;
    const cached = views.get(system.id);
    if (cached !== undefined) return cached;
    const queue = events ? (events(world) as unknown) : undefined;
    const view = trapped(world as W & object, system, (value) => value === queue) as W;
    views.set(system.id, view);
    return view;
  };

  const sealed: SealedSystems<W> = {
    order: Object.freeze(order),
    tick(world: W, step: FixedStep): void {
      // The frame's occurrences start empty and belong to this tick alone.
      events?.(world).beginFrame();
      for (const system of sequence) system.update(viewFor(world, system), step);
      if (resetOn.length === 0) return;
      const queue = events?.(world) as { frame?: readonly GameEvent[] } | undefined;
      const ending = queue?.frame?.some((event) =>
        (resetOn as readonly string[]).includes(event.type),
      );
      if (ending) sealed.reset(world, "run");
    },
    reset(world: W, scope: ResetScope): void {
      // Unguarded on purpose: a reset is the composition rebuilding the world,
      // not a system reaching into a slice mid-frame.
      for (const system of sequence) system.reset?.(world, scope);
      events?.(world).discardFrames();
      if (scope === "session") options.clock?.().reset();
    },
  };
  return Object.freeze(sealed);
}
