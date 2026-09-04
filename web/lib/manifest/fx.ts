// The published `fx` block: plates with producer-traced geometry, and moment bindings.
//
// Every genre's manifest embeds this block identically, so every genre parses
// it here. The mask polygon is geometry the validate node traced from the
// plate's eroded alpha — the portable form of the silhouette, for a consumer
// that clips by geometry rather than by the plate's own alpha. Either way the
// consumer is handed the shape and never reads pixels to rediscover it.

import { CUT_IN_CHOREOGRAPHY_NAMES, type CutInChoreographyName } from "@/lib/families/screen-fx/cut-in";

/**
 * The moments a package may bind, mirroring the generator's `FX_MOMENTS`.
 *
 * Which of them a given genre can actually play is the generator's business:
 * it refuses `encounter_start` from a runner that declares no encounter,
 * offline, before the plate is ever drawn. Here the vocabulary is simply
 * closed, so an unknown name is a refusal rather than a silent no-op.
 */
export const FX_MOMENTS = ["stage_start", "encounter_start"] as const;
export type FxMomentName = (typeof FX_MOMENTS)[number];
export const FX_EFFECTS = ["cut_in"] as const;
export type FxEffectName = (typeof FX_EFFECTS)[number];

export const CUT_IN_FRAME_LAYOUT = "cut_in_frame_1536x1024_v1";
export const CUT_IN_PORTRAIT_LAYOUT = "cut_in_portrait_1536x1024_v1";
export const CUT_IN_FRAME_ALPHA_POLICY = "transparent_exterior_opaque_body_v1";
export const CUT_IN_PORTRAIT_ALPHA_POLICY = "transparent_exterior_v1";
export const CUT_IN_FRAME_MODES = ["generated_v1", "procedural_v1"] as const;

export interface FxRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface FxCanvas {
  readonly width: number;
  readonly height: number;
}

export interface FxCutInFrame {
  readonly mode: (typeof CUT_IN_FRAME_MODES)[number];
  readonly layout: typeof CUT_IN_FRAME_LAYOUT;
  readonly alphaPolicy: typeof CUT_IN_FRAME_ALPHA_POLICY;
  readonly canvas: FxCanvas;
  /**
   * The eroded silhouette as one outline, normalized to the canvas — a portable
   * convenience for a consumer with no texture to clip with, and `null` when the
   * authored shape is one no single outline honestly describes. The runtime clips
   * with the plate's own alpha and never reads this.
   */
  readonly maskPolygon: readonly (readonly [number, number])[] | null;
  readonly bandRect: FxRect;
  readonly maskErodePx: number;
  readonly asset: string;
}

/**
 * Where the portrait sits inside the frame, as the placement agent judged it:
 * the portrait canvas centre in frame-canvas units (may lie outside 0..1) and
 * its display height as a fraction of the frame canvas height.
 */
export interface FxCutInPlacement {
  readonly scale: number;
  readonly x: number;
  readonly y: number;
}

export interface FxCutInPortrait {
  readonly portraitId: string;
  readonly layout: typeof CUT_IN_PORTRAIT_LAYOUT;
  readonly alphaPolicy: typeof CUT_IN_PORTRAIT_ALPHA_POLICY;
  readonly canvas: FxCanvas;
  readonly alphaRect: FxRect;
  readonly placement: FxCutInPlacement;
  readonly asset: string;
}

export interface FxCutInMoment {
  readonly moment: FxMomentName;
  readonly effect: "cut_in";
  readonly portraitId: string;
  readonly choreography: CutInChoreographyName;
  /**
   * The two lines the cut-in letters.
   *
   * Display names the producer already held - a track name, a boss name -
   * never a generated string, so what is on screen always answers to something
   * the package authored.
   */
  readonly title: string;
  readonly subtitle: string;
}

export type FxMoment = FxCutInMoment;

export const DUST_ATLAS_LAYOUT = "fx_dust_atlas_1024x1024_v1";
export const DUST_ATLAS_ALPHA_POLICY = "transparent_exterior_v1";
/** The contacts a dust cell can draw, in the order the layout fixes. */
export const DUST_CELL_KINDS = ["land", "takeoff", "stride", "slide"] as const;
export type FxDustCellKind = (typeof DUST_CELL_KINDS)[number];

/** One cell: the rectangle the producer measured, never re-derived from the image. */
export interface FxDustCell extends FxRect {
  readonly kind: FxDustCellKind;
}

export interface FxDustAtlas {
  readonly asset: string;
  readonly layout: typeof DUST_ATLAS_LAYOUT;
  readonly alphaPolicy: typeof DUST_ATLAS_ALPHA_POLICY;
  readonly canvas: FxCanvas;
  readonly cells: readonly FxDustCell[];
}

export interface FxBlock {
  readonly cutIn: {
    readonly frame: FxCutInFrame;
    readonly portraits: readonly FxCutInPortrait[];
  } | null;
  /** World-space effect atlases; null when the package authored none. */
  readonly sprite: { readonly dust: FxDustAtlas } | null;
  readonly moments: readonly FxMoment[];
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function literal<const T extends readonly string[]>(
  value: unknown,
  label: string,
  allowed: T,
): T[number] {
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw new Error(`${label} must be one of ${allowed.join(", ")}`);
  }
  return value;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`${label} must be an integer of at least ${minimum}`);
  }
  return value;
}

function finite(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}

function placement(value: unknown, label: string): FxCutInPlacement {
  const source = record(value, label);
  const scale = finite(source.scale, `${label}.scale`);
  if (scale <= 0) throw new Error(`${label}.scale must be positive`);
  return Object.freeze({
    scale,
    x: finite(source.x, `${label}.x`),
    y: finite(source.y, `${label}.y`),
  });
}

function rect(value: unknown, label: string): FxRect {
  const source = record(value, label);
  return Object.freeze({
    x: integer(source.x, `${label}.x`),
    y: integer(source.y, `${label}.y`),
    width: integer(source.width, `${label}.width`),
    height: integer(source.height, `${label}.height`),
  });
}

function canvas(value: unknown, label: string): FxCanvas {
  const source = record(value, label);
  return Object.freeze({
    width: integer(source.width, `${label}.width`, 1),
    height: integer(source.height, `${label}.height`, 1),
  });
}

function polygon(value: unknown, label: string): readonly (readonly [number, number])[] | null {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value) || value.length < 3) {
    throw new Error(`${label} must hold at least three vertices`);
  }
  return Object.freeze(
    value.map((entry, index): readonly [number, number] => {
      if (!Array.isArray(entry) || entry.length !== 2) {
        throw new Error(`${label}[${index}] must be an [x, y] pair`);
      }
      const [x, y] = entry as [unknown, unknown];
      for (const coordinate of [x, y]) {
        if (typeof coordinate !== "number" || !(coordinate >= 0 && coordinate <= 1)) {
          throw new Error(`${label}[${index}] must lie inside the unit canvas`);
        }
      }
      return Object.freeze([x as number, y as number] as const);
    }),
  );
}

/** Parse one published `fx` block, refusing bindings that name nothing. */
function dustAtlas(value: unknown, label: string): FxDustAtlas {
  const raw = record(value, label);
  if (!Array.isArray(raw.cells) || raw.cells.length !== DUST_CELL_KINDS.length) {
    throw new Error(`${label}.cells must carry one rectangle per dust kind`);
  }
  const plate = canvas(raw.canvas, `${label}.canvas`);
  const cells = raw.cells.map((entry, index): FxDustCell => {
    const cellLabel = `${label}.cells[${index}]`;
    const cell = record(entry, cellLabel);
    const box = rect(cell, cellLabel);
    if (box.width <= 0 || box.height <= 0) {
      throw new Error(`${cellLabel} must have a positive size`);
    }
    if (box.x + box.width > plate.width || box.y + box.height > plate.height) {
      throw new Error(`${cellLabel} runs off the atlas`);
    }
    return Object.freeze({
      kind: literal(cell.kind, `${cellLabel}.kind`, DUST_CELL_KINDS),
      ...box,
    });
  });
  const kinds = new Set(cells.map((cell) => cell.kind));
  if (kinds.size !== DUST_CELL_KINDS.length) {
    throw new Error(`${label}.cells must name each dust kind exactly once`);
  }
  return Object.freeze({
    asset: text(raw.asset, `${label}.asset`),
    layout: literal(raw.layout, `${label}.layout`, [DUST_ATLAS_LAYOUT]),
    alphaPolicy: literal(raw.alpha_policy, `${label}.alpha_policy`, [DUST_ATLAS_ALPHA_POLICY]),
    canvas: plate,
    cells: Object.freeze(cells),
  });
}

export function parseFxBlock(value: unknown, label = "fx"): FxBlock {
  const source = record(value, label);
  let cutIn: FxBlock["cutIn"] = null;
  if (source.cut_in !== null && source.cut_in !== undefined) {
    const rawCutIn = record(source.cut_in, `${label}.cut_in`);
    const rawFrame = record(rawCutIn.frame, `${label}.cut_in.frame`);
    const frame: FxCutInFrame = Object.freeze({
      mode: literal(rawFrame.mode, `${label}.cut_in.frame.mode`, CUT_IN_FRAME_MODES),
      layout: literal(rawFrame.layout, `${label}.cut_in.frame.layout`, [CUT_IN_FRAME_LAYOUT]),
      alphaPolicy: literal(rawFrame.alpha_policy, `${label}.cut_in.frame.alpha_policy`, [
        CUT_IN_FRAME_ALPHA_POLICY,
      ]),
      canvas: canvas(rawFrame.canvas, `${label}.cut_in.frame.canvas`),
      maskPolygon: polygon(rawFrame.mask_polygon, `${label}.cut_in.frame.mask_polygon`),
      bandRect: rect(rawFrame.band_rect, `${label}.cut_in.frame.band_rect`),
      maskErodePx: integer(rawFrame.mask_erode_px, `${label}.cut_in.frame.mask_erode_px`),
      asset: text(rawFrame.asset, `${label}.cut_in.frame.asset`),
    });
    if (!Array.isArray(rawCutIn.portraits) || rawCutIn.portraits.length === 0) {
      throw new Error(`${label}.cut_in.portraits must not be empty`);
    }
    const portraits = rawCutIn.portraits.map((entry, index): FxCutInPortrait => {
      const portraitLabel = `${label}.cut_in.portraits[${index}]`;
      const raw = record(entry, portraitLabel);
      return Object.freeze({
        portraitId: text(raw.portrait_id, `${portraitLabel}.portrait_id`),
        layout: literal(raw.layout, `${portraitLabel}.layout`, [CUT_IN_PORTRAIT_LAYOUT]),
        alphaPolicy: literal(raw.alpha_policy, `${portraitLabel}.alpha_policy`, [
          CUT_IN_PORTRAIT_ALPHA_POLICY,
        ]),
        canvas: canvas(raw.canvas, `${portraitLabel}.canvas`),
        alphaRect: rect(raw.alpha_rect, `${portraitLabel}.alpha_rect`),
        placement: placement(raw.placement, `${portraitLabel}.placement`),
        asset: text(raw.asset, `${portraitLabel}.asset`),
      });
    });
    const ids = new Set(portraits.map((entry) => entry.portraitId));
    if (ids.size !== portraits.length) {
      throw new Error(`${label}.cut_in.portraits must carry unique portrait ids`);
    }
    cutIn = Object.freeze({ frame, portraits: Object.freeze(portraits) });
  }
  let sprite: FxBlock["sprite"] = null;
  if (source.sprite !== null && source.sprite !== undefined) {
    const rawSprite = record(source.sprite, `${label}.sprite`);
    sprite = Object.freeze({ dust: dustAtlas(rawSprite.dust, `${label}.sprite.dust`) });
  }
  if (!Array.isArray(source.moments) || source.moments.length === 0) {
    throw new Error(`${label}.moments must not be empty`);
  }
  const moments = source.moments.map((entry, index): FxMoment => {
    const momentLabel = `${label}.moments[${index}]`;
    const raw = record(entry, momentLabel);
    const effect = literal(raw.effect, `${momentLabel}.effect`, FX_EFFECTS);
    const portraitId = text(raw.portrait_id, `${momentLabel}.portrait_id`);
    if (cutIn === null || !cutIn.portraits.some((p) => p.portraitId === portraitId)) {
      throw new Error(`${momentLabel} names a cut_in portrait the block does not publish`);
    }
    return Object.freeze({
      moment: literal(raw.moment, `${momentLabel}.moment`, FX_MOMENTS),
      effect,
      portraitId,
      choreography: literal(
        raw.choreography,
        `${momentLabel}.choreography`,
        CUT_IN_CHOREOGRAPHY_NAMES,
      ),
      title: text(raw.title, `${momentLabel}.title`),
      subtitle: text(raw.subtitle, `${momentLabel}.subtitle`),
    });
  });
  const names = new Set(moments.map((entry) => entry.moment));
  if (names.size !== moments.length) {
    throw new Error(`${label}.moments must bind each moment once`);
  }
  return Object.freeze({ cutIn, sprite, moments: Object.freeze(moments) });
}

/** The published fixture shape, for every consumer's manifest tests. */
export function fxBlockFixture(
  options: { readonly moments?: readonly FxMomentName[]; readonly dust?: boolean } = {},
): Record<string, unknown> {
  const names = options.moments ?? (["stage_start"] as const);
  const lettering: Record<string, readonly [string, string]> = {
    stage_start: ["Sunpetal Sprint", "Bellweather"],
    encounter_start: ["Thicket Router", "Sunpetal Sprint"],
  };
  const dust = options.dust ?? true;
  return {
    sprite: dust
      ? {
          dust: {
            asset: "fx/sprite/dust.png",
            layout: DUST_ATLAS_LAYOUT,
            alpha_policy: DUST_ATLAS_ALPHA_POLICY,
            canvas: { width: 1024, height: 1024 },
            cells: [
              { kind: "land", x: 80, y: 241, width: 440, height: 215 },
              { kind: "takeoff", x: 600, y: 104, width: 344, height: 368 },
              { kind: "stride", x: 161, y: 656, width: 215, height: 205 },
              { kind: "slide", x: 576, y: 602, width: 376, height: 274 },
            ],
          },
        }
      : null,
    cut_in: {
      frame: {
        role: "frame",
        mode: "generated_v1",
        layout: CUT_IN_FRAME_LAYOUT,
        alpha_policy: CUT_IN_FRAME_ALPHA_POLICY,
        canvas: { width: 1536, height: 1024 },
        mask_erode_px: 22,
        mask_polygon: [
          [0, 0.31],
          [1, 0.27],
          [1, 0.71],
          [0, 0.75],
        ],
        band_rect: { x: 0, y: 260, width: 1536, height: 520 },
        asset: "fx/cut_in/frame.png",
      },
      portraits: names.map((name) => ({
        role: "portrait",
        portrait_id: name,
        layout: CUT_IN_PORTRAIT_LAYOUT,
        alpha_policy: CUT_IN_PORTRAIT_ALPHA_POLICY,
        canvas: { width: 1536, height: 1024 },
        alpha_rect: { x: 120, y: 0, width: 1300, height: 1024 },
        placement: { scale: 0.44, x: 0.5, y: 0.53 },
        asset: `fx/cut_in/portrait.${name}.png`,
      })),
    },
    moments: names.map((name) => ({
      moment: name,
      effect: "cut_in",
      portrait_id: name,
      choreography: "tear_reveal_v1",
      title: lettering[name][0],
      subtitle: lettering[name][1],
    })),
  };
}
