import type { PlayerState } from "./player";
import type { MotionBinding } from "./prepared-manifest";
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
  climb: Object.freeze({ runtime_state: "climb", texture_key: "character_climb" }),
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

export function preparedPlayerMotionPlayback(
  states: Readonly<Record<string, MotionBinding>>,
): Partial<Record<PlayerState, RuntimeMotionPlayback>> {
  return Object.fromEntries(
    Object.entries(states).flatMap(([state, binding]) => {
      const adapter = preparedPlayerStateAdapter(state);
      return adapter ? [[adapter.runtime_state, binding.playback]] : [];
    }),
  );
}
