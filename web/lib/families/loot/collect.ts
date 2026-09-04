// The `loot` family, third half: picking it up, and passing it by.
//
// This is the half both genres have. The platformer drops loot and walks over
// it; the runner drops nothing at all — its pickups are authored into the
// streamed chunks — and still has to answer the same two questions on every
// frame: which of these is the body taking now, and which has it passed for
// good. The runner's answer had a ledger, because its pickups outlive the
// collection; the platformer's did not, because a taken drop is destroyed and
// the array *is* the ledger. That is why the ledger below is optional and its
// absence is a statement rather than a default.
//
// Neither the reach nor the passing test is here. "Near enough to take" is a
// forgiving circle in pixels in one genre and a strict box in track columns in
// the other, and admission proved the second against exactly those numbers; the
// same rule that keeps "which events can hurt" inside `vitals`' consumers keeps
// these two predicates inside theirs.

/** What a body has already taken and already passed, keyed by drop identity. */
export interface LootLedger {
  readonly collected: Set<string>;
  readonly missed: Set<string>;
}

export function createLootLedger(): LootLedger {
  return { collected: new Set<string>(), missed: new Set<string>() };
}

export interface CollectArgs<T> {
  /** This frame's candidates, in the order the caller wants them resolved. */
  readonly candidates: Iterable<T>;
  /** Stable identity for one drop. Position cannot serve: drops move, and indices are reused. */
  readonly key: (drop: T) => string;
  /** Whether the body is close enough to take this one. */
  readonly reached: (drop: T) => boolean;
  /**
   * Whether this one is behind the body for good.
   *
   * Omitted by a genre whose drops cannot be passed — a platformer's loot waits
   * on the ground until someone walks over it — which is an answer and not a
   * missing rule.
   */
  readonly passed?: (drop: T) => boolean;
  /**
   * What has already been taken or passed.
   *
   * Omitted by a genre that destroys a taken drop, where remembering it would
   * be a second copy of a fact the world already carries.
   */
  readonly ledger?: LootLedger;
}

export interface CollectVerdict<T> {
  /** Taken this frame, in candidate order, each exactly once ever. */
  readonly taken: readonly T[];
  /** Passed for good this frame, each exactly once ever. */
  readonly missed: readonly T[];
}

/**
 * Resolve one frame of collection.
 *
 * Order is the caller's, and it is load-bearing: two drops taken on one frame
 * are reported in two events, and which comes first is what a replay hashes.
 */
export function collectDrops<T>(args: CollectArgs<T>): CollectVerdict<T> {
  const taken: T[] = [];
  const missed: T[] = [];
  for (const drop of args.candidates) {
    const key = args.key(drop);
    if (args.ledger?.collected.has(key)) continue;
    if (args.passed?.(drop)) {
      if (args.ledger && !args.ledger.missed.has(key)) {
        args.ledger.missed.add(key);
        missed.push(drop);
      } else if (!args.ledger) {
        missed.push(drop);
      }
      continue;
    }
    if (!args.reached(drop)) continue;
    args.ledger?.collected.add(key);
    taken.push(drop);
  }
  return { taken, missed };
}
