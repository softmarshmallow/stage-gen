import { describe, expect, test } from "bun:test";
import {
  drawWave,
  playsInWaves,
  WaveRound,
  waveFractions,
  waveSourcesFromZones,
  type AuthoredPopulationZone,
} from "./waves";

/**
 * Two zones out of Bellweather's own census table, verbatim.
 *
 * The whole point of the profile is that these numbers were authored for a
 * hunting route and are read as waves without one of them changing.
 */
const ZONES: readonly AuthoredPopulationZone[] = [
  {
    zone_id: "amberbell_edge",
    left_fraction: 0.08,
    right_fraction: 0.34,
    target_population: 10,
    respawn_delay_ms: 3000,
    spawn_table: [
      { mob_id: "petal_puff", weight: 4 },
      { mob_id: "jewelwing_beetle", weight: 3 },
    ],
  },
  {
    zone_id: "crowncrag_approach",
    left_fraction: 0.7,
    right_fraction: 0.94,
    target_population: 8,
    respawn_delay_ms: 4000,
    spawn_table: [
      { mob_id: "bramblehart", weight: 2 },
      { mob_id: "thimblejay", weight: 1 },
    ],
  },
];

const SOURCES = waveSourcesFromZones(ZONES, 1705);

describe("a package plays in waves because it said so, in a table that exists", () => {
  test("an award for `wave_cleared` is the whole statement", () => {
    expect(playsInWaves(null)).toBe(false);
    expect(playsInWaves({ awards: { mob_defeated: 25 }, display: "hud" })).toBe(false);
    expect(playsInWaves({ awards: { wave_cleared: 250 }, display: "hud" })).toBe(true);
  });

  test("the census table is read as waves without one authored number changing", () => {
    expect(SOURCES[0]).toEqual({
      zoneId: "amberbell_edge",
      leftFraction: 0.08,
      rightFraction: 0.34,
      size: 10,
      respawnDelayMs: 3000,
      table: [
        { mobId: "petal_puff", weight: 4 },
        { mobId: "jewelwing_beetle", weight: 3 },
      ],
      seedSalt: 1705,
    });
  });
});

describe("what a wave is made of, and where it stands", () => {
  test("a wave is the zone's own headcount, drawn from its own table", () => {
    const drawn = drawWave(SOURCES[0]!, 0);
    expect(drawn).toHaveLength(10);
    expect(new Set(drawn).size).toBeGreaterThan(0);
    for (const mobId of drawn) {
      expect(["petal_puff", "jewelwing_beetle"]).toContain(mobId);
    }
  });

  test("the draw is seeded, so a replay of the run draws the same wave", () => {
    expect(drawWave(SOURCES[0]!, 0)).toEqual(drawWave(SOURCES[0]!, 0));
    // ...and two waves of one zone, and two zones of one map, do not.
    expect(drawWave(SOURCES[0]!, 0)).not.toEqual(drawWave(SOURCES[0]!, 1));
    expect(drawWave(SOURCES[0]!, 0)).not.toEqual(drawWave(SOURCES[1]!, 0));
  });

  test("the members stand inside the zone's own span, never on its boundary", () => {
    const fractions = waveFractions(SOURCES[0]!, 10);
    expect(fractions).toHaveLength(10);
    for (const fraction of fractions) {
      expect(fraction).toBeGreaterThan(0.08);
      expect(fraction).toBeLessThan(0.34);
    }
    // Evenly, so a wave is walked into rather than piled on the trigger.
    expect(fractions[1]! - fractions[0]!).toBeCloseTo(0.026, 6);
  });

  test("a table whose weights sum to nothing falls back rather than refusing", () => {
    const [flat] = waveSourcesFromZones(
      [{ ...ZONES[0]!, spawn_table: [{ mob_id: "petal_puff", weight: 0 }] }],
      7,
    );
    expect(drawWave(flat!, 0)).toEqual(Array.from({ length: 10 }, () => "petal_puff"));
  });
});

describe("the phase machine is the director family's, and the recurrence is the difference", () => {
  const WORLD_WIDTH = 4000;

  test("armed at the zone's left edge, engaged when the player reaches it", () => {
    const round = new WaveRound(SOURCES[0]!);
    expect(round.state.phase).toBe("armed");
    expect(round.trigger(WORLD_WIDTH).at).toBeCloseTo(320, 6);
    expect(round.reached(WORLD_WIDTH, 100)).toBe(false);
    expect(round.reached(WORLD_WIDTH, 320)).toBe(true);
    round.engage(1000);
    expect(round.state).toEqual({ phase: "engaged", phaseStartedAt: 1000, outcome: null });
  });

  test("cleared is a phase and not a terminus: the zone's own delay, then the next wave", () => {
    const round = new WaveRound(SOURCES[0]!);
    round.engage(1000);
    round.clear(5000);
    expect(round.state.phase).toBe("cleared");
    expect(round.state.outcome).toBe("cleared");
    expect(round.cleared).toBe(1);
    expect(round.waveIndex).toBe(1);
    // 3000ms is the zone's authored `respawn_delay_ms`, read as the pause
    // between waves rather than as the pause before one body is replaced.
    expect(round.readyToRearm(7999)).toBe(false);
    expect(round.readyToRearm(8000)).toBe(true);
    round.rearm(8000);
    expect(round.state).toEqual({ phase: "armed", phaseStartedAt: 8000, outcome: null });
    expect(round.recurrence).toBe("recurring");
  });

  test("a world torn down mid-wave leaves the round armed and the count intact", () => {
    // The same call the gate makes, and the same reason: the bodies are the
    // world's and the count is the run's.
    const round = new WaveRound(SOURCES[1]!);
    round.engage(1000);
    round.clear(2000);
    round.rearm(6000);
    round.engage(6100);
    round.worldTornDown();
    expect(round.state.phase).toBe("armed");
    expect(round.cleared).toBe(1);
    // And a round that is not engaged is left exactly where it was.
    const cleared = new WaveRound(SOURCES[1]!);
    cleared.engage(0);
    cleared.clear(10);
    cleared.worldTornDown();
    expect(cleared.state.phase).toBe("cleared");
  });
});
