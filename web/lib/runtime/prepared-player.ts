import type { ClimbArtwork, PlayerState } from "./player";
import type { ClimbableRole } from "./vertical";
import type { MotionBinding, MotionCalibration } from "./prepared-manifest";
import type { RuntimeMotionPlayback } from "./motion-playback";

type PreparedPlayerStateAdapter = Readonly<{
  runtime_state: PlayerState;
  texture_key: string;
}>;

/**
 * Exact prepared-contract to mature-player adapter.
 *
 * `crouch` is the public gameplay and presentation vocabulary. The mature
 * controller's historical `character_crawl` texture key remains private to
 * this adapter and does not leak back into authored contracts or manifests.
 *
 * `climb_ladder` and `climb_rope` both adapt to the single controller state `climb`: the physics
 * of the two are identical and only the artwork differs, so the role selects a strip rather than
 * the state machine carrying two climbing states. They are the one place this table is not
 * one-to-one, which is why climb playback is resolved by `preparedPlayerClimbArtwork` rather than
 * by `preparedPlayerMotionPlayback`.
 */
export const PREPARED_PLAYER_STATE_ADAPTERS: Readonly<
  Record<string, PreparedPlayerStateAdapter>
> = Object.freeze({
  idle: Object.freeze({ runtime_state: "idle", texture_key: "character_idle" }),
  walk: Object.freeze({ runtime_state: "walk", texture_key: "character_walk" }),
  run: Object.freeze({ runtime_state: "run", texture_key: "character_run" }),
  jump: Object.freeze({ runtime_state: "jump", texture_key: "character_jump" }),
  crouch: Object.freeze({
    runtime_state: "crouch",
    texture_key: "character_crawl",
  }),
  climb_ladder: Object.freeze({
    runtime_state: "climb",
    texture_key: "character_climb_ladder",
  }),
  climb_rope: Object.freeze({
    runtime_state: "climb",
    texture_key: "character_climb_rope",
  }),
  basic_attack: Object.freeze({
    runtime_state: "attack",
    texture_key: "character_attack",
  }),
  hurt: Object.freeze({ runtime_state: "hurt", texture_key: "character_hurt" }),
  death: Object.freeze({ runtime_state: "death", texture_key: "character_death" }),
});

/**
 * A crouch is intentionally shorter in world space. Matching its alpha-bbox
 * height back to idle would enlarge the pose and erase the posture, so the
 * prepared adapter keeps the canonical atlas scale while the mature sprite's
 * bottom origin continues to register the feet on the support surface.
 */
export const PREPARED_PLAYER_PRESERVE_SOURCE_SCALE_STATES: readonly PlayerState[] =
  Object.freeze(["crouch"]);

export function preparedPlayerStateAdapter(
  state: string,
): PreparedPlayerStateAdapter | undefined {
  return PREPARED_PLAYER_STATE_ADAPTERS[state];
}

/** Authored climb state per climbable role. The map's role picks which strip the player draws. */
export const PREPARED_PLAYER_CLIMB_STATE_BY_ROLE: Readonly<
  Record<ClimbableRole, string>
> = Object.freeze({ ladder: "climb_ladder", rope: "climb_rope" });

/**
 * Resolve the climb strip for each role the manifest publishes.
 *
 * Kept apart from `preparedPlayerMotionPlayback` because both climb states adapt to the same
 * controller state, so a single state-keyed record cannot hold them both.
 */
export function preparedPlayerClimbArtwork(
  states: Readonly<Record<string, MotionBinding>>,
): Partial<Record<ClimbableRole, ClimbArtwork>> {
  const resolved: Partial<Record<ClimbableRole, ClimbArtwork>> = {};
  for (const [role, state] of Object.entries(
    PREPARED_PLAYER_CLIMB_STATE_BY_ROLE,
  ) as readonly (readonly [ClimbableRole, string])[]) {
    const binding = states[state];
    const adapter = preparedPlayerStateAdapter(state);
    if (!binding || !adapter) continue;
    resolved[role] = Object.freeze({
      textureKey: adapter.texture_key,
      animKey: `player_${state}`,
      playback: binding.playback,
      anchor: binding.anchor,
    });
  }
  return resolved;
}

export function preparedPlayerMotionPlayback(
  states: Readonly<Record<string, MotionBinding>>,
): Partial<Record<PlayerState, RuntimeMotionPlayback>> {
  const climbStates = new Set(Object.values(PREPARED_PLAYER_CLIMB_STATE_BY_ROLE));
  return Object.fromEntries(
    Object.entries(states).flatMap(([state, binding]) => {
      if (climbStates.has(state)) return [];
      const adapter = preparedPlayerStateAdapter(state);
      return adapter ? [[adapter.runtime_state, binding.playback]] : [];
    }),
  );
}

/**
 * Re-key a published rebase from authored state names onto runtime texture keys.
 *
 * The adapter table is the one place those two vocabularies meet, and climb is the one entry
 * that is not one-to-one: two authored climb states resolve to one controller state but keep
 * separate strips, so each keeps its own multiplier.
 */
export function preparedPlayerStateRebase(
  calibration: MotionCalibration,
): ReadonlyMap<string, number> {
  const resolved = new Map<string, number>();
  for (const [state, multiplier] of Object.entries(calibration.stateRebase)) {
    const adapter = PREPARED_PLAYER_STATE_ADAPTERS[state];
    // A package may author more motion than this controller draws - `skill_cast` is authored and
    // published but has no runtime state here. A state the runtime never binds needs no scale,
    // so it is skipped rather than rejected; the adapter table is the runtime's own view of the
    // contract, not a claim that the contract may not exceed it.
    if (adapter === undefined) continue;
    resolved.set(adapter.texture_key, multiplier);
  }
  return resolved;
}
