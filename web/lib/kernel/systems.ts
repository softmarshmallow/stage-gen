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
// carries the explicit edge.
//
// `emits` and `consumes` are the third channel, and they carry occurrences
// rather than state — see `events.ts` for why state keys cannot. They order
// exactly the way reads and writes do (every emitter of an event type before
// every consumer of it) and refuse exactly the way they do, so a queue is not
// an escape hatch from sealing: an event loop is still a cycle, and still
// fails at seal time rather than on some later frame.

import type { EventQueueControl } from "./events";

export interface FixedStep {
  readonly dt: number;
  readonly now: number;
  readonly frame: number;
}

export interface GameSystem<W> {
  /** Stable identity, e.g. "runner/avatar". */
  readonly id: string;
  /** The version of this system's world contract, e.g. "avatar-system-v1". */
  readonly contractVersion: string;
  readonly reads: readonly (keyof W & string)[];
  readonly writes: readonly (keyof W & string)[];
  /** Event types this system may append to the frame queue. */
  readonly emits?: readonly string[];
  /** Event types this system reads out of the frame queue. */
  readonly consumes?: readonly string[];
  /** Explicit edges where reads/writes underdetermine the order. */
  readonly after?: readonly string[];
  update(world: W, step: FixedStep): void;
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
}

export interface SealedSystems<W> {
  /** The derived tick order, exposed so it can be asserted rather than trusted. */
  readonly order: readonly string[];
  tick(world: W, step: FixedStep): void;
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
  throw new Error("sealSystems detected a cycle it could not reconstruct");
}

/**
 * Seal a set of systems into one deterministic tick order.
 *
 * Refusals happen here, at seal time, exactly the way the generation graph
 * refuses at plan time: a duplicate id, an `after` edge naming a system that
 * is not registered, and a dependency cycle are all programming errors that
 * no amount of ticking can recover from, so none of them is allowed to reach
 * the first frame.
 *
 * The order is Kahn's algorithm over writes-before-reads plus `after` edges,
 * with registration order breaking every tie — so the result is total,
 * deterministic, and stable under edits that do not change the declarations.
 */
export function sealSystems<W>(
  systems: readonly GameSystem<W>[],
  options: SealOptions<W> = {},
): SealedSystems<W> {
  const byId = new Map<string, GameSystem<W>>();
  for (const system of systems) {
    if (byId.has(system.id)) {
      throw new Error(`sealSystems refused duplicate system id "${system.id}"`);
    }
    byId.set(system.id, system);
  }
  const ids = systems.map((system) => system.id);

  const usesEvents = systems.some(
    (system) => (system.emits?.length ?? 0) > 0 || (system.consumes?.length ?? 0) > 0,
  );
  if (usesEvents && !options.events) {
    throw new Error(
      "sealSystems refused an event-declaring set with no events accessor: " +
        "pass { events } so the frame queue can be cleared each tick",
    );
  }
  if (!usesEvents && options.events) {
    throw new Error(
      "sealSystems refused an events accessor no system uses: " +
        "declare emits/consumes or drop the accessor",
    );
  }

  const edges = new Map<string, Set<string>>(ids.map((id) => [id, new Set<string>()]));
  const writersByKey = new Map<string, string[]>();
  const emittersByType = new Map<string, string[]>();
  for (const system of systems) {
    for (const key of system.writes) {
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
  for (const system of systems) {
    for (const key of system.reads) {
      for (const writer of writersByKey.get(key) ?? []) {
        if (writer !== system.id) edges.get(writer)?.add(system.id);
      }
    }
    for (const type of system.consumes ?? []) {
      const emitters = emittersByType.get(type);
      if (!emitters) {
        throw new Error(
          `sealSystems refused "${system.id}": it consumes "${type}", which no system emits`,
        );
      }
      for (const emitter of emitters) {
        if (emitter !== system.id) edges.get(emitter)?.add(system.id);
      }
    }
    for (const dependency of system.after ?? []) {
      if (!byId.has(dependency)) {
        throw new Error(
          `sealSystems refused "${system.id}": its after edge names unregistered "${dependency}"`,
        );
      }
      if (dependency !== system.id) edges.get(dependency)?.add(system.id);
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
      throw new Error(
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
    if (!system) throw new Error(`sealSystems lost system "${id}"`);
    return system;
  });
  const events = options.events;
  return Object.freeze({
    order: Object.freeze(order),
    tick(world: W, step: FixedStep): void {
      // The frame's occurrences start empty and belong to this tick alone.
      events?.(world).beginFrame();
      for (const system of sequence) system.update(world, step);
    },
  });
}
