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

const { assembleRunnerSystems } = await import("./game");
const { sealSystems } = await import("@/lib/kernel/systems");
const { createIntentLatch } = await import("./intent");
const { SILENT_AUDIO_SINK } = await import("./audio");
const { createRunnerWorld } = await import("./world");
const { parseRunnerRuntimeManifest } = await import("./contract");
const { runnerManifestFixture } = await import("./fixture");
const { createFixedStepAccumulator } = await import("./fixed-step");

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

function digest(world: unknown, events: readonly unknown[]): string {
  const hasher = new Bun.CryptoHasher("sha256");
  hasher.update(JSON.stringify({ world: plain(world), events: plain(events) }));
  return hasher.digest("hex");
}

/** Digest chain checkpoints; the final value covers every frame. */
const GOLDEN: Record<number, string> = {
  60: "7bdfe7f4b742caf3b323a5c30f5faa1bf1f2b352edce5095caa2cf83eba5dfb1",
  300: "25016dd5ce1ee5b115988ec21b48199c675ed753f1023e7513e2c18e828dab69",
  600: "e7407a8694cb4b61d1669e0eb3efe6d4df7ca869fb5eb662f74e03b49e3353c3",
};

describe("the runner replays to its golden", () => {
  test("six hundred fixed steps under a scripted intent hash to the pinned chain", () => {
    const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());
    const world = createRunnerWorld(manifest, SEED);
    const latch = createIntentLatch();
    const noopView = { sync: () => undefined };
    const sealed = sealSystems(
      assembleRunnerSystems(latch, noopView, noopView, SILENT_AUDIO_SINK),
      { events: (w: { events: { beginFrame(): void } }) => w.events },
    );
    const clock = createFixedStepAccumulator();
    let chain = "";
    const seen: Record<number, string> = {};
    for (let frame = 1; frame <= FRAMES; frame += 1) {
      drive(latch, frame);
      const steps = clock.advance(FRAME_MS + 1e-9);
      expect(steps.length).toBe(1);
      sealed.tick(world, steps[0]);
      const hasher = new Bun.CryptoHasher("sha256");
      hasher.update(chain + digest(world, world.events.frame));
      chain = hasher.digest("hex");
      if (frame in GOLDEN) seen[frame] = chain;
    }
    expect(seen).toEqual(GOLDEN);
  });
});
