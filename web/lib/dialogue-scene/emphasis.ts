// Who the player is meant to be looking at, expressed as numbers a view can apply.
//
// Composition is authored: the script decides who is on stage and in which slot,
// and the consumer never adds or removes a figure to make a picture. Emphasis is
// the consumer's half of that bargain. A line names one speaker, and the drawing
// has to say so without the player reading the name plate first.
//
// The rule is that nobody vanishes. A listener who dimmed to nothing would
// destroy the composition the script wrote; a listener drawn exactly like the
// speaker would leave the composition unreadable. So the difference is small and
// paid on three channels at once - brightness, colour, and a little size -
// because any one of them alone has to be pushed far enough to be ugly before it
// is legible.

import { slotIsFarRank, slotStackOrder } from "./scene-hud";
import type { ScenarioSlot } from "@/lib/scenario/program";

/** How an actor is drawn this moment, relative to the frame their slot gives them. */
export interface ActorEmphasis {
  readonly alpha: number;
  /** A cool grey multiply for anyone who is not speaking, or null for full colour. */
  readonly tint: number | null;
  /** Multiplier on the slot frame, applied about the figure's feet. */
  readonly scale: number;
  /** Higher is nearer the viewer; the speaker outranks every slot. */
  readonly stackOrder: number;
}

export const SPEAKER_STACK_ORDER = 3;

/** Full colour, a touch forward, and in front of everyone. */
export const SPEAKING_SCALE = 1.045;

/** The near rank when somebody else has the line. */
export const LISTENER_ALPHA = 0.88;
export const LISTENER_TINT = 0xb7bdd0;

/** The far rank when somebody else has the line: further back, and further down. */
export const FAR_LISTENER_ALPHA = 0.72;
export const FAR_LISTENER_TINT = 0x8990a6;

/**
 * The emphasis for one staged actor.
 *
 * A speaker in a far slot is brightened and lifted forward like any other, and
 * stays smaller, because their slot already said how far away they are. Emphasis
 * says who is talking; it does not rearrange the room.
 */
export function actorEmphasis(slot: ScenarioSlot, speaking: boolean): ActorEmphasis {
  if (speaking) {
    return Object.freeze({
      alpha: 1,
      tint: null,
      scale: SPEAKING_SCALE,
      stackOrder: SPEAKER_STACK_ORDER,
    });
  }
  const far = slotIsFarRank(slot);
  return Object.freeze({
    alpha: far ? FAR_LISTENER_ALPHA : LISTENER_ALPHA,
    tint: far ? FAR_LISTENER_TINT : LISTENER_TINT,
    scale: 1,
    stackOrder: slotStackOrder(slot),
  });
}

/**
 * Emphasis for a moment with no speaker at all.
 *
 * Narration is not silence with the last speaker still lit: nobody is talking, so
 * nobody is picked out, and the whole staged composition is shown as the script
 * arranged it.
 */
export function narrationEmphasis(slot: ScenarioSlot): ActorEmphasis {
  const far = slotIsFarRank(slot);
  return Object.freeze({
    alpha: far ? FAR_LISTENER_ALPHA + 0.08 : 1,
    tint: far ? FAR_LISTENER_TINT : null,
    scale: 1,
    stackOrder: slotStackOrder(slot),
  });
}
