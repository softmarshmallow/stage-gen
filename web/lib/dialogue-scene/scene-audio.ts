/**
 * Script-driven music for a scenario, as a pure decision plus a thin transport.
 *
 * The runtime already says which tracks are playing at any moment - `audio play`
 * and `audio stop` fold into `state.tracks`. All that is left is the difference
 * between two moments, and that is a pure function so it can be tested; the part
 * that touches `HTMLAudioElement` cannot be, and is kept as small as possible
 * behind `SceneAudioTransport`.
 *
 * Browsers will not start audio before a user gesture, and a visual novel is
 * nothing but user gestures, so the first advance unlocks it. Until then the
 * player records what should be playing and starts it the moment it may.
 */

import type { DialogueSceneFixture } from "./schema";

export interface SceneAudioTransport {
  play: (trackId: string, src: string, loop: boolean) => void;
  stop: (trackId: string) => void;
}

export interface TrackTransition {
  readonly start: readonly string[];
  readonly stop: readonly string[];
}

/**
 * What changed between two moments of playback.
 *
 * Set difference, deliberately order-insensitive: `state.tracks` is a set of
 * what is playing, and a track that is playing before and after must not be
 * restarted - a restart is audible, and the script did not ask for one.
 */
export function trackTransition(
  previous: readonly string[],
  next: readonly string[],
): TrackTransition {
  const before = new Set(previous);
  const after = new Set(next);
  return Object.freeze({
    start: Object.freeze(next.filter((track) => !before.has(track))),
    stop: Object.freeze(previous.filter((track) => !after.has(track))),
  });
}

export class ScenarioAudio {
  private readonly sources: ReadonlyMap<string, string>;
  private readonly transport: SceneAudioTransport;
  private playing: readonly string[] = [];
  private unlocked = false;

  constructor(fixture: DialogueSceneFixture, transport: SceneAudioTransport) {
    this.sources = new Map(fixture.tracks.map((track) => [track.trackId, track.src]));
    this.transport = transport;
  }

  /** Call from the first user gesture; starts whatever the script already wants. */
  unlock(): void {
    if (this.unlocked) return;
    this.unlocked = true;
    for (const trackId of this.playing) this.start(trackId);
  }

  /** Bring the transport in line with what the scenario says is playing now. */
  apply(tracks: readonly string[]): void {
    const { start, stop } = trackTransition(this.playing, tracks);
    this.playing = [...tracks];
    if (!this.unlocked) return;
    for (const trackId of stop) this.transport.stop(trackId);
    for (const trackId of start) this.start(trackId);
  }

  /** Everything off - for leaving the scene, where the script gets no say. */
  stopAll(): void {
    for (const trackId of this.playing) this.transport.stop(trackId);
    this.playing = [];
  }

  private start(trackId: string): void {
    const src = this.sources.get(trackId);
    // The fixture validator refused a scenario that plays a track with no audio,
    // so a miss here would be a contract violation rather than a silence to
    // paper over. Skipping is still better than throwing mid-scene.
    if (src === undefined) return;
    this.transport.play(trackId, src, true);
  }
}

/** The real transport: one looping element per track, created on first use. */
export function htmlAudioTransport(volume = 0.55): SceneAudioTransport {
  const elements = new Map<string, HTMLAudioElement>();
  return {
    play(trackId, src, loop) {
      let element = elements.get(trackId);
      if (element === undefined) {
        element = new Audio(src);
        element.loop = loop;
        element.volume = volume;
        elements.set(trackId, element);
      }
      // A play() rejection is the browser declining, not a program error.
      void element.play().catch(() => undefined);
    },
    stop(trackId) {
      const element = elements.get(trackId);
      if (element === undefined) return;
      element.pause();
      element.currentTime = 0;
    },
  };
}
