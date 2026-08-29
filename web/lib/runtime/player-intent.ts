// Per-frame player intent — the single input the controller acts on.
//
// The controller used to read Phaser's keyboard from inside `update`, which made the keyboard the
// only thing that could ever move the player: an automated run, a demo, or a replay had no way in
// that did not involve synthesizing browser key events. Intent is the seam. A source decides what
// the player is trying to do this frame, the controller decides what that costs in physics, and
// neither knows anything about the other.
//
// Held fields describe a state that persists while the source keeps asking for it. Edge-triggered
// fields are requests: they are set on the frame the action is asked for and clear afterwards,
// which is what keeps a held key from re-triggering a jump on every frame it stays down. A source
// that cannot distinguish the two must not report the edge fields as held, or the controller will
// read a held key as an unbroken stream of fresh requests.

export type PlayerIntent = Readonly<{
  left: boolean;
  right: boolean;
  up: boolean;
  down: boolean;
  /** Held modifier. Horizontal movement falls back to the walk speed without it. */
  run: boolean;
  /** Edge-triggered. Combined with `down` on a one-way platform this is the drop-through request. */
  jump: boolean;
  /** Edge-triggered. The controller suppresses it for packages that disable combat. */
  attack: boolean;
  /**
   * Edge-triggered request to spend one healing consumable.
   *
   * Consumed by the scene rather than the controller: the controller owns the health pool, but
   * the inventory the drink comes out of belongs to the scene.
   */
  useHealing: boolean;
  /** Edge-triggered. Consumed by the scene, which owns the HUD. */
  toggleInventory: boolean;
}>;

/** Every action unrequested. The intent of a source that has nothing to say this frame. */
export const NEUTRAL_PLAYER_INTENT: PlayerIntent = Object.freeze({
  left: false,
  right: false,
  up: false,
  down: false,
  run: false,
  jump: false,
  attack: false,
  useHealing: false,
  toggleInventory: false,
});

/**
 * Build a frozen intent, defaulting every unstated field to "not asked for".
 *
 * Defaulting rather than requiring all nine fields is deliberate: a policy that only wants to walk
 * right should say `{ right: true }` and inherit silence everywhere else, so adding a future action
 * to the type cannot silently change what an existing source is asking for.
 */
export function playerIntent(requested: Partial<PlayerIntent> = {}): PlayerIntent {
  return Object.freeze({ ...NEUTRAL_PLAYER_INTENT, ...requested });
}
