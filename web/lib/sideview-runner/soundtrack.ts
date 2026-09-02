// The soundtrack element and the authored transitions it performs at the
// run's edges. Middleware vocabulary: an action on the music (stop, pause,
// resume, play) with a fade time and curve, posted beside the stinger the
// effect bindings own, and an optional duck under a survivable hit. Fades run
// on the element's volume through an injectable frame scheduler, one at a
// time; a new transition cancels the one in flight.

import type {
  MusicFadeCurve,
  RunnerMusicEvent,
  RunnerMusicTransitions,
  RunnerSoundtrack,
} from "./contract";

const DEFAULT_SOUNDTRACK_VOLUME = 0.34;
/** Web Audio's exponential-ramp floor: a geometric fade cannot pass through zero. */
const EXPONENTIAL_FLOOR = 0.0001;

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

interface FadeStep {
  readonly to: number;
  readonly seconds: number;
  readonly curve: MusicFadeCurve;
}

function shuffledTracks(
  soundtrack: RunnerSoundtrack,
  random: () => number,
): RunnerSoundtrack["tracks"] {
  const tracks = [...soundtrack.tracks];
  for (let index = tracks.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [tracks[index], tracks[swap]] = [tracks[swap], tracks[index]];
  }
  return tracks;
}

/** The gain at `progress` (0..1) along a fade, as Web Audio's ramps define the shapes. */
export function fadeGain(
  from: number,
  to: number,
  progress: number,
  curve: MusicFadeCurve,
): number {
  const clamped = Math.max(0, Math.min(1, progress));
  if (curve === "linear") return from + (to - from) * clamped;
  const start = Math.max(from, EXPONENTIAL_FLOOR);
  const end = Math.max(to, EXPONENTIAL_FLOOR);
  return start * (end / start) ** clamped;
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
  const queue = shuffledTracks(soundtrack, options.random ?? Math.random);
  const volume = options.volume ?? DEFAULT_SOUNDTRACK_VOLUME;
  const music = options.music ?? CONTINUE_MUSIC;
  const schedule = options.schedule ?? defaultSchedule;
  const now = options.now ?? defaultNow;
  let current: AudioElementLike | undefined;
  let index = 0;
  let disposed = false;
  let playbackAllowed = false;
  let latestAttempt = 0;
  /** True from a stop or pause until the restart action; ducks are ignored meanwhile. */
  let halted = false;

  let steps: FadeStep[] = [];
  let stepStart = 0;
  let stepFrom = 0;
  let settled: (() => void) | undefined;
  let cancelTick: (() => void) | undefined;

  const cancelFade = () => {
    cancelTick?.();
    cancelTick = undefined;
    steps = [];
    settled = undefined;
  };

  const tick = () => {
    cancelTick = undefined;
    const element = current;
    if (!element || disposed) {
      steps = [];
      return;
    }
    while (steps.length > 0) {
      const step = steps[0];
      const elapsed = (now() - stepStart) / 1_000;
      const progress = step.seconds <= 0 ? 1 : Math.min(1, elapsed / step.seconds);
      element.volume = progress >= 1 ? step.to : fadeGain(stepFrom, step.to, progress, step.curve);
      if (progress < 1) {
        cancelTick = schedule(tick);
        return;
      }
      steps.shift();
      stepStart = now();
      stepFrom = element.volume;
    }
    const done = settled;
    settled = undefined;
    done?.();
  };

  const fade = (next: readonly FadeStep[], onSettled?: () => void) => {
    cancelFade();
    if (!current) return;
    steps = [...next];
    stepStart = now();
    stepFrom = current.volume;
    settled = onSettled;
    tick();
  };

  const attemptPlayback = () => {
    if (!current || disposed) return;
    const candidate = current;
    const attempt = ++latestAttempt;
    void candidate.play().then(
      () => {
        if (!disposed && current === candidate && latestAttempt === attempt) {
          playbackAllowed = true;
        }
      },
      () => {
        if (!disposed && current === candidate && latestAttempt === attempt) {
          playbackAllowed = false;
        }
      },
    );
  };

  const onEnded = () => playNext(volume);
  const playNext = (startVolume: number) => {
    if (disposed) return;
    cancelFade();
    if (current) current.removeEventListener("ended", onEnded);
    const track = queue[index % queue.length];
    index += 1;
    current = createAudio(resolveUrl(track.audio));
    current.volume = startVolume;
    current.addEventListener("ended", onEnded);
    attemptPlayback();
  };

  playNext(volume);
  return {
    unlock() {
      if (!playbackAllowed && !halted) attemptPlayback();
    },
    transition(event) {
      if (disposed || !current) return;
      if (event === "death") {
        const action = music.death;
        if (action.action === "continue") return;
        halted = true;
        fade([{ to: 0, seconds: action.fadeSeconds, curve: action.curve }], () =>
          current?.pause(),
        );
        return;
      }
      if (event === "restart") {
        const action = music.restart;
        if (action.action === "continue" || !halted) return;
        halted = false;
        if (action.action === "play") {
          // The stopped element may still be mid-fade; it is done either way.
          current.pause();
          playNext(0);
        } else {
          current.volume = 0;
          attemptPlayback();
        }
        fade([{ to: volume, seconds: action.fadeSeconds, curve: action.curve }]);
        return;
      }
      const duck = music.hurt;
      if (!duck || halted) return;
      const ducked = volume * duck.duckGain;
      fade([
        { to: ducked, seconds: duck.fadeSeconds, curve: duck.curve },
        { to: ducked, seconds: duck.holdSeconds, curve: "linear" },
        { to: volume, seconds: duck.recoverySeconds, curve: duck.curve },
      ]);
    },
    dispose() {
      disposed = true;
      latestAttempt += 1;
      cancelFade();
      if (current) {
        current.pause();
        current = undefined;
      }
    },
  };
}
