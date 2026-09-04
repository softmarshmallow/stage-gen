// `waves`: a second `director` profile over the zones the package already authored.
//
// The plan's step 7 rules it in one clause — "`waves` is a `director` profile"
// — and the clause is doing real work, because the obvious reading is the wrong
// one. A wave looks like `population`: creatures appear, the map fills up. It is
// not. `population` is a CENSUS — a target headcount per zone, a cap, a respawn
// delay, and a director that keeps the number where the package says it should
// be, forever and with no beginning or end. A wave is a SET-PIECE: it is armed
// at a place, it starts, the world is different while it is on, it ENDS, and its
// ending is an outcome other families consume. That is `director`'s four facts
// exactly, which is why this file holds a phase machine and a trigger and not a
// single new mechanism.
//
// Where the waves come from is the other half of the ruling, and it is what
// makes this an authoring change rather than a content one: **the zones are
// already authored**. `[mob_population].maps[].zones` states, per zone, a span
// of the map, a headcount, a spawn table with weights, and a delay. A census
// reads those as "how many should be standing here"; a wave reads the same five
// numbers as "how many arrive at once, drawn from what, and how long until the
// next lot". No new table, no new asset, no generator module — which is the
// whole claim the taxonomy's minigame case makes.
//
// And what turns the census reading into the wave reading is authored too, in
// the block that exists: a package that awards `wave_cleared` in `[score]` is a
// package that plays in waves. `wave_cleared` is one of the four members of the
// contract's closed score vocabulary and the only one that names a thing no
// story game has; a package that pays for one is stating that its run is made
// of them. So the two readings of the zone table are chosen by a name the author
// wrote, and the same map plays as Bellweather's hunting route or as a
// time-attack arena depending on one line of TOML.

import {
  armAt,
  enterPhase,
  phaseElapsed,
  triggerReached,
  type DirectorPhaseState,
  type DirectorRecurrence,
  type SpatialTrigger,
} from "@/lib/families/director";
import { fnv1a32, mix32 } from "@/lib/kernel/hash";
import { mulberry32 } from "@/lib/kernel/rng";
import type { ScoreBlock } from "@/lib/manifest/prepared-manifest";

/**
 * This profile's phase vocabulary.
 *
 * Three, like the gate's, and the third is the difference between them: a gate
 * that has ended stays ended (`once`), and a wave that has been cleared is
 * waiting for the next one (`recurring`). `cleared` is therefore a phase and
 * not a terminus, and the delay it waits out is the zone's own authored
 * `respawn_delay_ms` — the census's word for the same pause.
 */
export type WavePhase = "armed" | "engaged" | "cleared";

/** What a wave ends as. One member: a wave is over when nothing in it is standing. */
export type WaveOutcome = "cleared";

/** One authored zone, read as a wave source rather than as a census. */
export interface WaveSource {
  readonly zoneId: string;
  readonly leftFraction: number;
  readonly rightFraction: number;
  /** How many arrive at once. The zone's target headcount, read as a wave size. */
  readonly size: number;
  /** How long after a wave is cleared the next one arrives. */
  readonly respawnDelayMs: number;
  /** What may arrive, and how likely each is. */
  readonly table: readonly { readonly mobId: string; readonly weight: number }[];
  /** The zone's own seed salt, so two zones of one map draw differently. */
  readonly seedSalt: number;
}

/** The authored shape a population zone is published in, as far as this profile reads it. */
export interface AuthoredPopulationZone {
  readonly zone_id: string;
  readonly left_fraction: number;
  readonly right_fraction: number;
  readonly target_population: number;
  readonly respawn_delay_ms: number;
  readonly spawn_table: readonly { readonly mob_id: string; readonly weight: number }[];
}

/**
 * Whether this package plays in waves, and the answer is one authored word.
 *
 * A `[score]` block that pays for `wave_cleared` is the statement. Nothing else
 * in the contract can carry it: the census table cannot say it (a census has no
 * waves to clear) and inventing a `[waves]` block would be a contract bump the
 * step's own ruling says is not needed.
 */
export function playsInWaves(score: ScoreBlock | null): boolean {
  return score !== null && (score.awards.wave_cleared ?? 0) > 0;
}

/** Read a map's authored zones as wave sources, in authored order. */
export function waveSourcesFromZones(
  zones: readonly AuthoredPopulationZone[],
  seedSalt: number,
): readonly WaveSource[] {
  return zones.map((zone) =>
    Object.freeze({
      zoneId: zone.zone_id,
      leftFraction: zone.left_fraction,
      rightFraction: zone.right_fraction,
      size: Math.max(1, Math.trunc(zone.target_population)),
      respawnDelayMs: Math.max(0, zone.respawn_delay_ms),
      table: Object.freeze(
        zone.spawn_table.map((entry) =>
          Object.freeze({ mobId: entry.mob_id, weight: Math.max(0, entry.weight) }),
        ),
      ),
      seedSalt,
    }),
  );
}

/**
 * Which creatures the nth wave of a zone is made of, and where each of them stands.
 *
 * Seeded off the zone id, the map's own salt and the wave's index, so a replay
 * of the same run draws the same wave and two zones of one map never draw the
 * same one. The weights are the authored spawn table's, and a table whose
 * weights sum to nothing falls back to its first member rather than refusing —
 * the census makes the same call about the same table.
 */
export function drawWave(source: WaveSource, waveIndex: number): readonly string[] {
  const total = source.table.reduce((sum, entry) => sum + entry.weight, 0);
  const first = source.table[0]?.mobId;
  if (first === undefined) return [];
  if (total <= 0) return Array.from({ length: source.size }, () => first);
  const rng = mulberry32(mix32(fnv1a32(`wave:${source.zoneId}:${waveIndex}`), source.seedSalt));
  const drawn: string[] = [];
  for (let index = 0; index < source.size; index += 1) {
    let ticket = rng() * total;
    let chosen = first;
    for (const entry of source.table) {
      ticket -= entry.weight;
      if (ticket <= 0) {
        chosen = entry.mobId;
        break;
      }
    }
    drawn.push(chosen);
  }
  return drawn;
}

/**
 * Where the members of a wave stand, as fractions of the map.
 *
 * Spread evenly across the zone's own span rather than piled on the trigger:
 * a wave the player walks into is a wave, and a wave standing on top of the
 * player is a defeat. The first and last are inset by half a gap so that no
 * member stands exactly on a zone boundary two zones share.
 */
export function waveFractions(source: WaveSource, count: number): readonly number[] {
  if (count <= 0) return [];
  const span = Math.max(0, source.rightFraction - source.leftFraction);
  const gap = span / count;
  return Array.from({ length: count }, (_, index) => source.leftFraction + gap * (index + 0.5));
}

/**
 * One zone's waves, for the life of the session.
 *
 * The family owns the phase machine and the trigger; what is here is the two
 * facts a wave has that a gate does not — which wave this is, and how many have
 * been cleared.
 */
export class WaveRound {
  readonly state: DirectorPhaseState<WavePhase, WaveOutcome> = {
    phase: "armed",
    phaseStartedAt: null,
    outcome: null,
  };
  /** Which wave of this zone is next; zero for the first. */
  waveIndex = 0;
  /** How many waves of this zone the run has cleared. */
  cleared = 0;
  readonly recurrence: DirectorRecurrence = "recurring";

  constructor(readonly source: WaveSource) {}

  /** The trigger, in world pixels: the zone's own left edge. */
  trigger(worldWidthPx: number): SpatialTrigger {
    return armAt(this.source.leftFraction * worldWidthPx);
  }

  reached(worldWidthPx: number, playerX: number): boolean {
    return triggerReached(this.trigger(worldWidthPx), playerX);
  }

  /** The wave has arrived. */
  engage(now: number): void {
    enterPhase(this.state, "engaged", now);
  }

  /** Nothing in the wave is standing. */
  clear(now: number): void {
    this.cleared += 1;
    this.waveIndex += 1;
    this.state.outcome = "cleared";
    enterPhase(this.state, "cleared", now);
  }

  /** Whether the authored pause between waves has run out. */
  readyToRearm(now: number): boolean {
    if (this.state.phase !== "cleared") return false;
    return (phaseElapsed(this.state, now) ?? 0) >= this.source.respawnDelayMs;
  }

  /** Arm the next wave. */
  rearm(now: number): void {
    this.state.outcome = null;
    enterPhase(this.state, "armed", now);
  }

  /** A world torn down mid-wave has no wave in it; the round goes back to armed. */
  worldTornDown(): void {
    if (this.state.phase !== "engaged") return;
    this.state.phase = "armed";
    this.state.phaseStartedAt = null;
  }
}
