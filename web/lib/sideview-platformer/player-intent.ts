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

import { defineIntent, intentFrom, parseIntentBlock, type IntentBlockView } from "@/lib/families/intent";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { BlockTable } from "@/lib/manifest/blocks";

export type PlayerIntent = Readonly<{
  left: boolean;
  right: boolean;
  up: boolean;
  down: boolean;
  /** Held modifier. Horizontal movement falls back to the walk speed without it. */
  run: boolean;
  /**
   * Held. Which way to face, regardless of which direction is pressed.
   *
   * Facing normally follows the movement key, which is the right rule for a keyboard and the wrong
   * one for a policy that backs out of contact: a character retreating from something it is
   * shooting must keep the target in front of it, and pressing away from the target would
   * otherwise turn it around mid-throw. Null means "follow the movement", which is what every
   * human input and every older source asks for.
   */
  face: "left" | "right" | null;
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
  face: null,
  jump: false,
  attack: false,
  useHealing: false,
  toggleInventory: false,
});

/**
 * Which of this genre's keys are requests and which are conditions.
 *
 * The paragraph above this file's type used to be the only statement of it, and a paragraph cannot
 * be checked: a field added to `PlayerIntent` and forgotten by whichever sampler was supposed to
 * clear it is a request nothing spends or a condition nothing holds, and both read as "the input is
 * dropping presses". `defineIntent` refuses a key classified twice or not at all, against the
 * record itself, at module load.
 *
 * `face` is a level and not a boolean, which is the reason the family is generic over the value
 * type rather than over a set of flags: "which way to face, regardless of which direction is
 * pressed" is a condition with three states.
 */
export const PLATFORMER_INTENT_SHAPE = defineIntent<PlayerIntent>(
  NEUTRAL_PLAYER_INTENT,
  ["jump", "attack", "useHealing", "toggleInventory"],
  ["left", "right", "up", "down", "run", "face"],
);

/**
 * The block this genre's intent depends on.
 *
 * `[gameplay] combat.enabled` is what makes `attack` an edge this package answers for rather than
 * one the controller suppresses, so `gameplay` is the block the family gates by name for itself.
 */
export const PLATFORMER_INTENT_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's intent block. Refuses by naming `gameplay`. */
export function parsePlatformerIntentBlock(blocks: BlockTable): IntentBlockView {
  return parseIntentBlock(blocks, PLATFORMER_INTENT_BLOCK);
}

/**
 * Build a frozen intent, defaulting every unstated field to "not asked for".
 *
 * Defaulting rather than requiring all ten fields is deliberate: a policy that only wants to walk
 * right should say `{ right: true }` and inherit silence everywhere else, so adding a future action
 * to the type cannot silently change what an existing source is asking for.
 */
export function playerIntent(requested: Partial<PlayerIntent> = {}): PlayerIntent {
  return intentFrom(PLATFORMER_INTENT_SHAPE, requested);
}

/**
 * A source of intent that is not a keyboard.
 *
 * The type this module's opening paragraph promised and nothing had yet declared: a policy, a demo,
 * or a replay's script answers this once per frame and the scene acts on it instead of reading keys.
 * Nothing about the source travels with the answer, which is what keeps the controller unable to
 * tell one apart from a person.
 */
export type ScenePlayerIntentSource = () => PlayerIntent;
