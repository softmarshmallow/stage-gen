// The runner's binding of the `soundtrack` family: an element, a queue, and
// the authored transitions the run's edges perform.
//
// This genre authors one half of the family. There is no place binding — the
// run is one endless stage, so there is nowhere for a pool to be narrowed to —
// and what it does author is the middleware vocabulary: an action on the music
// (stop, pause, resume, play) with a fade time and a curve, posted beside the
// stinger the effect bindings own, and an optional duck under a survivable hit.
//
// What is left in this file is the transport and the genre's own vocabulary.
// The transport is a browser `Audio` element per track, with the autoplay dance
// that goes with it: an optimistic start, a `playbackAllowed` flag the promise
// settles, and a retry from the first trusted gesture. The vocabulary is the
// three run edges and the map from each onto the family's `MusicAction`. The
// selection, the gesture gate, the fade machine and what a duck *is* are the
// family's, and the platformer instantiates the same object with the other half
// of it turned on.

import {
  fadeGain,
  ShuffleQueue,
  SoundtrackPlayer,
  soundtrackCatalog,
  type FadingTransport,
  type SoundtrackTrack,
} from "@/lib/families/soundtrack";
import { parseSoundtrackBlock, type SoundtrackBlockView } from "@/lib/families/soundtrack/manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import {
  RUNNER_BLOCKS,
  type RunnerMusicEvent,
  type RunnerMusicTransitions,
  type RunnerSoundtrack,
} from "./contract";

const DEFAULT_SOUNDTRACK_VOLUME = 0.34;

/**
 * The blocks this genre's soundtrack depends on.
 *
 * Two, because the authored file is two: `soundtrack` names the tracks, and
 * `audio` carries `[music.*]` — the action each run edge performs. A package
 * that moves either gets the refusal from the soundtrack, by name, which is the
 * point of a family taking its own dependency: `cues` reads `audio` as well,
 * and neither family speaks for the other.
 */
export const RUNNER_SOUNDTRACK_BLOCKS = Object.freeze([
  Object.freeze({ block: "soundtrack", version: RUNNER_BLOCKS.soundtrack }),
  Object.freeze({ block: "audio", version: RUNNER_BLOCKS.audio }),
]);

/** Gate the runner's soundtrack blocks. Refuses by naming `soundtrack` or `audio`. */
export function parseRunnerSoundtrackBlocks(blocks: BlockTable): readonly SoundtrackBlockView[] {
  return RUNNER_SOUNDTRACK_BLOCKS.map((binding) => parseSoundtrackBlock(blocks, binding));
}

/** Every edge is `continue`: the shape a consumer without a contract would assume. */
export const CONTINUE_MUSIC: RunnerMusicTransitions = Object.freeze({
  death: Object.freeze({ action: "continue", fadeSeconds: 0, curve: "linear" }),
  restart: Object.freeze({ action: "continue", fadeSeconds: 0, curve: "linear" }),
  hurt: null,
});

interface AudioElementLike {
  volume: number;
  play(): Promise<void>;
  pause(): void;
  addEventListener(type: "ended", listener: () => void): void;
  removeEventListener(type: "ended", listener: () => void): void;
}

export interface RunnerSoundtrackPlayback {
  /** Retry a browser-policy-blocked start from a trusted user gesture. */
  unlock(): void;
  /** Perform the authored music action for one run edge. */
  transition(event: RunnerMusicEvent): void;
  dispose(): void;
}

interface RunnerSoundtrackPlaybackOptions {
  readonly createAudio?: (source: string) => AudioElementLike;
  readonly random?: () => number;
  readonly volume?: number;
  /** The authored transitions; omitted means every edge continues. */
  readonly music?: RunnerMusicTransitions;
  /** Frame scheduler for fades; returns the cancel. Defaults to requestAnimationFrame. */
  readonly schedule?: (callback: () => void) => () => void;
  /** Monotonic milliseconds. Defaults to performance.now. */
  readonly now?: () => number;
}

function defaultSchedule(callback: () => void): () => void {
  if (typeof requestAnimationFrame === "function") {
    const handle = requestAnimationFrame(callback);
    return () => cancelAnimationFrame(handle);
  }
  const handle = setTimeout(callback, 16);
  return () => clearTimeout(handle);
}

function defaultNow(): number {
  return typeof performance === "object" ? performance.now() : Date.now();
}

/**
 * The element transport: one `Audio` per track, and the autoplay dance.
 *
 * A browser refuses an audible start no gesture asked for, and answers with a
 * rejected promise rather than an error, so "is it playing" is a flag settled
 * asynchronously and every attempt is tokened — a stale rejection must not mark
 * a later element blocked.
 */
function createElementTransport(
  resolveUrl: (path: string) => string,
  createAudio: (source: string) => AudioElementLike,
): FadingTransport {
  let current: AudioElementLike | undefined;
  let listener: (() => void) | undefined;
  let playbackAllowed = false;
  let latestAttempt = 0;
  let disposed = false;

  const attempt = () => {
    if (!current || disposed) return;
    const candidate = current;
    const token = ++latestAttempt;
    void candidate.play().then(
      () => {
        if (!disposed && current === candidate && latestAttempt === token) playbackAllowed = true;
      },
      () => {
        if (!disposed && current === candidate && latestAttempt === token) playbackAllowed = false;
      },
    );
  };

  return {
    play(track: SoundtrackTrack, onEnded: () => void, startGain?: number) {
      if (current && listener) current.removeEventListener("ended", listener);
      current = createAudio(resolveUrl(track.source));
      current.volume = startGain ?? 1;
      listener = onEnded;
      current.addEventListener("ended", listener);
      attempt();
    },
    stop() {
      disposed = true;
      latestAttempt += 1;
      if (current) {
        current.pause();
        current = undefined;
      }
    },
    pause() {
      current?.pause();
    },
    resume() {
      attempt();
    },
    gain: () => (current && !disposed ? current.volume : null),
    setGain(value: number) {
      if (current) current.volume = value;
    },
    get allowed() {
      return playbackAllowed;
    },
  };
}

/**
 * Start the declared soundtrack optimistically. Browsers that permit audible
 * autoplay begin at once; browsers that refuse it keep the same audio element
 * ready for `unlock()` on the first trusted key or pointer gesture.
 */
export function createRunnerSoundtrackPlayback(
  soundtrack: RunnerSoundtrack,
  resolveUrl: (path: string) => string,
  options: RunnerSoundtrackPlaybackOptions = {},
): RunnerSoundtrackPlayback {
  const createAudio = options.createAudio ?? ((source: string) => new Audio(source));
  const volume = options.volume ?? DEFAULT_SOUNDTRACK_VOLUME;
  const music = options.music ?? CONTINUE_MUSIC;
  const player = new SoundtrackPlayer({
    selector: new ShuffleQueue(
      soundtrackCatalog(
        soundtrack.tracks.map((track) => ({ trackId: track.trackId, source: track.audio })),
      ),
      options.random ?? Math.random,
    ),
    transport: createElementTransport(resolveUrl, createAudio),
    // No gesture gate: a browser that permits autoplay should be playing before
    // the player has touched anything, and one that refuses is retried by
    // `unlock`. The gate is the platformer's half of the same family.
    start: "eager",
    gain: volume,
    fades: { schedule: options.schedule ?? defaultSchedule, now: options.now ?? defaultNow },
  });

  return {
    unlock() {
      player.unlock();
    },
    transition(event) {
      if (event === "death") {
        player.transition(music.death);
        return;
      }
      if (event === "restart") {
        player.transition(music.restart);
        return;
      }
      const duck = music.hurt;
      if (duck) player.duck(duck);
    },
    dispose() {
      player.stop();
    },
  };
}

export { fadeGain };
