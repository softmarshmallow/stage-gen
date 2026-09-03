import { describe, expect, test } from "bun:test";
import {
  bottomContiguousSurfaceRow,
  parseRunnerRuntimeManifest,
  RUNNER_REFUSAL,
  RUNNER_AUDIO_EVENTS,
} from "./contract";
import {
  runnerArenaChunkFixture,
  runnerBossFixture,
  runnerCalibrationFixture as calibration,
  runnerManifestFixture,
  runnerManifestFixture as validRunnerManifest,
  runnerMotionFixture,
  runnerMotionFixture as motion,
} from "./fixture";

describe("parseRunnerRuntimeManifest", () => {
  test("parses the produced document into frozen runtime shapes", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    expect(manifest.gameId).toBe("bellweather");
    expect(manifest.trackId).toBe("sunpetal-sprint");
    expect(manifest.scale.tilePx).toBe(64);
    expect(manifest.ground.mode).toBe("terrain-atlas-3x3-minimal-v1");
    expect(manifest.gameplay.maxClearGapColumns).toBe(3);
    expect(manifest.segments.chunks[0].hazards[0]).toEqual({
      propId: "toppled_cart",
      column: 6,
      anchor: "surface",
      clearanceRows: null,
    });
    expect(manifest.gameplay.jumpProfile).toBe("double_arc_v1");
    expect(manifest.gameplay.duckProfile).toBe("slide_v1");
    expect(manifest.gameplay.baseSpeedColumnsPerSecond).toBe(6);
    expect(manifest.gameplay.duckedHeightFraction).toBe(0.5);
    expect(manifest.avatar.motions.map((entry) => entry.state)).toEqual([
      "run",
      "jump",
      "slide",
      "death",
    ]);
    expect(manifest.soundtrack).toBeNull();
    expect(manifest.audio.bindings.collect).toBe("token_chime");
    expect(manifest.audio.effects.find((effect) => effect.effectId === "token_chime")?.realization)
      .toMatchObject({ waveform: "sine", strengthPitchMultiplier: 1 });
    expect(Object.isFrozen(manifest)).toBe(true);
    expect(Object.isFrozen(manifest.segments.chunks[0])).toBe(true);
  });

  test("accepts the brisk speed and ramp names with their published arithmetic", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.speed_profile = "brisk_runner_v1";
    gameplay.ramp_profile = "brisk_ramp_v1";
    gameplay.base_speed_columns_per_second = 7.5;

    const manifest = parseRunnerRuntimeManifest(document);

    expect(manifest.gameplay.speedProfile).toBe("brisk_runner_v1");
    expect(manifest.gameplay.rampProfile).toBe("brisk_ramp_v1");
    expect(manifest.gameplay.baseSpeedColumnsPerSecond).toBe(7.5);
    expect(manifest.gameplay.maxSpeedMultiplier).toBe(1.5);
  });

  test("accepts the swift speed name with its published base", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.speed_profile = "swift_runner_v1";
    gameplay.base_speed_columns_per_second = 9;

    const manifest = parseRunnerRuntimeManifest(document);

    expect(manifest.gameplay.speedProfile).toBe("swift_runner_v1");
    expect(manifest.gameplay.baseSpeedColumnsPerSecond).toBe(9);
  });

  test("parses structural ground locked one-for-one to authored segment grids", () => {
    const document = validRunnerManifest();
    document.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 64,
      chunks: [
        {
          segment_id: "meadow_flat",
          image: "world/ground/meadow_flat.png",
          columns: 12,
          rows: 8,
        },
      ],
    };
    const manifest = parseRunnerRuntimeManifest(document);
    expect(manifest.ground).toEqual({
      mode: "runner-structural-ground-v1",
      verticalFit: "floor_to_screen_bottom",
      cellPx: 64,
      chunks: [
        {
          segmentId: "meadow_flat",
          image: "world/ground/meadow_flat.png",
          columns: 12,
          rows: 8,
        },
      ],
    });
    if (manifest.ground.mode !== "runner-structural-ground-v1") {
      throw new Error("fixture did not parse as structural ground");
    }
    expect(Object.isFrozen(manifest.ground)).toBe(true);
    expect(Object.isFrozen(manifest.ground.chunks)).toBe(true);
  });

  test("refuses structural ground that diverges from occupancy identity or dimensions", () => {
    const mismatchedId = validRunnerManifest();
    mismatchedId.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 64,
      chunks: [
        { segment_id: "other", image: "world/ground/other.png", columns: 12, rows: 8 },
      ],
    };
    expect(() => parseRunnerRuntimeManifest(mismatchedId)).toThrow(
      "segment_id must match segments.chunks[0].segment_id",
    );

    const wrongColumns = validRunnerManifest();
    wrongColumns.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 64,
      chunks: [
        {
          segment_id: "meadow_flat",
          image: "world/ground/meadow_flat.png",
          columns: 11,
          rows: 8,
        },
      ],
    };
    expect(() => parseRunnerRuntimeManifest(wrongColumns)).toThrow(
      "columns must match its occupancy width",
    );

    const missing = validRunnerManifest();
    missing.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 64,
      chunks: [],
    };
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow("one-for-one");

    const wrongCellSize = validRunnerManifest();
    wrongCellSize.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 32,
      chunks: [
        {
          segment_id: "meadow_flat",
          image: "world/ground/meadow_flat.png",
          columns: 12,
          rows: 8,
        },
      ],
    };
    expect(() => parseRunnerRuntimeManifest(wrongCellSize)).toThrow(
      "ground.cell_px must be exactly 64",
    );
  });

  test("keeps the ground discriminants mutually exclusive", () => {
    const atlasWithChunks = validRunnerManifest();
    (atlasWithChunks.ground as Record<string, unknown>).chunks = [];
    expect(() => parseRunnerRuntimeManifest(atlasWithChunks)).toThrow(
      "terrain-atlas ground must not declare structural",
    );

    const structuralWithAtlas = validRunnerManifest();
    structuralWithAtlas.ground = {
      mode: "runner-structural-ground-v1",
      vertical_fit: "floor_to_screen_bottom",
      cell_px: 64,
      atlas: "world/ground.png",
      chunks: [
        {
          segment_id: "meadow_flat",
          image: "world/ground/meadow_flat.png",
          columns: 12,
          rows: 8,
        },
      ],
    };
    expect(() => parseRunnerRuntimeManifest(structuralWithAtlas)).toThrow(
      "must not declare ground.atlas",
    );
  });

  test("requires exactly one correctly paired opaque canvas cover", () => {
    const missing = validRunnerManifest();
    const missingLayers = missing.layers as Record<string, unknown>[];
    missingLayers[0] = {
      ...missingLayers[0],
      alpha_mode: "transparent",
      vertical_anchor: "screen_top",
    };
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow(
      "exactly one opaque canvas_cover",
    );

    const duplicate = validRunnerManifest();
    const duplicateLayers = duplicate.layers as Record<string, unknown>[];
    duplicateLayers.push({
      ...duplicateLayers[0],
      layer_id: "second_cover",
      order: 1,
    });
    expect(() => parseRunnerRuntimeManifest(duplicate)).toThrow(
      "exactly one opaque canvas_cover",
    );

    const mismatched = validRunnerManifest();
    const mismatchedLayers = mismatched.layers as Record<string, unknown>[];
    mismatchedLayers.push({
      ...mismatchedLayers[0],
      layer_id: "transparent_cover",
      order: 1,
      alpha_mode: "transparent",
    });
    expect(() => parseRunnerRuntimeManifest(mismatched)).toThrow(
      "must pair alpha_mode opaque with vertical_anchor canvas_cover",
    );
  });

  test("accepts a soundtrack and optional calibration fields", () => {
    const document = validRunnerManifest();
    document.soundtrack = {
      selection: "shuffle",
      tracks: [{ track_id: "dawn_canter", audio: "soundtrack/dawn_canter.mp3" }],
    };
    const props = document.props as Record<string, unknown>[];
    props[0].calibration = {
      ...calibration(),
      downscale_ratio: 0.82,
      extent_axis: "width",
    };
    const manifest = parseRunnerRuntimeManifest(document);
    expect(manifest.soundtrack?.tracks[0].trackId).toBe("dawn_canter");
    expect(manifest.props[0].calibration.downscaleRatio).toBe(0.82);
    expect(manifest.props[0].calibration.extentAxis).toBe("width");
  });

  test("refuses an alien kind or schema version with the re-generate hint", () => {
    expect(() =>
      parseRunnerRuntimeManifest({ ...validRunnerManifest(), kind: "someone-elses-v1" }),
    ).toThrow(RUNNER_REFUSAL);
    expect(() =>
      parseRunnerRuntimeManifest({ ...validRunnerManifest(), schema_version: 2 }),
    ).toThrow(RUNNER_REFUSAL);
    expect(() => parseRunnerRuntimeManifest(null)).toThrow("must be an object");
  });

  test("parses a generated clip beside the oscillator and refuses a stray one", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    const clip = manifest.audio.effects.find((effect) => effect.effectId === "run_ended");
    expect(clip?.realization).toEqual({
      kind: "generated_clip_v1",
      clip: "audio/run_ended.mp3",
      durationSeconds: 1,
      gain: 0.5,
      strengthPitchMultiplier: 0,
    });
    expect(Object.isFrozen(clip?.realization)).toBe(true);

    const mutate = (change: (realization: Record<string, unknown>) => void) => {
      const document = validRunnerManifest();
      const audio = document.audio as { effects: Record<string, unknown>[] };
      const effect = audio.effects.find((entry) => entry.effect_id === "run_ended");
      change(effect!.realization as Record<string, unknown>);
      return document;
    };
    expect(() =>
      parseRunnerRuntimeManifest(mutate((r) => (r.kind = "generated_file_v1"))),
    ).toThrow("realization.kind");
    expect(() =>
      parseRunnerRuntimeManifest(mutate((r) => (r.clip = "soundtrack/run_ended.mp3"))),
    ).toThrow("run-relative audio/*.mp3");
    expect(() =>
      parseRunnerRuntimeManifest(mutate((r) => (r.clip = "audio/../run_ended.mp3"))),
    ).toThrow("run-relative audio/*.mp3");
    expect(() => parseRunnerRuntimeManifest(mutate((r) => (r.duration_seconds = 0.2)))).toThrow(
      "duration_seconds is out of range",
    );
    expect(() => parseRunnerRuntimeManifest(mutate((r) => (r.gain = 0)))).toThrow("gain");
  });

  test("parses a spoken line as a third clip kind and the announcement as the one optional binding", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    const line = manifest.audio.effects.find((effect) => effect.effectId === "mira_go");
    expect(line?.realization).toEqual({
      kind: "spoken_line_v1",
      clip: "audio/mira_go.mp3",
      durationSeconds: 2.01,
      gain: 0.7,
      strengthPitchMultiplier: 0,
    });
    expect(manifest.audio.bindings.stage_start).toBe("mira_go");
    expect(RUNNER_AUDIO_EVENTS[0]).toBe("stage_start");

    // Silent: null and absent both mean no announcement, and neither is an error.
    for (const silence of [null, undefined]) {
      const document = validRunnerManifest();
      const audio = document.audio as {
        bindings: Record<string, unknown>;
        effects: Record<string, unknown>[];
      };
      if (silence === undefined) delete audio.bindings.stage_start;
      else audio.bindings.stage_start = silence;
      audio.effects = audio.effects.filter((entry) => entry.effect_id !== "mira_go");
      expect(parseRunnerRuntimeManifest(document).audio.bindings.stage_start).toBeNull();
    }

    // A declared line nobody announces is dead art; an announcement of a
    // missing line is unresolved; every verb stays mandatory.
    const unused = validRunnerManifest();
    (unused.audio as { bindings: Record<string, unknown> }).bindings.stage_start = null;
    expect(() => parseRunnerRuntimeManifest(unused)).toThrow("mira_go is not bound");
    const unresolved = validRunnerManifest();
    (unresolved.audio as { bindings: Record<string, unknown> }).bindings.stage_start = "ghost";
    expect(() => parseRunnerRuntimeManifest(unresolved)).toThrow(
      "audio.bindings.stage_start references unknown effect ghost",
    );
    const verbless = validRunnerManifest();
    delete (verbless.audio as { bindings: Record<string, unknown> }).bindings.death;
    expect(() => parseRunnerRuntimeManifest(verbless)).toThrow("audio.bindings.death");
    const typed = validRunnerManifest();
    (typed.audio as { bindings: Record<string, unknown> }).bindings.stage_start = 7;
    expect(() => parseRunnerRuntimeManifest(typed)).toThrow("stage_start");
  });

  test("parses the music transitions and refuses an unpaired, unbounded, or alien one", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    expect(manifest.audio.music).toEqual({
      death: { action: "pause", fadeSeconds: 0.6, curve: "exponential" },
      restart: { action: "resume", fadeSeconds: 0.3, curve: "linear" },
      hurt: {
        duckGain: 0.5,
        fadeSeconds: 0.04,
        holdSeconds: 0.15,
        recoverySeconds: 0.5,
        curve: "linear",
      },
    });
    expect(Object.isFrozen(manifest.audio.music.death)).toBe(true);

    const music = (change: (music: Record<string, Record<string, unknown>>) => void) => {
      const document = validRunnerManifest();
      const audio = document.audio as { music: Record<string, Record<string, unknown>> };
      change(audio.music);
      return document;
    };
    expect(() => parseRunnerRuntimeManifest(music((m) => (m.restart.action = "play")))).toThrow(
      "audio.music.restart.action must be resume when audio.music.death.action is pause",
    );
    expect(() =>
      parseRunnerRuntimeManifest(music((m) => (m.death.fade_seconds = 11))),
    ).toThrow("audio.music.death.fade_seconds must be at most 10 seconds");
    expect(() => parseRunnerRuntimeManifest(music((m) => (m.death.curve = "s_curve")))).toThrow(
      "audio.music.death.curve",
    );
    expect(() => parseRunnerRuntimeManifest(music((m) => (m.hurt.duck_gain = 1)))).toThrow(
      "audio.music.hurt.duck_gain must be below 1",
    );
    const noDuck = validRunnerManifest();
    (noDuck.audio as { music: Record<string, unknown> }).music.hurt = null;
    expect(parseRunnerRuntimeManifest(noDuck).audio.music.hurt).toBeNull();
    const noMusic = validRunnerManifest();
    delete (noMusic.audio as Record<string, unknown>).music;
    expect(() => parseRunnerRuntimeManifest(noMusic)).toThrow("audio.music must be an object");
  });

  test("refuses missing, unresolved, or unused authored audio", () => {
    const missing = validRunnerManifest();
    delete missing.audio;
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow("audio must be an object");

    const unresolved = validRunnerManifest();
    const unresolvedAudio = unresolved.audio as { bindings: Record<string, unknown> };
    unresolvedAudio.bindings.takeoff = "missing_effect";
    expect(() => parseRunnerRuntimeManifest(unresolved)).toThrow(
      "audio.bindings.takeoff references unknown effect missing_effect",
    );

    const unused = validRunnerManifest();
    const unusedAudio = unused.audio as { effects: Record<string, unknown>[] };
    unusedAudio.effects.push({
      effect_id: "unused_effect",
      display_name: "Unused Effect",
      realization: {
        kind: "oscillator_sweep_v1",
        waveform: "sine",
        start_frequency_hz: 220,
        end_frequency_hz: 220,
        duration_milliseconds: 100,
        gain: 0.1,
        strength_pitch_multiplier: 0,
      },
    });
    expect(() => parseRunnerRuntimeManifest(unused)).toThrow(
      "audio effect unused_effect is not bound to an event",
    );
  });

  test("refuses a hazard naming an unknown prop or standing over a pit", () => {
    const unknown = validRunnerManifest();
    const segments = unknown.segments as { chunks: Record<string, unknown>[] };
    segments.chunks[0].hazards = [{ prop_id: "phantom", column: 6, anchor: "surface" }];
    expect(() => parseRunnerRuntimeManifest(unknown)).toThrow("unknown prop phantom");

    const pit = validRunnerManifest();
    const pitSegments = pit.segments as { chunks: Record<string, unknown>[] };
    pitSegments.chunks[0].occupancy = [
      "000000000000",
      "000000000000",
      "000000000000",
      "000000000000",
      "000000000000",
      "111111011111",
      "111111011111",
      "111111011111",
    ];
    expect(() => parseRunnerRuntimeManifest(pit)).toThrow("over a pit");
  });

  test("refuses a pickup inside solid terrain or naming an unknown item", () => {
    const solid = validRunnerManifest();
    const segments = solid.segments as { chunks: Record<string, unknown>[] };
    segments.chunks[0].pickups = [{ item_id: "sunleaf_token", column: 6, row: 6 }];
    expect(() => parseRunnerRuntimeManifest(solid)).toThrow("inside solid terrain");

    const unknown = validRunnerManifest();
    const unknownSegments = unknown.segments as { chunks: Record<string, unknown>[] };
    unknownSegments.chunks[0].pickups = [{ item_id: "phantom", column: 6, row: 2 }];
    expect(() => parseRunnerRuntimeManifest(unknown)).toThrow("unknown item phantom");
  });

  test("refuses malformed occupancy", () => {
    const ragged = validRunnerManifest();
    const segments = ragged.segments as { chunks: Record<string, unknown>[] };
    const occupancy = (segments.chunks[0].occupancy as string[]).slice();
    occupancy[3] = "0000";
    segments.chunks[0].occupancy = occupancy;
    expect(() => parseRunnerRuntimeManifest(ragged)).toThrow("string of 0 and 1");

    const alien = validRunnerManifest();
    const alienSegments = alien.segments as { chunks: Record<string, unknown>[] };
    const alienRows = (alienSegments.chunks[0].occupancy as string[]).slice();
    alienRows[5] = "1111112x1111";
    alienSegments.chunks[0].occupancy = alienRows;
    expect(() => parseRunnerRuntimeManifest(alien)).toThrow("string of 0 and 1");

    const shallow = validRunnerManifest();
    const shallowSegments = shallow.segments as { chunks: Record<string, unknown>[] };
    shallowSegments.chunks[0].occupancy = ["000000000000", "111111111111"];
    expect(() => parseRunnerRuntimeManifest(shallow)).toThrow("exactly 8 rows");
  });

  test("refuses an avatar missing a required state or misdeclaring playback", () => {
    const missing = validRunnerManifest();
    const avatar = missing.avatar as { motions: Record<string, unknown>[] };
    avatar.motions = avatar.motions.filter((entry) => entry.state !== "death");
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow("missing the death state");

    const looped = validRunnerManifest();
    const loopedAvatar = looped.avatar as { motions: Record<string, unknown>[] };
    loopedAvatar.motions = [
      motion("run", "loop"),
      motion("jump", "loop"),
      motion("slide", "once"),
      motion("death", "once"),
    ];
    expect(() => parseRunnerRuntimeManifest(looped)).toThrow("state jump must play once");
  });

  test("refuses a canonical frame outside its atlas and duplicate ids", () => {
    const outside = validRunnerManifest();
    const avatar = outside.avatar as { motions: Record<string, unknown>[] };
    avatar.motions[0] = { ...motion("run", "loop"), canonical_frame_indices: [0, 4] };
    expect(() => parseRunnerRuntimeManifest(outside)).toThrow("outside its 4-column atlas");

    const duplicate = validRunnerManifest();
    const layers = duplicate.layers as Record<string, unknown>[];
    layers.push({ ...layers[0] });
    expect(() => parseRunnerRuntimeManifest(duplicate)).toThrow("layer ids must be unique");
  });

  test("refuses a walk surface row outside the grid and a malformed digest", () => {
    const outside = validRunnerManifest();
    (outside.segments as Record<string, unknown>).walk_surface_row = 8;
    expect(() => parseRunnerRuntimeManifest(outside)).toThrow("walk_surface_row");

    const digest = validRunnerManifest();
    digest.package_sha256 = "not-a-digest";
    expect(() => parseRunnerRuntimeManifest(digest)).toThrow("64 lowercase hex characters");
  });
});

describe("bottomContiguousSurfaceRow", () => {
  const occupancy = [
    "0000",
    "1000",
    "1010",
    "1011",
  ];

  test("finds the top of a bottom-contiguous stack", () => {
    expect(bottomContiguousSurfaceRow(occupancy, 0)).toBe(1);
    expect(bottomContiguousSurfaceRow(occupancy, 3)).toBe(3);
  });

  test("treats an unsupported bottom row as a pit even under floating cells", () => {
    expect(bottomContiguousSurfaceRow(occupancy, 1)).toBeNull();
    // Column 2 has a floating "1" at row 2 above a solid bottom: contiguity
    // starts at the bottom, so the stack is rows 2..3.
    expect(bottomContiguousSurfaceRow(occupancy, 2)).toBe(2);
  });
});

describe("the verb obligations", () => {
  test("a duck profile obligates a slide strip", () => {
    const document = validRunnerManifest();
    const avatar = document.avatar as { motions: Record<string, unknown>[] };
    avatar.motions = avatar.motions.filter((entry) => entry.state !== "slide");
    expect(() => parseRunnerRuntimeManifest(document)).toThrow("missing the slide state");
  });

  test("a duckless manifest owes no slide", () => {
    const document = validRunnerManifest();
    (document.gameplay as Record<string, unknown>).duck_profile = null;
    (document.gameplay as Record<string, unknown>).ducked_height_fraction = null;
    const avatar = document.avatar as { motions: Record<string, unknown>[] };
    avatar.motions = avatar.motions.filter((entry) => entry.state !== "slide");
    const manifest = parseRunnerRuntimeManifest(document);
    expect(manifest.gameplay.duckProfile).toBeNull();
    expect(manifest.gameplay.duckedHeightFraction).toBeNull();
  });

  test("an overhead hazard without a duck profile is refused", () => {
    const document = validRunnerManifest();
    (document.gameplay as Record<string, unknown>).duck_profile = null;
    (document.gameplay as Record<string, unknown>).ducked_height_fraction = null;
    const segments = document.segments as { chunks: Record<string, unknown>[] };
    segments.chunks[0].hazards = [
      { prop_id: "toppled_cart", column: 6, anchor: "overhead", clearance_rows: 1.6 },
    ];
    expect(() => parseRunnerRuntimeManifest(document)).toThrow("no duck_profile");
  });

  test("an overhead hazard needs clearance and a surface one refuses it", () => {
    const missing = validRunnerManifest();
    const segments = missing.segments as { chunks: Record<string, unknown>[] };
    segments.chunks[0].hazards = [{ prop_id: "toppled_cart", column: 6, anchor: "overhead" }];
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow("clearance_rows");

    const surface = validRunnerManifest();
    const surfaceSegments = surface.segments as { chunks: Record<string, unknown>[] };
    surfaceSegments.chunks[0].hazards = [
      { prop_id: "toppled_cart", column: 6, anchor: "surface", clearance_rows: 1.6 },
    ];
    expect(() => parseRunnerRuntimeManifest(surface)).toThrow("declares clearance");
  });

  test("the runtime's motion order mirrors the generator's declaration", async () => {
    const { RUNNER_MOTION_STATES, RUNNER_LOOPING_MOTION_STATES } = await import("./contract");
    expect(RUNNER_MOTION_STATES).toEqual(["run", "jump", "slide", "fly", "hurt", "death"]);
    // Both sustained conditions loop; every other state is an event.
    expect(RUNNER_LOOPING_MOTION_STATES).toEqual(["run", "fly"]);
  });
});

describe("the vitals and consequence contract", () => {
  test("parses every damage source and the gauge it spends", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    expect(manifest.gameplay.collisionBox).toBe("torso_v1");
    expect(manifest.gameplay.consequences).toEqual({
      hazard: "drain_v1",
      pit: "drain_and_recover_v1",
      crush: "end_run_v1",
      // A package with no encounter has no shot to answer for.
      shot: null,
    });
    expect(manifest.gameplay.vitals).toEqual({
      profile: "three_point_v1",
      maxPoints: 3,
      hurtRepresentation: "blink_v1",
    });
  });

  test("refuses a draining consequence with no gauge to spend from", () => {
    const document = validRunnerManifest();
    (document.gameplay as Record<string, unknown>).vitals = null;
    expect(() => parseRunnerRuntimeManifest(document)).toThrow(
      "gameplay.vitals is required when a consequence drains it",
    );
  });

  test("refuses a gauge no consequence can drain", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.consequences = { hazard: "end_run_v1", pit: "end_run_v1", crush: "end_run_v1" };
    expect(() => parseRunnerRuntimeManifest(document)).toThrow(
      "gameplay.vitals is declared but no consequence can drain it",
    );
  });

  test("accepts a one-hit-kill package: every source terminal, no gauge", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.consequences = { hazard: "end_run_v1", pit: "end_run_v1", crush: "end_run_v1" };
    gameplay.vitals = null;
    expect(parseRunnerRuntimeManifest(document).gameplay.vitals).toBe(null);
  });

  test("refuses a missing damage source rather than defaulting it", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.consequences = { hazard: "drain_v1", pit: "drain_v1" };
    expect(() => parseRunnerRuntimeManifest(document)).toThrow("gameplay.consequences.crush");
  });

  test("refuses an unknown consequence name", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.consequences = { hazard: "shrug_it_off_v1", pit: "drain_v1", crush: "end_run_v1" };
    expect(() => parseRunnerRuntimeManifest(document)).toThrow("gameplay.consequences.hazard");
  });
});

describe("the hurt obligation", () => {
  test("a drawn representation requires the strip it plays", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.vitals = { profile: "three_point_v1", max_points: 3, hurt_representation: "drawn_v1" };
    expect(() => parseRunnerRuntimeManifest(document)).toThrow(
      "avatar.motions is missing the hurt state",
    );
  });

  test("the blink representation refuses a strip nothing would play", () => {
    const document = validRunnerManifest();
    const avatar = document.avatar as Record<string, unknown>;
    avatar.motions = [...(avatar.motions as unknown[]), motion("hurt", "once")];
    expect(() => parseRunnerRuntimeManifest(document)).toThrow(
      'gameplay.vitals.hurt_representation is not "drawn_v1"',
    );
  });

  test("a drawn representation with its strip parses", () => {
    const document = validRunnerManifest();
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.vitals = { profile: "three_point_v1", max_points: 3, hurt_representation: "drawn_v1" };
    const avatar = document.avatar as Record<string, unknown>;
    avatar.motions = [...(avatar.motions as unknown[]), motion("hurt", "once")];
    const parsed = parseRunnerRuntimeManifest(document);
    expect(parsed.avatar.motions.map((entry) => entry.state)).toContain("hurt");
  });
});

describe("the fx block", () => {
  test("is absent by default and parsed when published", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    expect(parseRunnerRuntimeManifest(validRunnerManifest()).fx).toBeNull();
    const document = validRunnerManifest();
    document.fx = fxBlockFixture();
    const manifest = parseRunnerRuntimeManifest(document);
    expect(manifest.fx?.cutIn?.frame.asset).toBe("fx/cut_in/frame.png");
    expect(manifest.fx?.moments[0]?.moment).toBe("stage_start");
  });

  test("a broken fx block refuses the whole manifest", async () => {
    const { fxBlockFixture } = await import("@/lib/manifest/fx");
    const document = validRunnerManifest();
    const fx = fxBlockFixture();
    (fx.moments as Record<string, unknown>[])[0].choreography = "slam_v1";
    document.fx = fx;
    expect(() => parseRunnerRuntimeManifest(document)).toThrow("choreography must be one of");
  });

  test("the previous runtime identity is refused", () => {
    const document = validRunnerManifest();
    document.kind = "sideview-runner-runtime-v8";
    document.schema_version = 8;
    expect(() => parseRunnerRuntimeManifest(document)).toThrow(RUNNER_REFUSAL);
  });
});

describe("the encounter contract", () => {
  test("parses the fight, its boss, its projectiles and its arena", () => {
    const manifest = parseRunnerRuntimeManifest(runnerManifestFixture({ encounter: true }));

    const encounter = manifest.gameplay.encounter;
    expect(encounter).not.toBeNull();
    expect(encounter?.bossId).toBe("thicket_router");
    expect(encounter?.locomotion).toBe("thrust_v1");
    expect(manifest.bosses.map((entry) => entry.bossId)).toEqual(["thicket_router"]);
    expect(manifest.projectiles.map((entry) => entry.projectileId)).toEqual([
      "thorn_burst",
      "spark_pin",
    ]);
    expect(
      manifest.segments.chunks.filter((entry) => entry.role === "arena").map((c) => c.segmentId),
    ).toEqual(["boss_arena"]);
    expect(manifest.gameplay.consequences.shot).toBe("drain_v1");
    expect(Object.isFrozen(encounter)).toBe(true);
  });

  test("a package that fights nothing publishes empty catalogs and a null block", () => {
    const manifest = parseRunnerRuntimeManifest(runnerManifestFixture());

    expect(manifest.gameplay.encounter).toBeNull();
    expect(manifest.bosses).toEqual([]);
    expect(manifest.projectiles).toEqual([]);
    expect(manifest.gameplay.consequences.shot).toBeNull();
  });

  test("an ordinary chunk cannot be the arena a fight is fought over", () => {
    const document = runnerManifestFixture({ encounter: true });
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.encounter = {
      ...(gameplay.encounter as Record<string, unknown>),
      arena_segment_id: "meadow_flat",
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("names no arena chunk");
  });

  test("an arena carrying a hazard is refused", () => {
    const document = runnerManifestFixture({ encounter: true });
    const segments = document.segments as Record<string, unknown>;
    const chunks = segments.chunks as Record<string, unknown>[];
    chunks[chunks.length - 1] = {
      ...runnerArenaChunkFixture(),
      hazards: [
        { prop_id: "toppled_cart", column: 6, anchor: "surface", clearance_rows: null },
      ],
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("carries no hazards");
  });

  test("an encounter naming an unpublished boss or projectile is refused", () => {
    for (const [field, message] of [
      ["boss_id", "names no published boss"],
      ["boss_projectile_id", "names no published projectile"],
    ] as const) {
      const document = runnerManifestFixture({ encounter: true });
      const gameplay = document.gameplay as Record<string, unknown>;
      gameplay.encounter = {
        ...(gameplay.encounter as Record<string, unknown>),
        [field]: "absent",
      };
      expect(() => parseRunnerRuntimeManifest(document)).toThrow(message);
    }
  });

  test("one projectile flying both ways is refused", () => {
    const document = runnerManifestFixture({ encounter: true });
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.encounter = {
      ...(gameplay.encounter as Record<string, unknown>),
      player_projectile_id: "thorn_burst",
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("one projectile");
  });

  test("a salvo that cannot leave the avatar a lane is refused", () => {
    const document = runnerManifestFixture({ encounter: true });
    const gameplay = document.gameplay as Record<string, unknown>;
    gameplay.encounter = {
      ...(gameplay.encounter as Record<string, unknown>),
      projectile_height_rows: 1.5,
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("lane");
  });

  test("the fly strip is owed with an encounter and refused without one", () => {
    const missing = runnerManifestFixture({ encounter: true });
    const avatar = missing.avatar as Record<string, unknown>;
    avatar.motions = (avatar.motions as Record<string, unknown>[]).filter(
      (entry) => entry.state !== "fly",
    );
    expect(() => parseRunnerRuntimeManifest(missing)).toThrow("missing the fly state");

    const spare = runnerManifestFixture();
    const plainAvatar = spare.avatar as Record<string, unknown>;
    plainAvatar.motions = [
      ...(plainAvatar.motions as Record<string, unknown>[]),
      { ...runnerMotionFixture("fly", "loop"), atlas: "avatar/fly.png" },
    ];
    expect(() => parseRunnerRuntimeManifest(spare)).toThrow("no encounter");
  });

  test("a shot answer and an encounter each require the other", () => {
    const unanswered = runnerManifestFixture({ encounter: true });
    const gameplay = unanswered.gameplay as Record<string, unknown>;
    gameplay.consequences = {
      ...(gameplay.consequences as Record<string, unknown>),
      shot: null,
    };
    expect(() => parseRunnerRuntimeManifest(unanswered)).toThrow("exactly when an encounter");
  });

  test("a boss owes every state it fights with", () => {
    const document = runnerManifestFixture({ encounter: true });
    const bosses = document.bosses as Record<string, unknown>[];
    bosses[0] = {
      ...runnerBossFixture(),
      motions: (runnerBossFixture().motions as Record<string, unknown>[]).filter(
        (entry) => entry.state !== "death",
      ),
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("declares no death motion");
  });

  test("the boss holds its hover and performs everything else once", () => {
    const document = runnerManifestFixture({ encounter: true });
    const bosses = document.bosses as Record<string, unknown>[];
    bosses[0] = {
      ...runnerBossFixture(),
      motions: [
        { ...runnerMotionFixture("hover", "once"), atlas: "boss/thicket_router/hover.png" },
        { ...runnerMotionFixture("attack", "once"), atlas: "boss/thicket_router/attack.png" },
        { ...runnerMotionFixture("death", "once"), atlas: "boss/thicket_router/death.png" },
      ],
    };

    expect(() => parseRunnerRuntimeManifest(document)).toThrow("must play loop");
  });
});
