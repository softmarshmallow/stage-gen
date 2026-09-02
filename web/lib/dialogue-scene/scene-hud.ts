// Layout for the in-canvas visual-novel HUD, kept free of Phaser.
//
// The scene is played inside the canvas the way a visual novel is: one fixed
// design space that the engine scales to whatever viewport it lands in. That
// only works if the layout is deterministic, so every rectangle the scene draws
// is computed here as a pure function of the design frame and unit-tested,
// rather than measured off DOM elements.
//
// Unlike the point-and-click room, the dialogue panel is drawn *over* the art
// rather than in a band beneath it. A room authors click targets across its
// whole frame, so a panel on top eventually covers something the player has to
// reach; a scene has exactly one target — advance — and it is the whole canvas.
// Overlaying is both the genre's convention and safe here for that reason.

import { containSize, type Rect, type Size } from "@/lib/shell/hud-geometry";

/**
 * The design frame: the producer's own background contract.
 *
 * `dialogue-scene-bundle-v5` admits exactly one background size, so the frame
 * is known before the texture loads and the layout never waits on it.
 */
export const DIALOGUE_STAGE: Size = Object.freeze({ width: 1672, height: 941 });

export const PANEL_MARGIN_X = 36;
export const PANEL_MARGIN_BOTTOM = 30;
export const PANEL_HEIGHT = 208;
export const PANEL_PADDING_X = 34;
export const PANEL_PADDING_TOP = 44;
export const CHIP_HEIGHT = 46;
export const CHIP_MIN_WIDTH = 150;
export const CHIP_PADDING_X = 26;
export const CHIP_OFFSET_X = 28;

/** The sprite's share of the frame, matching the authored presentation. */
export const SPRITE_HEIGHT_RATIO = 0.98;
export const SPRITE_MAX_WIDTH_RATIO = 0.66;

export interface FramingPlacement {
  /** Normalized presentation scale, about the sprite's top-centre. */
  readonly scale: number;
  readonly xPercent: number;
  readonly yPercent: number;
}

/**
 * Where the character stands, in design pixels.
 *
 * The authored presentation gives a scale and a top-centre anchor as
 * percentages; this resolves them against the frame while preserving the
 * sprite's aspect, so a wide plate is limited by width and a tall one by
 * height rather than being stretched to fit either.
 */
/**
 * Where an actor standing in one slot is drawn.
 *
 * Three slots across the stage rather than one fixed side, because a scene with
 * a cast has to be able to put two people on screen and have the player see who
 * is where. The centre slot is the old single-character position, so a one-actor
 * scene is framed exactly as it always was.
 */
export function slotFrame(
  stage: Size,
  source: Size,
  placement: FramingPlacement,
  slot: "left" | "center" | "right",
): Rect {
  const centred = spriteFrame(stage, source, placement);
  const offsets = { left: -0.26, center: 0, right: 0.26 } as const;
  // Not rounded: `spriteFrame` is not either, and the canvas is scaled to the
  // viewport anyway, so rounding here would only make the centre slot disagree
  // with the single-actor framing it is supposed to reproduce exactly.
  return Object.freeze({ ...centred, x: centred.x + stage.width * offsets[slot] });
}

export function spriteFrame(
  stage: Size,
  source: Size,
  placement: FramingPlacement,
): Rect {
  if (source.width <= 0 || source.height <= 0) {
    throw new Error("dialogue-scene sprite source must have a positive size");
  }
  // Aspect-fit into the sprite's share of the frame: full height by default,
  // clamped by the width budget so a wide plate shrinks instead of stretching.
  const fitted = containSize(source, {
    width: stage.width * SPRITE_MAX_WIDTH_RATIO,
    height: stage.height * SPRITE_HEIGHT_RATIO,
  });
  const scaled = { width: fitted.width * placement.scale, height: fitted.height * placement.scale };
  const anchorX = (placement.xPercent / 100) * stage.width;
  const anchorY = (placement.yPercent / 100) * stage.height;
  return Object.freeze({
    x: anchorX - scaled.width / 2,
    y: anchorY,
    width: scaled.width,
    height: scaled.height,
  });
}

export function dialoguePanelRect(stage: Size): Rect {
  return Object.freeze({
    x: PANEL_MARGIN_X,
    y: stage.height - PANEL_MARGIN_BOTTOM - PANEL_HEIGHT,
    width: stage.width - PANEL_MARGIN_X * 2,
    height: PANEL_HEIGHT,
  });
}

/** The speaker's name plate, straddling the panel's top edge. */
export function speakerChipRect(panel: Rect, labelWidth: number): Rect {
  const width = Math.max(CHIP_MIN_WIDTH, labelWidth + CHIP_PADDING_X * 2);
  return Object.freeze({
    x: panel.x + CHIP_OFFSET_X,
    y: panel.y - CHIP_HEIGHT / 2,
    width,
    height: CHIP_HEIGHT,
  });
}

/** Top-left anchor of the panel's body copy. */
export function bodyTextPoint(panel: Rect): { readonly x: number; readonly y: number } {
  return Object.freeze({ x: panel.x + PANEL_PADDING_X, y: panel.y + PANEL_PADDING_TOP });
}

export function bodyTextWrapWidth(panel: Rect): number {
  return panel.width - PANEL_PADDING_X * 2;
}

/** Bottom-right anchor of the one-line progress readout, inside the panel. */
export function progressPoint(panel: Rect): { readonly x: number; readonly y: number } {
  return Object.freeze({
    x: panel.x + panel.width - PANEL_PADDING_X,
    y: panel.y + panel.height - 16,
  });
}

/** The end card, centred on the frame. */
export function completeCardRect(stage: Size): Rect {
  const width = Math.min(760, stage.width - PANEL_MARGIN_X * 4);
  const height = 240;
  return Object.freeze({
    x: (stage.width - width) / 2,
    y: (stage.height - height) / 2,
    width,
    height,
  });
}

/** The end card's one control: an icon button centred under the title. */
export const COMPLETE_CONTROL_WIDTH = 108;
export const COMPLETE_CONTROL_HEIGHT = 64;
export const COMPLETE_CONTROL_OFFSET_Y = 28;

export function completeCardControlRect(card: Rect): Rect {
  return Object.freeze({
    x: card.x + (card.width - COMPLETE_CONTROL_WIDTH) / 2,
    y: card.y + card.height / 2 + COMPLETE_CONTROL_OFFSET_Y,
    width: COMPLETE_CONTROL_WIDTH,
    height: COMPLETE_CONTROL_HEIGHT,
  });
}

const CHOICE_HEIGHT = 84;
const CHOICE_GAP = 18;
const CHOICE_WIDTH_RATIO = 0.68;

/**
 * Where each option of a choice is drawn, stacked and centred over the stage.
 *
 * Pure and exported for the same reason `spriteFrame` is: no test in this
 * repository simulates a click, so hit-testing that lived inside the Phaser
 * scene would be verified by nothing at all. Keeping it here means the geometry
 * a player has to hit is checked by the same kind of unit test as the panel.
 */
export function choiceRects(stage: Size, count: number): readonly Rect[] {
  if (!Number.isSafeInteger(count) || count < 1) return [];
  const width = Math.round(stage.width * CHOICE_WIDTH_RATIO);
  const x = Math.round((stage.width - width) / 2);
  const block = count * CHOICE_HEIGHT + (count - 1) * CHOICE_GAP;
  // Centred in the space above the dialogue panel, never overlapping it.
  const available = dialoguePanelRect(stage).y;
  const top = Math.max(Math.round((available - block) / 2), CHOICE_GAP);
  return Object.freeze(
    Array.from({ length: count }, (_unused, index) =>
      Object.freeze({
        x,
        y: top + index * (CHOICE_HEIGHT + CHOICE_GAP),
        width,
        height: CHOICE_HEIGHT,
      }),
    ),
  );
}

/** Which option a pointer at this stage-space point is over, or null. */
export function choiceAt(
  stage: Size,
  count: number,
  point: { readonly x: number; readonly y: number },
): number | null {
  const rects = choiceRects(stage, count);
  const index = rects.findIndex(
    (rect) =>
      point.x >= rect.x &&
      point.x <= rect.x + rect.width &&
      point.y >= rect.y &&
      point.y <= rect.y + rect.height,
  );
  return index === -1 ? null : index;
}

/**
 * Where a dialogue box's contents sit inside a generated panel.
 *
 * The box is drawn art now, so its usable interior is measured on the artwork rather than
 * guessed from a fixed inset: the producer publishes the ornament-free rectangle and this
 * turns it into a name row, a wrapped body, and a bottom-right progress anchor. The knobs
 * are the scene's to tune; nothing about a specific game's border is baked in here.
 */
export type VisualNovelBoxKnobs = Readonly<{
  paddingX: number;
  paddingY: number;
  nameRowHeight: number;
  bodyGap: number;
  progressRowHeight: number;
}>;

export const DEFAULT_VISUAL_NOVEL_BOX_KNOBS: VisualNovelBoxKnobs = Object.freeze({
  paddingX: 10,
  paddingY: 6,
  nameRowHeight: 30,
  bodyGap: 6,
  progressRowHeight: 20,
});

export type VisualNovelBoxLayout = Readonly<{
  name: { readonly x: number; readonly y: number };
  body: { readonly x: number; readonly y: number };
  bodyWrapWidth: number;
  progress: { readonly x: number; readonly y: number };
}>;

export function visualNovelBoxLayout(
  safe: Rect,
  knobs: VisualNovelBoxKnobs = DEFAULT_VISUAL_NOVEL_BOX_KNOBS,
): VisualNovelBoxLayout {
  const left = safe.x + knobs.paddingX;
  const top = safe.y + knobs.paddingY;
  const right = safe.x + safe.width - knobs.paddingX;
  const bottom = safe.y + safe.height - knobs.paddingY;
  return Object.freeze({
    name: Object.freeze({ x: left, y: top }),
    body: Object.freeze({ x: left, y: top + knobs.nameRowHeight + knobs.bodyGap }),
    bodyWrapWidth: Math.max(1, right - left),
    progress: Object.freeze({ x: right, y: bottom }),
  });
}
