// Particles: a bounded ring of frozen birth records, and a pure sample.
//
// Two of these existed and neither knew about the other. The runner's ground
// dust is a list of puffs, each a record of where and when the ground was
// struck, sampled every frame into an ellipse; the platformer's impact
// presentation is a list of blows, each a record of where and when a hit
// landed, sampled every frame into rays and shards. Both cap the list, both
// drop records once they are spent, both draw from a hash of the record's own
// seed so that a fixed-step replay draws the same frame twice, and both had
// written that hash out character for character — `dustUnitNoise` and
// `impactUnitNoise` were the same eight lines under two names.
//
// The family is the mechanism and not the shapes. What a puff *looks* like is
// the runner's, what a shard looks like is the platformer's, and neither is
// something the other could use; the ring, the cap, the eviction and the noise
// are the same object in both, and this is it.
//
// Nothing here reads a clock, draws a random number or holds a frame's worth of
// state beyond the records themselves. A record is frozen at birth: what a
// frame does with it is `sample(record, now)`, which is the reason two runs of
// one seed draw identically and the reason a replay can assert the drawing at
// all.

/**
 * Deterministic unit noise in [0, 1) for one seed and channel.
 *
 * No state, no wall clock. The channel is how one record draws several
 * independent numbers — a shard's angle and its speed, a puff's radius and its
 * kick — without carrying a generator around.
 */
export function particleUnitNoise(seed: number, channel: number): number {
  let hash = (Math.imul(seed ^ channel, 0x9e3779b1) ^ (seed >>> 15)) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 13), 0x85ebca6b) >>> 0;
  hash = Math.imul(hash ^ (hash >>> 16), 0xc2b2ae35) >>> 0;
  return hash / 4294967296;
}

/** The ease both presentations swell and fan out along. */
export function easeOutCubic(progress: number): number {
  return 1 - (1 - progress) ** 3;
}

/** 0..1, whatever was handed in. */
export function unitProgress(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export interface ParticleRingOptions<R> {
  /** How many records may be live at once. */
  readonly max: number;
  /** A ceiling on that, so a mis-authored cap cannot allocate a run's worth. */
  readonly ceiling?: number;
  /**
   * Called for each record leaving the ring, whether evicted by the cap or
   * pruned once spent.
   *
   * The platformer needs it: a blow holds a target sprite white while it is
   * live, and the sprite has to be let go of when the record is. The runner
   * passes none, because a puff owns nothing.
   */
  readonly onRelease?: (record: R) => void;
}

/**
 * A bounded ring of live records, oldest evicted first.
 *
 * Lifecycle-bound state — it is what a presentation remembers between frames —
 * so it is a class, and it is the only thing in this family that is not a pure
 * function.
 */
export class ParticleRing<R> {
  private readonly max: number;
  private readonly onRelease?: (record: R) => void;
  private live: R[] = [];

  constructor(options: ParticleRingOptions<R>) {
    this.max = Math.max(1, Math.min(options.ceiling ?? Number.MAX_SAFE_INTEGER, options.max));
    this.onRelease = options.onRelease;
  }

  /** The live records, oldest first. */
  get records(): readonly R[] {
    return this.live;
  }

  get count(): number {
    return this.live.length;
  }

  /** The cap actually in force, after the ceiling. */
  get capacity(): number {
    return this.max;
  }

  /** Add one record, evicting the oldest while the ring is over its cap. */
  remember(record: R): void {
    this.live.push(record);
    while (this.live.length > this.max) this.releaseAt(0);
  }

  /** Make room for one more *before* adding it — the platformer's own order. */
  makeRoom(): void {
    while (this.live.length >= this.max) this.releaseAt(0);
  }

  /** Drop every record `spent` answers true for, oldest first. */
  prune(spent: (record: R) => boolean): void {
    for (let index = this.live.length - 1; index >= 0; index -= 1) {
      if (spent(this.live[index])) this.releaseAt(index);
    }
  }

  /** Drop one record by identity. */
  release(record: R): void {
    const index = this.live.indexOf(record);
    if (index >= 0) this.releaseAt(index);
  }

  /** Let go of everything. */
  clear(): void {
    while (this.live.length > 0) this.releaseAt(this.live.length - 1);
  }

  private releaseAt(index: number): void {
    const [record] = this.live.splice(index, 1);
    if (record !== undefined) this.onRelease?.(record);
  }
}
