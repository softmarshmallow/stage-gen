// The `score` family: what an occurrence is worth, and what a run has earned.
//
// It was one genre's private arithmetic with two integers typed into it. The
// runner paid `10` for a pickup and `500` for a defeated boss, both literals in
// `sideview-runner/score.ts`, and the composition table's entry for this family
// says exactly that: "runner-only, inside `run-loop`, with `10` and `500`
// hard-coded; blocks the minigames case". The minigame is what it blocks
// because a time-attack run *is* a score: the whole of what the player is
// asked for is a number, and the number is authored rather than compiled.
//
// So the family is three facts and no more:
//
//   - the AWARDS: a table from an occurrence kind to what it pays. The kinds
//     are the caller's — the runner counts `collected` and `boss-defeated`,
//     the platformer counts the four the authored `[score]` vocabulary names —
//     and the family never learns what any of them mean.
//   - the CHAIN: consecutive scored occurrences without a break, and the
//     multiplier a length earns. Optional, and its absence is a statement: a
//     genre with no chain is not a genre whose chain is always one, because a
//     chain that cannot break is not an instrument.
//   - the TOTAL: the accumulation itself, which is the one line neither genre
//     would have got wrong and the one line they would each have written.
//
// What the family deliberately does *not* own: what ended the run. That is
// `session`, and step 3 split the two apart for the reason this file inherits —
// the moment one system answers both, "what a token was worth" and "what ended
// the run" have one author again.

import type { GameSystem } from "@/lib/kernel/systems";

export interface ScoreState {
  total: number;
  /** Consecutive scored occurrences without a break; the multiplier's input. */
  chain: number;
  /** The multiplier the current chain earns; 1 with no chain, and 1 with no chain policy. */
  multiplier: number;
}

export function createScoreState(): ScoreState {
  return { total: 0, chain: 0, multiplier: 1 };
}

/** Forget the run, in place: the world object is held by the views and the seal. */
export function resetScore(state: ScoreState): void {
  state.total = 0;
  state.chain = 0;
  state.multiplier = 1;
}

/**
 * A chain, as the two numbers that describe one.
 *
 * `steps` is the ladder — a chain at or past each rung earns one more — and
 * `extendedBy` is which of the scored kinds count towards it. Both are the
 * genre's: the runner chains its token line and pays a boss flat, because the
 * fight is not a pickup line and a player who spent it dodging should not be
 * paid less for winning it.
 */
export interface ChainPolicy<Kind extends string> {
  readonly steps: readonly number[];
  readonly extendedBy: readonly Kind[];
}

export interface ScoreParams<Kind extends string> {
  /** What each scored kind pays, before the multiplier. A kind with no entry pays nothing. */
  readonly awards: Readonly<Partial<Record<Kind, number>>>;
  /** The chain, or null for a genre that has none. */
  readonly chain: ChainPolicy<Kind> | null;
}

/** How much a chain of this length multiplies by, under this ladder. */
export function chainMultiplier(chain: number, steps: readonly number[]): number {
  let multiplier = 1;
  for (const step of steps) {
    if (chain >= step) multiplier += 1;
  }
  return multiplier;
}

/** What one frame of scored occurrences was worth, and what it did to the chain. */
export interface ScoreAward {
  /** Points added this frame. */
  readonly delta: number;
  /** True when the chain was broken before this frame's occurrences extended it. */
  readonly broken: boolean;
}

/**
 * Score one frame, in place.
 *
 * The order is the runner's and it is load-bearing: a break is applied *before*
 * this frame's occurrences extend the chain, so a frame carrying both a miss
 * and a collection starts the new chain at that collection rather than losing
 * it. Chained kinds are paid at the multiplier the extended chain earns; every
 * other kind is paid flat.
 */
export function applyScore<Kind extends string>(
  state: ScoreState,
  params: ScoreParams<Kind>,
  counts: Readonly<Partial<Record<Kind, number>>>,
  broken = false,
): ScoreAward {
  const chain = params.chain;
  if (broken && chain !== null) state.chain = 0;
  if (chain !== null) {
    let extended = 0;
    for (const kind of chain.extendedBy) extended += counts[kind] ?? 0;
    state.chain += extended;
    state.multiplier = chainMultiplier(state.chain, chain.steps);
  }
  let delta = 0;
  for (const [kind, count] of Object.entries(counts) as [Kind, number | undefined][]) {
    const paid = count ?? 0;
    if (paid <= 0) continue;
    const award = params.awards[kind] ?? 0;
    const chained = chain !== null && chain.extendedBy.includes(kind);
    delta += paid * award * (chained ? state.multiplier : 1);
  }
  state.total += delta;
  return Object.freeze({ delta, broken: broken && chain !== null });
}

export const SCORE_SYSTEM_ID = "score/run";

export interface ScoreBinding<W, Kind extends string> {
  /** Where the score lives on this world. */
  readonly slice: keyof W & string;
  readonly params: ScoreParams<Kind>;
  readonly id?: string;
  readonly contractVersion?: string;
  readonly reads?: readonly (keyof W & string)[];
  readonly writes?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
  readonly emits?: readonly string[];
  readonly consumes?: readonly string[];
  readonly consumesDeferred?: readonly string[];
  /**
   * Whether this frame is scored at all.
   *
   * The runner's answer is "while the run is running"; a genre that scores
   * every frame it ticks says so by leaving this out.
   */
  scoring?(world: W): boolean;
  /** This frame's scored occurrences, by kind, in the genre's own vocabulary. */
  counts(world: W): Readonly<Partial<Record<Kind, number>>>;
  /** Whether the chain broke this frame. A genre with no chain does not answer. */
  chainBroken?(world: W): boolean;
  /** Say so, in the genre's own occurrences. Optional: a genre may say nothing. */
  onChanged?(world: W, award: ScoreAward, state: ScoreState): void;
}

/**
 * The scorekeeper, generic over the world it keeps score on.
 *
 * It owns its slice and reads nothing it is not handed: everything about
 * *which* occurrences happened is the binding's, so the system that scores a
 * streamed token line and the system that scores a wave of creatures are the
 * same eleven lines with two different tables behind them.
 */
export function createScoreSystem<W extends object, Kind extends string>(
  binding: ScoreBinding<W, Kind>,
): GameSystem<W, never> {
  const { slice } = binding;
  const state = (world: W): ScoreState =>
    (world as Record<string, unknown>)[slice] as ScoreState;
  return {
    id: binding.id ?? SCORE_SYSTEM_ID,
    contractVersion: binding.contractVersion ?? "score-system-v1",
    reads: binding.reads ?? [],
    writes: binding.writes ?? [],
    owns: [slice],
    ...(binding.emits ? { emits: binding.emits as never } : {}),
    ...(binding.consumes ? { consumes: binding.consumes as never } : {}),
    ...(binding.consumesDeferred ? { consumesDeferred: binding.consumesDeferred as never } : {}),
    ...(binding.after ? { after: binding.after } : {}),
    update(world) {
      if (binding.scoring && !binding.scoring(world)) return;
      const award = applyScore(
        state(world),
        binding.params,
        binding.counts(world),
        binding.chainBroken?.(world) ?? false,
      );
      if (award.delta !== 0 || award.broken) binding.onChanged?.(world, award, state(world));
    },
    reset(world) {
      resetScore(state(world));
    },
  };
}
