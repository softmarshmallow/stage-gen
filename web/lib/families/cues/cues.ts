// Cues: the one family that holds no state at all.
//
// A cue is what the world says out loud when something happens — a takeoff, a
// landing, a hit, a collect — and the only decisions in it are *which*
// occurrence posts *which* name, how loud, and to which sink. There is no
// slice, no memory between frames and nothing another system can read back, so
// the family is a pure consumer: it reads the frame's occurrences and posts.
//
// That matters because of what it replaces. The runner's cue system used to
// detect its own edges by keeping shadow copies of five fields another system
// owns — `prevJumpImpulses`, `prevGrounded`, `prevSliding`, `prevDead`,
// `prevDistance` — and comparing them frame to frame. Every one of those was a
// second, private answer to a question the owner had already answered inside
// its own step, and each had to be resynchronised by hand after a restart. The
// occurrences replace all five: the system that made the thing happen says so,
// and the cue system hears it.
//
// The **rename table** is the whole of the genre's contribution. A family emits
// `jumped`; a runner's package binds an effect to `takeoff`. Neither name is
// wrong and neither should be forced on the other, so the mapping is data: one
// rule per occurrence, in the order the cues should be posted.

import type { GameSystem } from "@/lib/kernel/systems";

/** Where a posted cue goes. `strength` grades it — a collect pitches up with the chain. */
export interface CueSink<Cue extends string> {
  play(cue: Cue, strength: number): void;
}

/**
 * One line of the rename table.
 *
 * `on` is the occurrence, `cue` the name this genre's package binds, `strength`
 * the grading (one by default), `when` a guard the genre answers — a run that
 * has already ended posts no collect — and `channel` the sink it goes to, for a
 * genre whose edges are heard by more than one listener.
 */
export interface CueRule<W, E extends string, Cue extends string, Channel extends string> {
  readonly on: E;
  readonly cue: Cue | ((world: W, event: never) => Cue);
  readonly strength?: (world: W, event: never) => number;
  readonly when?: (world: W, event: never) => boolean;
  readonly channel?: Channel;
  /**
   * Hear the occurrence on the frame *after* it is emitted.
   *
   * The event channel's feedback read. A restart is the case that needs it: the
   * composition resets the world at the end of the frame that asks for one, so
   * the music's restart belongs to the first frame of the new run and not to
   * the last frame of the old.
   */
  readonly deferred?: boolean;
}

export interface CueBinding<W, E extends string, Cue extends string, Channel extends string> {
  readonly id: string;
  readonly contractVersion: string;
  /** Slices the guards and the grading read. A cue system writes nothing. */
  readonly reads?: readonly (keyof W & string)[];
  readonly after?: readonly string[];
  /** One sink per channel; a genre with one listener declares one. */
  readonly sinks: Readonly<Record<Channel, CueSink<Cue>>>;
  /** The channel a rule that names none goes to. Required past one sink. */
  readonly channel?: Channel;
  readonly table: readonly CueRule<W, E, Cue, Channel>[];
  /**
   * Posted once, on the first frame of a boot, before any occurrence.
   *
   * The one thing a cue system says that nothing happened to cause: a stage is
   * announced because the stage is there. Never on a restart — the announcement
   * belongs to the boot, and so does this.
   */
  readonly announce?: Cue;
  readonly announceChannel?: Channel;
  /**
   * Posted on the first frame of a run that follows a reset.
   *
   * The one occurrence a pure consumer cannot hear, and the reason is the
   * composition's own: a restart is not a frame boundary, so the queue throws
   * both frames away and the ask never reaches the frame after it. The
   * composition tells this system instead, through the reset hook every system
   * has — which is a notification, not a shadow copy of somebody's state, and
   * is the same standing this family's boot announcement has.
   */
  readonly resumed?: Cue;
  readonly resumedChannel?: Channel;
}

type FrameEvent = { readonly type: string };

/**
 * The cue system: presentation, so it writes no world key.
 *
 * The declared `consumes` is derived from the table, which is what makes the
 * sealer order it after every emitter it listens to without anyone writing the
 * list twice — and what makes a cue bound to an occurrence nothing emits a
 * seal-time refusal rather than a sound nobody ever hears.
 */
export function createCueSystem<
  W extends {
    readonly events: {
      readonly frame: readonly FrameEvent[];
      ofType(type: never): readonly FrameEvent[];
      previous(type: never): readonly FrameEvent[];
    };
  },
  E extends string,
  Cue extends string,
  Channel extends string,
>(binding: CueBinding<W, E, Cue, Channel>): GameSystem<W> {
  const consumes = [...new Set(binding.table.filter((rule) => !rule.deferred).map((rule) => rule.on))];
  const deferred = [...new Set(binding.table.filter((rule) => rule.deferred).map((rule) => rule.on))];
  let announced = false;
  let resumed = false;
  const post = (rule: CueRule<W, E, Cue, Channel>, world: W, event: FrameEvent) => {
    if (rule.when && !(rule.when as (w: W, e: FrameEvent) => boolean)(world, event)) return;
    const cue =
      typeof rule.cue === "function"
        ? (rule.cue as (w: W, e: FrameEvent) => Cue)(world, event)
        : rule.cue;
    const strength = rule.strength
      ? (rule.strength as (w: W, e: FrameEvent) => number)(world, event)
      : 1;
    const channel = (rule.channel ?? defaultChannel(binding)) as Channel;
    binding.sinks[channel].play(cue, strength);
  };
  return {
    id: binding.id,
    contractVersion: binding.contractVersion,
    reads: binding.reads ?? [],
    writes: [],
    ...(consumes.length > 0 ? { consumes: consumes as never } : {}),
    ...(deferred.length > 0 ? { consumesDeferred: deferred as never } : {}),
    ...(binding.after ? { after: binding.after } : {}),
    update(world: W) {
      if (!announced && binding.announce !== undefined) {
        announced = true;
        const channel = (binding.announceChannel ?? defaultChannel(binding)) as Channel;
        binding.sinks[channel].play(binding.announce, 1);
      }
      if (resumed) {
        resumed = false;
        if (binding.resumed !== undefined) {
          const channel = (binding.resumedChannel ?? defaultChannel(binding)) as Channel;
          binding.sinks[channel].play(binding.resumed, 1);
        }
      }
      // Rule order is post order: the table reads top to bottom as the frame is
      // heard, which is the only thing a listener can tell about two cues in
      // one frame.
      for (const rule of binding.table) {
        const heard = rule.deferred
          ? world.events.previous(rule.on as never)
          : world.events.ofType(rule.on as never);
        for (const event of heard) post(rule, world, event);
      }
    },
    reset(_world, scope) {
      // A session reset is a fresh boot: the announcement is owed again and
      // nothing is resuming. A run reset is the restart this family posts for.
      if (scope === "session") {
        announced = false;
        resumed = false;
        return;
      }
      resumed = true;
    },
  } as GameSystem<W>;
}

function defaultChannel<W, E extends string, Cue extends string, Channel extends string>(
  binding: CueBinding<W, E, Cue, Channel>,
): string {
  if (binding.channel !== undefined) return binding.channel;
  const channels = Object.keys(binding.sinks);
  if (channels.length !== 1) {
    throw new Error("a cue rule with more than one sink must name its channel");
  }
  return channels[0];
}
