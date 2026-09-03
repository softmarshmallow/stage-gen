/**
 * The infinite-runner runtime contract: `sideview-runner-runtime-v9`.
 *
 * One strict, hand-written validating parser in the house style: unknown
 * kinds are refused with a re-generate hint, shapes are checked field by
 * field against what `prepared_runner.py` publishes, and the parsed document
 * is deep-frozen. The runtime plays a track from this document alone. v9
 * keeps everything v8 proved - the arc and duck arithmetic, the separate
 * `collision_box` / `consequences` / `vitals` trio, the closed ground
 * presentation, generated audio clips, the authored music transitions, the
 * optional `fx` block - and gives every cut-in portrait its judged
 * `placement` inside the frame, so the runtime draws what the reviewer saw.
 */

import { type FxBlock, parseFxBlock } from "@/lib/manifest/fx";
import type { PreparedLayerPresentation } from "@/lib/manifest/prepared-manifest";

export const RUNNER_RUNTIME_KIND = "sideview-runner-runtime-v12";
export const RUNNER_RUNTIME_SCHEMA_VERSION = 12;
export const RUNNER_STRUCTURAL_GROUND_CELL_PX = 64;

/** Every way a run can come to grief, each answered separately by the package. */
/** The sources every run answers, whatever it authors. */
export const RUNNER_TRACK_DAMAGE_SOURCES = ["hazard", "pit", "crush"] as const;
/** Plus `shot`, which only an encounter can deliver and only it may answer. */
export const RUNNER_DAMAGE_SOURCES = [...RUNNER_TRACK_DAMAGE_SOURCES, "shot"] as const;
export type RunnerDamageSource = (typeof RUNNER_DAMAGE_SOURCES)[number];

export const RUNNER_CONSEQUENCES = ["end_run_v1", "drain_v1", "drain_and_recover_v1"] as const;
export type RunnerConsequence = (typeof RUNNER_CONSEQUENCES)[number];

/** The consequences that spend a point, and so oblige a gauge to spend it from. */
export const RUNNER_DRAINING_CONSEQUENCES: ReadonlySet<RunnerConsequence> = new Set([
  "drain_v1",
  "drain_and_recover_v1",
]);

export type RunnerTrackDamageSource = (typeof RUNNER_TRACK_DAMAGE_SOURCES)[number];
export type RunnerConsequences = Readonly<
  Record<RunnerTrackDamageSource, RunnerConsequence> & {
    /** Null exactly when the package declares no encounter. */
    readonly shot: RunnerConsequence | null;
  }
>;

export type RunnerVitals = Readonly<{
  profile: "single_point_v1" | "three_point_v1" | "five_point_v1";
  /** The gauge's ceiling. Published because a bar cannot be drawn without it. */
  maxPoints: number;
  /**
   * How a survivable hit is shown. `blink_v1` is the contracted nonvisual
   * representation the game contract requires when no drawn asset covers the
   * transition; `drawn_v1` obligates a `hurt` motion in the avatar.
   */
  hurtRepresentation: "blink_v1" | "drawn_v1";
}>;

export const RUNNER_REFUSAL =
  "unsupported sideview-runner manifest; regenerate this track with a current stage-gen " +
  "(stage-gen generate --genre runner)";

// Producer bounds mirrored from the authored track contract, so a document a
// current producer could not have written is refused rather than played.
const MIN_SEGMENT_ROWS = 6;
const MAX_SEGMENT_ROWS = 32;
const MIN_SEGMENT_COLUMNS = 8;
const MAX_SEGMENT_COLUMNS = 64;

export type RunnerMotionState = "run" | "jump" | "slide" | "fly" | "hurt" | "death";

/**
 * The canonical motion order, mirroring the generator's RUNNER_MOTION_ORDER.
 * `run`, `jump`, and `death` are owed by every avatar; `slide` is owed
 * exactly when the manifest declares a duck profile, `fly` exactly when it
 * declares an encounter, and `hurt` exactly when it declares
 * `hurt_representation = "drawn_v1"`.
 */
export const RUNNER_MOTION_STATES: readonly RunnerMotionState[] = [
  "run",
  "jump",
  "slide",
  "fly",
  "hurt",
  "death",
];

/**
 * The states drawn as a cycle rather than a one-shot, mirroring the
 * generator's RUNNER_LOOP_STATES: both are sustained conditions rather than
 * events.
 */
export const RUNNER_LOOPING_MOTION_STATES: readonly RunnerMotionState[] = ["run", "fly"];

export const RUNNER_BASE_MOTION_STATES: readonly RunnerMotionState[] = [
  "run",
  "jump",
  "death",
];

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
  /**
   * Whether the offset was measured from the raster or authored as an override.
   * The producer resolves every transparent layer's offset from the pixels it
   * actually received, so an absent source only occurs on the opaque cover.
   */
  readonly verticalOffsetSource: "measured" | "authored" | null;
  readonly image: string;
  readonly width: number;
  readonly height: number;
  readonly presentation: PreparedLayerPresentation;
}

export interface RunnerHazardPlacement {
  readonly propId: string;
  readonly column: number;
  /** `surface` stands on the ground and answers to the jump; `overhead` hangs. */
  readonly anchor: "surface" | "overhead";
  /** Open rows beneath an overhead hazard's underside; null for surface. */
  readonly clearanceRows: number | null;
}

export interface RunnerPickupPlacement {
  readonly itemId: string;
  readonly column: number;
  readonly row: number;
}

export interface RunnerChunk {
  readonly segmentId: string;
  readonly difficulty: number;
  /**
   * What the chunk is for. `arena` is the flat floor an encounter is fought
   * over: never drawn by the difficulty band, streamed on demand while a boss
   * is present. Optional on the wire so a package that fights nothing says
   * nothing.
   */
  readonly role?: "run" | "arena";
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

/** The legacy 47-mask presentation. Occupancy still owns every collision. */
export interface RunnerTerrainAtlasGround {
  readonly mode: "terrain-atlas-3x3-minimal-v1";
  readonly verticalFit: "floor_to_screen_bottom";
  readonly atlas: string;
}

/** One canonical full-grid raster for one authored segment definition. */
export interface RunnerStructuralGroundChunk {
  readonly segmentId: string;
  readonly image: string;
  readonly columns: number;
  readonly rows: number;
}

/**
 * Structural ground is presentation only. Its ordered records are locked
 * one-for-one to `segments.chunks`; the occupancy grids remain the sole
 * support, pit, collision, and streaming authority.
 */
export interface RunnerStructuralGround {
  readonly mode: "runner-structural-ground-v1";
  readonly verticalFit: "floor_to_screen_bottom";
  /** Source pixels per occupancy cell in every canonical segment raster. */
  readonly cellPx: number;
  readonly chunks: readonly RunnerStructuralGroundChunk[];
}

export type RunnerGround = RunnerTerrainAtlasGround | RunnerStructuralGround;

export interface RunnerSoundtrackTrack {
  readonly trackId: string;
  readonly audio: string;
}

export interface RunnerSoundtrack {
  readonly selection: "shuffle";
  readonly tracks: readonly RunnerSoundtrackTrack[];
}

/** The eight player-verb consequences: every package binds all of them. */
export const RUNNER_VERB_AUDIO_EVENTS = [
  "takeoff",
  "air_jump",
  "land",
  "slide",
  "hazard_cleared",
  "collect",
  "hurt",
  "death",
] as const;

/**
 * Every event the audio system posts. `stage_start` is the announcement - the
 * stage-start moment's first frame, once per boot - and the one binding a
 * package may leave silent, because silence is a legitimate announcement.
 */
export const RUNNER_AUDIO_EVENTS = ["stage_start", ...RUNNER_VERB_AUDIO_EVENTS] as const;

export type RunnerAudioEvent = (typeof RUNNER_AUDIO_EVENTS)[number];

export interface RunnerOscillatorSweep {
  readonly kind: "oscillator_sweep_v1";
  readonly waveform: OscillatorType;
  readonly startFrequencyHz: number;
  readonly endFrequencyHz: number;
  readonly durationMilliseconds: number;
  readonly gain: number;
  readonly strengthPitchMultiplier: number;
}

/** A clip the run generated once; the consumer only plays it and mixes it. */
export interface RunnerGeneratedClip {
  readonly kind: "generated_clip_v1";
  /** Run-relative artifact path, always under `audio/`. */
  readonly clip: string;
  readonly durationSeconds: number;
  readonly gain: number;
  readonly strengthPitchMultiplier: number;
}

/**
 * A line a cast voice read once - a bark. Played exactly like a clip; the
 * duration is the measured read, published off the admission record, since
 * the route never took one.
 */
export interface RunnerSpokenLine {
  readonly kind: "spoken_line_v1";
  /** Run-relative artifact path, always under `audio/`. */
  readonly clip: string;
  readonly durationSeconds: number;
  readonly gain: number;
  readonly strengthPitchMultiplier: number;
}

export type RunnerEffectRealization =
  | RunnerOscillatorSweep
  | RunnerGeneratedClip
  | RunnerSpokenLine;

/** The realizations the sink decodes from bytes rather than synthesizes. */
export type RunnerClipRealization = RunnerGeneratedClip | RunnerSpokenLine;

export function isClipRealization(
  realization: RunnerEffectRealization,
): realization is RunnerClipRealization {
  return realization.kind === "generated_clip_v1" || realization.kind === "spoken_line_v1";
}

export interface RunnerSoundEffect {
  readonly effectId: string;
  readonly displayName: string;
  readonly realization: RunnerEffectRealization;
}

/** The run edges the soundtrack answers. */
export const RUNNER_MUSIC_EVENTS = ["death", "restart", "hurt"] as const;

export type RunnerMusicEvent = (typeof RUNNER_MUSIC_EVENTS)[number];

/** Fade shapes as Web Audio's ramps define them. */
export const MUSIC_FADE_CURVES = ["linear", "exponential"] as const;

export type MusicFadeCurve = (typeof MUSIC_FADE_CURVES)[number];

export interface MusicDeathTransition {
  readonly action: "stop" | "pause" | "continue";
  readonly fadeSeconds: number;
  readonly curve: MusicFadeCurve;
}

export interface MusicRestartTransition {
  readonly action: "play" | "resume" | "continue";
  readonly fadeSeconds: number;
  readonly curve: MusicFadeCurve;
}

/** Auto-ducking: the music dips under the hurt stinger, holds, and recovers. */
export interface MusicDuck {
  readonly duckGain: number;
  readonly fadeSeconds: number;
  readonly holdSeconds: number;
  readonly recoverySeconds: number;
  readonly curve: MusicFadeCurve;
}

/** What the soundtrack does at the run's edges; the death stinger plays beside it. */
export interface RunnerMusicTransitions {
  readonly death: MusicDeathTransition;
  readonly restart: MusicRestartTransition;
  readonly hurt: MusicDuck | null;
}

export interface RunnerAudio {
  /** Every verb binds an effect; `stage_start` alone may be null. */
  readonly bindings: Readonly<Record<RunnerAudioEvent, string | null>>;
  readonly effects: readonly RunnerSoundEffect[];
  readonly music: RunnerMusicTransitions;
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
    readonly speedProfile: "steady_runner_v1" | "brisk_runner_v1" | "swift_runner_v1";
    readonly jumpProfile: "single_arc_v1" | "double_arc_v1";
    readonly collisionBox: "torso_v1";
    readonly duckProfile: "slide_v1" | null;
    /** What each way of coming to grief costs. Every source is answered. */
    readonly consequences: RunnerConsequences;
    /** The gauge a draining consequence spends; null exactly when none drains. */
    readonly vitals: RunnerVitals | null;
    readonly rampProfile: "gentle_ramp_v1" | "brisk_ramp_v1";
    readonly maxClearGapColumns: number;
    readonly maxRiseTiles: number;
    /** The published arc arithmetic: the same closed forms admission proved. */
    readonly jumpPeakMarginTiles: number;
    readonly airtimeHeadroom: number;
    readonly baseSpeedColumnsPerSecond: number;
    /** The ramp's hard ceiling: spacing proofs were run at this multiplier. */
    readonly maxSpeedMultiplier: number;
    readonly avatarHalfWidthColumns: number;
    readonly hazardColumnInset: number;
    /** The slide's height fraction; null exactly when duckProfile is null. */
    readonly duckedHeightFraction: number | null;
    /** The overhead fit proof's daylight margin; null exactly when duckProfile is. */
    readonly minOverheadClearanceRows: number | null;
    /** The boss fight this run is interrupted by; null when it fights nothing. */
    readonly encounter: RunnerEncounter | null;
  };
  readonly ground: RunnerGround;
  readonly layers: readonly RunnerLayer[];
  readonly segments: RunnerSegments;
  readonly avatar: RunnerAvatar;
  readonly props: readonly RunnerCatalogEntry[];
  readonly items: readonly RunnerCatalogEntry[];
  readonly bosses: readonly RunnerBoss[];
  readonly projectiles: readonly RunnerProjectile[];
  readonly audio: RunnerAudio;
  readonly soundtrack: RunnerSoundtrack | null;
  /** Screen-FX plates and moment bindings; null exactly when the package authors none. */
  readonly fx: FxBlock | null;
}

export type BossMotionState = "hover" | "attack" | "death";

export const RUNNER_BOSS_MOTION_STATES: readonly BossMotionState[] = ["hover", "attack", "death"];
/** The boss holds its hover the way the avatar holds its run. */
export const RUNNER_BOSS_LOOPING_MOTION_STATES: readonly BossMotionState[] = ["hover"];

export interface RunnerBossMotion {
  readonly state: BossMotionState;
  readonly playbackMode: "loop" | "once";
  readonly canonicalFrameIndices: readonly number[];
  readonly framesPerSecond: number;
  readonly anchor: "bottom" | "top";
  readonly atlas: string;
  readonly columns: number;
  readonly rebaseMultiplier: number;
}

export interface RunnerBoss {
  readonly bossId: string;
  readonly displayName: string;
  readonly concept: string;
  readonly calibration: RunnerCalibration;
  readonly motions: readonly RunnerBossMotion[];
}

export interface RunnerProjectile {
  readonly projectileId: string;
  readonly displayName: string;
  readonly silhouette: "radial_v1" | "axial_v1" | "irregular_v1";
  readonly flight: "flat_bolt_v1" | "lobbed_arc_v1" | "drifting_orb_v1";
  readonly impact: "single_target_v1" | "burst_v1" | "piercing_v1";
  readonly image: string;
  /**
   * The measured record, whose extent was taken across rather than up.
   *
   * Every projectile is drawn pointing right, so its travel axis is its width;
   * the record names the axis so a consumer never has to infer it.
   */
  readonly calibration: RunnerCalibration;
  /** How long the object is along that axis, in player heights. */
  readonly lengthUnits: number;
}

/**
 * The published encounter arithmetic.
 *
 * Every number a refusal read offline is here, so the runtime mirrors the
 * proof rather than re-deriving it. Speeds are in the avatar's frame, which is
 * the frame the dodge proof was written in.
 */
export interface RunnerEncounter {
  readonly profile: "barrage_boss_v1";
  readonly locomotion: "thrust_v1";
  readonly intervalColumns: number;
  readonly arenaSegmentId: string;
  readonly bossId: string;
  readonly bossProjectileId: string;
  readonly playerProjectileId: string;
  readonly maxClimbRowsPerSecond: number;
  readonly maxFallRowsPerSecond: number;
  readonly climbAccelerationRowsPerSecondSquared: number;
  readonly firingDistanceColumns: number;
  readonly projectileSpeedColumnsPerSecond: number;
  readonly projectileHeightRows: number;
  readonly salvoShots: number;
  readonly salvoPeriodSeconds: number;
  readonly salvoBudget: number;
  readonly laneMarginRows: number;
  readonly hitsToDefeat: number;
  readonly playerFirePeriodSeconds: number;
  readonly playerShotSpeedColumnsPerSecond: number;
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

function positiveUnit(value: unknown, label: string): number {
  const parsed = positive(value, label);
  if (parsed > 1) throw new Error(`${label} must be a number in (0, 1]`);
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
    verticalOffsetSource:
      raw.vertical_offset_source === null || raw.vertical_offset_source === undefined
        ? null
        : literal(raw.vertical_offset_source, `${label}.vertical_offset_source`, [
            "measured",
            "authored",
          ]),
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
    const anchor = literal(hazard.anchor, `${label}.hazards[${index}].anchor`, [
      "surface",
      "overhead",
    ]);
    let clearanceRows: number | null = null;
    if (anchor === "overhead") {
      clearanceRows = positive(
        hazard.clearance_rows,
        `${label}.hazards[${index}].clearance_rows`,
      );
    } else if (hazard.clearance_rows !== null && hazard.clearance_rows !== undefined) {
      throw new Error(`${label}.hazards[${index}] is surface-anchored yet declares clearance`);
    }
    return Object.freeze({ propId, column, anchor, clearanceRows });
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
  const role =
    raw.role === undefined || raw.role === null
      ? "run"
      : literal(raw.role, `${label}.role`, ["run", "arena"]);
  if (role === "arena") {
    // The generator proved the arena flat and empty offline; the runtime says
    // so again because a manifest is a wire format, and a hazard reaching the
    // fight would sit in the lane the salvo has to leave open.
    if (hazards.length > 0) throw new Error(`${label} is an arena and carries no hazards`);
    if (pickups.length > 0) throw new Error(`${label} is an arena and carries no pickups`);
  }
  return Object.freeze({
    segmentId: text(raw.segment_id, `${label}.segment_id`),
    difficulty: boundedInteger(raw.difficulty, `${label}.difficulty`, 1, 10),
    role,
    occupancy: Object.freeze(occupancy),
    hazards: Object.freeze(hazards),
    pickups: Object.freeze(pickups),
  });
}

function runnerGround(
  raw: Record<string, unknown>,
  chunks: readonly RunnerChunk[],
  rows: number,
): RunnerGround {
  const mode = literal(raw.mode, "ground.mode", [
    "terrain-atlas-3x3-minimal-v1",
    "runner-structural-ground-v1",
  ]);
  const verticalFit = literal(raw.vertical_fit, "ground.vertical_fit", [
    "floor_to_screen_bottom",
  ]);
  if (mode === "terrain-atlas-3x3-minimal-v1") {
    if (raw.cell_px !== undefined || raw.chunks !== undefined) {
      throw new Error("terrain-atlas ground must not declare structural cell_px or chunks");
    }
    return Object.freeze({
      mode,
      verticalFit,
      atlas: text(raw.atlas, "ground.atlas"),
    });
  }

  if (raw.atlas !== undefined) {
    throw new Error("runner-structural-ground-v1 must not declare ground.atlas");
  }
  const cellPx = boundedInteger(raw.cell_px, "ground.cell_px", 1, 512);
  if (cellPx !== RUNNER_STRUCTURAL_GROUND_CELL_PX) {
    throw new Error(
      `ground.cell_px must be exactly ${RUNNER_STRUCTURAL_GROUND_CELL_PX}`,
    );
  }
  const groundChunks = array(raw.chunks, "ground.chunks").map((entry, index) => {
    const rawChunk = record(entry, `ground.chunks[${index}]`);
    const segmentId = text(rawChunk.segment_id, `ground.chunks[${index}].segment_id`);
    const columns = boundedInteger(
      rawChunk.columns,
      `ground.chunks[${index}].columns`,
      MIN_SEGMENT_COLUMNS,
      MAX_SEGMENT_COLUMNS,
    );
    const chunk = chunks[index];
    if (!chunk) {
      throw new Error("ground.chunks must correspond one-for-one with segments.chunks");
    }
    if (segmentId !== chunk.segmentId) {
      throw new Error(
        `ground.chunks[${index}].segment_id must match segments.chunks[${index}].segment_id`,
      );
    }
    if (columns !== chunk.occupancy[0].length) {
      throw new Error(
        `ground.chunks[${index}].columns must match its occupancy width`,
      );
    }
    const imageRows = boundedInteger(
      rawChunk.rows,
      `ground.chunks[${index}].rows`,
      MIN_SEGMENT_ROWS,
      MAX_SEGMENT_ROWS,
    );
    if (imageRows !== rows) {
      throw new Error(`ground.chunks[${index}].rows must match segments.rows`);
    }
    return Object.freeze({
      segmentId,
      image: text(rawChunk.image, `ground.chunks[${index}].image`),
      columns,
      rows: imageRows,
    });
  });
  if (groundChunks.length !== chunks.length) {
    throw new Error("ground.chunks must correspond one-for-one with segments.chunks");
  }
  uniqueIds(groundChunks.map((entry) => entry.segmentId), "ground chunk segment ids");
  return Object.freeze({
    mode,
    verticalFit,
    cellPx,
    chunks: Object.freeze(groundChunks),
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

function bossMotion(value: unknown, label: string): RunnerBossMotion {
  const raw = record(value, label);
  const state = literal(raw.state, `${label}.state`, RUNNER_BOSS_MOTION_STATES);
  const frames = array(raw.canonical_frame_indices, `${label}.canonical_frame_indices`).map(
    (entry, index) => boundedInteger(entry, `${label}.canonical_frame_indices[${index}]`, 0, 63),
  );
  if (frames.length === 0) throw new Error(`${label} names no frames`);
  const columns = boundedInteger(raw.columns, `${label}.columns`, 1, 64);
  for (const frame of frames) {
    if (frame >= columns) {
      throw new Error(`${label} canonical frame ${frame} is outside its ${columns}-column atlas`);
    }
  }
  const playbackMode = literal(raw.playback_mode, `${label}.playback_mode`, ["loop", "once"]);
  const loops = RUNNER_BOSS_LOOPING_MOTION_STATES.includes(state);
  if (loops !== (playbackMode === "loop")) {
    throw new Error(`${label} state ${state} must play ${loops ? "loop" : "once"}`);
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

function boss(value: unknown, label: string): RunnerBoss {
  const raw = record(value, label);
  const motions = array(raw.motions, `${label}.motions`).map((entry, index) =>
    bossMotion(entry, `${label}.motions[${index}]`),
  );
  const declared = new Set(motions.map((entry) => entry.state));
  for (const state of RUNNER_BOSS_MOTION_STATES) {
    if (!declared.has(state)) throw new Error(`${label} declares no ${state} motion`);
  }
  return Object.freeze({
    bossId: text(raw.boss_id, `${label}.boss_id`),
    displayName: text(raw.display_name, `${label}.display_name`),
    concept: text(raw.concept, `${label}.concept`),
    calibration: calibration(raw.calibration, `${label}.calibration`),
    motions: Object.freeze(motions),
  });
}

function projectile(value: unknown, label: string): RunnerProjectile {
  const raw = record(value, label);
  return Object.freeze({
    projectileId: text(raw.projectile_id, `${label}.projectile_id`),
    displayName: text(raw.display_name, `${label}.display_name`),
    silhouette: literal(raw.silhouette, `${label}.silhouette`, [
      "radial_v1",
      "axial_v1",
      "irregular_v1",
    ]),
    flight: literal(raw.flight, `${label}.flight`, [
      "flat_bolt_v1",
      "lobbed_arc_v1",
      "drifting_orb_v1",
    ]),
    impact: literal(raw.impact, `${label}.impact`, [
      "single_target_v1",
      "burst_v1",
      "piercing_v1",
    ]),
    image: text(raw.image, `${label}.image`),
    calibration: calibration(raw.calibration, `${label}.calibration`),
    lengthUnits: positive(raw.length_units, `${label}.length_units`),
  });
}

/**
 * The encounter block, with the obligations the generator proved offline
 * re-stated here.
 *
 * Not belt-and-braces: a manifest is a wire format, and the parser is the only
 * thing standing between a hand-edited document and a fight the runtime cannot
 * play. The lane check is the cheap half of the generator's pigeonhole - if
 * the band cannot hold a salvo and the avatar at once, no placement can save
 * it.
 */
function runnerEncounter(
  value: unknown,
  label: string,
  context: {
    readonly chunks: readonly RunnerChunk[];
    readonly bosses: readonly RunnerBoss[];
    readonly projectiles: readonly RunnerProjectile[];
    readonly walkSurfaceRow: number;
    readonly playerHeightTiles: number;
  },
): RunnerEncounter {
  const raw = record(value, label);
  const arenaSegmentId = text(raw.arena_segment_id, `${label}.arena_segment_id`);
  const arena = context.chunks.find((chunk) => chunk.segmentId === arenaSegmentId);
  if (arena === undefined || arena.role !== "arena") {
    throw new Error(`${label}.arena_segment_id ${arenaSegmentId} names no arena chunk`);
  }
  if (!context.chunks.some((chunk) => chunk.role !== "arena")) {
    throw new Error(`${label} leaves no ordinary chunk for the run between encounters`);
  }
  const bossId = text(raw.boss_id, `${label}.boss_id`);
  if (!context.bosses.some((entry) => entry.bossId === bossId)) {
    throw new Error(`${label}.boss_id ${bossId} names no published boss`);
  }
  const bossProjectileId = text(raw.boss_projectile_id, `${label}.boss_projectile_id`);
  const playerProjectileId = text(raw.player_projectile_id, `${label}.player_projectile_id`);
  for (const [field, id] of [
    ["boss_projectile_id", bossProjectileId],
    ["player_projectile_id", playerProjectileId],
  ] as const) {
    if (!context.projectiles.some((entry) => entry.projectileId === id)) {
      throw new Error(`${label}.${field} ${id} names no published projectile`);
    }
  }
  if (bossProjectileId === playerProjectileId) {
    throw new Error(`${label} fires and is fired at with one projectile`);
  }
  const projectileHeightRows = positive(
    raw.projectile_height_rows,
    `${label}.projectile_height_rows`,
  );
  const salvoShots = boundedInteger(raw.salvo_shots, `${label}.salvo_shots`, 1, 16);
  const laneMarginRows = nonNegative(raw.lane_margin_rows, `${label}.lane_margin_rows`);
  const lane = context.walkSurfaceRow - salvoShots * projectileHeightRows;
  if (lane < context.playerHeightTiles + laneMarginRows) {
    throw new Error(
      `${label} leaves a ${lane.toFixed(2)}-row lane; the avatar needs ` +
        `${(context.playerHeightTiles + laneMarginRows).toFixed(2)}`,
    );
  }
  return Object.freeze({
    profile: literal(raw.profile, `${label}.profile`, ["barrage_boss_v1"]),
    locomotion: literal(raw.locomotion, `${label}.locomotion`, ["thrust_v1"]),
    intervalColumns: boundedInteger(raw.interval_columns, `${label}.interval_columns`, 1, 100_000),
    arenaSegmentId,
    bossId,
    bossProjectileId,
    playerProjectileId,
    maxClimbRowsPerSecond: positive(
      raw.max_climb_rows_per_second,
      `${label}.max_climb_rows_per_second`,
    ),
    maxFallRowsPerSecond: positive(
      raw.max_fall_rows_per_second,
      `${label}.max_fall_rows_per_second`,
    ),
    climbAccelerationRowsPerSecondSquared: positive(
      raw.climb_acceleration_rows_per_second2,
      `${label}.climb_acceleration_rows_per_second2`,
    ),
    firingDistanceColumns: positive(
      raw.firing_distance_columns,
      `${label}.firing_distance_columns`,
    ),
    projectileSpeedColumnsPerSecond: positive(
      raw.projectile_speed_columns_per_second,
      `${label}.projectile_speed_columns_per_second`,
    ),
    projectileHeightRows,
    salvoShots,
    salvoPeriodSeconds: positive(raw.salvo_period_seconds, `${label}.salvo_period_seconds`),
    salvoBudget: boundedInteger(raw.salvo_budget, `${label}.salvo_budget`, 1, 1000),
    laneMarginRows,
    hitsToDefeat: boundedInteger(raw.hits_to_defeat, `${label}.hits_to_defeat`, 1, 100_000),
    playerFirePeriodSeconds: positive(
      raw.player_fire_period_seconds,
      `${label}.player_fire_period_seconds`,
    ),
    playerShotSpeedColumnsPerSecond: positive(
      raw.player_shot_speed_columns_per_second,
      `${label}.player_shot_speed_columns_per_second`,
    ),
  });
}

function motion(value: unknown, label: string): RunnerMotion {
  const raw = record(value, label);
  const state = literal(raw.state, `${label}.state`, RUNNER_MOTION_STATES);
  // The runner's states all play a timeline - all four of them, slide
  // included - so frames_per_second is mandatory here even though the wider
  // authored vocabulary lets a held pose omit it.
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
  const loops = RUNNER_LOOPING_MOTION_STATES.includes(state);
  if (loops !== (playbackMode === "loop")) {
    throw new Error(`${label} state ${state} must play ${loops ? "loop" : "once"}`);
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

const MUSIC_ACTION_PAIRS = {
  stop: "play",
  pause: "resume",
  continue: "continue",
} as const;

const MAX_FADE_SECONDS = 10;

function fadeSeconds(value: unknown, label: string): number {
  const seconds = nonNegative(value, label);
  if (seconds > MAX_FADE_SECONDS) throw new Error(`${label} must be at most 10 seconds`);
  return seconds;
}

function runnerMusic(value: unknown): RunnerMusicTransitions {
  const raw = record(value, "audio.music");
  const death = record(raw.death, "audio.music.death");
  const restart = record(raw.restart, "audio.music.restart");
  const deathAction = literal(death.action, "audio.music.death.action", [
    "stop",
    "pause",
    "continue",
  ]);
  const restartAction = literal(restart.action, "audio.music.restart.action", [
    "play",
    "resume",
    "continue",
  ]);
  const expected = MUSIC_ACTION_PAIRS[deathAction];
  if (restartAction !== expected) {
    throw new Error(
      `audio.music.restart.action must be ${expected} when audio.music.death.action is ${deathAction}`,
    );
  }
  let hurt: MusicDuck | null = null;
  if (raw.hurt !== null && raw.hurt !== undefined) {
    const duck = record(raw.hurt, "audio.music.hurt");
    const duckGain = positive(duck.duck_gain, "audio.music.hurt.duck_gain");
    if (duckGain >= 1) throw new Error("audio.music.hurt.duck_gain must be below 1");
    hurt = Object.freeze({
      duckGain,
      fadeSeconds: fadeSeconds(duck.fade_seconds, "audio.music.hurt.fade_seconds"),
      holdSeconds: fadeSeconds(duck.hold_seconds, "audio.music.hurt.hold_seconds"),
      recoverySeconds: fadeSeconds(duck.recovery_seconds, "audio.music.hurt.recovery_seconds"),
      curve: literal(duck.curve, "audio.music.hurt.curve", MUSIC_FADE_CURVES),
    });
  }
  return Object.freeze({
    death: Object.freeze({
      action: deathAction,
      fadeSeconds: fadeSeconds(death.fade_seconds, "audio.music.death.fade_seconds"),
      curve: literal(death.curve, "audio.music.death.curve", MUSIC_FADE_CURVES),
    }),
    restart: Object.freeze({
      action: restartAction,
      fadeSeconds: fadeSeconds(restart.fade_seconds, "audio.music.restart.fade_seconds"),
      curve: literal(restart.curve, "audio.music.restart.curve", MUSIC_FADE_CURVES),
    }),
    hurt,
  });
}

function runnerAudio(value: unknown): RunnerAudio {
  const raw = record(value, "audio");
  const rawBindings = record(raw.bindings, "audio.bindings");
  const stageStart = rawBindings.stage_start;
  if (stageStart !== undefined && stageStart !== null && typeof stageStart !== "string") {
    throw new Error("audio.bindings.stage_start must be an effect id or null");
  }
  const bindings = Object.freeze({
    ...(Object.fromEntries(
      RUNNER_VERB_AUDIO_EVENTS.map((event) => [
        event,
        text(rawBindings[event], `audio.bindings.${event}`),
      ]),
    ) as Record<(typeof RUNNER_VERB_AUDIO_EVENTS)[number], string>),
    stage_start: stageStart === undefined ? null : stageStart,
  }) as Readonly<Record<RunnerAudioEvent, string | null>>;
  const effects = array(raw.effects, "audio.effects").map((entry, index) => {
    const effect = record(entry, `audio.effects[${index}]`);
    const realization = record(effect.realization, `audio.effects[${index}].realization`);
    const kind = literal(realization.kind, `audio.effects[${index}].realization.kind`, [
      "oscillator_sweep_v1",
      "generated_clip_v1",
      "spoken_line_v1",
    ]);
    if (kind === "generated_clip_v1" || kind === "spoken_line_v1") {
      const clip = text(realization.clip, `audio.effects[${index}].realization.clip`);
      if (!/^audio\/[a-z][a-z0-9_]*\.mp3$/.test(clip)) {
        throw new Error(`audio.effects[${index}].realization.clip must be a run-relative audio/*.mp3`);
      }
      const durationSeconds = positive(
        realization.duration_seconds,
        `audio.effects[${index}].realization.duration_seconds`,
      );
      if (durationSeconds < 0.5 || durationSeconds > 30) {
        throw new Error(`audio.effects[${index}].realization.duration_seconds is out of range`);
      }
      return Object.freeze({
        effectId: text(effect.effect_id, `audio.effects[${index}].effect_id`),
        displayName: text(effect.display_name, `audio.effects[${index}].display_name`),
        realization: Object.freeze({
          kind,
          clip,
          durationSeconds,
          gain: positiveUnit(realization.gain, `audio.effects[${index}].realization.gain`),
          strengthPitchMultiplier: finite(
            realization.strength_pitch_multiplier,
            `audio.effects[${index}].realization.strength_pitch_multiplier`,
          ),
        }),
      });
    }
    const startFrequencyHz = positive(
      realization.start_frequency_hz,
      `audio.effects[${index}].realization.start_frequency_hz`,
    );
    const endFrequencyHz = positive(
      realization.end_frequency_hz,
      `audio.effects[${index}].realization.end_frequency_hz`,
    );
    if (startFrequencyHz < 20 || startFrequencyHz > 20_000) {
      throw new Error(`audio.effects[${index}].realization.start_frequency_hz is out of range`);
    }
    if (endFrequencyHz < 20 || endFrequencyHz > 20_000) {
      throw new Error(`audio.effects[${index}].realization.end_frequency_hz is out of range`);
    }
    return Object.freeze({
      effectId: text(effect.effect_id, `audio.effects[${index}].effect_id`),
      displayName: text(effect.display_name, `audio.effects[${index}].display_name`),
      realization: Object.freeze({
        kind,
        waveform: literal(realization.waveform, `audio.effects[${index}].realization.waveform`, [
          "sine",
          "square",
          "sawtooth",
          "triangle",
        ]),
        startFrequencyHz,
        endFrequencyHz,
        durationMilliseconds: boundedInteger(
          realization.duration_milliseconds,
          `audio.effects[${index}].realization.duration_milliseconds`,
          20,
          2_000,
        ),
        gain: positiveUnit(realization.gain, `audio.effects[${index}].realization.gain`),
        strengthPitchMultiplier: finite(
          realization.strength_pitch_multiplier,
          `audio.effects[${index}].realization.strength_pitch_multiplier`,
        ),
      }),
    });
  });
  if (effects.length === 0) throw new Error("audio.effects must not be empty");
  if (effects.length > 32) throw new Error("audio.effects must contain at most 32 effects");
  uniqueIds(effects.map((effect) => effect.effectId), "audio effect ids");
  const effectIds = new Set(effects.map((effect) => effect.effectId));
  for (const event of RUNNER_AUDIO_EVENTS) {
    const bound = bindings[event];
    // A silent announcement binds nothing; every verb still has to resolve.
    if (bound === null) continue;
    if (!effectIds.has(bound)) {
      throw new Error(`audio.bindings.${event} references unknown effect ${bound}`);
    }
  }
  for (const effectId of effectIds) {
    if (!RUNNER_AUDIO_EVENTS.some((event) => bindings[event] === effectId)) {
      throw new Error(`audio effect ${effectId} is not bound to an event`);
    }
  }
  for (const effect of effects) {
    const multiplier = effect.realization.strengthPitchMultiplier;
    if (multiplier < 0 || multiplier > 2) {
      throw new Error("audio realization strength_pitch_multiplier must be within [0, 2]");
    }
  }
  return Object.freeze({ bindings, effects: Object.freeze(effects), music: runnerMusic(raw.music) });
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
  const playerHeightTiles = positive(rawScale.player_height_tiles, "scale.player_height_tiles");
  const rawGameplay = record(raw.gameplay, "gameplay");

  // Consequences and the gauge are parsed together, because the interesting
  // check is the relationship between them rather than either one alone: a
  // gauge nothing can spend and a drain with nothing to spend are both
  // documents the producer refuses, and reproducing that refusal here is what
  // keeps the two sides one contract rather than two hopeful ones.
  const rawConsequences = record(rawGameplay.consequences, "gameplay.consequences");
  const consequences = Object.freeze({
    ...Object.fromEntries(
      RUNNER_TRACK_DAMAGE_SOURCES.map((source) => [
        source,
        literal(rawConsequences[source], `gameplay.consequences.${source}`, [
          ...RUNNER_CONSEQUENCES,
        ]),
      ]),
    ),
    shot:
      rawConsequences.shot === null || rawConsequences.shot === undefined
        ? null
        : literal(rawConsequences.shot, "gameplay.consequences.shot", [...RUNNER_CONSEQUENCES]),
  }) as RunnerConsequences;
  const drains = RUNNER_DAMAGE_SOURCES.some((source) => {
    const consequence = consequences[source];
    return consequence !== null && RUNNER_DRAINING_CONSEQUENCES.has(consequence);
  });
  const rawVitals =
    rawGameplay.vitals === null || rawGameplay.vitals === undefined
      ? null
      : record(rawGameplay.vitals, "gameplay.vitals");
  if (drains && rawVitals === null) {
    throw new Error("gameplay.vitals is required when a consequence drains it");
  }
  if (!drains && rawVitals !== null) {
    throw new Error("gameplay.vitals is declared but no consequence can drain it");
  }
  const vitals: RunnerVitals | null =
    rawVitals === null
      ? null
      : Object.freeze({
          profile: literal(rawVitals.profile, "gameplay.vitals.profile", [
            "single_point_v1",
            "three_point_v1",
            "five_point_v1",
          ]),
          maxPoints: boundedInteger(rawVitals.max_points, "gameplay.vitals.max_points", 1, 99),
          hurtRepresentation: literal(
            rawVitals.hurt_representation,
            "gameplay.vitals.hurt_representation",
            ["blink_v1", "drawn_v1"],
          ),
        });

  const rawGround = record(raw.ground, "ground");

  const props = array(raw.props, "props").map((entry, index) =>
    catalogEntry(entry, `props[${index}]`, "prop_id"),
  );
  const items = array(raw.items, "items").map((entry, index) =>
    catalogEntry(entry, `items[${index}]`, "item_id"),
  );
  const bosses = array(raw.bosses, "bosses").map((entry, index) =>
    boss(entry, `bosses[${index}]`),
  );
  const projectiles = array(raw.projectiles, "projectiles").map((entry, index) =>
    projectile(entry, `projectiles[${index}]`),
  );
  uniqueIds(props.map((entry) => entry.id), "prop ids");
  uniqueIds(items.map((entry) => entry.id), "item ids");
  uniqueIds(bosses.map((entry) => entry.bossId), "boss ids");
  uniqueIds(projectiles.map((entry) => entry.projectileId), "projectile ids");
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
  const declaresDuck =
    rawGameplay.duck_profile !== null && rawGameplay.duck_profile !== undefined;
  const requiredStates: readonly RunnerMotionState[] = [
    ...RUNNER_BASE_MOTION_STATES,
    ...(declaresDuck ? (["slide"] as const) : []),
    // The drawn hurt representation owes its strip, exactly as a duck profile
    // owes a slide. The blink representation owes none and must not ship one.
    ...(vitals?.hurtRepresentation === "drawn_v1" ? (["hurt"] as const) : []),
  ];
  for (const required of requiredStates) {
    if (!motionStates.includes(required)) {
      throw new Error(`avatar.motions is missing the ${required} state`);
    }
  }
  if (vitals?.hurtRepresentation !== "drawn_v1" && motionStates.includes("hurt")) {
    throw new Error(
      'avatar.motions declares hurt but gameplay.vitals.hurt_representation is not "drawn_v1"',
    );
  }
  // The encounter's own triangles, the same ones the generator refuses: a
  // fight with nothing to wear, a fly strip nothing can trigger, an arena no
  // fight is fought over, and a shot answer no shot can reach.
  const encounter =
    rawGameplay.encounter === null || rawGameplay.encounter === undefined
      ? null
      : runnerEncounter(rawGameplay.encounter, "gameplay.encounter", {
          chunks,
          bosses,
          projectiles,
          walkSurfaceRow,
          playerHeightTiles,
        });
  if (encounter !== null && !motionStates.includes("fly")) {
    throw new Error("gameplay declares an encounter but avatar.motions is missing the fly state");
  }
  if (encounter === null) {
    if (motionStates.includes("fly")) {
      throw new Error("avatar.motions declares fly but gameplay declares no encounter");
    }
    if (bosses.length > 0) throw new Error("bosses are published but no encounter fights one");
    if (projectiles.length > 0) {
      throw new Error("projectiles are published but no encounter fires one");
    }
    if (chunks.some((entry) => entry.role === "arena")) {
      throw new Error("an arena chunk is published but no encounter is fought over it");
    }
  }
  if ((consequences.shot !== null) !== (encounter !== null)) {
    throw new Error(
      "gameplay.consequences.shot is answered exactly when an encounter can fire one",
    );
  }
  const declaresOverhead = chunks.some((entry) =>
    entry.hazards.some((hazard) => hazard.anchor === "overhead"),
  );
  if (declaresOverhead && !declaresDuck) {
    throw new Error("segments hang overhead hazards but gameplay declares no duck_profile");
  }

  const layers = array(raw.layers, "layers").map((entry, index) =>
    layer(entry, `layers[${index}]`),
  );
  if (layers.length === 0) throw new Error("layers must not be empty");
  uniqueIds(layers.map((entry) => entry.layerId), "layer ids");
  for (const [index, entry] of layers.entries()) {
    const opaque = entry.alphaMode === "opaque";
    const canvasCover = entry.verticalAnchor === "canvas_cover";
    if (opaque !== canvasCover) {
      throw new Error(
        `layers[${index}] must pair alpha_mode opaque with vertical_anchor canvas_cover`,
      );
    }
  }
  if (
    layers.filter(
      (entry) => entry.alphaMode === "opaque" && entry.verticalAnchor === "canvas_cover",
    ).length !== 1
  ) {
    throw new Error("layers must declare exactly one opaque canvas_cover");
  }

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

  const fx = raw.fx === null || raw.fx === undefined ? null : parseFxBlock(raw.fx, "fx");

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
      playerHeightTiles,
      tilePx: boundedInteger(rawScale.tile_px, "scale.tile_px", 1, 512),
    }),
    gameplay: Object.freeze({
      speedProfile: literal(rawGameplay.speed_profile, "gameplay.speed_profile", [
        "steady_runner_v1",
        "brisk_runner_v1",
        "swift_runner_v1",
      ]),
      jumpProfile: literal(rawGameplay.jump_profile, "gameplay.jump_profile", [
        "single_arc_v1",
        "double_arc_v1",
      ]),
      collisionBox: literal(rawGameplay.collision_box, "gameplay.collision_box", ["torso_v1"]),
      consequences,
      vitals,
      duckProfile:
        rawGameplay.duck_profile === null || rawGameplay.duck_profile === undefined
          ? null
          : literal(rawGameplay.duck_profile, "gameplay.duck_profile", ["slide_v1"]),
      rampProfile: literal(rawGameplay.ramp_profile, "gameplay.ramp_profile", [
        "gentle_ramp_v1",
        "brisk_ramp_v1",
      ]),
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
      jumpPeakMarginTiles: positive(
        rawGameplay.jump_peak_margin_tiles,
        "gameplay.jump_peak_margin_tiles",
      ),
      airtimeHeadroom: positive(rawGameplay.airtime_headroom, "gameplay.airtime_headroom"),
      baseSpeedColumnsPerSecond: positive(
        rawGameplay.base_speed_columns_per_second,
        "gameplay.base_speed_columns_per_second",
      ),
      maxSpeedMultiplier: positive(
        rawGameplay.max_speed_multiplier,
        "gameplay.max_speed_multiplier",
      ),
      avatarHalfWidthColumns: positive(
        rawGameplay.avatar_half_width_columns,
        "gameplay.avatar_half_width_columns",
      ),
      hazardColumnInset: positive(
        rawGameplay.hazard_column_inset,
        "gameplay.hazard_column_inset",
      ),
      duckedHeightFraction:
        rawGameplay.duck_profile === null || rawGameplay.duck_profile === undefined
          ? null
          : unit(rawGameplay.ducked_height_fraction, "gameplay.ducked_height_fraction"),
      minOverheadClearanceRows:
        rawGameplay.duck_profile === null || rawGameplay.duck_profile === undefined
          ? null
          : positive(
              rawGameplay.min_overhead_clearance_rows,
              "gameplay.min_overhead_clearance_rows",
            ),
      encounter,
    }),
    ground: runnerGround(rawGround, chunks, rows),
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
    bosses: Object.freeze(bosses),
    projectiles: Object.freeze(projectiles),
    audio: runnerAudio(raw.audio),
    soundtrack,
    fx,
  };
  return Object.freeze(manifest);
}
