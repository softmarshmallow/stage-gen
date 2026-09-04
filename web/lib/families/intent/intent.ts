// The `intent` family: one record of what the player is asking for, and one
// latch, generic over which of its keys are edges.
//
// Both genres had this, written twice with different field names and the same
// rule stated twice in prose: a *level* describes a condition and persists
// while a source keeps asking for it; an *edge* is a request, set on the frame
// the action is asked for and gone afterwards, which is what stops a held key
// reading as an unbroken stream of fresh jumps. Neither file could check the
// rule it stated, because in both of them the rule was a comment and the
// difference between an edge and a level was which lines of the sampler
// happened to clear a variable.
//
// Here the split is data. `defineIntent` takes the neutral record and says
// which keys are which, refuses a key that is both or neither, and the latch
// is derived from that: edges accumulate until sampled and are spent by the
// sample, levels are held until the source changes them.
//
// Why it has to be a parameter and not a convention: the vertical jumper in
// the plan's target table needs a *held* axis, and the runner's latch spends
// everything it samples. A latch that consumes a level would report a held
// climb as one frame of climbing and then nothing, which is not a bug in the
// jumper — it is the runner's edge rule applied to a key that is not an edge.
// A held axis sampled twice reads twice, and `intent.test.ts` asserts exactly
// that with no jumper in the tree.

import type { GameSystem } from "@/lib/kernel/systems";

/** What a record's keys mean: which are requests, which are conditions. */
export interface IntentShape<I extends object> {
  /** Every action unrequested — the intent of a source with nothing to say. */
  readonly neutral: I;
  /** Keys spent by one sample. */
  readonly edges: ReadonlySet<keyof I & string>;
  /** Keys held until the source changes them. */
  readonly levels: ReadonlySet<keyof I & string>;
}

/** A key declared as both an edge and a level, or as neither. */
export class IntentShapeError extends Error {}

/**
 * Declare a record's edge and level keys, checked against the record itself.
 *
 * Every key of the neutral record must be classified exactly once. A key
 * nobody classified is the failure this catches: a field added to the type and
 * not to the sampler is a request that is never spent or a condition that
 * never persists, and both read as "the input is dropping presses".
 */
export function defineIntent<I extends object>(
  neutral: I,
  edges: readonly (keyof I & string)[],
  levels: readonly (keyof I & string)[],
): IntentShape<I> {
  const edgeSet = new Set(edges);
  const levelSet = new Set(levels);
  for (const key of edgeSet) {
    if (levelSet.has(key)) {
      throw new IntentShapeError(`intent key "${key}" is declared as both an edge and a level`);
    }
  }
  const keys = Object.keys(neutral) as (keyof I & string)[];
  for (const key of keys) {
    if (!edgeSet.has(key) && !levelSet.has(key)) {
      throw new IntentShapeError(
        `intent key "${key}" is declared as neither an edge nor a level: ` +
          `a request nothing spends and a condition nothing holds are the same defect`,
      );
    }
  }
  for (const key of [...edgeSet, ...levelSet]) {
    if (!keys.includes(key)) {
      throw new IntentShapeError(`intent declares "${key}", which the record does not carry`);
    }
  }
  return Object.freeze({
    neutral: Object.freeze({ ...neutral }),
    edges: edgeSet,
    levels: levelSet,
  });
}

/**
 * Build a frozen record, defaulting every unstated field to "not asked for".
 *
 * Defaulting rather than requiring every field is deliberate: a policy that
 * only wants to walk right should say `{ right: true }` and inherit silence
 * everywhere else, so adding a future action to the type cannot silently
 * change what an existing source is asking for.
 */
export function intentFrom<I extends object>(shape: IntentShape<I>, requested: Partial<I> = {}): I {
  return Object.freeze({ ...shape.neutral, ...requested });
}

/**
 * The latch between event-driven input and the fixed-step frame.
 *
 * Events arrive whenever the browser delivers them; the frame asks once per
 * tick. Edges accumulate until sampled and are consumed by the sample, so a
 * request that lands between two ticks is seen exactly once, never zero times
 * and never twice.
 */
export interface IntentLatch<I extends object> {
  /** Ask for an edge. Latched until the next sample spends it. */
  request(key: keyof I & string): void;
  /** Set a level. Held until the source changes it. */
  set<K extends keyof I & string>(key: K, value: I[K]): void;
  /** Read this frame's intent, spending the latched edges. */
  sample(): I;
  /**
   * Read this frame's intent under a hold: the edges are spent and reported
   * unasked, the levels are reported as they are.
   *
   * Spending rather than keeping is the point. A latch that held its edges
   * through a cut-in would fire every one of them the instant the overlay let
   * go, which is the opposite of what "the simulation was held" means.
   */
  sampleHeld(): I;
  /** Forget everything asked for. */
  reset(): void;
}

export function createIntentLatch<I extends object>(shape: IntentShape<I>): IntentLatch<I> {
  const pending = new Map<string, unknown>();
  const held = new Map<string, unknown>();
  const build = (withEdges: boolean): I => {
    const requested: Record<string, unknown> = {};
    for (const [key, value] of held) requested[key] = value;
    if (withEdges) for (const [key, value] of pending) requested[key] = value;
    pending.clear();
    return intentFrom(shape, requested as Partial<I>);
  };
  return {
    request(key) {
      if (!shape.edges.has(key)) {
        throw new IntentShapeError(`"${key}" is a level; set it rather than requesting it`);
      }
      pending.set(key, true);
    },
    set(key, value) {
      if (!shape.levels.has(key)) {
        throw new IntentShapeError(`"${key}" is an edge; request it rather than setting it`);
      }
      held.set(key, value);
    },
    sample: () => build(true),
    sampleHeld: () => build(false),
    reset() {
      pending.clear();
      held.clear();
    },
  };
}

export interface IntentBinding<W extends object, I extends object> {
  /** Where this frame's intent is published. */
  readonly slice: keyof W & string;
  readonly latch: IntentLatch<I>;
  readonly id?: string;
  readonly contractVersion?: string;
  /**
   * Where to read whether the simulation is held, if this genre has a clock.
   *
   * A genre without one passes nothing and every sample is a live sample.
   */
  readonly held?: (world: W) => boolean;
  readonly reads?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
}

/** Publish this frame's sampled intent as world data. */
export function createIntentSystem<W extends object, I extends object>(
  binding: IntentBinding<W, I>,
): GameSystem<W, never> {
  const slice = binding.slice;
  return {
    id: binding.id ?? "intent/frame",
    contractVersion: binding.contractVersion ?? "intent-system-v1",
    reads: binding.reads ?? [],
    writes: [],
    owns: [slice],
    ...(binding.after ? { after: binding.after } : {}),
    update(world) {
      const held = binding.held?.(world) ?? false;
      (world as Record<string, unknown>)[slice] = held
        ? binding.latch.sampleHeld()
        : binding.latch.sample();
    },
    reset() {
      binding.latch.reset();
    },
  };
}
