// Where defeat sends the player, and how long it takes to get there.
//
// Defeat used to be terminal: control locked, the death strip played, and the run stopped there
// with nothing to restart it. That is survivable for a person with a reload button and fatal for
// anything meant to keep playing on its own, so recovery belongs to the runtime alongside the rest
// of the gameplay rules.
//
// Home is derived from the package rather than authored into it. The gameplay contract already
// says which maps are safe hubs and where the game starts, and those two facts are enough to name
// the village without asking every game to declare a respawn point it would have to keep in sync
// with its own entry spawn.

import { DEATH_STRIP_DURATION_MS } from "./death-presentation";

/** The map role a package uses for a settlement with no hostile population. */
export const SAFE_HUB_MAP_ROLE = "safe_village_hub";

export type HomeSpawnInput = Readonly<{
  entry_map_id: string;
  entry_spawn_id: string;
  map_uses: readonly Readonly<{ map_id: string; role: string }>[];
  spawns: readonly Readonly<{
    spawn_id: string;
    map_id: string;
    normalized_x: number;
  }>[];
}>;

export type HomeSpawn = Readonly<{
  spawn_id: string;
  map_id: string;
  normalized_x: number;
}>;

/**
 * Resolve the spawn a defeated player wakes up at.
 *
 * Preference order, and the reason for it: the game's own entry spawn wins when it stands in a
 * safe hub, because that is the arrival the package was authored and art-directed around. When the
 * game instead opens on a hostile route, the first safe hub it declares wins, because respawning
 * into the population that just killed the player is a death loop rather than a recovery. With no
 * safe hub declared at all the entry spawn is the only home a package has, and it is used as-is.
 */
export function resolveHomeSpawn(input: HomeSpawnInput): HomeSpawn {
  const entrySpawn = input.spawns.find(
    (spawn) => spawn.spawn_id === input.entry_spawn_id,
  );
  if (!entrySpawn) {
    throw new Error(
      `gameplay entry spawn ${input.entry_spawn_id} does not resolve to a spawn point`,
    );
  }
  const safeHubMapIds = new Set(
    input.map_uses
      .filter((use) => use.role === SAFE_HUB_MAP_ROLE)
      .map((use) => use.map_id),
  );
  if (safeHubMapIds.has(entrySpawn.map_id)) return frozenSpawn(entrySpawn);
  for (const use of input.map_uses) {
    if (!safeHubMapIds.has(use.map_id)) continue;
    const hubSpawn = input.spawns.find((spawn) => spawn.map_id === use.map_id);
    if (hubSpawn) return frozenSpawn(hubSpawn);
  }
  return frozenSpawn(entrySpawn);
}

function frozenSpawn(
  spawn: Readonly<{ spawn_id: string; map_id: string; normalized_x: number }>,
): HomeSpawn {
  return Object.freeze({
    spawn_id: spawn.spawn_id,
    map_id: spawn.map_id,
    normalized_x: spawn.normalized_x,
  });
}

/**
 * How long a defeated player lies there before the world reloads around them.
 *
 * Long enough for the authored terminal strip to finish and register as an ending rather than a
 * stutter, and short enough that an unattended run is not mostly a corpse. It is expressed against
 * the strip duration so a change to the death artwork's frame rate carries the beat with it.
 */
export const DEFEAT_RECOVERY_DELAY_MS = DEATH_STRIP_DURATION_MS + 1300;

/** Whether a defeat that began at `defeatedAtMs` has finished its recovery delay. */
export function defeatRecoveryDue(
  input: Readonly<{
    defeatedAtMs: number;
    nowMs: number;
    delayMs?: number;
  }>,
): boolean {
  const delayMs = input.delayMs ?? DEFEAT_RECOVERY_DELAY_MS;
  if (
    !Number.isFinite(input.defeatedAtMs) ||
    !Number.isFinite(input.nowMs) ||
    !Number.isFinite(delayMs) ||
    delayMs < 0
  ) {
    throw new Error("defeat recovery timing requires finite milliseconds");
  }
  return input.nowMs - input.defeatedAtMs >= delayMs;
}
