// A minimal but fully valid runner manifest, shaped exactly like the document
// prepared_runner.py assembles. Tests mutate copies of it to probe one refusal
// at a time, so it stays the single place the happy path is spelled out.
//
// Its ids are fiction and stay that way deliberately. They read as bellweather
// because this fixture was written while bellweather carried the runner member
// the genre was built against; that member has since been retired in favour of
// Iron Petal, and nothing here mirrors a committed package. A fixture that
// tracked a real one would fail for the package's reasons as well as its own.

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

export function runnerAudioFixture(): Record<string, unknown> {
  const definitions = [
    ["takeoff_whistle", "Takeoff Whistle", "triangle", 330, 660, 120, 0.16, 0],
    ["air_jump_whistle", "Air Jump Whistle", "triangle", 440, 990, 120, 0.16, 0],
    ["soft_landing", "Soft Landing", "sine", 220, 160, 80, 0.12, 0],
    ["leaf_slide", "Leaf Slide", "sawtooth", 200, 120, 160, 0.07, 0],
    ["clear_sparkle", "Clear Sparkle", "sine", 520, 780, 100, 0.1, 0],
    ["token_chime", "Token Chime", "sine", 660, 880, 90, 0.12, 1],
  ] as const;
  return {
    bindings: {
      takeoff: "takeoff_whistle",
      air_jump: "air_jump_whistle",
      land: "soft_landing",
      slide: "leaf_slide",
      hazard_cleared: "clear_sparkle",
      collect: "token_chime",
      hurt: "soft_landing",
      death: "run_ended",
    },
    effects: [
      ...definitions.map(
        ([effect_id, display_name, waveform, start_frequency_hz, end_frequency_hz, duration_milliseconds, gain, strength_pitch_multiplier]) => ({
          effect_id,
          display_name,
          realization: {
            kind: "oscillator_sweep_v1",
            waveform,
            start_frequency_hz,
            end_frequency_hz,
            duration_milliseconds,
            gain,
            strength_pitch_multiplier,
          },
        }),
      ),
      // One effect realized as a generated clip, so the union is exercised.
      {
        effect_id: "run_ended",
        display_name: "Run Ended",
        realization: {
          kind: "generated_clip_v1",
          clip: "audio/run_ended.mp3",
          duration_seconds: 1,
          gain: 0.5,
          strength_pitch_multiplier: 0,
        },
      },
    ],
  };
}

export function runnerManifestFixture(): Record<string, unknown> {
  return {
    schema_version: 6,
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
      jump_profile: "double_arc_v1",
      collision_box: "torso_v1",
      duck_profile: "slide_v1",
      consequences: {
        hazard: "drain_v1",
        pit: "drain_and_recover_v1",
        crush: "end_run_v1",
      },
      vitals: {
        profile: "three_point_v1",
        max_points: 3,
        hurt_representation: "blink_v1",
      },
      ramp_profile: "gentle_ramp_v1",
      max_clear_gap_columns: 3,
      max_rise_tiles: 2,
      jump_peak_margin_tiles: 0.75,
      airtime_headroom: 1.15,
      base_speed_columns_per_second: 6,
      max_speed_multiplier: 1.5,
      avatar_half_width_columns: 0.3,
      hazard_column_inset: 0.15,
      ducked_height_fraction: 0.5,
      min_overhead_clearance_rows: 0.25,
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
          hazards: [{ prop_id: "toppled_cart", column: 6, anchor: "surface", clearance_rows: null }],
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
        runnerMotionFixture("slide", "once"),
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
    audio: runnerAudioFixture(),
    soundtrack: null,
  };
}
