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

import { createCueSystem } from "@/lib/families/cues";
import { parseCuesBlock, type CuesBlockView } from "@/lib/families/cues/manifest";
import type { BlockTable } from "@/lib/manifest/blocks";
import type { GameSystem } from "@/lib/kernel/systems";
import {
  isClipRealization,
  type RunnerAudio,
  type RunnerAudioEvent,
  type RunnerMusicEvent,
} from "./contract";
import type { RunnerEvent } from "./vitals";
import { RUNNER_BLOCKS } from "./contract";
import type { RunnerWorld } from "./world";

/**
 * The block this genre's cues are authored in.
 *
 * `audio` — `[bindings]` names which effect id each cue reaches and
 * `[[effects]]` says how each id is realized. A producer that moves it gets
 * `manifest block "audio" is published as …; this build reads
 * runner-audio-block-v1`, from the cues, and separately from the soundtrack,
 * which reads `[music.*]` out of the same file.
 */
export const RUNNER_CUES_BLOCK = Object.freeze({
  block: "audio",
  version: RUNNER_BLOCKS.audio,
});

/** Gate the runner's cues block. Refuses by naming `audio`. */
export function parseRunnerCuesBlock(blocks: BlockTable): CuesBlockView {
  return parseCuesBlock(blocks, RUNNER_CUES_BLOCK);
}

export type RunnerAudioCue = RunnerAudioEvent;

/**
 * Every name this genre's cue table posts, across both channels.
 *
 * The effect sink answers for the nine verbs and the music sink for the three
 * run edges, and `restart` is the one name only the second has — a run that
 * begins again is a thing the music does and not a sound the world makes.
 */
export type RunnerCueName = RunnerAudioCue | RunnerMusicEvent;

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
 * The runner's binding of the `cues` family: nine verbs, renamed.
 *
 * A pure consumer. Every cue below is an occurrence some other system emitted
 * on the frame it happened — the avatar's three traversal verbs, the two the
 * obstacle field raises, the drain the vitals resolve, the end the session
 * hears — and this table is only the map from those onto the names a package's
 * `[bindings]` binds an effect to. It used to be a hundred lines of edge
 * detection over five shadow copies of two other systems' slices, resynced by
 * hand after every restart.
 *
 * Two channels, because in this genre one occurrence is heard by two listeners:
 * the effect sink plays the stinger and the music sink performs the
 * soundtrack's authored action, side by side, which is what the audio contract
 * has always said. The music vocabulary is the `soundtrack` family's, not this
 * one's; the cue system is the consumer both reach through.
 *
 * The explicit edges pin it to the very end of the frame — after the session
 * that settles the phase and score, and after the hud that closes the drawing
 * chain — so the sealed order stays unique regardless of registration order.
 */
export function createAudioSystem(
  sink: RunnerAudioSink,
  music: RunnerMusicSink = SILENT_MUSIC_SINK,
): GameSystem<RunnerWorld> {
  /** A run that has already ended answers for its own death and nothing else. */
  const alive = (world: RunnerWorld) => world.run.phase !== "dead";
  return createCueSystem<RunnerWorld, RunnerEvent["type"], RunnerCueName, "effect" | "music">({
    id: "runner/audio",
    // v5: the edges are occurrences rather than shadow copies.
    contractVersion: "audio-system-v5",
    reads: ["run", "score"],
    after: ["session/run", "runner/hud"],
    // Every rule that names no channel is an effect; the music channel is
    // named at the three rules that reach it.
    channel: "effect",
    sinks: {
      effect: { play: (cue, strength) => sink.play(cue as RunnerAudioCue, strength) },
      // The music sink takes the same names; what it does with each is the
      // package's authored `[music]` action, resolved inside the playback.
      music: { play: (cue) => music.transition(cue as RunnerMusicEvent) },
    },
    // The stage start is announced once per boot, on the first frame. The one
    // cue nothing happened to cause: with a stage-start moment that is the
    // intro's first frame, so the line and the rip are one beat; without one it
    // is the first running frame. Never on a restart.
    announce: "stage_start",
    announceChannel: "effect",
    // And the next run's first frame. Not a rule, because the ask never
    // survives into it: the composition rebuilds the world at the end of the
    // frame that asks for a restart and throws both frames of occurrences away
    // with the run they described. So the music starts again over the run that
    // exists rather than the one that just ended, and the composition is what
    // says so.
    resumed: "restart",
    resumedChannel: "music",
    // Rule order is post order, and it is the order the hand-written system
    // posted in: the traversal verbs, then the field, then the consequence,
    // then the end of the run.
    table: [
      { on: "jumped", cue: (_world, event: { airJump: boolean }) => (event.airJump ? "air_jump" : "takeoff") },
      { on: "landed", cue: "land", when: alive },
      { on: "slid", cue: "slide" },
      { on: "hazard-cleared", cue: "hazard_cleared", when: alive },
      {
        on: "collected",
        cue: "collect",
        when: alive,
        // The chain is this frame's: the scorer is sealed before this system.
        strength: (world: RunnerWorld) => Math.min(1, world.score.chain / 30),
      },
      // A survivable hit: the stinger, and the duck under it.
      { on: "drained", cue: "hurt", when: alive },
      { on: "drained", cue: "hurt", when: alive, channel: "music" },
      // The one that ends it. `run-ended` is the vitals' verdict and the
      // session's input, and it is this frame's for both.
      { on: "run-ended", cue: "death" },
      { on: "run-ended", cue: "death", channel: "music" },
    ],
  });
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
