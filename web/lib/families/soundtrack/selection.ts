// What plays next, and the two named policies a package may author for it.
//
// The two genres arrived at two answers and neither is wrong: the platformer
// authors `selection = "shuffle"` with `no_immediate_repeat = true` and wants a
// cyclic bag it can narrow to a map's pool, seeded off the package digest so
// two runs of one package hear the same order; the runner shuffles its handful
// of tracks once at boot and cycles them. That is a *parameter* of the family
// and not a branch in it — the same shape as the clock's holders or the
// vitals' sources — so both live here, as two selectors behind one interface,
// and a genre names the one its package authored.

import { poolKey, resolvePool, type SoundtrackTrack } from "./track";

export interface TrackSelector {
  /** The tracks currently admitted. */
  readonly pool: readonly SoundtrackTrack[];
  /** What `take` would return, without consuming it; null when nothing is planned. */
  readonly planned: SoundtrackTrack | null;
  /** Consume the next track, or null once the selection is exhausted. */
  take(): SoundtrackTrack | null;
  /** Forget what is planned: nothing plays until something is selected again. */
  clear(): void;
  /**
   * Narrow to a named pool. `retain` is a track the caller intends to keep
   * playing across the change, which counts as the destination's first
   * consumed item. Returns false when the pool is the one already bound.
   */
  bindPool(trackIds: readonly string[], retain?: string): boolean;
}

/** FNV-1a over a string: the platformer's own seeding, so its bags replay. */
export function seedFromString(value: string): number {
  let seed = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    seed ^= value.charCodeAt(index);
    seed = Math.imul(seed, 0x01000193);
  }
  return seed >>> 0;
}

/** A small deterministic generator used only to order a finite shuffle bag. */
function nextRandom(state: { value: number }): number {
  state.value = (state.value + 0x6d2b79f5) >>> 0;
  let value = state.value;
  value = Math.imul(value ^ (value >>> 15), value | 1);
  value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
  return ((value ^ (value >>> 14)) >>> 0) / 0x1_0000_0000;
}

/**
 * A deterministic, cyclic shuffle bag.
 *
 * Every multi-track bag is exhausted once before refill, and the first item
 * after refill cannot equal the prior item. A one-track catalog ends after one
 * play, because a repeat-free cycle is impossible for that catalog — which is a
 * stated contract and not an oversight.
 */
export class ShuffleBag implements TrackSelector {
  private readonly catalog: readonly SoundtrackTrack[];
  private admitted: readonly SoundtrackTrack[];
  private admittedKey: string;
  private readonly randomState: { value: number };
  private bag: SoundtrackTrack[] = [];
  private lastTrackId: string | null = null;

  constructor(
    catalog: readonly SoundtrackTrack[],
    seed: string,
    trackIds?: readonly string[],
  ) {
    this.catalog = catalog;
    this.admitted = resolvePool(catalog, trackIds);
    this.admittedKey = poolKey(this.admitted);
    this.randomState = { value: seedFromString(seed) };
    this.refill();
  }

  get pool(): readonly SoundtrackTrack[] {
    return this.admitted;
  }

  get planned(): SoundtrackTrack | null {
    return this.bag[0] ?? null;
  }

  take(): SoundtrackTrack | null {
    const track = this.bag.shift();
    if (!track) return null;
    this.lastTrackId = track.trackId;
    this.refill();
    return track;
  }

  clear(): void {
    this.bag = [];
  }

  bindPool(trackIds: readonly string[], retain?: string): boolean {
    const next = resolvePool(this.catalog, trackIds);
    const key = poolKey(next);
    if (key === this.admittedKey) return false;
    this.admitted = next;
    this.admittedKey = key;
    this.bag = [];
    this.refill(retain);
    return true;
  }

  /** Whether a track is admitted by the pool currently bound. */
  admits(trackId: string): boolean {
    return this.admitted.some((track) => track.trackId === trackId);
  }

  private refill(excludedTrackId?: string): void {
    if (this.bag.length > 0) return;
    if (excludedTrackId === undefined && this.admitted.length === 1 && this.lastTrackId !== null) {
      return;
    }
    const next = this.admitted.filter((track) => track.trackId !== excludedTrackId);
    for (let index = next.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(nextRandom(this.randomState) * (index + 1));
      [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
    }
    if (this.lastTrackId !== null && next[0]?.trackId === this.lastTrackId) {
      const replacement = next.findIndex((track) => track.trackId !== this.lastTrackId);
      if (replacement > 0) [next[0], next[replacement]] = [next[replacement], next[0]];
    }
    this.bag = next;
  }
}

/**
 * One shuffle at boot, then the queue cycles forever.
 *
 * The runner's policy. It binds no pool — this genre authors no place — so
 * `bindPool` refuses rather than silently doing nothing: a package that asks a
 * queue-selected soundtrack for a place binding has authored two things that do
 * not go together, and hearing about it at the call is better than at the
 * mixing desk.
 */
export class ShuffleQueue implements TrackSelector {
  private readonly queue: readonly SoundtrackTrack[];
  private index = 0;
  private spent = false;

  constructor(catalog: readonly SoundtrackTrack[], random: () => number) {
    const tracks = [...catalog];
    for (let index = tracks.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(random() * (index + 1));
      [tracks[index], tracks[swap]] = [tracks[swap], tracks[index]];
    }
    this.queue = Object.freeze(tracks);
  }

  get pool(): readonly SoundtrackTrack[] {
    return this.queue;
  }

  get planned(): SoundtrackTrack | null {
    if (this.spent) return null;
    return this.queue[this.index % this.queue.length] ?? null;
  }

  take(): SoundtrackTrack | null {
    if (this.spent) return null;
    const track = this.queue[this.index % this.queue.length];
    this.index += 1;
    return track ?? null;
  }

  clear(): void {
    this.spent = true;
  }

  bindPool(): boolean {
    throw new Error("a queue-selected soundtrack has no place binding to narrow");
  }
}
