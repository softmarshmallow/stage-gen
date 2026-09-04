import { describe, expect, mock, test } from "bun:test";

// The replay golden: one seed, one scripted intent, one hash per fixed step.
//
// This is the regression guard for every refactor of the runner's systems. A
// change that must preserve behaviour shows the same digest chain; a change
// that intends new behaviour shows a diff at exactly the documented frame and
// nowhere else, and re-pins with a sentence saying why. The world is hashed
// after each sealed tick, slices only - the RNG closure, the config derived
// from the manifest, and the queue's methods are not state.

mock.module("phaser", () => ({
  default: {
    Scene: class {},
    AUTO: 0,
    Scale: { FIT: 1, CENTER_BOTH: 2 },
    Textures: { FilterMode: { NEAREST: 0 } },
  },
}));

const { assembleRunnerSystems, runnerSealOptions } = await import("./game");
const { sealSystems } = await import("@/lib/kernel/systems");
const { createIntentLatch } = await import("./intent");
const { SILENT_AUDIO_SINK } = await import("./audio");
const { createRunnerWorld } = await import("./world");
const { parseRunnerRuntimeManifest } = await import("./contract");
const { runnerManifestFixture } = await import("./fixture");
const { createFixedStepAccumulator } = await import("@/lib/kernel/fixed-step");
type RunnerWorld = import("./world").RunnerWorld;

const SEED = 0x5eed_1234;
const FRAMES = 600;
const FRAME_MS = 1000 / 60;

/** A deterministic script: jumps, a held slide, and a restart request. */
function drive(latch: ReturnType<typeof createIntentLatch>, frame: number): void {
  if (frame === 30 || frame === 95 || frame === 96 || frame === 240 || frame === 410) {
    latch.requestJump();
  }
  latch.setDuck(frame >= 300 && frame < 360);
  latch.setThrust(frame >= 500 && frame < 520);
  if (frame === 580) latch.requestAction();
}

function plain(value: unknown): unknown {
  if (value instanceof Set) return [...value].map(plain).sort();
  if (value instanceof Map) return [...value.entries()].map(([k, v]) => [plain(k), plain(v)]);
  if (Array.isArray(value)) return value.map(plain);
  if (typeof value === "function") return undefined;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(value).sort()) {
      if (key === "rng" || key === "config") continue;
      const inner = plain((value as Record<string, unknown>)[key]);
      if (inner !== undefined) out[key] = inner;
    }
    return out;
  }
  if (typeof value === "number" && !Number.isInteger(value)) return value.toFixed(9);
  return value;
}

/**
 * The slices this digest covers, or null for all of them.
 *
 * `REPLAY_SLICES` is the instrument a step that *adds* a slice needs. A new
 * slice moves every frame's digest by existing, which says nothing about
 * behaviour; naming the slices that were there before turns "did the run
 * change" back into a frame-by-frame question with an answer. The clock family
 * is the first user: eleven slices named, six hundred digests identical.
 */
const RESTRICT: readonly string[] | null = process.env.REPLAY_SLICES
  ? process.env.REPLAY_SLICES.split(",")
  : null;

function restrict(world: RunnerWorld): unknown {
  if (RESTRICT === null) return world;
  const out: Record<string, unknown> = {};
  for (const key of RESTRICT) out[key] = (world as unknown as Record<string, unknown>)[key];
  return out;
}

function digest(world: unknown, events: readonly unknown[]): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(JSON.stringify({ world: plain(world), events: plain(events) }));
  return hasher.digest("hex");
}

/**
 * Digest chain checkpoints; the final value covers every frame.
 *
 * Re-pinned once, for the kernel step, against a frame-by-frame diff of the
 * previous chain. Exactly ONE of the six hundred frames moved: frame 278, the
 * frame the run ends. The run-loop used to write `avatar.motion = "death"`
 * itself — an undeclared write into a slice it does not own — so at 278 the
 * avatar wore the death pose while still reading `jump`. It now wears it at
 * 279, written by the avatar system, which is the one frame of delay that
 * system's own comment has always claimed. 279 onward are identical, the
 * restart at frame 410 included.
 */
const GOLDEN: Record<number, string> = {
  60: "18bc90f7f233169ad3d8de407b6d16fe878adcad9036a2acff2f91fce2df8263",
  300: "c7a384414ff712e177cc128b8c95b3ceaf94729de7f142b174ae2e66c3696b31",
  600: "d0eb468b03c722166edb5cc032ec600b7a30f6c8eda74cb383f7bbfa883afd29",
};

/**
 * Re-pinned a second time, for the `clock` family.
 *
 * All three checkpoints moved and no frame of the run did. The world gained a
 * `clock` slice — four numbers the digest had never hashed — so every frame's
 * digest is a different digest of the same run. Measured rather than claimed:
 * with `REPLAY_SLICES` naming the eleven slices that existed before (avatar,
 * camera, difficulty, encounter, fx, intent, locomotion, obstacles, run,
 * segments, vitals) all six hundred per-frame digests are byte-identical to
 * the previous chain, the death at 278 and the restart at 410 included.
 *
 * The behaviour the family exists to change — a jump pressed under a cut-in no
 * longer firing, and a refractory window that no longer expires while the
 * simulation is held — is invisible here for the reason step 0 left
 * `defeatedAtMs` alone: this package publishes no `fx` block, so it has no
 * moment, so it never holds. `clock.simulationDt` equals `step.dt` and
 * `clock.simulationNow` equals `step.now` on every one of these frames, which
 * is exactly why nothing moved. The hold is exhibited in
 * `lib/families/clock/clock.test.ts` and in `intent.test.ts` instead.
 */

/** The frame the run ends, and the frame after it takes the pose. */
const DEATH_FRAME = 278;
/** The frame the scripted jump asks for a restart. */
const RESTART_FRAME = 410;

describe("the runner replays to its golden", () => {
  test("six hundred fixed steps under a scripted intent hash to the pinned chain", async () => {
    const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
    const world = createRunnerWorld(manifest, SEED);
    const latch = createIntentLatch();
    const noopView = { sync: () => undefined, hide: () => undefined };
    // Sealed with the trap on: six hundred frames of the real roster is the
    // strongest statement available that every write is declared, and it costs
    // thirty milliseconds. A refusal fails this test by being thrown.
    const sealed = sealSystems(
      assembleRunnerSystems(latch, noopView, noopView, SILENT_AUDIO_SINK),
      runnerSealOptions({ clock: () => clock, devTrap: true }),
    );
    const clock = createFixedStepAccumulator();
    let chain = "";
    const seen: Record<number, string> = {};
    const frames: string[] = [];
    const dumps: string[] = [];
    const notes: { death?: string; restartSeed?: number; restartEvents?: number } = {};
    for (let frame = 1; frame <= FRAMES; frame += 1) {
      drive(latch, frame);
      const steps = clock.advance(FRAME_MS + 1e-9);
      expect(steps.length).toBe(1);
      sealed.tick(world, steps[0]);
      const frameDigest = digest(restrict(world), world.events.frame);
      const hasher = new Bun.CryptoHasher("sha256");
      hasher.update(chain + frameDigest);
      chain = hasher.digest("hex");
      frames.push(`${frame} ${frameDigest}`);
      if (process.env.REPLAY_DUMP) {
        dumps.push(`${frame} ${JSON.stringify(plain({ w: restrict(world), e: world.events.frame }))}`);
      }
      if (frame in GOLDEN) seen[frame] = chain;
      if (frame === DEATH_FRAME) notes.death = world.avatar.motion;
      if (frame === RESTART_FRAME) {
        notes.restartSeed = world.run.seed;
        notes.restartEvents = world.events.frame.length;
      }
    }
    // The same two instruments the platformer's golden carries: one unchained
    // digest per frame, so "which frames moved" is a diff rather than a claim,
    // and the whole hashed world per frame, so "and why" is a field diff.
    if (process.env.REPLAY_DUMP) await Bun.write(process.env.REPLAY_DUMP, `${dumps.join("\n")}\n`);
    if (process.env.REPLAY_FRAMES) {
      await Bun.write(process.env.REPLAY_FRAMES, `${frames.join("\n")}\n`);
    }
    if (RESTRICT !== null) return;
    expect(seen).toEqual(GOLDEN);
    // The documented frame, asserted rather than only described: the pose is
    // the avatar's to write, one frame later.
    expect(notes.death).not.toBe("death");
    // And the restart happened, through the composition rather than mid-tick:
    // a new seed, and no occurrence of the dead run left in the queue.
    expect(notes.restartSeed).not.toBe(SEED);
    expect(notes.restartEvents).toBe(0);
    expect(world.run.phase).toBe("running");
  });
});
