// The `checkpoints` family, first half: where a defeated body wakes up.
//
// `respawn.ts` derived this from the package rather than asking every game to
// author a respawn point it would have to keep in sync with its own entry
// spawn, which is right and stays. What was wrong is that it did the deriving
// against a *constant*: `SAFE_HUB_MAP_ROLE = "safe_village_hub"` was a literal
// in the consumer, so a genre whose safe place is called anything else — a
// metroidvania's save room, a cinematic platformer's last lit brazier — could
// not use one line of it. The role is a parameter here, and the rule is the
// same rule.
//
// The second thing this family carries is the datum a checkpoint *sets*. A
// package that authors none has an empty ledger and falls back to the home
// spawn, which is exactly the platformer today; a package that authors some
// wakes the player at the last one they reached. Both are the same query with
// a different ledger, which is what makes "trial and death" a composition
// rather than a new genre.

export interface RespawnSpawn {
  readonly spawn_id: string;
  readonly map_id: string;
  readonly normalized_x: number;
}

export interface RespawnTargetInput {
  readonly entry_spawn_id: string;
  readonly map_uses: readonly Readonly<{ map_id: string; role: string }>[];
  readonly spawns: readonly RespawnSpawn[];
  /**
   * The role a package uses for a place with nothing hostile in it.
   *
   * A parameter, not a constant. Every genre has one and no two have to call it
   * the same thing.
   */
  readonly safeRole: string;
}

function frozenSpawn(spawn: RespawnSpawn): RespawnSpawn {
  return Object.freeze({
    spawn_id: spawn.spawn_id,
    map_id: spawn.map_id,
    normalized_x: spawn.normalized_x,
  });
}

/**
 * Resolve the spawn a defeated player wakes up at.
 *
 * Preference order, and the reason for it: the game's own entry spawn wins when
 * it stands in a safe place, because that is the arrival the package was
 * authored and art-directed around. When the game instead opens on a hostile
 * route, the first safe place it declares wins, because respawning into the
 * population that just killed the player is a death loop rather than a
 * recovery. With no safe place declared at all the entry spawn is the only home
 * a package has, and it is used as-is.
 */
export function resolveRespawnTarget(input: RespawnTargetInput): RespawnSpawn {
  const entrySpawn = input.spawns.find((spawn) => spawn.spawn_id === input.entry_spawn_id);
  if (!entrySpawn) {
    throw new Error(
      `gameplay entry spawn ${input.entry_spawn_id} does not resolve to a spawn point`,
    );
  }
  const safeMapIds = new Set(
    input.map_uses.filter((use) => use.role === input.safeRole).map((use) => use.map_id),
  );
  if (safeMapIds.has(entrySpawn.map_id)) return frozenSpawn(entrySpawn);
  for (const use of input.map_uses) {
    if (!safeMapIds.has(use.map_id)) continue;
    const safeSpawn = input.spawns.find((spawn) => spawn.map_id === use.map_id);
    if (safeSpawn) return frozenSpawn(safeSpawn);
  }
  return frozenSpawn(entrySpawn);
}

/**
 * The last safe datum a body reached, or none.
 *
 * Deliberately not a set of "checkpoints visited": what a recovery needs is the
 * most recent one, and keeping the rest would be a history nothing reads. A
 * genre that authors no checkpoints holds one of these and never writes to it,
 * which is the whole of what "the platformer has no checkpoints" costs.
 */
export class CheckpointLedger {
  private last: RespawnSpawn | null = null;
  private reachedCount = 0;

  /** Record arriving at a checkpoint; false when it is the one already held. */
  reach(spawn: RespawnSpawn): boolean {
    if (this.last?.spawn_id === spawn.spawn_id) return false;
    this.last = frozenSpawn(spawn);
    this.reachedCount += 1;
    return true;
  }

  /** Where a recovery should place the body: the last checkpoint, or the home spawn. */
  placement(home: RespawnSpawn): RespawnSpawn {
    return this.last ?? home;
  }

  reached(): number {
    return this.reachedCount;
  }

  clear(): void {
    this.last = null;
  }
}
