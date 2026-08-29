import type { RuntimeArtifact } from "@/lib/runtime/prepared-manifest";
import { INVENTORY_GRID_4X2_V1 } from "@/lib/runtime/inventory-layout";

const HASH = "a".repeat(64);

function artifact(path: string, mediaType = "image/png"): RuntimeArtifact {
  return {
    path,
    sha256: HASH,
    bytes: 128,
    media_type: mediaType,
    width: 64,
    height: 64,
  };
}

export function preparedRuntimeManifestFixture(): Record<string, unknown> {
  const background = artifact("maps/village/background.png");
  const ground = artifact("maps/village/ground.png");
  const portal = artifact("maps/village/portal.png");
  const playerConcept = artifact("content/player/concept.png");
  const playerIdle = artifact("content/player/states/idle.png");
  const playerCrouch = artifact("content/player/states/crouch.png");
  const playerDialogue = artifact("content/player/dialogue.png");
  const inventoryPanel = artifact("ui/inventory_panel.png");
  const artifacts = [
    background,
    ground,
    portal,
    playerConcept,
    playerIdle,
    playerCrouch,
    playerDialogue,
    inventoryPanel,
  ];

  return {
    schema_version: 9,
    kind: "prepared-game-runtime-v9",
    game_id: "prepared_fixture",
    revision: 1,
    display_name: "Prepared Fixture",
    package_sha256: "b".repeat(64),
    presentation: {
      view_profile: "side_view_2d",
      gameplay_space: "side_plane",
      contact_shadows: {
        enabled: true,
        opacity: 0.18,
        softness_screen_pixels: 6,
      },
    },
    entry_map_id: "village",
    entry_spawn_id: "arrival",
    scale: {
      unit: "player_height",
      player_height_tiles: 2.4,
      minimum: 0.25,
      steps: [0.25, 0.5, 0.75, 1, 1.5, 2, 3],
      ranks: { common: 0.5, uncommon: 0.65, elite: 0.85, boss: 1.5 },
    },
    maps: [
      {
        map_id: "village",
        revision: 1,
        display_name: "Village",
        role: "safe_village_hub",
        camera: { mode: "player_follow", follow_axes: ["x"] },
        hostile_population_enabled: false,
        track_ids: [],
        layers: [
          {
            layer_id: "blue_sky",
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
            asset: background,
          },
        ],
        ground: {
          mode: "terrain-atlas-3x3-minimal-v1",
          occupancy: ["0".repeat(20), "1".repeat(20)],
          vertical_fit: "floor_to_screen_bottom",
          walk_surface_row: 0,
          asset: ground,
        },
        portal: {
          mode: "portal-pair-1x2-v1",
          asset: portal,
          endpoints: [
            { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
            { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
          ],
        },
      },
    ],
    player: {
      player_id: "hero",
      display_name: "Hero",
      concept: playerConcept,
      states: {
        idle: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          source_frame_count: 4,
          anchor: "bottom",
          playback: {
            mode: "hold",
            canonical_frame_indices: [0],
          },
          asset: playerIdle,
        },
        crouch: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          source_frame_count: 4,
          anchor: "bottom",
          playback: {
            mode: "loop",
            canonical_frame_indices: [0, 1, 2, 3],
            frames_per_second: 6,
          },
          asset: playerCrouch,
        },
      },
      calibration: {
        height_units: 1,
        height_units_source: "definition",
        source_px_per_unit: 600,
        measured_sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        subject_extent_px: 600,
        baseline_state: "idle",
        state_rebase: { idle: 1, crouch: 1.09 },
        plate_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      },
      dialogue: {
        columns: 1,
        rows: 1,
        index_order: "row_major",
        expressions: ["neutral"],
        asset: playerDialogue,
      },
    },
    mobs: [],
    npcs: [],
    props: [],
    items: [],
    ui: {
      inventory_panel: {
        ...INVENTORY_GRID_4X2_V1,
        asset: inventoryPanel,
      },
    },
    soundtrack: {
      playback: { selection: "shuffle", no_immediate_repeat: true },
      tracks: [],
    },
    gameplay: {},
    sequences: [],
    closure: {
      artifact_count: artifacts.length,
      artifacts_sha256: "c".repeat(64),
      artifacts,
    },
  };
}
