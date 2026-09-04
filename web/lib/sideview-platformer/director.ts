// The platformer's instantiation of the `director` family: an authored gate.
//
// `[[boss_encounters]]` publishes four facts about a set-piece — where it
// stands (`anchor`), what stands there (`mob_id`), what plays while it does
// (`track_id`), and whether it comes back (`respawn_policy`) — and the runtime
// used exactly one of them. It resolved the entry to an ordinary creature
// placed at ninety-one percent of the map at world build and dropped the other
// three on the floor. That is the framing example the plan opens with, and this
// file is the half of it that is code.
//
// What each of the four becomes:
//
//   - `anchor` is the family's spatial trigger. It resolves against the map's
//     own portal endpoints — the same table `[[spawns]]` and `[[transitions]]`
//     resolve their anchors against — so a gate is a *place in the map* rather
//     than a fraction somebody typed into the consumer.
//   - `mob_id` is what the set-piece places when it fires. A boss is `director`
//     plus a profile: everything about the creature itself is already
//     somebody's — the rank scale, the vitals gauge, the actor-ai archetype.
//   - `track_id` is a swap, applied when the gate fires and put back when it
//     ends. It was never applied at all, which is the same defect as a swap
//     nobody reverts at the far end of the same spectrum.
//   - `respawn_policy = "quest_reset_only"` is `once`. A gate is a place in a
//     story, and the story does not un-happen because the player walked back
//     through the map.

import {
  armAt,
  enterPhase,
  parseDirectorBlock,
  SwapLedger,
  triggerReached,
  type DirectorBlockView,
  type DirectorPhaseState,
  type DirectorRecurrence,
  type DirectorSwap,
  type SpatialTrigger,
} from "@/lib/families/director";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS, type PreparedMap } from "@/lib/manifest/prepared-manifest";

/**
 * This genre's phase vocabulary, and it is deliberately short.
 *
 * The runner's has six because a streamed track has an arena to wait for and a
 * cut-in to play over; an authored map has neither. `armed` is before the
 * player has reached the gate, `engaged` is the fight, `ended` is after it —
 * and with `once` recurrence `ended` is where the set-piece stays.
 */
export type SetPiecePhase = "armed" | "engaged" | "ended";

/**
 * What a gate ended as.
 *
 * One member today: the fight ends when the thing standing in it is defeated.
 * A gate the player walks away from is still `engaged` — the world it stood in
 * is torn down and the set-piece is re-armed — which is why "left" is not an
 * outcome here the way `exhausted` is in the runner.
 */
export type SetPieceOutcome = "won";

/** The authored shape this genre publishes a set-piece in. */
export interface AuthoredSetPiece {
  readonly encounter_id: string;
  readonly map_id: string;
  readonly anchor: string;
  readonly mob_id: string;
  readonly track_id: string;
  readonly respawn_policy: string;
}

/**
 * Resolve an authored anchor to a place on the map, in world pixels.
 *
 * The map's portal endpoints are the anchor table: `[[spawns]].anchor` and
 * `[[transitions]].from_anchor` already resolve against them, and the package
 * validator already refuses a spawn whose anchor does not. A set-piece's anchor
 * was never checked, because nothing read it — so an unresolved one is answered
 * with null here and reported by the consumer rather than thrown, which is the
 * same call `dropLoot` makes about an item id that does not resolve.
 */
export function setPieceAnchorX(
  map: PreparedMap,
  anchor: string,
  worldWidthPx: number,
): number | null {
  const endpoint = map.portal?.endpoints.find((candidate) => candidate.anchor === anchor);
  if (!endpoint) return null;
  return endpoint.normalized_x * worldWidthPx;
}

/** How this genre's authored policy reads as the family's recurrence. */
export function setPieceRecurrence(respawnPolicy: string): DirectorRecurrence {
  return respawnPolicy === "quest_reset_only" ? "once" : "recurring";
}

/**
 * One authored gate, for the life of the session.
 *
 * Session-scoped rather than world-scoped, and that is what honours the
 * respawn policy: a set-piece that has ended stays ended when the player walks
 * back onto the map. What *is* world-scoped is the body standing in it, which
 * the scene holds and the teardown destroys.
 */
export class SetPiece {
  readonly state: DirectorPhaseState<SetPiecePhase, SetPieceOutcome> = {
    phase: "armed",
    phaseStartedAt: null,
    outcome: null,
  };
  private readonly swaps = new SwapLedger();

  constructor(
    readonly authored: AuthoredSetPiece,
    readonly recurrence: DirectorRecurrence,
  ) {}

  /** Whether this gate is done with, for good. */
  spent(): boolean {
    return this.state.phase === "ended" && this.recurrence === "once";
  }

  /**
   * Re-arm a gate whose world was torn down mid-fight.
   *
   * A player who walks out of the map during the fight has not beaten it, and a
   * gate stuck on `engaged` with nothing standing in it would never fire again.
   * Whatever it had swapped is put back on the way, because the run it swapped
   * for is over.
   */
  worldTornDown(): void {
    if (this.state.phase !== "engaged") return;
    this.swaps.revertAll();
    this.state.phase = "armed";
    this.state.phaseStartedAt = null;
  }

  /** Fire the gate: the player has reached it. */
  engage(now: number, swaps: readonly DirectorSwap[]): void {
    for (const swap of swaps) this.swaps.apply(swap);
    enterPhase(this.state, "engaged", now);
  }

  /** End the gate, putting back everything it swapped. */
  end(now: number, outcome: SetPieceOutcome): void {
    this.swaps.revertAll();
    this.state.outcome = outcome;
    enterPhase(this.state, "ended", now);
  }

  /** What the gate has in force, for a probe or a test. */
  inForce(): readonly string[] {
    return this.swaps.ids();
  }
}

/** The trigger a gate is armed at, in world pixels. */
export function setPieceTrigger(anchorX: number): SpatialTrigger {
  return armAt(anchorX);
}

/** Whether the body has reached the gate. */
export function setPieceReached(trigger: SpatialTrigger, playerX: number): boolean {
  return triggerReached(trigger, playerX);
}

export const PLATFORMER_DIRECTOR_BLOCKS = Object.freeze([
  Object.freeze({ block: "gameplay", version: PREPARED_RUNTIME_BLOCKS.gameplay }),
  Object.freeze({ block: "maps", version: PREPARED_RUNTIME_BLOCKS.maps }),
]);

/** Gate the platformer's director blocks. Refuses by naming the block that moved. */
export function parsePlatformerDirectorBlocks(blocks: BlockTable): readonly DirectorBlockView[] {
  return PLATFORMER_DIRECTOR_BLOCKS.map((binding) => parseDirectorBlock(blocks, binding));
}
