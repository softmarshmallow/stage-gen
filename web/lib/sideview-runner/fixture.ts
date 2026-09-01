// A minimal but fully valid runner manifest, shaped exactly like the document
// prepared_runner.py assembles. Tests mutate copies of it to probe one refusal
// at a time, so it stays the single place the happy path is spelled out.

import { RUNNER_RUNTIME_KIND } from "./contract";

const SHA = "a".repeat(64);

export function runnerCalibrationFixture(): Record<string, unknown> {
  return {
    height_units: 1,
    height_units_source: "definition",
    source_px_per_unit: 812.3,
    measured_sha256: SHA,
    subject_extent_px: 812,
  };
}

export function runnerMotionFixture(state: string, playback: string): Record<string, unknown> {
  return {
    state,
    playback_mode: playback,
    canonical_frame_indices: [0, 1, 2, 3],
    frames_per_second: 10,
    anchor: "bottom",
    atlas: `avatar/${state}.png`,
    columns: 4,
    rebase_multiplier: 1,
  };
}

export function runnerManifestFixture(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: RUNNER_RUNTIME_KIND,
    game_id: "bellweather",
    display_name: "Bellweather",
    track_id: "sunpetal-sprint",
    track_display_name: "Sunpetal Sprint",
    package_sha256: SHA,
    presentation: {
      view_profile: "side_view_2d",
      gameplay_space: "side_plane",
      contact_shadows: { enabled: true, opacity: 0.18, softness_screen_pixels: 6 },
    },
    camera: { mode: "auto_run_x_v1" },
    scale: { player_height_tiles: 2.4, tile_px: 64 },
    gameplay: {
      speed_profile: "steady_runner_v1",
      jump_profile: "single_arc_v1",
      collision_policy: "end_run_v1",
      ramp_profile: "gentle_ramp_v1",
      max_clear_gap_columns: 3,
      max_rise_tiles: 2,
    },
    ground: {
      atlas: "world/ground.png",
      mode: "terrain-atlas-3x3-minimal-v1",
      vertical_fit: "floor_to_screen_bottom",
    },
    layers: [
      {
        layer_id: "meadow_sky",
        plane: "background",
        order: 0,
        parallax: 0.05,
        alpha_mode: "opaque",
        vertical_anchor: "canvas_cover",
        vertical_offset: null,
        image: "world/layers/meadow_sky.png",
        width: 1536,
        height: 1024,
        presentation: {
          contrast: 0.95,
          saturation: 0.9,
          atmosphere_color: "#bcd6ef",
          atmosphere_strength: 0.12,
          detail_blur_screen_pixels: 1.2,
        },
      },
    ],
    segments: {
      rows: 8,
      walk_surface_row: 5,
      chunks: [
        {
          segment_id: "meadow_flat",
          difficulty: 1,
          occupancy: [
            "000000000000",
            "000000000000",
            "000000000000",
            "000000000000",
            "000000000000",
            "111111111111",
            "111111111111",
            "111111111111",
          ],
          hazards: [{ prop_id: "toppled_cart", column: 6 }],
          pickups: [{ item_id: "sunleaf_token", column: 6, row: 2 }],
        },
      ],
    },
    avatar: {
      avatar_id: "wayfarer_sprinter",
      display_name: "Wayfarer Sprinter",
      concept: "avatar/concept.png",
      calibration: runnerCalibrationFixture(),
      motions: [
        runnerMotionFixture("run", "loop"),
        runnerMotionFixture("jump", "once"),
        runnerMotionFixture("death", "once"),
      ],
    },
    props: [
      {
        prop_id: "toppled_cart",
        display_name: "Toppled Cart",
        image: "catalog/props/toppled_cart.png",
        calibration: runnerCalibrationFixture(),
      },
    ],
    items: [
      {
        item_id: "sunleaf_token",
        display_name: "Sunleaf Token",
        image: "catalog/items/sunleaf_token.png",
        calibration: runnerCalibrationFixture(),
      },
    ],
    soundtrack: null,
  };
}
