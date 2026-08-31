// Layout and input rules for the in-canvas room HUD, kept free of Phaser.
//
// The room is played inside the canvas the way a mobile game is: the backdrop,
// the narration panel, the inventory and the verb controls are all drawn in one
// fixed design space that the engine scales to whatever viewport it lands in.
// That only works if the layout is deterministic, so every rectangle the scene
// draws is computed here as a pure function of the authored frame and
// unit-tested, rather than measured off DOM elements that no longer exist.
//
// The HUD gets its own band under the room rather than floating over it. A room
// authors hotspot regions across its whole frame — the attic hides a music box
// low and to the right — so any panel drawn on top of the scene eventually
// covers something the player has to be able to click. The canvas is therefore
// taller than the authored frame by exactly the band, which also makes the
// playfield a friendlier shape on a phone than bare 16:9.
//
// The pointer rule lives here for the same reason: "which verb did that press
// mean" is a small decision with three inputs (the mode toggle, the mouse
// button, how long the press was held) and exactly the kind of thing that goes
// subtly wrong on touch, where there is no right-click and no hover.

import type { Verb } from "./contract";

export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface StageSize {
  readonly width: number;
  readonly height: number;
}

/** Gap between the HUD and the canvas edges, in design pixels. */
export const HUD_MARGIN = 24;

/** The strip holding the inventory and the verb controls. */
export const HUD_BAR_HEIGHT = 132;

/**
 * The narration panel above it.
 *
 * Three wrapped lines at the narration size, because the longest line a room
 * can produce is an interaction's own line followed by the win line, and a
 * panel that fits only the common case clips exactly the sentence that ends
 * the game.
 */
export const HUD_NARRATION_HEIGHT = 156;

export const HUD_GAP = 12;

export const INVENTORY_SLOT_SIZE = 84;
export const INVENTORY_SLOT_GAP = 14;

/** Height reserved above the slots for the one-line control hint. */
export const HUD_LABEL_BAND = 26;

export const VERB_BUTTON_WIDTH = 132;
export const VERB_BUTTON_HEIGHT = 60;

/** How long a press must be held, with no second button, to mean "look at it". */
export const LONG_PRESS_MS = 420;

export type VerbMode = "act" | "look";

/**
 * Which verb one press meant.
 *
 * Total by construction, because the alternative is a room that cannot be
 * inspected on a phone: touch has no secondary button, so the long press and
 * the mode toggle are the only two ways in, and both have to work whatever the
 * other is doing.
 */
export function resolveVerb(
  mode: VerbMode,
  press: { readonly secondary: boolean; readonly heldMs: number },
): Verb {
  if (press.secondary || press.heldMs >= LONG_PRESS_MS) return "inspect";
  return mode === "look" ? "inspect" : "use";
}

/** A hotspot's normalized region in design pixels. */
export function hotspotRect(
  stage: StageSize,
  region: { readonly x: number; readonly y: number; readonly w: number; readonly h: number },
): Rect {
  return {
    x: region.x * stage.width,
    y: region.y * stage.height,
    width: region.w * stage.width,
    height: region.h * stage.height,
  };
}

/**
 * The largest rectangle of `source`'s aspect that fits inside `outer`, centred.
 *
 * A hotspot sprite is composited into an authored region, and stretching it to
 * that region's aspect is how a music box ends up wider than the shelf it
 * stands on.
 */
export function containRect(outer: Rect, source: { width: number; height: number }): Rect {
  if (source.width <= 0 || source.height <= 0) return outer;
  const scale = Math.min(outer.width / source.width, outer.height / source.height);
  const width = source.width * scale;
  const height = source.height * scale;
  return {
    x: outer.x + (outer.width - width) / 2,
    y: outer.y + (outer.height - height) / 2,
    width,
    height,
  };
}

/** Everything below the room: gap, narration, gap, control bar. */
export const HUD_BAND_HEIGHT = HUD_GAP + HUD_NARRATION_HEIGHT + HUD_GAP + HUD_BAR_HEIGHT;

/** The canvas the engine is booted at: the authored frame plus the HUD band. */
export function canvasSize(room: StageSize): StageSize {
  return { width: room.width, height: room.height + HUD_BAND_HEIGHT };
}

/** The playfield: the authored frame, at the top of the canvas. */
export function roomRect(room: StageSize): Rect {
  return { x: 0, y: 0, width: room.width, height: room.height };
}

export function hudBarRect(room: StageSize): Rect {
  return {
    x: 0,
    y: room.height + HUD_GAP + HUD_NARRATION_HEIGHT + HUD_GAP,
    width: room.width,
    height: HUD_BAR_HEIGHT,
  };
}

export function narrationRect(room: StageSize): Rect {
  return {
    x: HUD_MARGIN,
    y: room.height + HUD_GAP,
    width: room.width - HUD_MARGIN * 2,
    height: HUD_NARRATION_HEIGHT,
  };
}

/**
 * One slot per carried item, laid left to right from the bar's left edge.
 *
 * Slots are positioned by index rather than packed by a layout pass, so an item
 * keeps its place in the bar for as long as it is carried.
 */
export function inventorySlotRects(room: StageSize, count: number): readonly Rect[] {
  const y = hudLabelPoint(room).y + HUD_LABEL_BAND;
  const slots: Rect[] = [];
  for (let index = 0; index < Math.max(0, count); index += 1) {
    slots.push({
      x: HUD_MARGIN + index * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GAP),
      y,
      width: INVENTORY_SLOT_SIZE,
      height: INVENTORY_SLOT_SIZE,
    });
  }
  return slots;
}

/**
 * Where the control hint sits: a band above the slots, not behind them.
 *
 * The line changes with the game — it says what a tap does until something is
 * held, then what the held thing is for — so it needs its own row rather than
 * whatever space the inventory happens to leave.
 */
export function hudLabelPoint(room: StageSize): { readonly x: number; readonly y: number } {
  return { x: HUD_MARGIN, y: hudBarRect(room).y + 6 };
}

export interface VerbButtons {
  readonly act: Rect;
  readonly look: Rect;
  readonly hint: Rect;
}

/** The verb controls, right-aligned in the bar so the inventory grows towards them. */
export function verbButtonRects(room: StageSize): VerbButtons {
  const bar = hudBarRect(room);
  const y = bar.y + (bar.height - VERB_BUTTON_HEIGHT) / 2;
  const right = room.width - HUD_MARGIN;
  const rect = (indexFromRight: number): Rect => ({
    x: right - (indexFromRight + 1) * VERB_BUTTON_WIDTH - indexFromRight * HUD_GAP,
    y,
    width: VERB_BUTTON_WIDTH,
    height: VERB_BUTTON_HEIGHT,
  });
  return { hint: rect(0), look: rect(1), act: rect(2) };
}

/** The end card, centred on the room rather than on the whole canvas. */
export function winPanelRect(room: StageSize): Rect {
  const width = Math.min(room.width - HUD_MARGIN * 4, 720);
  const height = 220;
  return {
    x: (room.width - width) / 2,
    y: (room.height - height) / 2,
    width,
    height,
  };
}

/**
 * How many slots fit before the inventory would run under the verb controls.
 *
 * A room that grants more items than the bar can hold is a design problem, not
 * a rendering one, so this is exported for the scene to assert against rather
 * than silently overlapping the controls.
 */
export function inventoryCapacity(room: StageSize): number {
  const controls = verbButtonRects(room);
  const available = controls.act.x - HUD_GAP - HUD_MARGIN;
  return Math.max(0, Math.floor((available + INVENTORY_SLOT_GAP) / (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GAP)));
}
