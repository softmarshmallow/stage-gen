import { parseScenarioProgram, type ScenarioProgram } from "@/lib/scenario/program";
import type { ScaleVocabulary, SubjectCalibration } from "./asset-unit";
import {
  parseInventoryPanelLayout,
  type InventoryPanelLayout,
} from "./inventory-layout";
import {
  parseUiAtlasRoleLayout,
  type UiAtlasRoleLayout,
  type UiAtlasRoleName,
} from "./ui-atlas-layout";
import { parseUiIconSetLayout, type UiIconSetLayout } from "./ui-icon-layout";

/**
 * What the producer says one published byte set is for.
 *
 * `asset` is media the package publishes as its own content, and every one of them is bound by
 * name somewhere in this manifest. `provenance` is a record or judged plate the run ships so it
 * can be re-derived and audited; its readable values are already inlined here, so no consumer
 * fetches it to present the game.
 *
 * Declared rather than inferred, because nothing observable separates the two: a judged
 * comparison plate is a PNG under `content/` exactly like the artwork it was composed from.
 */
export type RuntimeArtifactRole = "asset" | "provenance";

/** The one prepared-runtime identity this build reads. There is no second one. */
export const PREPARED_RUNTIME_KIND = "prepared-game-runtime-v10";
export const PREPARED_RUNTIME_SCHEMA_VERSION = 10;

export type RuntimeArtifact = Readonly<{
  path: string;
  sha256: string;
  bytes: number;
  media_type: string;
  role: RuntimeArtifactRole;
  width?: number;
  height?: number;
}>;

export type LayerVerticalAnchor =
  | "canvas_cover"
  | "screen_center"
  | "screen_top"
  | "screen_bottom"
  | "walk_surface";

/**
 * Resolved vertical placement for one map layer.
 *
 * Every value here is producer-measured. The runtime applies them and never inspects the raster,
 * so placement stays identical between the local review composite and the browser.
 */
export type PreparedLayerPlacement = Readonly<{
  vertical_anchor: LayerVerticalAnchor;
  /** Fraction of `trimmed_height`, positive pushing the layer down past its anchor datum. */
  vertical_offset: number;
  vertical_offset_source: "measured" | "authored";
  /** Height of the frame the layer was painted in; this stays the scale datum after trimming. */
  source_height: number;
  trimmed_height: number;
  trimmed_top: number;
}>;

export type PreparedLayerPresentation = Readonly<{
  contrast: number;
  saturation: number;
  atmosphere_color: string;
  atmosphere_strength: number;
  detail_blur_screen_pixels: number;
}>;

export type PreparedLayer = Readonly<{
  layer_id: string;
  /** Painter order only. Vertical intent lives in `placement`. */
  plane: "background" | "foreground";
  order: number;
  parallax: number;
  alpha_mode: "opaque" | "transparent";
  placement: PreparedLayerPlacement;
  presentation: PreparedLayerPresentation;
  asset: RuntimeArtifact;
}>;

/** Axes the camera is permitted to follow the player along, in canonical order. */
export type PreparedCameraAxis = "x" | "y";

export type PreparedMapCamera = Readonly<{
  mode: "player_follow";
  follow_axes: readonly PreparedCameraAxis[];
}>;

export type PreparedMap = Readonly<{
  map_id: string;
  revision: number;
  display_name: string;
  role: "safe_village_hub" | "scrolling_hunting_route";
  camera: PreparedMapCamera;
  hostile_population_enabled: boolean;
  track_ids: readonly string[];
  layers: readonly PreparedLayer[];
  ground: Readonly<{
    mode: "terrain-atlas-3x3-minimal-v1";
    /** Top-to-bottom rectangular binary terrain topology. */
    occupancy: readonly string[];
    /** The deepest authored row bottoms out at the viewport edge, so no gap can open below it. */
    vertical_fit: "floor_to_screen_bottom";
    /** Occupancy row whose top edge is the datum for `walk_surface` anchored layers. */
    walk_surface_row: number;
    asset: RuntimeArtifact;
  }>;
  climbable?: Readonly<{
    mode: "climbable-atlas-v1";
    asset: RuntimeArtifact;
    /** Atlas cell index is roster index: ladders left to right, then ropes. */
    index_order: "left_to_right";
    variants: readonly Readonly<{
      variant_id: string;
      role: "ladder" | "rope";
      cell_index: number;
      /** Trimmed rectangle of this variant inside the repacked sheet. */
      cell: Readonly<{ x: number; y: number; width: number; height: number }>;
    }>[];
    placements: readonly Readonly<{
      climbable_id: string;
      variant_id: string;
      normalized_x: number;
      bottom_surface: "terrain";
      rise_tiles: 4;
    }>[];
  }>;
  portal?: Readonly<{
    mode: "portal-pair-1x2-v1";
    asset: RuntimeArtifact;
    endpoints: readonly Readonly<{
      anchor: string;
      normalized_x: number;
      role: "entry" | "exit";
    }>[];
  }>;
}>;

export type MotionBinding = Readonly<{
  source_facing: "right" | "back" | "front";
  runtime_mirror: boolean;
  columns: number;
  rows: 1;
  source_frame_count: number;
  /**
   * Which cell edge this motion's frames register against. Vertical only - horizontal placement is
   * unconditionally centered. Published for provenance and for the anchor work tracked in TODO.md;
   * the sprite origin does not branch on it, because a top-packed strip still puts the tallest
   * pose's feet on the same origin a bottom-packed one does.
   */
  anchor: "bottom" | "top";
  playback: MotionPlayback;
  asset: RuntimeArtifact;
}>;

export type MotionPlayback = Readonly<{
  mode: "hold" | "loop" | "once" | "gameplay_driven";
  canonical_frame_indices: readonly number[];
  frames_per_second?: number;
}>;

export type DialogueBinding = Readonly<{
  columns: number;
  rows: number;
  index_order: "row_major";
  expressions: readonly string[];
  asset: RuntimeArtifact;
}>;

export type PreparedInventoryPanel = InventoryPanelLayout &
  Readonly<{ asset: RuntimeArtifact }>;

/** One nine-slice atlas role: the geometry the producer detected, bound to its sheet. */
export type PreparedUiAtlasRole = UiAtlasRoleLayout & Readonly<{ asset: RuntimeArtifact }>;

/** The preview icon grid: the cells the producer registered glyphs to, bound to its sheet. */
export type PreparedUiIconSet = UiIconSetLayout & Readonly<{ asset: RuntimeArtifact }>;

/**
 * How every one of an actor's states is brought onto its baseline's scale.
 *
 * Separately generated atlases do not share a draw scale, and an alpha box cannot tell a short
 * pose from a small drawing. The producer judges each state against the baseline on one plate
 * and publishes the ratio; the runtime multiplies rather than re-measuring.
 */
export type MotionCalibration = Readonly<{
  baselineState: string;
  stateRebase: Readonly<Record<string, number>>;
  plateSha256: string;
}>;

export type PreparedRuntimeManifest = Readonly<{
  schema_version: 10;
  kind: "prepared-game-runtime-v10";
  game_id: string;
  revision: number;
  display_name: string;
  package_sha256: string;
  presentation: Readonly<{
    view_profile: "side_view_2d";
    gameplay_space: "side_plane";
    contact_shadows: Readonly<{
      enabled: boolean;
      opacity: number;
      softness_screen_pixels: number;
    }>;
  }>;
  entry_map_id: string;
  entry_spawn_id: string;
  scale: ScaleVocabulary;
  maps: readonly PreparedMap[];
  player: Readonly<{
    player_id: string;
    display_name: string;
    concept: RuntimeArtifact;
    states: Readonly<Record<string, MotionBinding>>;
    dialogue: DialogueBinding;
    calibration: MotionCalibration & SubjectCalibration;
  }>;
  mobs: readonly Readonly<{
    mob_id: string;
    display_name: string;
    rank: string;
    /** The archetype the package named, or null when it left that to the rank. */
    aggression: string | null;
    concept: RuntimeArtifact;
    states: Readonly<Record<string, MotionBinding>>;
    calibration: SubjectCalibration;
  }>[];
  npcs: readonly Readonly<{
    npc_id: string;
    display_name: string;
    role: string;
    world: MotionBinding;
    dialogue: DialogueBinding;
    calibration: SubjectCalibration;
  }>[];
  props: readonly Readonly<{
    prop_id: string;
    display_name: string;
    ground_contact_y_normalized: number;
    calibration: SubjectCalibration;
    asset: RuntimeArtifact;
  }>[];
  items: readonly Readonly<{
    item_id: string;
    display_name: string;
    item_kind: string;
    asset: RuntimeArtifact;
    calibration: SubjectCalibration;
  }>[];
  /** Empty for a package whose weapons throw nothing, which is most of them. */
  projectiles: readonly Readonly<{
    projectile_id: string;
    display_name: string;
    silhouette: string;
    flight: string;
    impact: string;
    asset: RuntimeArtifact;
    calibration: SubjectCalibration;
  }>[];
  ui: Readonly<{
    inventory_panel: PreparedInventoryPanel;
    panel_frame: PreparedUiAtlasRole;
    button_rect: PreparedUiAtlasRole;
    preview_icons: PreparedUiIconSet;
  }>;
  soundtrack: Readonly<{
    playback: Readonly<{ selection: "shuffle"; no_immediate_repeat: true }>;
    tracks: readonly Readonly<{
      track_id: string;
      display_name: string;
      asset: RuntimeArtifact;
    }>[];
  }>;
  gameplay: Record<string, unknown>;
  /** The compiled narratives, validated rather than passed through opaque. */
  scenarios: readonly ScenarioProgram[];
  closure: Readonly<{
    artifact_count: number;
    artifacts_sha256: string;
    artifacts: readonly RuntimeArtifact[];
  }>;
}>;

const SAFE_ID = /^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$/;
const SNAKE_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const SHA256 = /^[a-f0-9]{64}$/;
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
const HEX_COLOR = /^#[0-9a-f]{6}$/;

function object(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) {
    throw new Error(`${label} must be a non-empty trimmed string`);
  }
  return value;
}

function id(value: unknown, label: string): string {
  const parsed = text(value, label);
  if (!SAFE_ID.test(parsed)) throw new Error(`${label} is invalid`);
  return parsed;
}

function snakeId(value: unknown, label: string): string {
  const parsed = text(value, label);
  if (!SNAKE_ID.test(parsed) || parsed.length > 96) {
    throw new Error(`${label} is invalid`);
  }
  return parsed;
}

function integer(value: unknown, label: string, minimum = 0): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    throw new Error(`${label} must be a safe integer >= ${minimum}`);
  }
  return value as number;
}

function normalizedX(value: unknown, label: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value <= 0 ||
    value >= 1
  ) {
    throw new Error(`${label} must be a finite number between zero and one`);
  }
  return value;
}

function finiteRange(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(`${label} must be between ${minimum} and ${maximum}`);
  }
  return value;
}

function normalizedGroundContactY(value: unknown, label: string): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    value <= 0 ||
    value > 1
  ) {
    throw new Error(`${label} must be a finite number greater than zero and at most one`);
  }
  return value;
}

function binaryOccupancy(value: unknown, label: string): readonly string[] {
  const rows = array(value, label).map((entry, index) =>
    text(entry, `${label}[${index}]`),
  );
  if (
    rows.length < 2 ||
    rows.length > 64 ||
    rows[0]!.length < 8 ||
    rows[0]!.length > 512 ||
    rows.some((row) => row.length !== rows[0]!.length || /[^01]/.test(row)) ||
    !rows.at(-1)!.includes("1")
  ) {
    throw new Error(
      `${label} must be a 2-64 row, 8-512 column zero-one rectangle supported by its bottom row`,
    );
  }
  return Object.freeze(rows);
}

function artifact(value: unknown, label: string): RuntimeArtifact {
  const record = object(value, label);
  const path = text(record.path, `${label}.path`);
  if (path.split("/").some((part) => !SEGMENT.test(part))) {
    throw new Error(`${label}.path must be portable and run-local`);
  }
  const sha256 = text(record.sha256, `${label}.sha256`);
  if (!SHA256.test(sha256)) throw new Error(`${label}.sha256 is invalid`);
  const role = record.role;
  if (role !== "asset" && role !== "provenance") {
    throw new Error(`${label}.role is invalid`);
  }
  return Object.freeze({
    path,
    sha256,
    bytes: integer(record.bytes, `${label}.bytes`, 1),
    media_type: text(record.media_type, `${label}.media_type`),
    role,
    ...(record.width === undefined
      ? {}
      : { width: integer(record.width, `${label}.width`, 1) }),
    ...(record.height === undefined
      ? {}
      : { height: integer(record.height, `${label}.height`, 1) }),
  });
}

function motion(value: unknown, label: string): MotionBinding {
  const record = object(value, label);
  const sourceFacing = record.source_facing;
  if (
    sourceFacing !== "right" &&
    sourceFacing !== "back" &&
    sourceFacing !== "front"
  ) {
    throw new Error(`${label}.source_facing is invalid`);
  }
  if (typeof record.runtime_mirror !== "boolean") {
    throw new Error(`${label}.runtime_mirror must be boolean`);
  }
  // The cell count is per state rather than fixed: an ordinary state carries four poses, and a
  // climb carries two because its cycle has exactly two. Rows stay at one - every motion strip is
  // a single row, and stacking cells into rows was measured to cost figure size, not buy it.
  const columns = integer(record.columns, `${label}.columns`, 1);
  const sourceFrameCount = integer(
    record.source_frame_count,
    `${label}.source_frame_count`,
    1,
  );
  if (record.rows !== 1 || columns !== sourceFrameCount) {
    throw new Error(`${label} must be one single-row strip of equal cells`);
  }
  const anchor = record.anchor;
  if (anchor !== "bottom" && anchor !== "top") {
    throw new Error(`${label}.anchor is invalid`);
  }
  if (record.runtime_mirror !== (sourceFacing === "right")) {
    throw new Error(`${label} facing and runtime mirroring disagree`);
  }
  const playbackRecord = object(record.playback, `${label}.playback`);
  const mode = playbackRecord.mode;
  if (
    mode !== "hold" &&
    mode !== "loop" &&
    mode !== "once" &&
    mode !== "gameplay_driven"
  ) {
    throw new Error(`${label}.playback.mode is invalid`);
  }
  const canonicalFrameIndices = array(
    playbackRecord.canonical_frame_indices,
    `${label}.playback.canonical_frame_indices`,
  ).map((entry, index) =>
    integer(entry, `${label}.playback.canonical_frame_indices[${index}]`),
  );
  if (
    canonicalFrameIndices.length === 0 ||
    new Set(canonicalFrameIndices).size !== canonicalFrameIndices.length ||
    canonicalFrameIndices.some((index) => index >= sourceFrameCount)
  ) {
    throw new Error(`${label}.playback canonical frame selection is invalid`);
  }
  const framesPerSecond =
    playbackRecord.frames_per_second === undefined
      ? undefined
      : integer(
          playbackRecord.frames_per_second,
          `${label}.playback.frames_per_second`,
          1,
        );
  if (
    (mode === "hold" &&
      (canonicalFrameIndices.length !== 1 || framesPerSecond !== undefined)) ||
    ((mode === "loop" || mode === "once") && framesPerSecond === undefined) ||
    (mode === "gameplay_driven" && framesPerSecond !== undefined)
  ) {
    throw new Error(`${label}.playback shape is invalid for ${mode}`);
  }
  const playback = Object.freeze({
    mode,
    canonical_frame_indices: Object.freeze(canonicalFrameIndices),
    ...(framesPerSecond === undefined
      ? {}
      : { frames_per_second: framesPerSecond }),
  });
  return Object.freeze({
    source_facing: sourceFacing,
    runtime_mirror: record.runtime_mirror,
    columns,
    rows: 1,
    source_frame_count: sourceFrameCount,
    anchor,
    playback,
    asset: artifact(record.asset, `${label}.asset`),
  });
}

function scaleVocabulary(value: unknown, label: string): ScaleVocabulary {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  if (record["unit"] !== "player_height") {
    throw new Error(`${label}.unit must be player_height`);
  }
  const playerHeightTiles = positive(record["player_height_tiles"], `${label}.player_height_tiles`);
  const minimum = positive(record["minimum"], `${label}.minimum`);
  const stepsValue = record["steps"];
  if (!Array.isArray(stepsValue)) {
    throw new Error(`${label}.steps must be an array`);
  }
  const steps = stepsValue.map((step, index) => positive(step, `${label}.steps[${index}]`));
  const ranksValue = record["ranks"];
  if (typeof ranksValue !== "object" || ranksValue === null || Array.isArray(ranksValue)) {
    throw new Error(`${label}.ranks must be an object`);
  }
  const ranks: Record<string, number> = {};
  for (const [rank, units] of Object.entries(ranksValue as Record<string, unknown>)) {
    ranks[rank] = positive(units, `${label}.ranks.${rank}`);
  }
  return Object.freeze({
    unit: "player_height" as const,
    playerHeightTiles,
    minimum,
    steps: Object.freeze(steps),
    ranks: Object.freeze(ranks),
  });
}

function subjectCalibration(value: unknown, label: string): SubjectCalibration {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const measuredSha256 = text(record["measured_sha256"], `${label}.measured_sha256`);
  if (!/^[0-9a-f]{64}$/.test(measuredSha256)) {
    throw new Error(`${label}.measured_sha256 must be a sha256 digest`);
  }
  const subjectExtentPx = positive(record["subject_extent_px"], `${label}.subject_extent_px`);
  if (!Number.isSafeInteger(subjectExtentPx)) {
    throw new Error(`${label}.subject_extent_px must be a whole number of pixels`);
  }
  const rawAxis = record["extent_axis"];
  // Absent means height, which is what every family that stands still declares and what every
  // record published before a projectile needed a second axis carries.
  if (rawAxis !== undefined && rawAxis !== "height" && rawAxis !== "width") {
    throw new Error(`${label}.extent_axis must be height or width`);
  }
  return Object.freeze({
    heightUnits: positive(record["height_units"], `${label}.height_units`),
    heightUnitsSource: text(record["height_units_source"], `${label}.height_units_source`),
    sourcePxPerUnit: positive(record["source_px_per_unit"], `${label}.source_px_per_unit`),
    measuredSha256,
    subjectExtentPx,
    extentAxis: rawAxis === undefined ? ("height" as const) : rawAxis,
  });
}

function positive(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive finite number`);
  }
  return value;
}

function motionCalibration(
  value: unknown,
  label: string,
  states: Readonly<Record<string, MotionBinding>>,
): MotionCalibration {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const baselineState = text(record["baseline_state"], `${label}.baseline_state`);
  const plateSha256 = text(record["plate_sha256"], `${label}.plate_sha256`);
  if (!/^[0-9a-f]{64}$/.test(plateSha256)) {
    throw new Error(`${label}.plate_sha256 must be a sha256 digest`);
  }
  const rebaseValue = record["state_rebase"];
  if (typeof rebaseValue !== "object" || rebaseValue === null || Array.isArray(rebaseValue)) {
    throw new Error(`${label}.state_rebase must be an object`);
  }
  const rebase: Record<string, number> = {};
  for (const [state, multiplier] of Object.entries(rebaseValue as Record<string, unknown>)) {
    if (
      typeof multiplier !== "number" ||
      !Number.isFinite(multiplier) ||
      multiplier < 0.2 ||
      multiplier > 5
    ) {
      throw new Error(`${label}.state_rebase.${state} must be a multiplier within [0.2, 5]`);
    }
    rebase[state] = multiplier;
  }
  // Coverage is checked here rather than trusted, because a state drawn with no multiplier is
  // exactly the defect this contract removes: it would silently inherit the baseline's scale.
  const published = Object.keys(states).sort();
  const covered = Object.keys(rebase).sort();
  if (published.length !== covered.length || published.some((s, i) => s !== covered[i])) {
    throw new Error(
      `${label}.state_rebase must cover exactly the published states ${published.join(", ")}`,
    );
  }
  if (rebase[baselineState] !== 1) {
    throw new Error(`${label}.state_rebase.${baselineState} must be exactly 1 for the baseline`);
  }
  return Object.freeze({
    baselineState,
    stateRebase: Object.freeze(rebase),
    plateSha256,
  });
}

function dialogue(value: unknown, label: string): DialogueBinding {
  const record = object(value, label);
  const expressions = array(record.expressions, `${label}.expressions`).map((entry, index) =>
    id(entry, `${label}.expressions[${index}]`),
  );
  const columns = integer(record.columns, `${label}.columns`, 1);
  const rows = integer(record.rows, `${label}.rows`, 1);
  if (
    record.index_order !== "row_major" ||
    expressions.length === 0 ||
    expressions.length > columns * rows ||
    new Set(expressions).size !== expressions.length
  ) {
    throw new Error(`${label} layout is invalid`);
  }
  return Object.freeze({
    columns,
    rows,
    index_order: "row_major",
    expressions: Object.freeze(expressions),
    asset: artifact(record.asset, `${label}.asset`),
  });
}

function motionStates(value: unknown, label: string): Readonly<Record<string, MotionBinding>> {
  const record = object(value, label);
  const states = Object.fromEntries(
    Object.entries(record).map(([state, binding]) => [id(state, `${label} state`), motion(binding, `${label}.${state}`)]),
  );
  if (Object.keys(states).length === 0) throw new Error(`${label} must not be empty`);
  return Object.freeze(states);
}

export function parsePreparedRuntimeManifest(value: unknown): PreparedRuntimeManifest {
  const root = object(value, "prepared runtime manifest");
  if (
    root.schema_version !== PREPARED_RUNTIME_SCHEMA_VERSION ||
    root.kind !== PREPARED_RUNTIME_KIND
  ) {
    throw new Error("prepared runtime manifest identity is invalid");
  }
  const rawPresentation = object(root.presentation, "presentation");
  if (
    rawPresentation.view_profile !== "side_view_2d" ||
    rawPresentation.gameplay_space !== "side_plane"
  ) {
    throw new Error("prepared runtime presentation space is invalid");
  }
  const rawContactShadows = object(
    rawPresentation.contact_shadows,
    "presentation.contact_shadows",
  );
  if (typeof rawContactShadows.enabled !== "boolean") {
    throw new Error("presentation.contact_shadows.enabled must be boolean");
  }
  const presentation = Object.freeze({
    view_profile: "side_view_2d" as const,
    gameplay_space: "side_plane" as const,
    contact_shadows: Object.freeze({
      enabled: rawContactShadows.enabled,
      opacity: finiteRange(
        rawContactShadows.opacity,
        "presentation.contact_shadows.opacity",
        0,
        1,
      ),
      softness_screen_pixels: finiteRange(
        rawContactShadows.softness_screen_pixels,
        "presentation.contact_shadows.softness_screen_pixels",
        0,
        32,
      ),
    }),
  });
  const gameId = id(root.game_id, "game_id");
  const maps = array(root.maps, "maps").map((rawMap, mapIndex): PreparedMap => {
    const map = object(rawMap, `maps[${mapIndex}]`);
    const layers = array(map.layers, `maps[${mapIndex}].layers`).map((rawLayer, layerIndex) => {
      const layer = object(rawLayer, `maps[${mapIndex}].layers[${layerIndex}]`);
      if (layer.plane !== "background" && layer.plane !== "foreground") {
        throw new Error("map layer plane is invalid");
      }
      if (layer.alpha_mode !== "opaque" && layer.alpha_mode !== "transparent") {
        throw new Error("map layer alpha_mode is invalid");
      }
      if (typeof layer.parallax !== "number" || !Number.isFinite(layer.parallax)) {
        throw new Error("map layer parallax is invalid");
      }
      const placement = object(
        layer.placement,
        `maps[${mapIndex}].layers[${layerIndex}].placement`,
      );
      const anchor = placement.vertical_anchor;
      if (
        anchor !== "canvas_cover" &&
        anchor !== "screen_center" &&
        anchor !== "screen_top" &&
        anchor !== "screen_bottom" &&
        anchor !== "walk_surface"
      ) {
        throw new Error("map layer vertical_anchor is invalid");
      }
      const offsetSource = placement.vertical_offset_source;
      if (offsetSource !== "measured" && offsetSource !== "authored") {
        throw new Error("map layer vertical_offset_source is invalid");
      }
      if (
        typeof placement.vertical_offset !== "number" ||
        !Number.isFinite(placement.vertical_offset)
      ) {
        throw new Error("map layer vertical_offset is invalid");
      }
      const trimmedHeight = integer(placement.trimmed_height, "layer trimmed_height", 1);
      const sourceHeight = integer(placement.source_height, "layer source_height", 1);
      if (trimmedHeight > sourceHeight) {
        throw new Error("map layer trimmed height cannot exceed its painted frame");
      }
      const rawLayerPresentation = object(
        layer.presentation,
        `maps[${mapIndex}].layers[${layerIndex}].presentation`,
      );
      const atmosphereColor = text(
        rawLayerPresentation.atmosphere_color,
        "layer atmosphere_color",
      );
      if (!HEX_COLOR.test(atmosphereColor)) {
        throw new Error("map layer atmosphere_color must be lowercase #rrggbb");
      }
      return Object.freeze({
        layer_id: id(layer.layer_id, "layer_id"),
        plane: layer.plane,
        order: integer(layer.order, "layer order"),
        parallax: layer.parallax,
        alpha_mode: layer.alpha_mode,
        placement: Object.freeze({
          vertical_anchor: anchor,
          vertical_offset: placement.vertical_offset,
          vertical_offset_source: offsetSource,
          source_height: sourceHeight,
          trimmed_height: trimmedHeight,
          trimmed_top: integer(placement.trimmed_top, "layer trimmed_top", 0),
        }),
        presentation: Object.freeze({
          contrast: finiteRange(rawLayerPresentation.contrast, "layer contrast", 0.25, 2),
          saturation: finiteRange(rawLayerPresentation.saturation, "layer saturation", 0, 2),
          atmosphere_color: atmosphereColor,
          atmosphere_strength: finiteRange(
            rawLayerPresentation.atmosphere_strength,
            "layer atmosphere_strength",
            0,
            1,
          ),
          detail_blur_screen_pixels: finiteRange(
            rawLayerPresentation.detail_blur_screen_pixels,
            "layer detail_blur_screen_pixels",
            0,
            4,
          ),
        }),
        asset: artifact(layer.asset, "layer asset"),
      });
    });
    const ground = object(map.ground, `maps[${mapIndex}].ground`);
    if (ground.mode !== "terrain-atlas-3x3-minimal-v1") {
      throw new Error("ground mode is invalid");
    }
    const occupancy = binaryOccupancy(
      ground.occupancy,
      `maps[${mapIndex}].ground.occupancy`,
    );
    if (ground.vertical_fit !== "floor_to_screen_bottom") {
      throw new Error("ground vertical_fit is invalid");
    }
    const verticalFit = ground.vertical_fit;
    const walkSurfaceRow = integer(
      ground.walk_surface_row,
      "ground walk_surface_row",
      0,
    );
    if (walkSurfaceRow >= occupancy.length) {
      throw new Error("ground walk_surface_row must index an authored occupancy row");
    }
    const climbable =
      map.climbable === undefined
        ? undefined
        : (() => {
            const raw = object(map.climbable, `maps[${mapIndex}].climbable`);
            if (raw.mode !== "climbable-atlas-v1") {
              throw new Error("climbable mode is invalid");
            }
            if (raw.index_order !== "left_to_right") {
              throw new Error("climbable index_order is invalid");
            }
            const variants = array(
              raw.variants,
              `maps[${mapIndex}].climbable.variants`,
            ).map((rawVariant, variantIndex) => {
              const variant = object(
                rawVariant,
                `maps[${mapIndex}].climbable.variants[${variantIndex}]`,
              );
              if (variant.role !== "ladder" && variant.role !== "rope") {
                throw new Error("climbable variant role is invalid");
              }
              // Cell index is roster index. Reject any manifest that disagrees rather than
              // trusting an index the producer and the sheet may not share.
              if (variant.cell_index !== variantIndex) {
                throw new Error("climbable variant cell_index must equal its roster index");
              }
              const cell = object(
                variant.cell,
                `maps[${mapIndex}].climbable.variants[${variantIndex}].cell`,
              );
              const box = Object.freeze({
                x: integer(cell.x, "climbable cell x", 0),
                y: integer(cell.y, "climbable cell y", 0),
                width: integer(cell.width, "climbable cell width", 1),
                height: integer(cell.height, "climbable cell height", 1),
              });
              return Object.freeze({
                variant_id: snakeId(variant.variant_id, "variant_id"),
                role: variant.role,
                cell_index: variantIndex,
                cell: box,
              });
            });
            if (
              variants.length === 0 ||
              variants.length > 6 ||
              new Set(variants.map((entry) => entry.variant_id)).size !== variants.length
            ) {
              throw new Error("climbable variants must be a bounded unique roster");
            }
            const declared = new Set(variants.map((entry) => entry.variant_id));
            const placements = array(
              raw.placements,
              `maps[${mapIndex}].climbable.placements`,
            ).map((rawPlacement, placementIndex) => {
              const placement = object(
                rawPlacement,
                `maps[${mapIndex}].climbable.placements[${placementIndex}]`,
              );
              if (
                placement.bottom_surface !== "terrain" ||
                placement.rise_tiles !== 4
              ) {
                throw new Error("climbable placement geometry is invalid");
              }
              const variantId = snakeId(placement.variant_id, "variant_id");
              if (!declared.has(variantId)) {
                throw new Error("climbable placement names an undeclared variant");
              }
              return Object.freeze({
                climbable_id: snakeId(placement.climbable_id, "climbable_id"),
                variant_id: variantId,
                normalized_x: normalizedX(
                  placement.normalized_x,
                  "climbable normalized_x",
                ),
                bottom_surface: "terrain" as const,
                rise_tiles: 4 as const,
              });
            });
            if (
              placements.length === 0 ||
              placements.length > 8 ||
              new Set(placements.map((entry) => entry.climbable_id)).size !==
                placements.length ||
              new Set(placements.map((entry) => entry.normalized_x)).size !==
                placements.length
            ) {
              throw new Error("climbable placements must have unique identities and positions");
            }
            return Object.freeze({
              mode: "climbable-atlas-v1" as const,
              asset: artifact(raw.asset, "climbable asset"),
              index_order: "left_to_right" as const,
              variants: Object.freeze(variants),
              placements: Object.freeze(placements),
            });
          })();
    const portal =
      map.portal === undefined
        ? undefined
        : (() => {
            const rawPortal = object(map.portal, `maps[${mapIndex}].portal`);
            if (rawPortal.mode !== "portal-pair-1x2-v1") {
              throw new Error("portal mode is invalid");
            }
            const endpoints = array(
              rawPortal.endpoints,
              `maps[${mapIndex}].portal.endpoints`,
            ).map((rawEndpoint, endpointIndex) => {
              const endpoint = object(
                rawEndpoint,
                `maps[${mapIndex}].portal.endpoints[${endpointIndex}]`,
              );
              if (endpoint.role !== "entry" && endpoint.role !== "exit") {
                throw new Error("portal endpoint role is invalid");
              }
              return Object.freeze({
                anchor: snakeId(endpoint.anchor, "portal anchor"),
                normalized_x: normalizedX(
                  endpoint.normalized_x,
                  "portal normalized_x",
                ),
                role: endpoint.role,
              });
            });
            if (
              endpoints.length === 0 ||
              endpoints.length > 2 ||
              new Set(endpoints.map((entry) => entry.anchor)).size !==
                endpoints.length ||
              new Set(endpoints.map((entry) => entry.normalized_x)).size !==
                endpoints.length ||
              new Set(endpoints.map((entry) => entry.role)).size !==
                endpoints.length
            ) {
              throw new Error("portal endpoints must have unique anchors, positions, and roles");
            }
            return Object.freeze({
              mode: "portal-pair-1x2-v1" as const,
              asset: artifact(rawPortal.asset, "portal asset"),
              endpoints: Object.freeze(endpoints),
            });
          })();
    const role = map.role;
    if (role !== "safe_village_hub" && role !== "scrolling_hunting_route") {
      throw new Error("map role is invalid");
    }
    // Rejected rather than defaulted. A camera this scene cannot drive is a map it cannot play
    // correctly, and silently ignoring a declared axis would strand the player above the frame.
    const rawCamera = object(map.camera, "map camera");
    if (rawCamera.mode !== "player_follow") throw new Error("map camera mode is unsupported");
    const followAxes = array(rawCamera.follow_axes, "map camera follow_axes").map((axis) => {
      if (axis !== "x" && axis !== "y") throw new Error("map camera follow axis is invalid");
      return axis;
    });
    if (new Set(followAxes).size !== followAxes.length) {
      throw new Error("map camera follow_axes must be unique");
    }
    if (followAxes.join(",") !== (["x", "y"] as const).filter((a) => followAxes.includes(a)).join(",")) {
      throw new Error("map camera follow_axes must use canonical x, y order");
    }
    return Object.freeze({
      map_id: id(map.map_id, "map_id"),
      revision: integer(map.revision, "map revision", 1),
      display_name: text(map.display_name, "map display_name"),
      role,
      camera: Object.freeze({
        mode: "player_follow" as const,
        follow_axes: Object.freeze(followAxes),
      }),
      hostile_population_enabled: map.hostile_population_enabled === true,
      track_ids: Object.freeze(array(map.track_ids, "map track_ids").map((track) => id(track, "track_id"))),
      layers: Object.freeze(layers),
      ground: Object.freeze({
        mode: "terrain-atlas-3x3-minimal-v1",
        occupancy,
        vertical_fit: verticalFit,
        walk_surface_row: walkSurfaceRow,
        asset: artifact(ground.asset, "ground asset"),
      }),
      ...(climbable === undefined ? {} : { climbable }),
      ...(portal === undefined ? {} : { portal }),
    });
  });
  const player = object(root.player, "player");
  const mobs = array(root.mobs, "mobs").map((rawMob, index) => {
    const mob = object(rawMob, `mobs[${index}]`);
    return Object.freeze({
      mob_id: id(mob.mob_id, "mob_id"),
      display_name: text(mob.display_name, "mob display_name"),
      rank: text(mob.rank, "mob rank"),
      // Absent and null read the same: every run published before the field left it to the
      // rank, and a package that names nothing means exactly that.
      aggression:
        mob.aggression === undefined || mob.aggression === null
          ? null
          : text(mob.aggression, "mob aggression"),
      concept: artifact(mob.concept, `mobs[${index}].concept`),
      states: motionStates(mob.states, `mobs[${index}].states`),
      calibration: subjectCalibration(mob.calibration, `mobs[${index}].calibration`),
    });
  });
  const npcs = array(root.npcs, "npcs").map((rawNpc, index) => {
    const npc = object(rawNpc, `npcs[${index}]`);
    return Object.freeze({
      npc_id: id(npc.npc_id, "npc_id"),
      display_name: text(npc.display_name, "npc display_name"),
      role: text(npc.role, "npc role"),
      world: motion(npc.world, `npcs[${index}].world`),
      dialogue: dialogue(npc.dialogue, `npcs[${index}].dialogue`),
      calibration: subjectCalibration(npc.calibration, `npcs[${index}].calibration`),
    });
  });
  const props = array(root.props, "props").map((rawProp, index) => {
    const prop = object(rawProp, `props[${index}]`);
    return Object.freeze({
      prop_id: id(prop.prop_id, "prop_id"),
      display_name: text(prop.display_name, "prop display_name"),
      ground_contact_y_normalized: normalizedGroundContactY(
        prop.ground_contact_y_normalized,
        `props[${index}].ground_contact_y_normalized`,
      ),
      calibration: subjectCalibration(prop.calibration, `props[${index}].calibration`),
      asset: artifact(prop.asset, "prop asset"),
    });
  });
  const items = array(root.items, "items").map((rawItem, index) => {
    const item = object(rawItem, `items[${index}]`);
    return Object.freeze({ item_id: id(item.item_id, "item_id"), display_name: text(item.display_name, "item display_name"), item_kind: text(item.item_kind, "item kind"), calibration: subjectCalibration(item.calibration, `items[${index}].calibration`), asset: artifact(item.asset, "item asset") });
  });
  // Absent for every package published before the family existed, and for every game whose
  // weapons throw nothing. Both mean the same thing: nothing to put in the air.
  const projectiles = (root.projectiles === undefined
    ? []
    : array(root.projectiles, "projectiles")
  ).map((rawProjectile, index) => {
    const entry = object(rawProjectile, `projectiles[${index}]`);
    return Object.freeze({
      projectile_id: id(entry.projectile_id, "projectile_id"),
      display_name: text(entry.display_name, "projectile display_name"),
      silhouette: text(entry.silhouette, "projectile silhouette"),
      flight: text(entry.flight, "projectile flight"),
      impact: text(entry.impact, "projectile impact"),
      calibration: subjectCalibration(
        entry.calibration,
        `projectiles[${index}].calibration`,
      ),
      asset: artifact(entry.asset, "projectile asset"),
    });
  });
  const ui = object(root.ui, "ui");
  const rawInventoryPanel = object(ui.inventory_panel, "ui.inventory_panel");
  const inventoryPanelLayout = parseInventoryPanelLayout(rawInventoryPanel);
  const inventoryPanel = Object.freeze({
    ...inventoryPanelLayout,
    asset: artifact(rawInventoryPanel.asset, "ui.inventory_panel.asset"),
  });
  const uiAtlasRole = (role: UiAtlasRoleName): PreparedUiAtlasRole => {
    const raw = object(ui[role], `ui.${role}`);
    return Object.freeze({
      ...parseUiAtlasRoleLayout(raw, role),
      asset: artifact(raw.asset, `ui.${role}.asset`),
    });
  };
  const panelFrame = uiAtlasRole("panel_frame");
  const buttonRect = uiAtlasRole("button_rect");
  const rawIcons = object(ui.preview_icons, "ui.preview_icons");
  const previewIcons: PreparedUiIconSet = Object.freeze({
    ...parseUiIconSetLayout(rawIcons),
    asset: artifact(rawIcons.asset, "ui.preview_icons.asset"),
  });
  const soundtrack = object(root.soundtrack, "soundtrack");
  const playback = object(soundtrack.playback, "soundtrack.playback");
  if (playback.selection !== "shuffle" || playback.no_immediate_repeat !== true) {
    throw new Error("soundtrack playback policy is invalid");
  }
  const tracks = array(soundtrack.tracks, "soundtrack.tracks").map((rawTrack, index) => {
    const track = object(rawTrack, `soundtrack.tracks[${index}]`);
    return Object.freeze({ track_id: id(track.track_id, "track_id"), display_name: text(track.display_name, "track display_name"), asset: artifact(track.asset, "track asset") });
  });
  const closure = object(root.closure, "closure");
  const closureArtifacts = array(closure.artifacts, "closure.artifacts").map((entry, index) => artifact(entry, `closure.artifacts[${index}]`));
  if (integer(closure.artifact_count, "closure.artifact_count") !== closureArtifacts.length) {
    throw new Error("closure artifact_count disagrees with artifacts");
  }
  const packageSha256 = text(root.package_sha256, "package_sha256");
  const artifactsSha256 = text(closure.artifacts_sha256, "closure.artifacts_sha256");
  if (!SHA256.test(packageSha256) || !SHA256.test(artifactsSha256)) throw new Error("manifest digest is invalid");
  const entryMapId = id(root.entry_map_id, "entry_map_id");
  if (!maps.some((map) => map.map_id === entryMapId)) throw new Error("entry_map_id does not resolve");
  return Object.freeze({
    schema_version: 10,
    kind: "prepared-game-runtime-v10",
    game_id: gameId,
    revision: integer(root.revision, "revision", 1),
    display_name: text(root.display_name, "display_name"),
    package_sha256: packageSha256,
    presentation,
    entry_map_id: entryMapId,
    entry_spawn_id: id(root.entry_spawn_id, "entry_spawn_id"),
    scale: scaleVocabulary(root.scale, "scale"),
    maps: Object.freeze(maps),
    player: Object.freeze({ player_id: id(player.player_id, "player_id"), display_name: text(player.display_name, "player display_name"), concept: artifact(player.concept, "player.concept"), states: motionStates(player.states, "player.states"), dialogue: dialogue(player.dialogue, "player.dialogue"), calibration: Object.freeze({ ...subjectCalibration(player.calibration, "player.calibration"), ...motionCalibration(player.calibration, "player.calibration", motionStates(player.states, "player.states")) }) }),
    mobs: Object.freeze(mobs),
    npcs: Object.freeze(npcs),
    props: Object.freeze(props),
    items: Object.freeze(items),
    projectiles: Object.freeze(projectiles),
    ui: Object.freeze({ inventory_panel: inventoryPanel, panel_frame: panelFrame, button_rect: buttonRect, preview_icons: previewIcons }),
    soundtrack: Object.freeze({ playback: Object.freeze({ selection: "shuffle", no_immediate_repeat: true }), tracks: Object.freeze(tracks) }),
    gameplay: object(root.gameplay, "gameplay"),
    scenarios: Object.freeze(array(root.scenarios, "scenarios").map(parseScenarioProgram)),
    closure: Object.freeze({ artifact_count: closureArtifacts.length, artifacts_sha256: artifactsSha256, artifacts: Object.freeze(closureArtifacts) }),
  });
}
