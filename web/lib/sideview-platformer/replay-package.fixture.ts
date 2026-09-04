import { INVENTORY_GRID_4X2_V1 } from "@/lib/manifest/inventory-layout";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";
import type { RuntimeArtifact, RuntimeArtifactRole } from "@/lib/manifest/prepared-manifest";
import { UI_ATLAS_FIXTURE_ROLES } from "@/lib/shell/prepared-runtime.fixture";

/**
 * The package the platformer's replay golden is recorded against.
 *
 * `preparedRuntimeManifestFixture` in `lib/shell` is a one-map village with no creature, no item and
 * no round: it exists to prove the parser, and a replay of it would prove that a character can walk.
 * This one is authored for the instrument instead. Two maps joined by a portal pair, a hunting route
 * with a population zone and a boss encounter, a throwing kit with ammunition to spend and healing to
 * drink, a floating deck with a ladder onto it, and a villager with a conversation — so that a single
 * scripted run touches the map transition, the spawn director, the projectile pool, loot, the
 * inventory, the dialogue hold and the defeat path, which is the whole surface Step 0's bug list is
 * about.
 *
 * Every geometry number here is authored, and therefore real in the golden: occupancy, deck spans,
 * ladder placement, portal anchors, spawn fractions. Nothing here is art — the harness serves no
 * asset, so the runtime's own presentation fallback stands in for every texture.
 */

const HASH = "a".repeat(64);
const HEIGHT_UNITS_SOURCE = "definition" as const;

function artifact(
  path: string,
  mediaType = "image/png",
  role: RuntimeArtifactRole = "asset",
): RuntimeArtifact {
  return { path, sha256: HASH, bytes: 128, media_type: mediaType, role, width: 1536, height: 512 };
}

function calibration(extent = 600) {
  return {
    height_units: 1,
    height_units_source: HEIGHT_UNITS_SOURCE,
    source_px_per_unit: extent,
    measured_sha256: "c".repeat(64),
    subject_extent_px: extent,
  };
}

/** Four frames at a stated cadence: the shape every actor strip in a real package has. */
function strip(
  path: string,
  mode: "hold" | "loop" | "gameplay_driven" | "once",
  framesPerSecond?: number,
) {
  return {
    source_facing: "right" as const,
    runtime_mirror: true,
    columns: 4,
    rows: 1,
    source_frame_count: 4,
    anchor: "bottom" as const,
    playback: {
      mode,
      canonical_frame_indices: mode === "hold" ? [0] : [0, 1, 2, 3],
      ...(framesPerSecond === undefined ? {} : { frames_per_second: framesPerSecond }),
    },
    asset: artifact(path),
  };
}

function dialogueSheet(path: string) {
  return {
    columns: 1,
    rows: 1,
    index_order: "row_major" as const,
    expressions: ["neutral"],
    asset: artifact(path),
  };
}

/** Ground row on the bottom, one exposed deck four tiles up, and nothing else. */
function routeOccupancy(columns: number, deckStart: number, deckEnd: number): string[] {
  const empty = "0".repeat(columns);
  const deck = Array.from({ length: columns }, (_, column) =>
    column >= deckStart && column < deckEnd ? "1" : "0",
  ).join("");
  return [empty, deck, empty, empty, empty, "1".repeat(columns)];
}

export const REPLAY_VILLAGE_COLUMNS = 24;
export const REPLAY_ROUTE_COLUMNS = 40;
const DECK_START = 0;
const DECK_END = 8;

const PLAYER_STATES = {
  idle: strip("content/player/states/idle.png", "hold"),
  walk: strip("content/player/states/walk.png", "loop", 8),
  run: strip("content/player/states/run.png", "loop", 12),
  jump: strip("content/player/states/jump.png", "gameplay_driven"),
  crouch: strip("content/player/states/crouch.png", "loop", 6),
  climb_ladder: strip("content/player/states/climb_ladder.png", "gameplay_driven"),
  skill_cast: strip("content/player/states/skill_cast.png", "once", 10),
  hurt: strip("content/player/states/hurt.png", "once", 12),
  death: strip("content/player/states/death.png", "once", 8),
};

function mob(mobId: string, rank: string, aggression: string | null) {
  return {
    mob_id: mobId,
    display_name: mobId,
    rank,
    aggression,
    concept: artifact(`content/mobs/${mobId}/concept.png`),
    states: {
      idle: strip(`content/mobs/${mobId}/idle.png`, "loop", 6),
      hurt: strip(`content/mobs/${mobId}/hurt.png`, "once", 12),
      attack: strip(`content/mobs/${mobId}/attack.png`, "once", 10),
      death: strip(`content/mobs/${mobId}/death.png`, "once", 8),
    },
    calibration: calibration(),
  };
}

function item(itemId: string, kind: string) {
  return {
    item_id: itemId,
    display_name: itemId,
    item_kind: kind,
    asset: artifact(`content/items/${itemId}.png`),
    calibration: calibration(96),
  };
}

/** The prepared runtime manifest, `gameplay` block included, exactly as the scene fetches it. */
export function replayRuntimeManifest(): Record<string, unknown> {
  const artifacts = [artifact("content/player/concept.png")];
  return {
    schema_version: 12,
    kind: "prepared-game-runtime-v12",
    blocks: { ...PREPARED_RUNTIME_BLOCKS },
    game_id: "replay-route",
    revision: 1,
    display_name: "Replay Route",
    package_sha256: "b".repeat(64),
    presentation: {
      view_profile: "side_view_2d",
      gameplay_space: "side_plane",
      contact_shadows: { enabled: true, opacity: 0.18, softness_screen_pixels: 6 },
    },
    entry_map_id: "village-map",
    entry_spawn_id: "village_start",
    scale: {
      unit: "player_height",
      player_height_tiles: 2.4,
      minimum: 0.25,
      steps: [0.25, 0.5, 0.75, 1, 1.5, 2, 3],
      ranks: { common: 0.5, uncommon: 0.65, elite: 0.85, boss: 1.5 },
    },
    maps: [villageMap(), routeMap()],
    player: {
      player_id: "hero",
      display_name: "Hero",
      concept: artifact("content/player/concept.png"),
      states: PLAYER_STATES,
      dialogue: dialogueSheet("content/player/dialogue.png"),
      calibration: {
        ...calibration(),
        baseline_state: "idle",
        state_rebase: Object.fromEntries(Object.keys(PLAYER_STATES).map((state) => [state, 1])),
        plate_sha256: "d".repeat(64),
      },
    },
    mobs: [mob("moth", "common", "hunting"), mob("page_eater", "boss", "relentless")],
    npcs: [
      {
        npc_id: "baker",
        display_name: "Baker",
        role: "merchant",
        world: strip("content/npcs/baker/world.png", "loop", 6),
        dialogue: dialogueSheet("content/npcs/baker/dialogue.png"),
        calibration: calibration(),
      },
    ],
    props: [
      {
        prop_id: "village_well",
        display_name: "Village Well",
        ground_contact_y_normalized: 1,
        calibration: calibration(240),
        asset: artifact("content/props/village_well.png"),
      },
    ],
    items: [
      item("welcome_tart", "healing_consumable"),
      item("paper_dart", "throwable_ammo"),
      item("gold_coin", "currency"),
    ],
    projectiles: [
      {
        projectile_id: "paperwing_dart",
        display_name: "Paperwing Dart",
        silhouette: "dart",
        flight: "flat_fast_v1",
        impact: "single_target_v1",
        asset: artifact("content/projectiles/paperwing_dart.png"),
        calibration: calibration(64),
      },
    ],
    ui: {
      inventory_panel: { ...INVENTORY_GRID_4X2_V1, asset: artifact("ui/inventory_panel.png") },
      panel_frame: { ...UI_ATLAS_FIXTURE_ROLES.panel_frame, asset: artifact("ui/panel_frame.png") },
      button_rect: { ...UI_ATLAS_FIXTURE_ROLES.button_rect, asset: artifact("ui/button_rect.png") },
      preview_icons: {
        ...UI_ATLAS_FIXTURE_ROLES.preview_icons,
        asset: artifact("ui/preview_icons.png"),
      },
    },
    soundtrack: {
      playback: { selection: "shuffle", no_immediate_repeat: true },
      tracks: [
        {
          track_id: "village_theme",
          display_name: "Village Theme",
          asset: artifact("soundtrack/village_theme.ogg", "audio/ogg"),
        },
        {
          track_id: "road_theme",
          display_name: "Road Theme",
          asset: artifact("soundtrack/road_theme.ogg", "audio/ogg"),
        },
        // Two tracks on the route, because a shuffle bag that cannot repeat has nothing to shuffle
        // in a pool of one - the player says so and stops after a single play.
        {
          track_id: "road_theme_b",
          display_name: "Road Theme, Reprise",
          asset: artifact("soundtrack/road_theme_b.ogg", "audio/ogg"),
        },
      ],
    },
    gameplay: replayGameplayContract(),
    scenarios: [bakerScenario()],
    closure: {
      artifact_count: artifacts.length,
      artifacts_sha256: "c".repeat(64),
      artifacts,
    },
  };
}

function layer(layerId: string, path: string) {
  return {
    layer_id: layerId,
    plane: "background",
    order: 0,
    parallax: 0.1,
    alpha_mode: "opaque",
    placement: {
      vertical_anchor: "canvas_cover",
      vertical_offset: 0,
      vertical_offset_source: "measured",
      source_height: 1024,
      trimmed_height: 1024,
      trimmed_top: 0,
    },
    presentation: {
      contrast: 1,
      saturation: 1,
      atmosphere_color: "#ffffff",
      atmosphere_strength: 0,
      detail_blur_screen_pixels: 0,
    },
    asset: artifact(path),
  };
}

function villageMap(): Record<string, unknown> {
  return {
    map_id: "village-map",
    revision: 1,
    display_name: "Village",
    role: "safe_village_hub",
    camera: { mode: "player_follow", follow_axes: ["x"] },
    hostile_population_enabled: false,
    track_ids: ["village_theme"],
    layers: [layer("blue_sky", "maps/village/background.png")],
    ground: {
      mode: "terrain-atlas-3x3-minimal-v1",
      occupancy: ["0".repeat(REPLAY_VILLAGE_COLUMNS), "1".repeat(REPLAY_VILLAGE_COLUMNS)],
      vertical_fit: "floor_to_screen_bottom",
      walk_surface_row: 1,
      asset: artifact("maps/village/ground.png"),
    },
    portal: {
      mode: "portal-pair-1x2-v1",
      asset: artifact("maps/village/portal.png"),
      endpoints: [
        { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
        // Hard against the eastern clamp, so a walk that simply runs out of world arrives at the
        // gate: the script says "go east until the world stops" rather than naming a frame.
        { anchor: "east_gate", normalized_x: 0.97, role: "exit" },
      ],
    },
  };
}

function routeMap(): Record<string, unknown> {
  return {
    map_id: "road-map",
    revision: 1,
    display_name: "Crowncrag Road",
    role: "scrolling_hunting_route",
    camera: { mode: "player_follow", follow_axes: ["x", "y"] },
    hostile_population_enabled: true,
    track_ids: ["road_theme", "road_theme_b"],
    layers: [layer("dawn_sky", "maps/road/background.png")],
    ground: {
      mode: "terrain-atlas-3x3-minimal-v1",
      occupancy: routeOccupancy(REPLAY_ROUTE_COLUMNS, DECK_START, DECK_END),
      vertical_fit: "floor_to_screen_bottom",
      walk_surface_row: 5,
      asset: artifact("maps/road/ground.png"),
    },
    climbable: {
      mode: "climbable-atlas-v1",
      asset: artifact("maps/road/climbable.png"),
      index_order: "left_to_right",
      variants: [
        {
          variant_id: "road_ladder",
          role: "ladder",
          cell_index: 0,
          cell: { x: 0, y: 0, width: 96, height: 384 },
        },
      ],
      placements: [
        {
          climbable_id: "road_ladder_a",
          variant_id: "road_ladder",
          normalized_x: 0.0125,
          bottom_surface: "terrain",
          rise_tiles: 4,
        },
      ],
    },
    portal: {
      mode: "portal-pair-1x2-v1",
      asset: artifact("maps/road/portal.png"),
      endpoints: [
        { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
        { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
      ],
    },
  };
}

/** The gameplay contract block, in the shape `parsePreparedGameplayContract` admits. */
function replayGameplayContract(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "gameplay-contract-v1",
    game_id: "replay-route",
    revision: 3,
    entry_map_id: "village-map",
    entry_spawn_id: "village_start",
    navigation: {
      allowed_movements: ["move_left", "move_right", "jump", "crouch", "climb"],
      logical_world_wrap: false,
      fall_recovery: "last_safe_ground",
    },
    player: {
      player_id: "hero",
      starting_level: 1,
      starting_health: 6,
      starting_item_ids: ["paper_dart", "welcome_tart"],
    },
    progression: {
      enabled: true,
      maximum_level: 20,
      experience_curve: "gentle_rpg_v1",
      stat_growth: "balanced_novice_v1",
    },
    inventory: { currency_item_id: "gold_coin", starting_capacity: 24 },
    combat: {
      enabled: true,
      basic_action: "basic_attack",
      secondary_action: "skill_cast",
      contact_damage: true,
      critical_profile: "standard_v1",
      lethal_presentation: false,
      defeat_presentation: "story_beast_disperses_into_page_light",
      weapon_class: "ranged_dps_v1",
      projectile_id: "paperwing_dart",
      number_scale: "unit_v1",
    },
    combat_text: { enabled: true },
    map_uses: [
      {
        map_id: "village-map",
        role: "safe_village_hub",
        hostile_population_enabled: false,
        track_ids: ["village_theme"],
      },
      {
        map_id: "road-map",
        role: "scrolling_hunting_route",
        hostile_population_enabled: true,
        track_ids: ["road_theme", "road_theme_b"],
      },
    ],
    spawns: [
      { spawn_id: "village_start", map_id: "village-map", anchor: "west_gate", normalized_x: 0.1 },
      { spawn_id: "road_start", map_id: "road-map", anchor: "west_gate", normalized_x: 0.1 },
    ],
    transitions: [
      {
        transition_id: "village_to_road",
        from_map_id: "village-map",
        from_anchor: "east_gate",
        to_map_id: "road-map",
        to_spawn_id: "road_start",
      },
      {
        transition_id: "road_to_village",
        from_map_id: "road-map",
        from_anchor: "west_gate",
        to_map_id: "village-map",
        to_spawn_id: "village_start",
      },
    ],
    mob_population: {
      update_interval_ms: 250,
      max_spawn_batch_per_update: 2,
      maps: [
        {
          map_id: "road-map",
          seed_salt: 7,
          zones: [
            {
              zone_id: "road_zone",
              surface: "terrain",
              left_fraction: 0.12,
              right_fraction: 0.6,
              initial_population: 2,
              target_population: 3,
              population_cap: 4,
              respawn_delay_ms: 1200,
              spawn_table: [{ mob_id: "moth", weight: 1 }],
            },
          ],
        },
      ],
    },
    boss_encounters: [
      {
        encounter_id: "road_boss",
        map_id: "road-map",
        anchor: "east_gate",
        mob_id: "page_eater",
        track_id: "road_theme",
        respawn_policy: "quest_reset_only",
      },
    ],
    loot_rules: [
      { mob_id: "moth", item_id: "gold_coin", chance: 1, quantity_min: 1, quantity_max: 1 },
      { mob_id: "moth", item_id: "paper_dart", chance: 1, quantity_min: 1, quantity_max: 2 },
    ],
    npc_placements: [
      { map_id: "village-map", npc_id: "baker", anchor: "bakery", normalized_x: 0.4 },
    ],
    prop_placements: [
      { map_id: "village-map", prop_id: "village_well", anchor: "square", normalized_x: 0.6 },
    ],
    interactions: [
      {
        interaction_id: "meet_baker",
        map_id: "village-map",
        actor_id: "baker",
        scenario_id: "meet_baker",
        outcomes: [{ outcome_id: "greeted", effect_ids: ["grant_welcome_tart"] }],
      },
    ],
    quests: [
      {
        quest_id: "first_quest",
        display_name: "The First Quest",
        start_effect_id: "start_first_quest",
        completion_item_id: "gold_coin",
        completion_count: 3,
        completion_effect_id: "complete_first_quest",
      },
    ],
    effects: [
      {
        effect_id: "start_first_quest",
        operation: "set_quest_state",
        quest_id: "first_quest",
        state: "active",
      },
      {
        effect_id: "complete_first_quest",
        operation: "set_quest_state",
        quest_id: "first_quest",
        state: "completed",
      },
      {
        effect_id: "grant_welcome_tart",
        operation: "grant_item",
        item_id: "welcome_tart",
        quantity: 1,
      },
    ],
  };
}

/** A two-line conversation with a choice, which is what makes the dialogue hold observable. */
function bakerScenario(): Record<string, unknown> {
  return {
    schema_version: 2,
    kind: "scenario-program-v2",
    game_id: "replay-route",
    scenario_id: "meet_baker",
    display_name: "Meet the Baker",
    revision: 1,
    script_sha256: "0".repeat(64),
    entry: "greeting",
    cast: [{ actor_id: "baker", expressions: ["neutral"] }],
    stages: [{ stage_id: "village", brief: "The village square" }],
    endings: [{ outcome_id: "greeted", label: "You said hello" }],
    blocks: [
      {
        label: "greeting",
        statements: [
          { kind: "stage", stage: "village" },
          { kind: "show", actor: "baker", expression: "neutral", slot: "center" },
          { kind: "line", speaker: "baker", text: "Fresh bread today." },
          { kind: "line", speaker: "baker", text: "Mind the road east." },
          { kind: "end", outcome: "greeted" },
        ],
      },
    ],
  };
}
