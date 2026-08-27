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

export type PreparedLayer = Readonly<{
  layer_id: string;
  plane: "background" | "foreground";
  order: number;
  parallax: number;
  alpha_mode: "opaque" | "transparent";
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
    asset: RuntimeArtifact;
  }>;
  ladder?: Readonly<{
    mode: "ladder-4-tile-v1";
    asset: RuntimeArtifact;
    placements: readonly Readonly<{
      ladder_id: string;
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
  source_facing: "right" | "back";
  runtime_mirror: boolean;
  columns: 4;
  rows: 1;
  source_frame_count: 4;
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
  schema_version: 4;
  kind: "prepared-game-runtime-v4";
  game_id: string;
  revision: number;
  display_name: string;
  package_sha256: string;
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
  if (sourceFacing !== "right" && sourceFacing !== "back") {
    throw new Error(`${label}.source_facing is invalid`);
  }
  if (typeof record.runtime_mirror !== "boolean") {
    throw new Error(`${label}.runtime_mirror must be boolean`);
  }
  if (
    record.columns !== 4 ||
    record.rows !== 1 ||
    record.source_frame_count !== 4
  ) {
    throw new Error(`${label} must be one 4-by-1 strip`);
  }
  if ((sourceFacing === "back") === record.runtime_mirror) {
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
    canonicalFrameIndices.some((index) => index >= 4)
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
    columns: 4,
    rows: 1,
    source_frame_count: 4,
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
  if (root.schema_version !== 4 || root.kind !== "prepared-game-runtime-v4") {
    throw new Error("prepared runtime manifest identity is invalid");
  }
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
      return Object.freeze({
        layer_id: id(layer.layer_id, "layer_id"),
        plane: layer.plane,
        order: integer(layer.order, "layer order"),
        parallax: layer.parallax,
        alpha_mode: layer.alpha_mode,
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
    const ladder =
      map.ladder === undefined
        ? undefined
        : (() => {
            const rawLadder = object(map.ladder, `maps[${mapIndex}].ladder`);
            if (rawLadder.mode !== "ladder-4-tile-v1") {
              throw new Error("ladder mode is invalid");
            }
            const placements = array(
              rawLadder.placements,
              `maps[${mapIndex}].ladder.placements`,
            ).map((rawPlacement, placementIndex) => {
              const placement = object(
                rawPlacement,
                `maps[${mapIndex}].ladder.placements[${placementIndex}]`,
              );
              if (
                placement.bottom_surface !== "terrain" ||
                placement.rise_tiles !== 4
              ) {
                throw new Error("ladder placement geometry is invalid");
              }
              return Object.freeze({
                ladder_id: snakeId(placement.ladder_id, "ladder_id"),
                normalized_x: normalizedX(
                  placement.normalized_x,
                  "ladder normalized_x",
                ),
                bottom_surface: "terrain" as const,
                rise_tiles: 4 as const,
              });
            });
            if (
              placements.length === 0 ||
              placements.length > 8 ||
              new Set(placements.map((entry) => entry.ladder_id)).size !==
                placements.length ||
              new Set(placements.map((entry) => entry.normalized_x)).size !==
                placements.length
            ) {
              throw new Error("ladder placements must have unique identities and positions");
            }
            return Object.freeze({
              mode: "ladder-4-tile-v1" as const,
              asset: artifact(rawLadder.asset, "ladder asset"),
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
        asset: artifact(ground.asset, "ground asset"),
      }),
      ...(ladder === undefined ? {} : { ladder }),
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
    return Object.freeze({ prop_id: id(prop.prop_id, "prop_id"), display_name: text(prop.display_name, "prop display_name"), asset: artifact(prop.asset, "prop asset") });
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
    schema_version: 4,
    kind: "prepared-game-runtime-v4",
    game_id: gameId,
    revision: integer(root.revision, "revision", 1),
    display_name: text(root.display_name, "display_name"),
    package_sha256: packageSha256,
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
