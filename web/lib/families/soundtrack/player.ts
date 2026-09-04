// The soundtrack: what is playing, what a place admits, and what the run's
// edges do to it.
//
// Two genres had one half each. The platformer shipped a fully extracted
// deterministic player — shuffle bag, map-scoped pool, a transport port — that
// its scene ignored in favour of `new Audio`, with no transitions at all; the
// runner shipped transitions, fades and a duck, over a queue with no place
// binding. Neither half is a genre's: a place that narrows the catalog and an
// edge that fades it are both things a soundtrack does, and this is the one
// object that does both.
//
// What stays outside it is the transport — a browser element, a Web Audio
// node, a recorder in a headless suite — because "how a sound is made audible"
// is the host's, and because that is the seam that let the platformer's player
// be tested without a browser in the first place.

import { FadeRunner, type FadeCurve, type FadeStep } from "./fade";
import type { TrackSelector } from "./selection";
import type { SoundtrackTrack } from "./track";

export type { SoundtrackTrack };

/** How a sound is made audible. Everything above this line is deterministic. */
export interface SoundtrackTransport {
  /**
   * Start `track`, and call `onEnded` when it finishes.
   *
   * `startGain` is the gain the track should begin at when the host has one to
   * set — a fade-in starts at silence — and is ignored by a transport with no
   * volume of its own.
   */
  play(track: SoundtrackTrack, onEnded: () => void, startGain?: number): void;
  stop(): void;
}

/** A transport a fade can act on: it has a gain, and it can be halted and retried. */
export interface FadingTransport extends SoundtrackTransport {
  pause(): void;
  /** Retry playback of whatever is loaded — a policy-blocked start, or a resume. */
  resume(): void;
  /** The current gain, or null when nothing is loaded. */
  gain(): number | null;
  setGain(value: number): void;
  /** Whether the host has playback running; a blocked start answers false. */
  readonly allowed: boolean;
}

export type SoundtrackSnapshot = Readonly<{
  started: boolean;
  current_track_id: string | null;
  next_track_id: string | null;
}>;

/** What one authored edge does to the music. */
export type MusicAction = Readonly<{
  action: "continue" | "stop" | "pause" | "play" | "resume";
  fadeSeconds: number;
  curve: FadeCurve;
}>;

/** The dip under a stinger: down, hold, back up. */
export type MusicDuck = Readonly<{
  duckGain: number;
  fadeSeconds: number;
  holdSeconds: number;
  recoverySeconds: number;
  curve: FadeCurve;
}>;

export type SoundtrackPlayerOptions = Readonly<{
  /** Which track plays next: a bag, a queue, or a genre's own policy. */
  selector: TrackSelector;
  transport: SoundtrackTransport;
  /**
   * When the first track starts.
   *
   * `gesture` waits to be asked, which is what a browser's autoplay policy
   * makes of a scene that has never been touched; `eager` starts at once and
   * lets a refused start be retried on the first gesture instead.
   */
  start?: "gesture" | "eager";
  /** The gain a track plays at when nothing is fading it. */
  gain?: number;
  onStateChange?: (snapshot: SoundtrackSnapshot) => void;
  /** Frame scheduler and clock for fades; required for any genre with transitions. */
  fades?: Readonly<{ schedule: (callback: () => void) => () => void; now: () => number }>;
}>;

/**
 * The player: selection, place binding, the gesture gate, and the fades.
 *
 * Lifecycle-bound by construction — it owns what is playing and the callback
 * that says the track ended — so it is a class, and every method is safe to
 * call after `stop`.
 */
export class SoundtrackPlayer {
  private readonly selector: TrackSelector;
  private readonly transport: SoundtrackTransport;
  private readonly onStateChange?: (snapshot: SoundtrackSnapshot) => void;
  private readonly fader: FadeRunner | null;
  private readonly gain: number;
  private currentTrack: SoundtrackTrack | null = null;
  private hasStarted = false;
  private stopped = false;
  private playToken = 0;
  /** True from a stop or pause until the restart action; ducks are ignored meanwhile. */
  private halted = false;

  constructor(options: SoundtrackPlayerOptions) {
    this.selector = options.selector;
    this.transport = options.transport;
    this.onStateChange = options.onStateChange;
    this.gain = options.gain ?? 1;
    this.fader = options.fades
      ? new FadeRunner({
          schedule: options.fades.schedule,
          now: options.fades.now,
          gain: () => this.fading().gain(),
          setGain: (value) => this.fading().setGain(value),
        })
      : null;
    if (options.start === "eager") {
      this.hasStarted = true;
      this.playNext(this.gain);
    }
  }

  get current_track_id(): string | null {
    return this.currentTrack?.trackId ?? null;
  }

  get next_track_id(): string | null {
    return this.selector.planned?.trackId ?? null;
  }

  get started(): boolean {
    return this.hasStarted;
  }

  snapshot(): SoundtrackSnapshot {
    return Object.freeze({
      started: this.hasStarted,
      current_track_id: this.current_track_id,
      next_track_id: this.next_track_id,
    });
  }

  /** Must be called synchronously from a real pointer or keyboard gesture. */
  beginFromPlayerGesture(): boolean {
    if (this.stopped || this.hasStarted || this.selector.planned === null) return false;
    this.hasStarted = true;
    this.playNext(this.gain);
    return true;
  }

  /**
   * Retry a start the host refused.
   *
   * Only for an `eager` player: a `gesture` player has not asked yet, and a
   * halted one was stopped on purpose.
   */
  unlock(): void {
    if (this.stopped || this.halted) return;
    const transport = this.maybeFading();
    if (transport && !transport.allowed) transport.resume();
  }

  /**
   * Narrow playback to a named pool — the place binding.
   *
   * If the current track belongs to the destination it keeps playing and only
   * the planned remainder changes; otherwise playback switches at once. The
   * prior track remains the no-repeat sentinel across the switch.
   */
  bindPool(trackIds: readonly string[]): boolean {
    if (this.stopped) return false;
    const current = this.currentTrack;
    const admitted = current !== null && trackIds.includes(current.trackId);
    const retained = admitted || !this.hasStarted;
    // A retained current track counts as the first consumed item of the
    // destination's new bag: it must not be scheduled a second time before
    // every other admitted track has had its turn.
    if (!this.selector.bindPool(trackIds, admitted && current ? current.trackId : undefined)) {
      return false;
    }
    if (retained) {
      this.emitState();
      return true;
    }
    // Invalidate the prior transport callback before replacing its media.
    this.currentTrack = null;
    this.playToken += 1;
    this.playNext(this.gain);
    return true;
  }

  /** Perform one authored edge. */
  transition(action: MusicAction): void {
    if (this.stopped || this.currentTrack === null || action.action === "continue") return;
    const transport = this.fading();
    if (action.action === "stop" || action.action === "pause") {
      this.halted = true;
      this.fade([{ to: 0, seconds: action.fadeSeconds, curve: action.curve }], () =>
        transport.pause(),
      );
      return;
    }
    if (!this.halted) return;
    this.halted = false;
    if (action.action === "play") {
      // The stopped element may still be mid-fade; it is done either way.
      transport.pause();
      this.playNext(0);
    } else {
      transport.setGain(0);
      transport.resume();
    }
    this.fade([{ to: this.gain, seconds: action.fadeSeconds, curve: action.curve }]);
  }

  /** Dip under a stinger and come back; ignored while halted. */
  duck(duck: MusicDuck): void {
    if (this.stopped || this.currentTrack === null || this.halted) return;
    const ducked = this.gain * duck.duckGain;
    this.fade([
      { to: ducked, seconds: duck.fadeSeconds, curve: duck.curve },
      { to: ducked, seconds: duck.holdSeconds, curve: "linear" },
      { to: this.gain, seconds: duck.recoverySeconds, curve: duck.curve },
    ]);
  }

  /** Silence the run for good. */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.hasStarted = false;
    this.currentTrack = null;
    this.playToken += 1;
    this.selector.clear();
    this.fader?.cancel();
    this.transport.stop();
    this.emitState();
  }

  private playNext(startGain: number): void {
    if (this.stopped) return;
    this.fader?.cancel();
    const track = this.selector.take();
    if (!track) {
      this.currentTrack = null;
      this.emitState();
      return;
    }
    this.currentTrack = track;
    const token = ++this.playToken;
    this.emitState();
    this.transport.play(
      track,
      () => {
        if (this.stopped || token !== this.playToken) return;
        this.currentTrack = null;
        this.playNext(this.gain);
      },
      startGain,
    );
  }

  private fade(steps: readonly FadeStep[], onSettled?: () => void): void {
    if (!this.fader) throw new Error("a soundtrack with transitions requires a fade scheduler");
    this.fader.run(steps, onSettled);
  }

  private fading(): FadingTransport {
    const transport = this.maybeFading();
    if (!transport) {
      throw new Error("a soundtrack with transitions requires a transport with a gain");
    }
    return transport;
  }

  private maybeFading(): FadingTransport | null {
    const transport = this.transport as FadingTransport;
    return typeof transport.gain === "function" ? transport : null;
  }

  private emitState(): void {
    this.onStateChange?.(this.snapshot());
  }
}
