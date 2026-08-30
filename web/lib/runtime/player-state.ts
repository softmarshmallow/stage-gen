// The controller's state vocabulary, with nothing else in it.
//
// Split out of `player.ts` for one reason: that module imports Phaser, and Phaser cannot be
// evaluated outside a browser. Anything that needs to *reason* about a player state — the bot
// adapter deciding whether the character is mid-attack, the automation probe declaring what it
// publishes — would otherwise have to drag a rendering engine in behind it, or re-declare the list
// and let it go stale in silence. `import type` hides that problem only for as long as nobody
// needs a value.

export type PlayerState =
  | "idle"
  | "walk"
  | "run"
  | "jump"
  | "crouch"
  | "attack"
  | "ranged_attack"
  | "hurt"
  | "death"
  | "climb";

/**
 * The states in which the character is committed to an attack.
 *
 * A set rather than a comparison, because "is this character attacking" is asked in more than one
 * place and every one of them used to spell `state === "attack"`. That comparison stays type-valid
 * when a second attack state appears, so a missed call site does not fail to compile — it simply
 * reports a casting character as idle for the rest of the run.
 */
export const PLAYER_ATTACK_STATES: ReadonlySet<PlayerState> = Object.freeze(
  new Set<PlayerState>(["attack", "ranged_attack"]),
) as ReadonlySet<PlayerState>;

/** Which runtime state plays each weapon class's drawn strip. */
export const PLAYER_ATTACK_STATE_BY_MOTION: Readonly<
  Record<"basic_attack" | "skill_cast", PlayerState>
> = Object.freeze({
  basic_attack: "attack",
  skill_cast: "ranged_attack",
});
