// The kernel's one generator, with named channels.
//
// A run's identity is its seed: the same manifest and the same seed must
// stream the same chunks, seed the same salvo lanes and lay the same
// heightmap, or no report about a run means anything. That guarantee is worth
// exactly as much as the number of generators it is spread across, and before
// this module the tree had five — two byte-identical `mulberry32` copies in
// the runner alone, an xorshift32 in the platformer's heightmap, and a
// hand-rolled mulberry32 class in its spawn director.
//
// Two problems follow from copies, and only the second needs a new idea. The
// first is drift: nothing made the copies agree. The second is order
// coupling. When every consumer draws from one stream, adding a draw anywhere
// shifts every later draw everywhere — the chunk stream moves because a
// salvo asked one extra question. `channel(name)` is the fix: a named
// substream derived from the seed and the name, so one channel's draws are
// independent of every other channel's, and a new consumer is a new name
// rather than a re-baked golden.
//
// `mulberry32` stays exported and unchanged because replays depend on its
// exact stream; `xorshift32` is here for the platformer's heightmap for the
// same reason.

import { fnv1a32, mix32 } from "./hash";

export type Rng = () => number;

/** The classic mulberry32: 32-bit state, uniform floats in [0, 1). */
export function mulberry32(seed: number): Rng {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * xorshift32, kept for the platformer's heightmap.
 *
 * A zero state is a fixed point of the recurrence, so a zero seed is replaced
 * rather than allowed to produce a constant stream — the same guard the
 * heightmap has always had.
 */
export function xorshift32(seed: number): Rng {
  let state = (seed | 0) || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return ((state >>> 0) % 0x100000000) / 0x100000000;
  };
}

export interface SeededRng {
  /** The seed this generator and every channel of it derive from. */
  readonly seed: number;
  /**
   * A named substream.
   *
   * The same name on the same seed is the same stream, and it is the same
   * object: a channel is a position in a sequence of draws, so handing out a
   * fresh one per call would silently restart it.
   */
  channel(name: string): Rng;
}

export function createRng(seed: number): SeededRng {
  const channels = new Map<string, Rng>();
  return {
    seed: seed >>> 0,
    channel(name: string): Rng {
      const existing = channels.get(name);
      if (existing) return existing;
      const created = mulberry32(mix32(seed >>> 0, fnv1a32(name)));
      channels.set(name, created);
      return created;
    },
  };
}
