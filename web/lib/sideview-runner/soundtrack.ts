import type { RunnerSoundtrack } from "./contract";

const DEFAULT_SOUNDTRACK_VOLUME = 0.34;

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
  dispose(): void;
}

interface RunnerSoundtrackPlaybackOptions {
  readonly createAudio?: (source: string) => AudioElementLike;
  readonly random?: () => number;
  readonly volume?: number;
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
  let current: AudioElementLike | undefined;
  let index = 0;
  let disposed = false;
  let playbackAllowed = false;
  let latestAttempt = 0;

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

  const playNext = () => {
    if (disposed) return;
    if (current) current.removeEventListener("ended", playNext);
    const track = queue[index % queue.length];
    index += 1;
    current = createAudio(resolveUrl(track.audio));
    current.volume = volume;
    current.addEventListener("ended", playNext);
    attemptPlayback();
  };

  playNext();
  return {
    unlock() {
      if (!playbackAllowed) attemptPlayback();
    },
    dispose() {
      disposed = true;
      latestAttempt += 1;
      if (current) {
        current.removeEventListener("ended", playNext);
        current.pause();
        current = undefined;
      }
    },
  };
}
