import {
  parseInventoryPanelLayout,
  type InventoryPanelLayout,
} from "./inventory-layout";

export type RuntimeArtifact = Readonly<{
  path: string;
  sha256: string;
  bytes: number;
  media_type: string;
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

export type PreparedMap = Readonly<{
  map_id: string;
  revision: number;
  display_name: string;
  role: "safe_village_hub" | "scrolling_hunting_route";
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

export type PreparedRuntimeManifest = Readonly<{
  schema_version: 9;
  kind: "prepared-game-runtime-v9";
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
  maps: readonly PreparedMap[];
  player: Readonly<{
    player_id: string;
    display_name: string;
    concept: RuntimeArtifact;
    states: Readonly<Record<string, MotionBinding>>;
    dialogue: DialogueBinding;
  }>;
  mobs: readonly Readonly<{
    mob_id: string;
    display_name: string;
    rank: string;
    concept: RuntimeArtifact;
    states: Readonly<Record<string, MotionBinding>>;
  }>[];
  npcs: readonly Readonly<{
    npc_id: string;
    display_name: string;
    role: string;
    world: MotionBinding;
    dialogue: DialogueBinding;
  }>[];
  props: readonly Readonly<{
    prop_id: string;
    display_name: string;
    ground_contact_y_normalized: number;
    asset: RuntimeArtifact;
  }>[];
  items: readonly Readonly<{
    item_id: string;
    display_name: string;
    item_kind: string;
    asset: RuntimeArtifact;
  }>[];
  ui: Readonly<{ inventory_panel: PreparedInventoryPanel }>;
  soundtrack: Readonly<{
    playback: Readonly<{ selection: "shuffle"; no_immediate_repeat: true }>;
    tracks: readonly Readonly<{
      track_id: string;
      display_name: string;
      asset: RuntimeArtifact;
    }>[];
  }>;
  gameplay: Record<string, unknown>;
  sequences: readonly Record<string, unknown>[];
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
  return Object.freeze({
    path,
    sha256,
    bytes: integer(record.bytes, `${label}.bytes`, 1),
    media_type: text(record.media_type, `${label}.media_type`),
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
  if (root.schema_version !== 9 || root.kind !== "prepared-game-runtime-v9") {
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
    return Object.freeze({
      map_id: id(map.map_id, "map_id"),
      revision: integer(map.revision, "map revision", 1),
      display_name: text(map.display_name, "map display_name"),
      role,
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
      concept: artifact(mob.concept, `mobs[${index}].concept`),
      states: motionStates(mob.states, `mobs[${index}].states`),
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
      asset: artifact(prop.asset, "prop asset"),
    });
  });
  const items = array(root.items, "items").map((rawItem, index) => {
    const item = object(rawItem, `items[${index}]`);
    return Object.freeze({ item_id: id(item.item_id, "item_id"), display_name: text(item.display_name, "item display_name"), item_kind: text(item.item_kind, "item kind"), asset: artifact(item.asset, "item asset") });
  });
  const ui = object(root.ui, "ui");
  const rawInventoryPanel = object(ui.inventory_panel, "ui.inventory_panel");
  const inventoryPanelLayout = parseInventoryPanelLayout(rawInventoryPanel);
  const inventoryPanel = Object.freeze({
    ...inventoryPanelLayout,
    asset: artifact(rawInventoryPanel.asset, "ui.inventory_panel.asset"),
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
    schema_version: 9,
    kind: "prepared-game-runtime-v9",
    game_id: gameId,
    revision: integer(root.revision, "revision", 1),
    display_name: text(root.display_name, "display_name"),
    package_sha256: packageSha256,
    presentation,
    entry_map_id: entryMapId,
    entry_spawn_id: id(root.entry_spawn_id, "entry_spawn_id"),
    maps: Object.freeze(maps),
    player: Object.freeze({ player_id: id(player.player_id, "player_id"), display_name: text(player.display_name, "player display_name"), concept: artifact(player.concept, "player.concept"), states: motionStates(player.states, "player.states"), dialogue: dialogue(player.dialogue, "player.dialogue") }),
    mobs: Object.freeze(mobs),
    npcs: Object.freeze(npcs),
    props: Object.freeze(props),
    items: Object.freeze(items),
    ui: Object.freeze({ inventory_panel: inventoryPanel }),
    soundtrack: Object.freeze({ playback: Object.freeze({ selection: "shuffle", no_immediate_repeat: true }), tracks: Object.freeze(tracks) }),
    gameplay: object(root.gameplay, "gameplay"),
    sequences: Object.freeze(array(root.sequences, "sequences").map((entry, index) => object(entry, `sequences[${index}]`))),
    closure: Object.freeze({ artifact_count: closureArtifacts.length, artifacts_sha256: artifactsSha256, artifacts: Object.freeze(closureArtifacts) }),
  });
}

export function preparedAssetUrl(tag: string, path: string): string {
  return `/api/assets/${encodeURIComponent(tag)}/${path.split("/").map(encodeURIComponent).join("/")}`;
}
