// A villager's readout: the name that floats over them, and the offer to talk.
//
// This file used to hold an `Npc` class — a sprite, a name label, a talk prompt
// and the show-and-hide for it — constructed by nothing. The prepared scene
// builds its villagers itself, from the manifest's own placements and motion
// bindings, and had done so for long enough that the class was a *fourth* copy
// of the prompt rule: the scene's, the portal's, and this one, none of which
// could say what was on offer without being asked to draw it.
//
// The rule is the `prompt` family's now, so the class had nothing left that was
// its own and is gone. What survives is what the scene actually reads: the
// range at which a conversation is offered, the line of text, and the two
// pieces of geometry and style the prompt is drawn with. Everything below is
// world-space — the name and the prompt belong to a position in the town, not
// to the screen; the panel that opens when the player talks is the
// screen-fixed half of this feature, and the conversation it plays is a
// scenario walked by `lib/scenario/runtime.ts`.

import type Phaser from "phaser";

/**
 * Marker shown above the villager the player can currently talk to.
 *
 * Exported so a probe or a harness can assert the prompt's text without duplicating the literal,
 * which is exactly how a rename silently breaks a capture check.
 */
export const NPC_TALK_PROMPT_TEXT = "▲ Talk";

/**
 * How near the player has to stand for a villager to offer a conversation.
 *
 * Consumer-owned: nothing refuses over it, and it is a fact about how far a
 * person will reasonably walk to be spoken to rather than about the package.
 */
export const NPC_TALK_RANGE_PX = 145;

/** Clearance between the top of the name label and the bottom of the talk prompt. */
export const NPC_TALK_PROMPT_GAP_PX = 6;

export const NPC_TALK_PROMPT_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "monospace",
  fontSize: "13px",
  color: "#ffdf8a",
  backgroundColor: "#000000a0",
  padding: { x: 6, y: 3 },
};
