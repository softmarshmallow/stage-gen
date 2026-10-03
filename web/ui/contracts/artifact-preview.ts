// Application preview adapters. The engine transports JSON and does not own sprite
// geometry or the list of renderer capabilities.

export interface LegacyMotionPreview {
  readonly frameCount: number;
  readonly mode: "hold" | "loop" | "once" | "gameplay_driven" | null;
  readonly framesPerSecond: number | null;
  readonly canonicalFrameIndices: readonly number[];
}

/**
 * A renderer hint an artifact carries. The engine passes it through as opaque JSON; a
 * consumer that knows its kind may draw it, and every other kind uses the ordinary
 * artifact display. A step's own picture of its work is its view (`view-context.ts`).
 */
export interface ArtifactPreview {
  readonly kind: string;
}

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

/** Any preview kind passes through; none is drawn by this build. */
export function parseArtifactPreview(value: unknown, label: string): ArtifactPreview | null {
  if (value === null || value === undefined) return null;
  const record = object(value, label);
  return Object.freeze({ kind: text(record.kind, `${label}.kind`) });
}
