/**
 * The infinite-runner runtime contract: `sideview-runner-runtime-v1`.
 *
 * One strict, hand-written validating parser in the house style: unknown
 * kinds are refused with a re-generate hint, shapes are checked field by
 * field against what `prepared_runner.py` publishes, and the parsed document
 * is deep-frozen. The runtime plays a track from this document alone.
 */

import type { PreparedLayerPresentation } from "@/lib/manifest/prepared-manifest";

export const RUNNER_RUNTIME_KIND = "sideview-runner-runtime-v1";
export const RUNNER_RUNTIME_SCHEMA_VERSION = 1;

export const RUNNER_REFUSAL =
  "unsupported sideview-runner manifest; regenerate this track with a current stage-gen " +
  "(stage-gen generate --genre runner)";

// Producer bounds mirrored from the authored track contract, so a document a
// current producer could not have written is refused rather than played.
const MIN_SEGMENT_ROWS = 6;
const MAX_SEGMENT_ROWS = 32;
const MIN_SEGMENT_COLUMNS = 8;
const MAX_SEGMENT_COLUMNS = 64;

export type RunnerMotionState = "run" | "jump" | "death";

/** Every motion the avatar plays, and the mode each one is authored to play in. */
export const RUNNER_MOTION_STATES: readonly RunnerMotionState[] = ["run", "jump", "death"];

export interface RunnerCalibration {
  readonly heightUnits: number;
  readonly heightUnitsSource: string;
  /** Source pixels the artwork spends per player-height unit: the scale datum. */
  readonly sourcePxPerUnit: number;
  readonly measuredSha256: string;
  readonly subjectExtentPx: number;
  readonly downscaleRatio: number | null;
  readonly extentAxis: "height" | "width";
}

export interface RunnerMotion {
  readonly state: RunnerMotionState;
  readonly playbackMode: "loop" | "once";
  readonly canonicalFrameIndices: readonly number[];
  readonly framesPerSecond: number;
  readonly anchor: "bottom" | "top";
  readonly atlas: string;
  readonly columns: number;
  readonly rebaseMultiplier: number;
}

export interface RunnerAvatar {
  readonly avatarId: string;
  readonly displayName: string;
  readonly concept: string;
  readonly calibration: RunnerCalibration;
  readonly motions: readonly RunnerMotion[];
}

export interface RunnerCatalogEntry {
  readonly id: string;
  readonly displayName: string;
  readonly image: string;
  readonly calibration: RunnerCalibration;
}

export interface RunnerLayer {
  readonly layerId: string;
  readonly plane: "background" | "foreground";
  readonly order: number;
  readonly parallax: number;
  readonly alphaMode: "opaque" | "transparent";
  readonly verticalAnchor: "canvas_cover" | "screen_top" | "screen_bottom" | "walk_surface";
  readonly verticalOffset: number | null;
  readonly image: string;
  readonly width: number;
  readonly height: number;
  readonly presentation: PreparedLayerPresentation;
}

export interface RunnerHazardPlacement {
  readonly propId: string;
  readonly column: number;
}

export interface RunnerPickupPlacement {
  readonly itemId: string;
  readonly column: number;
  readonly row: number;
}

export interface RunnerChunk {
  readonly segmentId: string;
  readonly difficulty: number;
  /** Row 0 is the top; a column is supported when its bottom row is "1". */
  readonly occupancy: readonly string[];
  readonly hazards: readonly RunnerHazardPlacement[];
  readonly pickups: readonly RunnerPickupPlacement[];
}

export interface RunnerSegments {
  readonly rows: number;
  /** Top row index of the seam-column ground stack: the shared walk datum. */
  readonly walkSurfaceRow: number;
  readonly chunks: readonly RunnerChunk[];
}

export interface RunnerSoundtrackTrack {
  readonly trackId: string;
  readonly audio: string;
}

export interface RunnerSoundtrack {
  readonly selection: "shuffle";
  readonly tracks: readonly RunnerSoundtrackTrack[];
}

export interface RunnerRuntimeManifest {
  readonly gameId: string;
  readonly displayName: string;
  readonly trackId: string;
  readonly trackDisplayName: string;
  readonly packageSha256: string;
  readonly presentation: {
    readonly viewProfile: "side_view_2d";
    readonly gameplaySpace: "side_plane";
    readonly contactShadows: {
      readonly enabled: boolean;
      readonly opacity: number;
      readonly softnessScreenPixels: number;
    };
  };
  readonly camera: { readonly mode: "auto_run_x_v1" };
  readonly scale: { readonly playerHeightTiles: number; readonly tilePx: number };
  readonly gameplay: {
    readonly speedProfile: "steady_runner_v1";
    readonly jumpProfile: "single_arc_v1";
    readonly collisionPolicy: "end_run_v1";
    readonly rampProfile: "gentle_ramp_v1";
    readonly maxClearGapColumns: number;
    readonly maxRiseTiles: number;
  };
  readonly ground: {
    readonly atlas: string;
    readonly mode: "terrain-atlas-3x3-minimal-v1";
    readonly verticalFit: "floor_to_screen_bottom";
  };
  readonly layers: readonly RunnerLayer[];
  readonly segments: RunnerSegments;
  readonly avatar: RunnerAvatar;
  readonly props: readonly RunnerCatalogEntry[];
  readonly items: readonly RunnerCatalogEntry[];
  readonly soundtrack: RunnerSoundtrack | null;
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function finite(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}

function positive(value: unknown, label: string): number {
  const parsed = finite(value, label);
  if (parsed <= 0) throw new Error(`${label} must be positive`);
  return parsed;
}

function unit(value: unknown, label: string): number {
  const parsed = finite(value, label);
  if (parsed < 0 || parsed > 1) throw new Error(`${label} must be a number in [0, 1]`);
  return parsed;
}

function nonNegative(value: unknown, label: string): number {
  const parsed = finite(value, label);
  if (parsed < 0) throw new Error(`${label} must not be negative`);
  return parsed;
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new Error(`${label} must be an integer`);
  }
  return value;
}

function boundedInteger(value: unknown, label: string, min: number, max: number): number {
  const parsed = integer(value, label);
  if (parsed < min || parsed > max) {
    throw new Error(`${label} must be an integer from ${min} through ${max}`);
  }
  return parsed;
}

function sha256(value: unknown, label: string): string {
  const parsed = text(value, label);
  if (!/^[0-9a-f]{64}$/.test(parsed)) {
    throw new Error(`${label} must be 64 lowercase hex characters`);
  }
  return parsed;
}

function literal<T extends string>(value: unknown, label: string, allowed: readonly T[]): T {
  if (!(allowed as readonly unknown[]).includes(value)) {
    throw new Error(`${label} must be ${allowed.map((entry) => `"${entry}"`).join(" or ")}`);
  }
  return value as T;
}

function uniqueIds(values: readonly string[], label: string): void {
  if (new Set(values).size !== values.length) {
    throw new Error(`${label} must be unique`);
  }
}

function calibration(value: unknown, label: string): RunnerCalibration {
  const raw = record(value, label);
  const downscale =
    raw.downscale_ratio === undefined || raw.downscale_ratio === null
      ? null
      : positive(raw.downscale_ratio, `${label}.downscale_ratio`);
  const axis =
    raw.extent_axis === undefined
      ? ("height" as const)
      : literal(raw.extent_axis, `${label}.extent_axis`, ["height", "width"]);
  return Object.freeze({
    heightUnits: positive(raw.height_units, `${label}.height_units`),
    heightUnitsSource: text(raw.height_units_source, `${label}.height_units_source`),
    sourcePxPerUnit: positive(raw.source_px_per_unit, `${label}.source_px_per_unit`),
    measuredSha256: sha256(raw.measured_sha256, `${label}.measured_sha256`),
    subjectExtentPx: boundedInteger(
      raw.subject_extent_px,
      `${label}.subject_extent_px`,
      1,
      Number.MAX_SAFE_INTEGER,
    ),
    downscaleRatio: downscale,
    extentAxis: axis,
  });
}

function layerPresentation(value: unknown, label: string): PreparedLayerPresentation {
  const raw = record(value, label);
  const color = text(raw.atmosphere_color, `${label}.atmosphere_color`);
  if (!/^#[0-9a-f]{6}$/.test(color)) {
    throw new Error(`${label}.atmosphere_color must be lowercase #rrggbb`);
  }
  const contrast = finite(raw.contrast, `${label}.contrast`);
  if (contrast < 0.25 || contrast > 2) {
    throw new Error(`${label}.contrast must be within [0.25, 2]`);
  }
  const saturation = finite(raw.saturation, `${label}.saturation`);
  if (saturation < 0 || saturation > 2) {
    throw new Error(`${label}.saturation must be within [0, 2]`);
  }
  const blur = nonNegative(raw.detail_blur_screen_pixels, `${label}.detail_blur_screen_pixels`);
  if (blur > 4) throw new Error(`${label}.detail_blur_screen_pixels must not exceed 4`);
  return Object.freeze({
    contrast,
    saturation,
    atmosphere_color: color,
    atmosphere_strength: unit(raw.atmosphere_strength, `${label}.atmosphere_strength`),
    detail_blur_screen_pixels: blur,
  });
}

function layer(value: unknown, label: string): RunnerLayer {
  const raw = record(value, label);
  const offset =
    raw.vertical_offset === null || raw.vertical_offset === undefined
      ? null
      : finite(raw.vertical_offset, `${label}.vertical_offset`);
  if (offset !== null && (offset < -1 || offset > 1)) {
    throw new Error(`${label}.vertical_offset must be within [-1, 1]`);
  }
  const parallax = nonNegative(raw.parallax, `${label}.parallax`);
  if (parallax > 8) throw new Error(`${label}.parallax must not exceed 8`);
  return Object.freeze({
    layerId: text(raw.layer_id, `${label}.layer_id`),
    plane: literal(raw.plane, `${label}.plane`, ["background", "foreground"]),
    order: boundedInteger(raw.order, `${label}.order`, 0, 7),
    parallax,
    alphaMode: literal(raw.alpha_mode, `${label}.alpha_mode`, ["opaque", "transparent"]),
    verticalAnchor: literal(raw.vertical_anchor, `${label}.vertical_anchor`, [
      "canvas_cover",
      "screen_top",
      "screen_bottom",
      "walk_surface",
    ]),
    verticalOffset: offset,
    image: text(raw.image, `${label}.image`),
    width: boundedInteger(raw.width, `${label}.width`, 1, Number.MAX_SAFE_INTEGER),
    height: boundedInteger(raw.height, `${label}.height`, 1, Number.MAX_SAFE_INTEGER),
    presentation: layerPresentation(raw.presentation, `${label}.presentation`),
  });
}

/**
 * The row a runner stands on in `column`, or null over a pit.
 *
 * Support is bottom-contiguous by contract: a column carries a runner only
 * when its ground stack grows up from the bottom row, and the surface is the
 * top row of that stack. A floating "1" above a gap is scenery, not floor.
 */
export function bottomContiguousSurfaceRow(
  occupancy: readonly string[],
  column: number,
): number | null {
  const rows = occupancy.length;
  if (occupancy[rows - 1]?.[column] !== "1") return null;
  let surface = rows - 1;
  while (surface > 0 && occupancy[surface - 1]?.[column] === "1") surface -= 1;
  return surface;
}

function chunk(
  value: unknown,
  label: string,
  rows: number,
  propIds: ReadonlySet<string>,
  itemIds: ReadonlySet<string>,
): RunnerChunk {
  const raw = record(value, label);
  const occupancy = array(raw.occupancy, `${label}.occupancy`).map((entry, index) =>
    text(entry, `${label}.occupancy[${index}]`),
  );
  if (occupancy.length !== rows) {
    throw new Error(`${label}.occupancy must carry exactly ${rows} rows`);
  }
  const width = occupancy[0].length;
  if (width < MIN_SEGMENT_COLUMNS || width > MAX_SEGMENT_COLUMNS) {
    throw new Error(
      `${label}.occupancy must be ${MIN_SEGMENT_COLUMNS}-${MAX_SEGMENT_COLUMNS} columns wide`,
    );
  }
  for (const [index, row] of occupancy.entries()) {
    if (row.length !== width || /[^01]/.test(row)) {
      throw new Error(`${label}.occupancy[${index}] must be a ${width}-column string of 0 and 1`);
    }
  }
  const hazards = array(raw.hazards, `${label}.hazards`).map((entry, index) => {
    const hazard = record(entry, `${label}.hazards[${index}]`);
    const propId = text(hazard.prop_id, `${label}.hazards[${index}].prop_id`);
    if (!propIds.has(propId)) {
      throw new Error(`${label}.hazards[${index}] names unknown prop ${propId}`);
    }
    const column = boundedInteger(hazard.column, `${label}.hazards[${index}].column`, 0, width - 1);
    if (bottomContiguousSurfaceRow(occupancy, column) === null) {
      throw new Error(`${label}.hazards[${index}] places ${propId} over a pit`);
    }
    return Object.freeze({ propId, column });
  });
  uniqueIds(
    hazards.map((entry) => String(entry.column)),
    `${label} hazard columns`,
  );
  const pickups = array(raw.pickups, `${label}.pickups`).map((entry, index) => {
    const pickup = record(entry, `${label}.pickups[${index}]`);
    const itemId = text(pickup.item_id, `${label}.pickups[${index}].item_id`);
    if (!itemIds.has(itemId)) {
      throw new Error(`${label}.pickups[${index}] names unknown item ${itemId}`);
    }
    const column = boundedInteger(pickup.column, `${label}.pickups[${index}].column`, 0, width - 1);
    const row = boundedInteger(pickup.row, `${label}.pickups[${index}].row`, 0, rows - 1);
    if (occupancy[row][column] !== "0") {
      throw new Error(`${label}.pickups[${index}] places ${itemId} inside solid terrain`);
    }
    return Object.freeze({ itemId, column, row });
  });
  uniqueIds(
    pickups.map((entry) => `${entry.column}:${entry.row}`),
    `${label} pickup cells`,
  );
  return Object.freeze({
    segmentId: text(raw.segment_id, `${label}.segment_id`),
    difficulty: boundedInteger(raw.difficulty, `${label}.difficulty`, 1, 10),
    occupancy: Object.freeze(occupancy),
    hazards: Object.freeze(hazards),
    pickups: Object.freeze(pickups),
  });
}

function catalogEntry(
  value: unknown,
  label: string,
  idField: "prop_id" | "item_id",
): RunnerCatalogEntry {
  const raw = record(value, label);
  return Object.freeze({
    id: text(raw[idField], `${label}.${idField}`),
    displayName: text(raw.display_name, `${label}.display_name`),
    image: text(raw.image, `${label}.image`),
    calibration: calibration(raw.calibration, `${label}.calibration`),
  });
}

function motion(value: unknown, label: string): RunnerMotion {
  const raw = record(value, label);
  const state = literal(raw.state, `${label}.state`, RUNNER_MOTION_STATES);
  // The runner's three states all play a timeline, so frames_per_second is
  // mandatory here even though the wider authored vocabulary lets a held pose
  // omit it.
  const frames = array(raw.canonical_frame_indices, `${label}.canonical_frame_indices`).map(
    (entry, index) =>
      boundedInteger(entry, `${label}.canonical_frame_indices[${index}]`, 0, 63),
  );
  if (frames.length === 0) {
    throw new Error(`${label}.canonical_frame_indices must not be empty`);
  }
  uniqueIds(
    frames.map((entry) => String(entry)),
    `${label}.canonical_frame_indices`,
  );
  const columns = boundedInteger(raw.columns, `${label}.columns`, 1, 64);
  for (const frame of frames) {
    if (frame >= columns) {
      throw new Error(`${label} canonical frame ${frame} is outside its ${columns}-column atlas`);
    }
  }
  const playbackMode = literal(raw.playback_mode, `${label}.playback_mode`, ["loop", "once"]);
  if ((state === "run") !== (playbackMode === "loop")) {
    throw new Error(`${label} state ${state} must play ${state === "run" ? "loop" : "once"}`);
  }
  return Object.freeze({
    state,
    playbackMode,
    canonicalFrameIndices: Object.freeze(frames),
    framesPerSecond: boundedInteger(raw.frames_per_second, `${label}.frames_per_second`, 1, 60),
    anchor: literal(raw.anchor, `${label}.anchor`, ["bottom", "top"]),
    atlas: text(raw.atlas, `${label}.atlas`),
    columns,
    rebaseMultiplier: positive(raw.rebase_multiplier, `${label}.rebase_multiplier`),
  });
}

export function parseRunnerRuntimeManifest(value: unknown): RunnerRuntimeManifest {
  const raw = record(value, "runner manifest");
  if (
    raw.kind !== RUNNER_RUNTIME_KIND ||
    raw.schema_version !== RUNNER_RUNTIME_SCHEMA_VERSION
  ) {
    throw new Error(RUNNER_REFUSAL);
  }

  const rawPresentation = record(raw.presentation, "presentation");
  const rawShadows = record(rawPresentation.contact_shadows, "presentation.contact_shadows");
  if (typeof rawShadows.enabled !== "boolean") {
    throw new Error("presentation.contact_shadows.enabled must be a boolean");
  }
  const shadowSoftness = nonNegative(
    rawShadows.softness_screen_pixels,
    "presentation.contact_shadows.softness_screen_pixels",
  );
  if (shadowSoftness > 32) {
    throw new Error("presentation.contact_shadows.softness_screen_pixels must not exceed 32");
  }

  const rawCamera = record(raw.camera, "camera");
  const rawScale = record(raw.scale, "scale");
  const rawGameplay = record(raw.gameplay, "gameplay");
  const rawGround = record(raw.ground, "ground");

  const props = array(raw.props, "props").map((entry, index) =>
    catalogEntry(entry, `props[${index}]`, "prop_id"),
  );
  const items = array(raw.items, "items").map((entry, index) =>
    catalogEntry(entry, `items[${index}]`, "item_id"),
  );
  uniqueIds(props.map((entry) => entry.id), "prop ids");
  uniqueIds(items.map((entry) => entry.id), "item ids");
  const propIds = new Set(props.map((entry) => entry.id));
  const itemIds = new Set(items.map((entry) => entry.id));

  const rawSegments = record(raw.segments, "segments");
  const rows = boundedInteger(rawSegments.rows, "segments.rows", MIN_SEGMENT_ROWS, MAX_SEGMENT_ROWS);
  const walkSurfaceRow = boundedInteger(
    rawSegments.walk_surface_row,
    "segments.walk_surface_row",
    1,
    rows - 1,
  );
  const chunks = array(rawSegments.chunks, "segments.chunks").map((entry, index) =>
    chunk(entry, `segments.chunks[${index}]`, rows, propIds, itemIds),
  );
  if (chunks.length === 0) throw new Error("segments.chunks must not be empty");
  uniqueIds(chunks.map((entry) => entry.segmentId), "segment ids");

  const rawAvatar = record(raw.avatar, "avatar");
  const motions = array(rawAvatar.motions, "avatar.motions").map((entry, index) =>
    motion(entry, `avatar.motions[${index}]`),
  );
  const motionStates = motions.map((entry) => entry.state);
  uniqueIds(motionStates, "avatar motion states");
  for (const required of RUNNER_MOTION_STATES) {
    if (!motionStates.includes(required)) {
      throw new Error(`avatar.motions is missing the ${required} state`);
    }
  }

  const layers = array(raw.layers, "layers").map((entry, index) =>
    layer(entry, `layers[${index}]`),
  );
  if (layers.length === 0) throw new Error("layers must not be empty");
  uniqueIds(layers.map((entry) => entry.layerId), "layer ids");

  let soundtrack: RunnerSoundtrack | null = null;
  if (raw.soundtrack !== null && raw.soundtrack !== undefined) {
    const rawSoundtrack = record(raw.soundtrack, "soundtrack");
    const tracks = array(rawSoundtrack.tracks, "soundtrack.tracks").map((entry, index) => {
      const track = record(entry, `soundtrack.tracks[${index}]`);
      return Object.freeze({
        trackId: text(track.track_id, `soundtrack.tracks[${index}].track_id`),
        audio: text(track.audio, `soundtrack.tracks[${index}].audio`),
      });
    });
    if (tracks.length === 0) throw new Error("soundtrack.tracks must not be empty");
    uniqueIds(tracks.map((entry) => entry.trackId), "soundtrack track ids");
    soundtrack = Object.freeze({
      selection: literal(rawSoundtrack.selection, "soundtrack.selection", ["shuffle"]),
      tracks: Object.freeze(tracks),
    });
  }

  const manifest: RunnerRuntimeManifest = {
    gameId: text(raw.game_id, "game_id"),
    displayName: text(raw.display_name, "display_name"),
    trackId: text(raw.track_id, "track_id"),
    trackDisplayName: text(raw.track_display_name, "track_display_name"),
    packageSha256: sha256(raw.package_sha256, "package_sha256"),
    presentation: Object.freeze({
      viewProfile: literal(rawPresentation.view_profile, "presentation.view_profile", [
        "side_view_2d",
      ]),
      gameplaySpace: literal(rawPresentation.gameplay_space, "presentation.gameplay_space", [
        "side_plane",
      ]),
      contactShadows: Object.freeze({
        enabled: rawShadows.enabled,
        opacity: unit(rawShadows.opacity, "presentation.contact_shadows.opacity"),
        softnessScreenPixels: shadowSoftness,
      }),
    }),
    camera: Object.freeze({
      mode: literal(rawCamera.mode, "camera.mode", ["auto_run_x_v1"]),
    }),
    scale: Object.freeze({
      playerHeightTiles: positive(rawScale.player_height_tiles, "scale.player_height_tiles"),
      tilePx: boundedInteger(rawScale.tile_px, "scale.tile_px", 1, 512),
    }),
    gameplay: Object.freeze({
      speedProfile: literal(rawGameplay.speed_profile, "gameplay.speed_profile", [
        "steady_runner_v1",
      ]),
      jumpProfile: literal(rawGameplay.jump_profile, "gameplay.jump_profile", ["single_arc_v1"]),
      collisionPolicy: literal(rawGameplay.collision_policy, "gameplay.collision_policy", [
        "end_run_v1",
      ]),
      rampProfile: literal(rawGameplay.ramp_profile, "gameplay.ramp_profile", ["gentle_ramp_v1"]),
      maxClearGapColumns: boundedInteger(
        rawGameplay.max_clear_gap_columns,
        "gameplay.max_clear_gap_columns",
        1,
        MAX_SEGMENT_COLUMNS,
      ),
      maxRiseTiles: boundedInteger(
        rawGameplay.max_rise_tiles,
        "gameplay.max_rise_tiles",
        1,
        MAX_SEGMENT_ROWS,
      ),
    }),
    ground: Object.freeze({
      atlas: text(rawGround.atlas, "ground.atlas"),
      mode: literal(rawGround.mode, "ground.mode", ["terrain-atlas-3x3-minimal-v1"]),
      verticalFit: literal(rawGround.vertical_fit, "ground.vertical_fit", [
        "floor_to_screen_bottom",
      ]),
    }),
    layers: Object.freeze(layers),
    segments: Object.freeze({ rows, walkSurfaceRow, chunks: Object.freeze(chunks) }),
    avatar: Object.freeze({
      avatarId: text(rawAvatar.avatar_id, "avatar.avatar_id"),
      displayName: text(rawAvatar.display_name, "avatar.display_name"),
      concept: text(rawAvatar.concept, "avatar.concept"),
      calibration: calibration(rawAvatar.calibration, "avatar.calibration"),
      motions: Object.freeze(motions),
    }),
    props: Object.freeze(props),
    items: Object.freeze(items),
    soundtrack,
  };
  return Object.freeze(manifest);
}
