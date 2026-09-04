// The kernel's one string hash.
//
// Determinism in this codebase is bought with seeds, and seeds are routinely
// derived from names: a heightmap tag, a map and zone id, an RNG channel. That
// derivation is a hash, and until this module there were three copies of the
// same FNV-1a in the tree (`sideview-platformer/heightmap.ts`,
// `sideview-platformer/spawn-director.ts`, and the mixing inside each) with
// nothing saying they had to agree. They did agree, by luck; a fourth would
// not have to, and every one of them is load-bearing for a replay.
//
// So: one hash, here, with its constants written once. The values it produces
// are exactly what the old copies produced, which is what lets the platformer
// import it without re-baking a single heightmap.

/** FNV-1a, 32-bit, over UTF-16 code units. Returns an unsigned 32-bit int. */
export function fnv1a32(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * Mix two 32-bit values into one, avalanching both halves.
 *
 * Used to fold a name's hash into a run's seed so that two channels of one
 * seed are as unrelated as two seeds. The constant is the usual 32-bit
 * finalizer; what matters here is only that it is fixed and written once.
 */
export function mix32(a: number, b: number): number {
  let mixed = (a ^ b) >>> 0;
  mixed = Math.imul(mixed ^ (mixed >>> 16), 0x45d9f3b);
  mixed = Math.imul(mixed ^ (mixed >>> 16), 0x45d9f3b);
  return (mixed ^ (mixed >>> 16)) >>> 0;
}
