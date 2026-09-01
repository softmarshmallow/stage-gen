import { describe, expect, test } from "bun:test";
import {
  bottomContiguousSurfaceRow,
  parseRunnerRuntimeManifest,
  RUNNER_REFUSAL,
} from "./contract";
import {
  runnerCalibrationFixture as calibration,
  runnerManifestFixture as validRunnerManifest,
  runnerMotionFixture as motion,
} from "./fixture";

describe("parseRunnerRuntimeManifest", () => {
  test("parses the produced document into frozen runtime shapes", () => {
    const manifest = parseRunnerRuntimeManifest(validRunnerManifest());
    expect(manifest.gameId).toBe("bellweather");
    expect(manifest.trackId).toBe("sunpetal-sprint");
    expect(manifest.scale.tilePx).toBe(64);
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
    const { RUNNER_MOTION_STATES } = await import("./contract");
    expect(RUNNER_MOTION_STATES).toEqual(["run", "jump", "slide", "death"]);
  });
});
