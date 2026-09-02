// Per-event audio one-shots: the cue is specific to HOW the obstacle was
// avoided, which is the compatible fraction of "feels musical" — the seam
// rule forbids beat sync, but nothing forbids the world answering each verb.
//
// The system detects edges (takeoff, the air jump, landing, the slide, a
// cleared hazard, a collect, a survivable hit, death) by comparing world state across frames
// and reports them to an injected sink. The Web Audio sink plays the authored
// manifest realization for the bound effect — synthesizing an oscillator
// sweep, or decoding a clip the run generated once — with no hidden cue
// table, while headless suites inject a recorder. The run's edges also reach
// a music sink: the stinger the effect binding owns and the authored action
// on the soundtrack (a fade, a pause, a duck) are posted side by side.

import type { GameSystem } from "@/lib/game-systems/systems";
import type { RunnerAudio, RunnerAudioEvent, RunnerMusicEvent } from "./contract";
import type { RunnerWorld } from "./world";

export type RunnerAudioCue = RunnerAudioEvent;

export interface RunnerAudioSink {
  /** `strength` grades the cue: the collect pitch rises with the chain. */
  play(cue: RunnerAudioCue, strength: number): void;
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
  return {
    id: "runner/audio",
    // v3: the run's edges also reach the music sink.
    contractVersion: "audio-system-v3",
    reads: ["avatar", "obstacles", "run", "vitals"],
    writes: [],
    after: ["runner/run-loop", "runner/hud"],
    update(world) {
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
 * clip is fetched as soon as the sink exists and decoded on the first cue
 * that needs it; a cue that fires before its clip is ready is dropped rather
 * than delayed, because a late cue is worse than a missing one.
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
  for (const effect of audio.effects) {
    if (effect.realization.kind !== "generated_clip_v1") continue;
    const clip = effect.realization.clip;
    if (!bytes.has(clip)) bytes.set(clip, fetchBytes(resolveUrl(clip)));
  }

  const decodeClip = (ctx: AudioContext, clip: string) => {
    const pending = bytes.get(clip);
    if (!pending || decoding.has(clip)) return;
    decoding.add(clip);
    void pending
      .then((data) => ctx.decodeAudioData(data.slice(0)))
      .then((buffer) => {
        buffers.set(clip, buffer);
      })
      .catch(() => undefined)
      .finally(() => decoding.delete(clip));
  };

  return {
    play(cue, strength) {
      try {
        context ??= new AudioContext();
        if (context.state === "suspended") void context.resume();
        const effect = effects.get(audio.bindings[cue]);
        if (!effect) return;
        const voice = effect.realization;
        const lift = strengthLift(strength, voice.strengthPitchMultiplier);
        const now = context.currentTime;
        const gain = context.createGain();
        if (voice.kind === "generated_clip_v1") {
          const buffer = buffers.get(voice.clip);
          if (!buffer) {
            decodeClip(context, voice.clip);
            return;
          }
          const source = context.createBufferSource();
          source.buffer = buffer;
          source.playbackRate.setValueAtTime(lift, now);
          gain.gain.setValueAtTime(voice.gain, now);
          source.connect(gain).connect(context.destination);
          source.start(now);
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
