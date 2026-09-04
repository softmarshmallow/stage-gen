import { describe, expect, mock, test } from "bun:test";

// The wave variant's replay golden: the same instrument, a third run, its own chain.
//
// `replay.test.ts` drives the shipped package twice — a walk that talks and fights, and a walk that
// dies. This drives the same package authored as a timed round: `[score]`, `[timers]` and an entry
// on the route, three tables over content that has not changed by a byte. What it is evidence of is
// the plan's capstone claim, that a genre can be a composition of families whose parameters a
// package names — so the assertions below are deliberately about the *round* rather than about the
// hash alone: waves spawned, waves cleared, points awarded, and the frame `session/ended` lands on.
//
// The run is 2760 fixed steps rather than the other two runs' 600, because ninety seconds at 1/30s
// is 2700 of them and the countdown does not advance on a frame the simulation is held — every
// blow's hitstop is a frame the player is not racing the clock through, which is the `clock` family
// doing on this genre exactly what step 3 said it would.

const { headlessPhaserModule } = await import("./headless-phaser.fixture");
mock.module("phaser", headlessPhaserModule);

const { installHeadlessBrowser } = await import("./headless-browser.fixture");
const { wavesRuntimeManifest } = await import("./replay-package.fixture");
const { playerIntent } = await import("./player-intent");
const { PreparedStageScene } = await import("./prepared-scene");

type StubScene = import("./headless-phaser.fixture").StubScene;

/** Ninety seconds is 2700 frames; the tail is the room the holds take. */
const FRAMES = 2760;
const FRAME_MS = 1000 / 30;

/**
 * The scripted round.
 *
 * East across the zone, swinging on a cadence, then back west and out again — which is what a
 * time-attack run of a hunting route looks like when nobody is choosing where to go. Nothing here
 * names a wave: the waves arrive because the run reaches the zone's own left edge, and they arrive
 * again because the zone's own `respawn_delay_ms` has run out.
 */
function rushIntent(frame: number) {
  const cycle = frame % 600;
  return playerIntent({
    right: cycle < 380,
    left: cycle >= 400 && cycle < 580,
    run: true,
    attack: frame % 9 === 0,
  });
}

async function settle(): Promise<void> {
  for (let turn = 0; turn < 3000; turn += 1) await Promise.resolve();
}

type RoundSnapshot = Readonly<{
  score: { total: number };
  timers: readonly { remainingMs: number; elapsedMs: number; expired: boolean }[];
  session: { phase: string; seed: number; runIndex: number; endedBy: string | null };
  waves: readonly {
    zoneId: string;
    phase: string;
    wave: number;
    cleared: number;
    standing: number;
  }[];
  readout: string | null;
}>;

describe("the wave variant plays, and the round ends at the timer", () => {
  test("ninety seconds of Crowncrag-shaped route, scored, drawn from the authored zone", async () => {
    let clockMs = 0;
    const browser = installHeadlessBrowser({
      manifest: wavesRuntimeManifest(),
      now: () => clockMs,
    });
    const scene = new PreparedStageScene("waves", "canonical-alpha", "gameplay-v2");
    const engine = scene as unknown as StubScene;
    scene.create();
    await settle();
    let frame = 0;
    scene.driveWithIntent(() => rushIntent(frame));
    try {
      const counts: Record<string, number> = {};
      const firsts: Record<string, number> = {};
      let heldFrames = 0;
      let ended: { frame: number; data: unknown } | null = null;
      let round: RoundSnapshot | null = null;
      for (let step = 1; step <= FRAMES; step += 1) {
        frame = step;
        clockMs = step * FRAME_MS;
        engine.stepEngine(clockMs, FRAME_MS, () => scene.update(clockMs, FRAME_MS));
        for (const event of scene.transcript) {
          counts[event.kind] = (counts[event.kind] ?? 0) + 1;
          firsts[event.kind] ??= step;
          if (event.kind === "session-ended" && ended === null) {
            ended = { frame: step, data: event.data };
          }
        }
        const snapshot = scene.replaySnapshot();
        if (snapshot.ready === true && !snapshot.loading) {
          const world = (scene as unknown as { frameWorld: { clock: { simulationDt: number } } })
            .frameWorld;
          if (world.clock.simulationDt === 0) heldFrames += 1;
        }
        round = (snapshot.round as RoundSnapshot | undefined) ?? round;
      }

      // The round exists at all, which is the block gate's half of the claim: two optional blocks
      // published, two families live, and a slice on the world where the shipped package has none.
      expect(round).not.toBeNull();
      const settled = round as RoundSnapshot;

      // Waves. Drawn from `[mob_population]`'s one authored zone, armed at its own left edge,
      // recurring after its own delay. Nothing about a wave is authored anywhere.
      expect(counts["wave-spawned"] ?? 0).toBeGreaterThan(0);
      expect(counts["wave-cleared"] ?? 0).toBeGreaterThan(0);
      expect(settled.waves.map((wave) => wave.zoneId)).toEqual(["road_zone"]);
      expect(settled.waves[0]?.cleared).toBe(counts["wave-cleared"] ?? 0);
      // A wave arrives because the run reached the zone, not because the map loaded.
      expect(firsts["wave-spawned"]).toBeGreaterThan(1);

      // Score. Every point of it is an authored award times an occurrence some other family named.
      expect(settled.score.total).toBeGreaterThan(0);
      const expected =
        25 * (counts["mob-defeated"] ?? 0) +
        10 * (counts["item-collected"] ?? 0) +
        250 * (counts["wave-cleared"] ?? 0) +
        500 * (counts["encounter-ended"] ?? 0);
      expect(settled.score.total).toBe(expected);
      // No chain: this genre authors none, and the family does not invent one.
      expect(settled.score.total).toBe(expected);

      // The countdown, and the hold. The ninety seconds are exactly ninety seconds of *simulation*
      // time, and the frame they land on is later than the 2701st because every blow's hitstop is a
      // frame the clock did not count.
      expect(settled.timers[0]?.expired).toBe(true);
      expect(settled.timers[0]?.elapsedMs).toBe(90_000);
      expect(settled.timers[0]?.remainingMs).toBe(0);
      // Measured, not asserted loosely: the ninety seconds land this many frames late because
      // exactly this many frames of the run carried no simulation time at all.
      expect(heldFrames).toBeGreaterThan(0);
      expect((ended?.frame ?? 0) - heldFrames).toBeLessThanOrEqual(2702);

      // `session/ended`, once, at the timer, carrying the score it ended on.
      expect(counts["session-ended"]).toBe(1);
      expect(ended?.frame).toBe(firsts["session-ended"]);
      expect(ended?.data).toEqual({ cause: "timer", score: settled.score.total });
      expect(settled.session).toEqual({ phase: "ended", seed: 0, runIndex: 0, endedBy: "timer" });
      expect((ended?.frame ?? 0) > 2700).toBe(true);

      // The round, pinned. Re-pin only against a diff, with a sentence naming what moved and why —
      // the discipline `replay.test.ts` states for its two chains applies to this one.
      expect({ counts, endedFrame: ended?.frame, heldFrames, ...settled.waves[0] }).toEqual({
        counts: {
          // Five waves arrived; the fifth was still standing when the clock ran out.
          "wave-spawned": 5,
          "wave-cleared": 4,
          "projectile-thrown": 154,
          "mob-defeated": 13,
          "item-collected": 31,
          // The route's authored gate is on this map too, and a time-attack run walks into it: the
          // set-piece fires and is won, which is where the `boss_defeated` award comes from.
          "encounter-started": 1,
          "encounter-ended": 1,
          "player-damaged": 4,
          "score-changed": 39,
          "session-ended": 1,
        },
        endedFrame: 2748,
        // 2748 - 46 = 2702: the ninety seconds are ninety seconds of simulation time, and the run
        // spent forty-six frames held by the hitstop of its own blows.
        heldFrames: 46,
        zoneId: "road_zone",
        phase: "engaged",
        wave: 4,
        cleared: 4,
        // The fifth wave was still on its feet when the clock ran out, which is
        // what a time attack looks like from the inside.
        standing: 3,
      });
      // 25x13 + 10x31 + 250x4 + 500x1. Every point of it is an authored number.
      expect(settled.score.total).toBe(2135);

      // And the readout the HUD port drew, which is the whole of what the player is asked for.
      expect(settled.readout).toBe(`0:00  ✦ ${settled.score.total}  time`);
    } finally {
      browser.restore();
    }
  });
});
