// Per-event audio one-shots: the cue is specific to HOW the obstacle was
// avoided, which is the compatible fraction of "feels musical" — the seam
// rule forbids beat sync, but nothing forbids the world answering each verb.
//
// The system detects edges (takeoff, the air jump, landing, the slide, a
// cleared hazard, a collect, a survivable hit, death) by comparing world state across frames
// and reports them to an injected sink, and posts one announcement - the
// stage start - on its first frame of a boot. The Web Audio sink plays the
// authored manifest realization for the bound effect — synthesizing an
// oscillator sweep, or decoding a clip the run generated once, a spoken line
// among them — with no hidden cue table, while headless suites inject a
// recorder. The run's edges also reach a music sink: the stinger the effect
// binding owns and the authored action on the soundtrack (a fade, a pause, a
// duck) are posted side by side.

import type { GameSystem } from "@/lib/game-systems/systems";
import {
  isClipRealization,
  type RunnerAudio,
  type RunnerAudioEvent,
  type RunnerMusicEvent,
} from "./contract";
import type { RunnerWorld } from "./world";

export type RunnerAudioCue = RunnerAudioEvent;

export interface RunnerAudioSink {
  /** `strength` grades the cue: the collect pitch rises with the chain. */
  play(cue: RunnerAudioCue, strength: number): void;
  /**
   * Retry a browser-policy-blocked start from a trusted user gesture. Only
   * the announcement waits for it: every other cue is a consequence of an
   * input, which is itself the gesture.
   */
  unlock?(): void;
}

export const SILENT_AUDIO_SINK: RunnerAudioSink = Object.freeze({
  play: () => undefined,
});

export interface RunnerMusicSink {
  /** The soundtrack performs its authored action for this run edge. */
  transition(event: RunnerMusicEvent): void;
}

export const SILENT_MUSIC_SINK: RunnerMusicSink = Object.freeze({
  transition: () => undefined,
});

/**
 * The cue system: presentation, so it writes no world key. The explicit
 * edges pin it to the very end of the frame - after the run-loop that
 * settles the phase and score, and after the hud that closes the drawing
 * chain - so the sealed order stays unique regardless of registration order.
 */
export function createAudioSystem(
  sink: RunnerAudioSink,
  music: RunnerMusicSink = SILENT_MUSIC_SINK,
): GameSystem<RunnerWorld> {
  let prevJumpImpulses = 0;
  let prevGrounded = true;
  let prevSliding = false;
  let prevDead = false;
  let prevDistance = 0;
  let announced = false;
  return {
    id: "runner/audio",
    // v4: the stage start is announced once per boot.
    contractVersion: "audio-system-v4",
    reads: ["avatar", "obstacles", "run", "vitals"],
    writes: [],
    after: ["runner/run-loop", "runner/hud"],
    update(world) {
      // The announcement rides the first frame of a boot: with a stage-start
      // moment that is the intro's first frame, so the line and the rip are
      // one beat; without one it is the first running frame. Never on a
      // restart - the intro plays once per boot, and so does this.
      if (!announced) {
        announced = true;
        sink.play("stage_start", 1);
      }
      const avatar = world.avatar;
      const dead = world.run.phase === "dead";
      const restarted = avatar.distanceColumns < prevDistance;
      if (restarted) {
        music.transition("restart");
        prevJumpImpulses = avatar.jumpImpulses;
        prevGrounded = avatar.grounded;
        prevSliding = avatar.sliding;
        prevDead = dead;
        prevDistance = avatar.distanceColumns;
        return;
      }

      if (avatar.jumpImpulses > prevJumpImpulses) {
        sink.play(avatar.airJumpsUsed > 0 ? "air_jump" : "takeoff", 1);
      }
      if (avatar.grounded && !prevGrounded && !dead) {
        sink.play("land", 1);
      }
      if (avatar.sliding && !prevSliding) {
        sink.play("slide", 1);
      }
      if (!dead) {
        for (const hazard of world.segments.chunks.flatMap((chunk) => chunk.hazards)) {
          const passed = hazard.worldColumn + 1;
          if (prevDistance < passed && avatar.distanceColumns >= passed) {
            sink.play("hazard_cleared", 1);
          }
        }
        for (let i = 0; i < world.obstacles.collectedThisFrame.length; i += 1) {
          sink.play("collect", Math.min(1, world.run.chain / 30));
        }
        // The vitals system sets this on the frame a drain connects; a hit
        // that ends the run is death's to answer, not this cue's.
        if (world.vitals.hurtThisFrame) {
          sink.play("hurt", 1);
          music.transition("hurt");
        }
      }
      if (dead && !prevDead) {
        sink.play("death", 1);
        music.transition("death");
      }

      prevJumpImpulses = avatar.jumpImpulses;
      prevGrounded = avatar.grounded;
      prevSliding = avatar.sliding;
      prevDead = dead;
      prevDistance = avatar.distanceColumns;
    },
  };
}

/** The playback-rate lift a strength-graded cue applies to a realization. */
export function strengthLift(strength: number, multiplier: number): number {
  return 1 + Math.max(0, Math.min(1, strength)) * multiplier;
}

/**
 * The browser sink: a lazily created AudioContext (browsers demand a user
 * gesture before audio; the first post-gesture cue starts it) and the exact
 * authored realization reached through each event binding. Every generated
 * clip and spoken line is fetched as soon as the sink exists and decoded on
 * the first cue that needs it; a cue that fires before its clip is ready is
 * dropped rather than delayed, because a late cue is worse than a missing one.
 *
 * The one exception is the announcement. `stage_start` fires on the first
 * frame of a boot, before any clip can have decoded and before any gesture
 * can have unlocked the context, so it is held in a single slot and played
 * when the clip lands or `unlock()` lets the context start - and dropped the
 * moment any other cue fires, because by then the run has begun and an
 * announcement of its start is stale.
 */
export function createWebAudioSink(
  audio: RunnerAudio,
  resolveUrl: (path: string) => string,
  fetchBytes: (url: string) => Promise<ArrayBuffer> = (url) =>
    fetch(url).then((response) => response.arrayBuffer()),
): RunnerAudioSink {
  let context: AudioContext | null = null;
  const effects = new Map(audio.effects.map((effect) => [effect.effectId, effect]));
  const bytes = new Map<string, Promise<ArrayBuffer>>();
  const buffers = new Map<string, AudioBuffer>();
  const decoding = new Set<string>();
  let held: { readonly clip: string; readonly strength: number } | null = null;
  for (const effect of audio.effects) {
    if (!isClipRealization(effect.realization)) continue;
    const clip = effect.realization.clip;
    if (!bytes.has(clip)) bytes.set(clip, fetchBytes(resolveUrl(clip)));
  }

  const playBuffer = (
    ctx: AudioContext,
    buffer: AudioBuffer,
    gainValue: number,
    lift: number,
  ) => {
    const now = ctx.currentTime;
    const gain = ctx.createGain();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.playbackRate.setValueAtTime(lift, now);
    gain.gain.setValueAtTime(gainValue, now);
    source.connect(gain).connect(ctx.destination);
    source.start(now);
  };

  /** Play the held announcement if its clip is decoded and the context runs. */
  const releaseHeld = () => {
    if (!held || !context || context.state !== "running") return;
    const buffer = buffers.get(held.clip);
    if (!buffer) return;
    const effect = effects.get(audio.bindings.stage_start ?? "");
    const voice = effect?.realization;
    held = null;
    if (!voice || !isClipRealization(voice)) return;
    try {
      playBuffer(context, buffer, voice.gain, strengthLift(1, voice.strengthPitchMultiplier));
    } catch {
      // Same garnish rule as every other cue.
    }
  };

  const decodeClip = (ctx: AudioContext, clip: string) => {
    const pending = bytes.get(clip);
    if (!pending || decoding.has(clip)) return;
    decoding.add(clip);
    void pending
      .then((data) => ctx.decodeAudioData(data.slice(0)))
      .then((buffer) => {
        buffers.set(clip, buffer);
        releaseHeld();
      })
      .catch(() => undefined)
      .finally(() => decoding.delete(clip));
  };

  return {
    unlock() {
      if (!context || context.state !== "suspended") return;
      void context.resume().then(releaseHeld, () => undefined);
    },
    play(cue, strength) {
      try {
        context ??= new AudioContext();
        if (context.state === "suspended") void context.resume().then(releaseHeld, () => undefined);
        if (cue !== "stage_start") held = null;
        const effect = effects.get(audio.bindings[cue] ?? "");
        if (!effect) return;
        const voice = effect.realization;
        const lift = strengthLift(strength, voice.strengthPitchMultiplier);
        const now = context.currentTime;
        const gain = context.createGain();
        if (isClipRealization(voice)) {
          const buffer = buffers.get(voice.clip);
          if (!buffer || context.state !== "running") {
            decodeClip(context, voice.clip);
            if (cue === "stage_start") held = { clip: voice.clip, strength };
            return;
          }
          playBuffer(context, buffer, voice.gain, lift);
          return;
        }
        const seconds = voice.durationMilliseconds / 1_000;
        const oscillator = context.createOscillator();
        oscillator.type = voice.waveform;
        oscillator.frequency.setValueAtTime(voice.startFrequencyHz * lift, now);
        oscillator.frequency.exponentialRampToValueAtTime(
          Math.max(1, voice.endFrequencyHz * lift),
          now + seconds,
        );
        gain.gain.setValueAtTime(voice.gain, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start(now);
        oscillator.stop(now + seconds + 0.02);
      } catch {
        // Audio is a garnish: a context the browser refuses is not an error
        // the run should feel.
      }
    },
  };
}
