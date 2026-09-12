// Application preview adapters. The engine transports JSON and does not own
// sprite geometry, parallax composition, or the list of renderer capabilities.

export interface LegacyMotionPreview {
  readonly frameCount: number;
  readonly mode: "hold" | "loop" | "once" | "gameplay_driven" | null;
  readonly framesPerSecond: number | null;
  readonly canonicalFrameIndices: readonly number[];
}

export interface ParallaxLayer {
  readonly layerId: string;
  readonly assetRef: string;
  readonly order: number;
  readonly parallax: number;
  readonly offsetX: number;
  readonly offsetY: number;
  readonly repeatX: boolean;
  readonly repeatY: boolean;
  readonly width: number;
  readonly height: number;
}

export interface ParallaxPreview {
  readonly kind: "parallax-background-v1";
  readonly width: number;
  readonly height: number;
  readonly layers: readonly ParallaxLayer[];
}

export type ArtifactPreview =
  | { readonly supported: true; readonly content: ParallaxPreview }
  | { readonly supported: false; readonly kind: string };

function object(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} must be an object`);
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim())
    throw new Error(`${label} must be a non-empty string`);
  return value;
}

function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value))
    throw new Error(`${label} must be a finite number`);
  return value;
}

function integer(value: unknown, label: string, min: number, max: number): number {
  const result = number(value, label);
  if (!Number.isInteger(result) || result < min || result > max)
    throw new Error(`${label} must be an integer between ${min} and ${max}`);
  return result;
}

function bool(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
  return value;
}

/** Same portable, already-decoded path vocabulary as the confined asset API. */
export function artifactReference(value: unknown, label: string): string {
  const ref = text(value, label);
  if (!ref.split("/").every((segment) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/.test(segment)))
    throw new Error(`${label} must be a portable run-local artifact path`);
  return ref;
}

export function parseLegacyMotion(value: unknown, label: string): LegacyMotionPreview | null {
  if (value === null || value === undefined) return null;
  const record = object(value, label);
  const mode = record.mode ?? null;
  if (mode !== null && mode !== "hold" && mode !== "loop" && mode !== "once" && mode !== "gameplay_driven")
    throw new Error(`${label}.mode is invalid`);
  const frameCount = integer(record.frame_count, `${label}.frame_count`, 1, 16);
  const fps = record.frames_per_second == null ? null : number(record.frames_per_second, `${label}.frames_per_second`);
  if (fps !== null && fps <= 0) throw new Error(`${label}.frames_per_second must be positive`);
  const indices = record.canonical_frame_indices ?? [];
  if (!Array.isArray(indices)) throw new Error(`${label}.canonical_frame_indices must be an array`);
  return Object.freeze({
    frameCount,
    mode,
    framesPerSecond: fps,
    canonicalFrameIndices: Object.freeze(indices.map((entry, index) =>
      integer(entry, `${label}.canonical_frame_indices[${index}]`, 0, Number.MAX_SAFE_INTEGER))),
  });
}

/** Unknown valid preview kinds use the ordinary artifact fallback. */
export function parseArtifactPreview(value: unknown, label: string): ArtifactPreview | null {
  if (value === null || value === undefined) return null;
  const record = object(value, label);
  const kind = text(record.kind, `${label}.kind`);
  if (kind !== "parallax-background-v1") return Object.freeze({ supported: false, kind });
  const canvas = object(record.canvas, `${label}.canvas`);
  const width = integer(canvas.width, `${label}.canvas.width`, 1, 16384);
  const height = integer(canvas.height, `${label}.canvas.height`, 1, 16384);
  if (!Array.isArray(record.layers) || record.layers.length < 1 || record.layers.length > 32)
    throw new Error(`${label}.layers must contain between 1 and 32 layers`);
  const layers = record.layers.map((value, index): ParallaxLayer => {
    const prefix = `${label}.layers[${index}]`;
    const layer = object(value, prefix);
    return Object.freeze({
      layerId: text(layer.layer_id, `${prefix}.layer_id`),
      assetRef: artifactReference(layer.asset_ref, `${prefix}.asset_ref`),
      order: number(layer.order, `${prefix}.order`),
      parallax: number(layer.parallax, `${prefix}.parallax`),
      offsetX: number(layer.offset_x, `${prefix}.offset_x`),
      offsetY: number(layer.offset_y, `${prefix}.offset_y`),
      repeatX: bool(layer.repeat_x, `${prefix}.repeat_x`),
      repeatY: bool(layer.repeat_y, `${prefix}.repeat_y`),
      width: integer(layer.width, `${prefix}.width`, 1, 16384),
      height: integer(layer.height, `${prefix}.height`, 1, 16384),
    });
  });
  if (new Set(layers.map((layer) => layer.layerId)).size !== layers.length)
    throw new Error(`${label}.layers must declare unique layer ids`);
  return Object.freeze({
    supported: true,
    content: Object.freeze({ kind, width, height, layers: Object.freeze(layers.sort((a, b) => a.order - b.order)) }),
  });
}

/** Offsets in source canvas pixels, converted by the renderer to viewport size. */
export function parallaxOffset(layer: ParallaxLayer, scrollX: number, scrollY: number): readonly [number, number] {
  return [layer.offsetX - scrollX * layer.parallax, layer.offsetY - scrollY * layer.parallax];
}
