import {
  parseScaleReference,
  REQUIRED_PLAYER_SCALE_REFERENCE_ROLES,
  runtimeRoleOwnsScaleReference,
  type ScaleReference,
} from "./sprite-scale";

const SCROLLING_MANIFEST_SCHEMA_VERSION = 7;

const SCROLLING_MANIFEST_CORE_KEYS = [
  "schema_version",
  "recipe",
  "tag",
  "transparency_mode",
  "artifacts",
  "canonical_artifacts",
  "world_spec",
  "runtime_assets",
  "image_repeat",
] as const;

const SCROLLING_MANIFEST_KEYS = new Set([
  "schema_version",
  "recipe",
  "tag",
  "transparency_mode",
  "artifacts",
  "canonical_artifacts",
  "world_spec",
  "runtime_assets",
  "character_profile",
  "game_contract",
  "gameplay",
  "village",
  "image_repeat",
  "soundtrack",
  "map_book",
  "dialogue_characters",
]);

const GAME_CONTRACT_PROJECTION_KEYS = [
  "schema_version",
  "kind",
  "resolution_version",
  "binding",
  "game_id",
  "revision",
  "projection",
  "source_sha256",
  "canonical_sha256",
  "canonical_bytes",
  "vocabulary_sha256",
  "rights_status",
  "recipe_resolution_version",
  "art_direction_sha256",
  "artifact_ref",
  "artifact_sha256",
  "artifact_bytes",
  "path",
  "provenance_path",
  "contract_schema_version",
] as const;

const GAME_CONTRACT_BINDING_KEYS = [
  "schema_version",
  "kind",
  "ref",
  "source_sha256",
] as const;

const GAME_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const GAME_CONTRACT_SHA256 = /^[a-f0-9]{64}$/;

export type CombatTextManifest = Readonly<{
  schema_version: 1;
  kind: "combat-text-v1";
  enabled: boolean;
}>;

const DEFAULT_COMBAT_TEXT_MANIFEST: CombatTextManifest = Object.freeze({
  schema_version: 1,
  kind: "combat-text-v1",
  enabled: true,
});

export type ImageRepeatAxis = "x" | "y";
export type ImageRepeatDecision = "admitted" | "repaired";

export type ImageRepeatArtifactV2 = Readonly<{
  schemaVersion: 2;
  kind: "single_axis_repeat_unit";
  axis: ImageRepeatAxis;
  decision: ImageRepeatDecision;
  sourcePath: string;
  repeatUnitPath: string;
  periodPx: number;
}>;

export type ImageRepeatManifest = Readonly<{
  enabled: boolean;
  status: "available" | "deferred";
  artifacts: readonly ImageRepeatArtifactV2[];
}>;

const DEFERRED_IMAGE_REPEAT_MANIFEST: ImageRepeatManifest = Object.freeze({
  enabled: false,
  status: "deferred",
  artifacts: Object.freeze([]),
});

const SAFE_ARTIFACT_PATH = /^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$/;
const IMAGE_REPEAT_SHA256 = /^[a-f0-9]{64}$/;
const IMAGE_REPEAT_BACKEND_LABEL =
  /^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})(?:\/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63}))*$/;
const MIN_IMAGE_REPEAT_ACCEPT_CONFIDENCE = 0.9;

const IMAGE_REPEAT_FAILURE_CODES = new Set([
  "visible_boundary_pop",
  "clipped_or_disconnected_form",
  "unintended_transparent_gap",
  "structure_or_horizon_reset",
  "lighting_or_texture_reset",
  "mirror_or_reverse_shortcut",
  "salient_periodic_cadence",
  "orientation_or_gravity_break",
  "alpha_halo_or_matte_contamination",
  "intended_behavior_mismatch",
  "insufficient_evidence",
]);

const IMAGE_REPEAT_ARTIFACT_KEYS = [
  "schema_version",
  "kind",
  "axis",
  "decision",
  "source",
  "repeat_unit",
  "period_px",
  "cross_axis_extent_px",
  "intent",
  "construction",
  "validation",
  "lineage",
  "rights_status",
] as const;

const IMAGE_REPEAT_ASSET_KEYS = [
  "path",
  "provenance_path",
  "sha256",
  "bytes",
  "width",
  "height",
] as const;

const IMAGE_REPEAT_POLICY_KEYS = [
  "scales",
  "color_mae",
  "color_p95",
  "color_max",
  "gradient_mae",
  "gradient_p95",
  "gradient_max",
  "alpha_mae",
  "alpha_p95",
  "alpha_max",
  "coverage_mismatch_ratio",
  "internal_baseline_multiplier",
  "coverage_alpha_threshold",
] as const;

const IMAGE_REPEAT_SCALE_METRIC_KEYS = [
  "scale",
  "boundary_width_px",
  "color_mae",
  "color_p95",
  "color_max",
  "gradient_mae",
  "gradient_p95",
  "gradient_max",
  "alpha_mae",
  "alpha_p95",
  "alpha_max",
  "coverage_mismatch_ratio",
  "internal_color_p95",
  "color_limit",
  "gradient_limit",
  "alpha_limit",
  "coverage_limit",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && keys.every((key) => expected.includes(key));
}

function exactRecord(
  value: unknown,
  label: string,
  keys: readonly string[],
): Record<string, unknown> {
  if (!isRecord(value) || !hasExactKeys(value, keys)) {
    throw new Error(`${label} must contain exactly ${keys.join(", ")}`);
  }
  return value;
}

function boundedNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
  minimumExclusive = false,
): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    (minimumExclusive ? value <= minimum : value < minimum) ||
    value > maximum
  ) {
    throw new Error(`${label} must be a finite number in its declared range`);
  }
  return value;
}

function boundedInteger(
  value: unknown,
  label: string,
  minimum: number,
  maximum = Number.MAX_SAFE_INTEGER,
): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum || (value as number) > maximum) {
    throw new Error(`${label} must be an integer in its declared range`);
  }
  return value as number;
}

function imageRepeatDigest(value: unknown, label: string): string {
  if (typeof value !== "string" || !IMAGE_REPEAT_SHA256.test(value)) {
    throw new Error(`${label} must be one lowercase SHA-256 digest`);
  }
  return value;
}

function imageRepeatBackendLabel(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    value.length > 255 ||
    value !== value.trim() ||
    !IMAGE_REPEAT_BACKEND_LABEL.test(value)
  ) {
    throw new Error(`${label} must be a safe provider or model identifier`);
  }
  return value;
}

function imageRepeatText(value: unknown, label: string, maximum: number): string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > maximum ||
    value !== value.trim()
  ) {
    throw new Error(`${label} must be a trimmed non-empty string`);
  }
  return value;
}

function parseImageRepeatFailureCodes(value: unknown, label: string): readonly string[] {
  if (
    !Array.isArray(value) ||
    value.some((code) => typeof code !== "string" || !IMAGE_REPEAT_FAILURE_CODES.has(code)) ||
    new Set(value).size !== value.length
  ) {
    throw new Error(`${label} must contain unique recognized image-repeat failure codes`);
  }
  return value;
}

function imageRepeatPath(value: unknown, label: string): string {
  if (typeof value !== "string" || !SAFE_ARTIFACT_PATH.test(value)) {
    throw new Error(`${label} must be one safe run-local artifact filename`);
  }
  return value;
}

type ParsedImageRepeatAsset = Readonly<{
  path: string;
  sha256: string;
  bytes: number;
  width: number;
  height: number;
}>;

function parseImageRepeatAsset(value: unknown, label: string): ParsedImageRepeatAsset {
  const asset = exactRecord(value, label, IMAGE_REPEAT_ASSET_KEYS);
  imageRepeatPath(asset["provenance_path"], `${label}.provenance_path`);
  return Object.freeze({
    path: imageRepeatPath(asset["path"], `${label}.path`),
    sha256: imageRepeatDigest(asset["sha256"], `${label}.sha256`),
    bytes: boundedInteger(asset["bytes"], `${label}.bytes`, 1),
    width: boundedInteger(asset["width"], `${label}.width`, 1),
    height: boundedInteger(asset["height"], `${label}.height`, 1),
  });
}

function parseImageRepeatPolicy(value: unknown): void {
  const policy = exactRecord(value, "image_repeat validation.policy", IMAGE_REPEAT_POLICY_KEYS);
  const scales = policy["scales"];
  if (!Array.isArray(scales) || scales.length === 0) {
    throw new Error("image_repeat validation.policy.scales must be a non-empty array");
  }
  const parsedScales = scales.map((scale, index) =>
    boundedNumber(
      scale,
      `image_repeat validation.policy.scales[${index}]`,
      0.01,
      1,
    ),
  );
  if (parsedScales[0] !== 1 || new Set(parsedScales).size !== parsedScales.length) {
    throw new Error("image_repeat validation.policy.scales must start at one and be unique");
  }

  for (const key of [
    "color_mae",
    "color_p95",
    "color_max",
    "gradient_mae",
    "gradient_p95",
    "gradient_max",
    "alpha_mae",
    "alpha_p95",
    "alpha_max",
    "coverage_mismatch_ratio",
    "coverage_alpha_threshold",
  ] as const) {
    boundedNumber(policy[key], `image_repeat validation.policy.${key}`, 0, 1);
  }
  boundedNumber(
    policy["internal_baseline_multiplier"],
    "image_repeat validation.policy.internal_baseline_multiplier",
    1,
    10,
  );
  for (const prefix of ["color", "gradient", "alpha"] as const) {
    const mean = policy[`${prefix}_mae`];
    const percentile = policy[`${prefix}_p95`];
    const maximum = policy[`${prefix}_max`];
    if (
      typeof mean !== "number" ||
      typeof percentile !== "number" ||
      typeof maximum !== "number" ||
      mean > percentile ||
      percentile > maximum
    ) {
      throw new Error(`image_repeat validation.policy ${prefix} thresholds are unordered`);
    }
  }
}

function parseImageRepeatScaleMetrics(value: unknown, label: string): void {
  const metrics = exactRecord(value, label, IMAGE_REPEAT_SCALE_METRIC_KEYS);
  boundedNumber(metrics["scale"], `${label}.scale`, 0, 1, true);
  boundedInteger(metrics["boundary_width_px"], `${label}.boundary_width_px`, 1);
  for (const key of IMAGE_REPEAT_SCALE_METRIC_KEYS.slice(2)) {
    boundedNumber(metrics[key], `${label}.${key}`, 0, 1);
  }
}

type ParsedImageRepeatJoin = Readonly<{
  verdict: "pass" | "reject";
  failureCodes: readonly string[];
}>;

function parseImageRepeatJoin(value: unknown, label: string): ParsedImageRepeatJoin {
  const join = exactRecord(value, label, ["name", "verdict", "scales", "failure_codes"]);
  if (
    join["name"] !== "wrap" &&
    join["name"] !== "source_to_repair" &&
    join["name"] !== "repair_to_source"
  ) {
    throw new Error(`${label}.name is invalid`);
  }
  const verdict = join["verdict"];
  if (verdict !== "pass" && verdict !== "reject") {
    throw new Error(`${label}.verdict is invalid`);
  }
  const scales = join["scales"];
  if (!Array.isArray(scales) || scales.length === 0) {
    throw new Error(`${label}.scales must be a non-empty array`);
  }
  scales.forEach((scale, index) => parseImageRepeatScaleMetrics(scale, `${label}.scales[${index}]`));
  const failureCodes = parseImageRepeatFailureCodes(join["failure_codes"], `${label}.failure_codes`);
  if ((verdict === "pass" && failureCodes.length !== 0) || (verdict === "reject" && failureCodes.length === 0)) {
    throw new Error(`${label} verdict and failure_codes disagree`);
  }
  return Object.freeze({ verdict, failureCodes });
}

type ParsedImageRepeatDeterministic = Readonly<{
  axis: ImageRepeatAxis;
  verdict: "pass" | "reject";
  alphaPolicy: "preserve" | "require_opaque";
  coveragePolicy: "continuous" | "sparse_allowed";
}>;

function parseImageRepeatDeterministic(value: unknown): ParsedImageRepeatDeterministic {
  const report = exactRecord(value, "image_repeat validation.deterministic", [
    "validator_version",
    "axis",
    "verdict",
    "alpha_policy",
    "coverage_policy",
    "source_immutable",
    "joins",
    "failure_codes",
  ]);
  if (report["validator_version"] !== "single-axis-continuity-v2") {
    throw new Error("image_repeat deterministic validator_version is invalid");
  }
  const axis = report["axis"];
  if (axis !== "x" && axis !== "y") {
    throw new Error("image_repeat deterministic axis must be x or y");
  }
  const verdict = report["verdict"];
  if (verdict !== "pass" && verdict !== "reject") {
    throw new Error("image_repeat deterministic verdict is invalid");
  }
  const alphaPolicy = report["alpha_policy"];
  if (alphaPolicy !== "preserve" && alphaPolicy !== "require_opaque") {
    throw new Error("image_repeat deterministic alpha_policy is invalid");
  }
  const coveragePolicy = report["coverage_policy"];
  if (coveragePolicy !== "continuous" && coveragePolicy !== "sparse_allowed") {
    throw new Error("image_repeat deterministic coverage_policy is invalid");
  }
  if (typeof report["source_immutable"] !== "boolean") {
    throw new Error("image_repeat deterministic source_immutable must be a boolean");
  }
  const joins = report["joins"];
  if (!Array.isArray(joins) || joins.length < 1 || joins.length > 2) {
    throw new Error("image_repeat deterministic joins must contain one or two joins");
  }
  const parsedJoins = joins.map((join, index) =>
    parseImageRepeatJoin(join, `image_repeat validation.deterministic.joins[${index}]`),
  );
  const failureCodes = parseImageRepeatFailureCodes(
    report["failure_codes"],
    "image_repeat validation.deterministic.failure_codes",
  );
  const reportedCodes = new Set(failureCodes);
  if (parsedJoins.some((join) => join.failureCodes.some((code) => !reportedCodes.has(code)))) {
    throw new Error("image_repeat deterministic report omits a join failure code");
  }
  if (
    verdict === "pass" &&
    (failureCodes.length !== 0 ||
      report["source_immutable"] !== true ||
      parsedJoins.some((join) => join.verdict !== "pass"))
  ) {
    throw new Error("image_repeat passing deterministic report is internally inconsistent");
  }
  if (verdict === "reject" && failureCodes.length === 0) {
    throw new Error("image_repeat rejected deterministic report requires failure_codes");
  }
  return Object.freeze({ axis, verdict, alphaPolicy, coveragePolicy });
}

type ParsedImageRepeatSemantic = Readonly<{
  verdict: "accept" | "reject" | "uncertain";
  confidence: number;
  judgedSha256: string;
  criteriaSha256: string;
  independent: boolean;
}>;

function parseImageRepeatSemantic(value: unknown): ParsedImageRepeatSemantic {
  const semantic = exactRecord(value, "image_repeat validation.intended_loop", [
    "review_version",
    "verdict",
    "confidence",
    "failure_codes",
    "evidence",
    "judged_sha256",
    "preview_sha256",
    "criteria_sha256",
    "reviewer_provider",
    "reviewer_model",
    "independent",
    "review_artifact",
  ]);
  if (semantic["review_version"] !== "intended-loop-review-v1") {
    throw new Error("image_repeat semantic review_version is invalid");
  }
  const verdict = semantic["verdict"];
  if (verdict !== "accept" && verdict !== "reject" && verdict !== "uncertain") {
    throw new Error("image_repeat semantic verdict is invalid");
  }
  const confidence = boundedNumber(
    semantic["confidence"],
    "image_repeat semantic confidence",
    0,
    1,
  );
  const failureCodes = parseImageRepeatFailureCodes(
    semantic["failure_codes"],
    "image_repeat validation.intended_loop.failure_codes",
  );
  imageRepeatText(semantic["evidence"], "image_repeat semantic evidence", 4096);
  const judgedSha256 = imageRepeatDigest(
    semantic["judged_sha256"],
    "image_repeat semantic judged_sha256",
  );
  imageRepeatDigest(semantic["preview_sha256"], "image_repeat semantic preview_sha256");
  const criteriaSha256 = imageRepeatDigest(
    semantic["criteria_sha256"],
    "image_repeat semantic criteria_sha256",
  );
  imageRepeatBackendLabel(
    semantic["reviewer_provider"],
    "image_repeat semantic reviewer_provider",
  );
  imageRepeatBackendLabel(semantic["reviewer_model"], "image_repeat semantic reviewer_model");
  if (typeof semantic["independent"] !== "boolean") {
    throw new Error("image_repeat semantic independent must be a boolean");
  }
  if ((verdict === "accept" && failureCodes.length !== 0) || (verdict === "reject" && failureCodes.length === 0)) {
    throw new Error("image_repeat semantic verdict and failure_codes disagree");
  }
  if (verdict === "uncertain" && !failureCodes.includes("insufficient_evidence")) {
    throw new Error("image_repeat uncertain semantic review requires insufficient_evidence");
  }
  const binding = exactRecord(
    semantic["review_artifact"],
    "image_repeat semantic review_artifact",
    ["path", "provenance_path", "sha256", "provenance_sha256", "bytes"],
  );
  imageRepeatPath(binding["path"], "image_repeat semantic review_artifact.path");
  imageRepeatPath(
    binding["provenance_path"],
    "image_repeat semantic review_artifact.provenance_path",
  );
  imageRepeatDigest(binding["sha256"], "image_repeat semantic review_artifact.sha256");
  imageRepeatDigest(
    binding["provenance_sha256"],
    "image_repeat semantic review_artifact.provenance_sha256",
  );
  boundedInteger(binding["bytes"], "image_repeat semantic review_artifact.bytes", 1);
  return Object.freeze({
    verdict,
    confidence,
    judgedSha256,
    criteriaSha256,
    independent: semantic["independent"],
  });
}

type ParsedImageRepeatIntent = Readonly<{
  alphaPolicy: "preserve" | "require_opaque";
  coveragePolicy: "continuous" | "sparse_allowed";
  criteriaSha256: string;
}>;

function parseImageRepeatIntent(value: unknown): ParsedImageRepeatIntent {
  const intent = exactRecord(value, "image_repeat intent", [
    "intended_behavior",
    "alpha_policy",
    "coverage_policy",
    "criteria_sha256",
  ]);
  imageRepeatText(intent["intended_behavior"], "image_repeat intent.intended_behavior", 512);
  const alphaPolicy = intent["alpha_policy"];
  if (alphaPolicy !== "preserve" && alphaPolicy !== "require_opaque") {
    throw new Error("image_repeat intent.alpha_policy is invalid");
  }
  const coveragePolicy = intent["coverage_policy"];
  if (coveragePolicy !== "continuous" && coveragePolicy !== "sparse_allowed") {
    throw new Error("image_repeat intent.coverage_policy is invalid");
  }
  return Object.freeze({
    alphaPolicy,
    coveragePolicy,
    criteriaSha256: imageRepeatDigest(
      intent["criteria_sha256"],
      "image_repeat intent.criteria_sha256",
    ),
  });
}

type ParsedImageRepeatConstruction = Readonly<{
  mode: ImageRepeatDecision;
  contextSpanPx: number | null;
  repairSpanPx: number | null;
  providerCandidate: ParsedImageRepeatAsset | null;
}>;

function parseImageRepeatConstruction(value: unknown): ParsedImageRepeatConstruction {
  if (!isRecord(value)) {
    throw new Error("image_repeat construction must be an object");
  }
  if (value["mode"] === "admitted") {
    const construction = exactRecord(value, "image_repeat admitted construction", [
      "mode",
      "algorithm",
      "source_bytes_preserved",
    ]);
    if (
      construction["algorithm"] !== "direct-wrap-admission-v2" ||
      construction["source_bytes_preserved"] !== true
    ) {
      throw new Error("image_repeat admitted construction is invalid");
    }
    return Object.freeze({
      mode: "admitted",
      contextSpanPx: null,
      repairSpanPx: null,
      providerCandidate: null,
    });
  }
  if (value["mode"] === "repaired") {
    const construction = exactRecord(value, "image_repeat repaired construction", [
      "mode",
      "algorithm",
      "context_span_px",
      "repair_span_px",
      "mask_semantics",
      "immutable_regions_reimposed",
      "endpoint_anchor_algorithm",
      "endpoint_anchor_span_px",
      "endpoint_anchors_reimposed",
      "alpha_reconstruction_algorithm",
      "alpha_topology_reconstructed",
      "provider_rgb_interior_preserved",
      "deterministically_reconstructible",
      "provider_candidate",
      "provider",
      "model",
      "attempts",
    ]);
    if (
      construction["algorithm"] !==
        "endpoint-alpha-reconstructed-anchored-repair-v4" ||
      construction["mask_semantics"] !== "white_edit_black_preserve" ||
      construction["immutable_regions_reimposed"] !== true ||
      construction["endpoint_anchor_algorithm"] !==
        "linear-light-premultiplied-smoothstep-v1" ||
      construction["endpoint_anchors_reimposed"] !== true ||
      construction["alpha_reconstruction_algorithm"] !==
        "source-endpoint-alpha-smoothstep-v1" ||
      construction["alpha_topology_reconstructed"] !== true ||
      construction["provider_rgb_interior_preserved"] !== true ||
      construction["deterministically_reconstructible"] !== true
    ) {
      throw new Error("image_repeat repaired construction is invalid");
    }
    const contextSpanPx = boundedInteger(
      construction["context_span_px"],
      "image_repeat context_span_px",
      2,
      1024,
    );
    const repairSpanPx = boundedInteger(
      construction["repair_span_px"],
      "image_repeat repair_span_px",
      4,
      4096,
    );
    const endpointAnchorSpanPx = boundedInteger(
      construction["endpoint_anchor_span_px"],
      "image_repeat endpoint_anchor_span_px",
      1,
      8,
    );
    if (repairSpanPx < endpointAnchorSpanPx * 2 + 2) {
      throw new Error("image_repeat repair span leaves no provider-owned interior");
    }
    const providerCandidate = parseImageRepeatAsset(
      construction["provider_candidate"],
      "image_repeat provider_candidate",
    );
    imageRepeatBackendLabel(construction["provider"], "image_repeat repair provider");
    imageRepeatBackendLabel(construction["model"], "image_repeat repair model");
    boundedInteger(construction["attempts"], "image_repeat repair attempts", 1, 6);
    return Object.freeze({
      mode: "repaired",
      contextSpanPx,
      repairSpanPx,
      providerCandidate,
    });
  }
  throw new Error("image_repeat construction.mode must be admitted or repaired");
}

type ParsedImageRepeatLineage = Readonly<{
  mode: ImageRepeatDecision;
  sourceSha256: string;
  repeatUnitSha256: string;
  providerCandidateSha256: string | null;
}>;

function parseImageRepeatLineage(value: unknown): ParsedImageRepeatLineage {
  if (!isRecord(value)) {
    throw new Error("image_repeat lineage must be an object");
  }
  const mode = value["mode"];
  const keys =
    mode === "admitted"
      ? ["mode", "source_sha256", "repeat_unit_sha256"]
      : [
          "mode",
          "source_sha256",
          "head_context_sha256",
          "tail_context_sha256",
          "conditioning_sha256",
          "mask_sha256",
          "provider_candidate_sha256",
          "raw_repair_sha256",
          "provider_interior_sha256",
          "alpha_reconstructed_repair_sha256",
          "repair_sha256",
          "repeat_unit_sha256",
        ];
  const lineage = exactRecord(value, "image_repeat lineage", keys);
  if (mode !== "admitted" && mode !== "repaired") {
    throw new Error("image_repeat lineage.mode must be admitted or repaired");
  }
  for (const key of keys.slice(1)) {
    imageRepeatDigest(lineage[key], `image_repeat lineage.${key}`);
  }
  return Object.freeze({
    mode,
    sourceSha256: lineage["source_sha256"] as string,
    repeatUnitSha256: lineage["repeat_unit_sha256"] as string,
    providerCandidateSha256:
      mode === "repaired" ? (lineage["provider_candidate_sha256"] as string) : null,
  });
}

function parseImageRepeatArtifact(value: unknown): ImageRepeatArtifactV2 {
  const artifact = exactRecord(value, "image_repeat artifact", IMAGE_REPEAT_ARTIFACT_KEYS);
  if (
    artifact["schema_version"] !== 2 ||
    artifact["kind"] !== "single_axis_repeat_unit"
  ) {
    throw new Error("image_repeat artifact identity is invalid");
  }
  const axis = artifact["axis"];
  if (axis !== "x" && axis !== "y") {
    throw new Error("image_repeat artifact axis must be x or y");
  }
  const decision = artifact["decision"];
  if (decision !== "admitted" && decision !== "repaired") {
    throw new Error("image_repeat artifact decision must be admitted or repaired");
  }
  const periodPx = boundedInteger(artifact["period_px"], "image_repeat artifact period_px", 2);
  const crossAxisExtentPx = boundedInteger(
    artifact["cross_axis_extent_px"],
    "image_repeat artifact cross_axis_extent_px",
    1,
  );
  const source = parseImageRepeatAsset(artifact["source"], "image_repeat source");
  const repeatUnit = parseImageRepeatAsset(
    artifact["repeat_unit"],
    "image_repeat repeat_unit",
  );
  const intent = parseImageRepeatIntent(artifact["intent"]);
  const construction = parseImageRepeatConstruction(artifact["construction"]);
  const validation = exactRecord(artifact["validation"], "image_repeat validation", [
    "policy",
    "deterministic",
    "intended_loop",
    "other_axis_status",
  ]);
  parseImageRepeatPolicy(validation["policy"]);
  const deterministic = parseImageRepeatDeterministic(validation["deterministic"]);
  const intendedLoop = parseImageRepeatSemantic(validation["intended_loop"]);
  if (
    deterministic.axis !== axis ||
    deterministic.verdict !== "pass" ||
    deterministic.alphaPolicy !== intent.alphaPolicy ||
    deterministic.coveragePolicy !== intent.coveragePolicy ||
    intendedLoop.verdict !== "accept" ||
    intendedLoop.confidence < MIN_IMAGE_REPEAT_ACCEPT_CONFIDENCE ||
    intendedLoop.independent !== true ||
    validation["other_axis_status"] !== "not_evaluated"
  ) {
    throw new Error("image_repeat artifact validation is not an accepted independent result");
  }
  const lineage = parseImageRepeatLineage(artifact["lineage"]);
  if (
    artifact["rights_status"] !== "unreviewed" &&
    artifact["rights_status"] !== "restricted" &&
    artifact["rights_status"] !== "redistribution-approved"
  ) {
    throw new Error("image_repeat artifact rights_status is invalid");
  }
  const sourcePeriod = axis === "x" ? source.width : source.height;
  const sourceCross = axis === "x" ? source.height : source.width;
  const repeatPeriod = axis === "x" ? repeatUnit.width : repeatUnit.height;
  const repeatCross = axis === "x" ? repeatUnit.height : repeatUnit.width;
  if (
    construction.mode !== decision ||
    lineage.mode !== decision ||
    lineage.sourceSha256 !== source.sha256 ||
    lineage.repeatUnitSha256 !== repeatUnit.sha256 ||
    repeatPeriod !== periodPx ||
    sourceCross !== crossAxisExtentPx ||
    repeatCross !== crossAxisExtentPx ||
    intendedLoop.judgedSha256 !== repeatUnit.sha256 ||
    intendedLoop.criteriaSha256 !== intent.criteriaSha256
  ) {
    throw new Error("image_repeat artifact bindings and lineage disagree");
  }
  if (
    decision === "admitted" &&
    (repeatPeriod !== sourcePeriod || source.sha256 !== repeatUnit.sha256)
  ) {
    throw new Error("image_repeat admitted artifact must preserve the source exactly");
  }
  if (
    decision === "repaired" &&
    repeatPeriod !== sourcePeriod + (construction.repairSpanPx ?? 0)
  ) {
    throw new Error("image_repeat repaired artifact geometry is invalid");
  }
  if (decision === "repaired") {
    const providerCandidate = construction.providerCandidate;
    const contextSpanPx = construction.contextSpanPx;
    const repairSpanPx = construction.repairSpanPx;
    if (
      providerCandidate === null ||
      contextSpanPx === null ||
      repairSpanPx === null ||
      lineage.providerCandidateSha256 !== providerCandidate.sha256 ||
      (axis === "x"
        ? providerCandidate.width !== contextSpanPx * 2 + repairSpanPx ||
          providerCandidate.height !== crossAxisExtentPx
        : providerCandidate.height !== contextSpanPx * 2 + repairSpanPx ||
          providerCandidate.width !== crossAxisExtentPx) ||
      providerCandidate.path === source.path ||
      providerCandidate.path === repeatUnit.path
    ) {
      throw new Error("image_repeat repaired provider evidence is invalid");
    }
  }

  return Object.freeze({
    schemaVersion: 2,
    kind: "single_axis_repeat_unit",
    axis,
    decision,
    sourcePath: source.path,
    repeatUnitPath: repeatUnit.path,
    periodPx,
  });
}

/**
 * Parse the promoted repeat block and duplicate its success checks at the browser boundary.
 *
 * The producer revalidates the media before publishing this block, but the browser still refuses
 * a forged or incomplete envelope rather than treating it as permission to bypass its static
 * seam adapter.
 */
export function parseImageRepeatManifest(value: unknown): ImageRepeatManifest {
  if (value === undefined) return DEFERRED_IMAGE_REPEAT_MANIFEST;
  const block = exactRecord(value, "image_repeat", ["enabled", "status", "artifacts"]);
  const enabled = block["enabled"];
  const status = block["status"];
  const artifacts = block["artifacts"];
  if (typeof enabled !== "boolean") {
    throw new Error("image_repeat.enabled must be a boolean");
  }
  if (status !== "available" && status !== "deferred") {
    throw new Error("image_repeat.status must be available or deferred");
  }
  if (!Array.isArray(artifacts)) {
    throw new Error("image_repeat.artifacts must be an array");
  }
  if (
    (enabled && (status !== "available" || artifacts.length === 0)) ||
    (!enabled && (status !== "deferred" || artifacts.length !== 0))
  ) {
    throw new Error("image_repeat enabled, status, and artifacts disagree");
  }

  const parsed = artifacts.map(parseImageRepeatArtifact);
  const identities = new Set<string>();
  for (const artifact of parsed) {
    const identity = `${artifact.axis}\0${artifact.sourcePath}`;
    if (identities.has(identity)) {
      throw new Error("image_repeat contains duplicate axis/source bindings");
    }
    identities.add(identity);
  }
  return Object.freeze({
    enabled,
    status,
    artifacts: Object.freeze(parsed),
  });
}

/** Resolve only verified X-axis artifacts, keyed by the exact canonical source path. */
export function horizontalImageRepeats(
  manifest: unknown,
): ReadonlyMap<string, ImageRepeatArtifactV2> {
  if (manifest === null || manifest === undefined) return new Map();
  if (!isRecord(manifest)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }
  const parsed = parseImageRepeatManifest(manifest["image_repeat"]);
  return new Map(
    parsed.artifacts
      .filter((artifact) => artifact.axis === "x")
      .map((artifact) => [artifact.sourcePath, artifact] as const),
  );
}

/** Strict block-local parser for the static floating-combat-text policy. */
export function parseCombatTextManifest(value: unknown): CombatTextManifest {
  if (!isRecord(value) || !hasExactKeys(value, ["schema_version", "kind", "enabled"])) {
    throw new Error("gameplay.combat_text must contain exactly schema_version, kind, enabled");
  }
  if (value["schema_version"] !== 1 || value["kind"] !== "combat-text-v1") {
    throw new Error("gameplay.combat_text identity is invalid");
  }
  if (typeof value["enabled"] !== "boolean") {
    throw new Error("gameplay.combat_text.enabled must be a boolean");
  }
  return Object.freeze({
    schema_version: 1,
    kind: "combat-text-v1",
    enabled: value["enabled"],
  });
}

/** Resolve static floating combat text from a whole manifest when no game declares a policy. */
export function resolveCombatTextManifest(value: unknown): CombatTextManifest {
  if (value === undefined || value === null) {
    return DEFAULT_COMBAT_TEXT_MANIFEST;
  }
  if (!isRecord(value)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }

  const gameplay = value["gameplay"];
  if (gameplay === undefined) {
    return DEFAULT_COMBAT_TEXT_MANIFEST;
  }
  if (!isRecord(gameplay)) {
    throw new Error("scrolling-preview manifest gameplay must be an object");
  }

  const combatText = gameplay["combat_text"];
  if (combatText === undefined) {
    return DEFAULT_COMBAT_TEXT_MANIFEST;
  }
  return parseCombatTextManifest(combatText);
}

function manifestDigest(value: unknown, label: string): string {
  if (typeof value !== "string" || !GAME_CONTRACT_SHA256.test(value)) {
    throw new Error(`${label} must be one lowercase SHA-256 digest`);
  }
  return value;
}

function manifestArtifactPath(value: unknown, label: string): string {
  if (typeof value !== "string" || !SAFE_ARTIFACT_PATH.test(value)) {
    throw new Error(`${label} must be one safe run-local artifact filename`);
  }
  return value;
}

function manifestPortableRef(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.trim() !== value ||
    value.startsWith("/") ||
    value.includes("\\") ||
    value.includes(":") ||
    value.includes("?") ||
    value.includes("#") ||
    value.includes("%") ||
    /[\u0000-\u001f\u007f]/u.test(value) ||
    !value
      .split("/")
      .every((segment) => segment.length > 0 && segment !== "." && segment !== "..")
  ) {
    throw new Error(`${label} must be one portable relative path`);
  }
  return value;
}

function validateScrollingManifestCore(
  value: Record<string, unknown>,
  expectedTag: string,
): void {
  for (const key of SCROLLING_MANIFEST_CORE_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      throw new Error(`scrolling-preview manifest is missing required core key ${key}`);
    }
  }

  if (
    value["transparency_mode"] !== "native" &&
    value["transparency_mode"] !== "ai" &&
    value["transparency_mode"] !== "chroma"
  ) {
    throw new Error(
      "scrolling-preview manifest transparency_mode must be native, ai, or chroma",
    );
  }

  const artifacts = value["artifacts"];
  if (
    !Array.isArray(artifacts) ||
    artifacts.some((path) => typeof path !== "string" || !SAFE_ARTIFACT_PATH.test(path)) ||
    new Set(artifacts).size !== artifacts.length
  ) {
    throw new Error("scrolling-preview manifest artifacts must be unique safe filenames");
  }

  const canonicalArtifacts = value["canonical_artifacts"];
  if (!Array.isArray(canonicalArtifacts) || canonicalArtifacts.some((entry) => !isRecord(entry))) {
    throw new Error("scrolling-preview manifest canonical_artifacts must be an array of objects");
  }

  const worldSpec = exactRecord(value["world_spec"], "world_spec", [
    "path",
    "provenance_path",
  ]);
  const expectedWorldPath = `world_spec_${expectedTag}.json`;
  if (
    manifestArtifactPath(worldSpec["path"], "world_spec.path") !== expectedWorldPath ||
    manifestArtifactPath(worldSpec["provenance_path"], "world_spec.provenance_path") !==
      `${expectedWorldPath}.meta.json`
  ) {
    throw new Error("scrolling-preview manifest world_spec paths do not match the run tag");
  }

  const runtimeAssets = value["runtime_assets"];
  if (!Array.isArray(runtimeAssets) || runtimeAssets.some((entry) => !isRecord(entry))) {
    throw new Error("scrolling-preview manifest runtime_assets must be an array of objects");
  }
  runtimeScaleReferences(value);

  if (value["image_repeat"] === undefined) {
    throw new Error("scrolling-preview manifest image_repeat must be an object");
  }
  parseImageRepeatManifest(value["image_repeat"]);
}

/**
 * Parse the current manifest's measured actor roles and prove the required player closure.
 *
 * Optional current systems remain optional: a run without a village declares no resident roles,
 * and a run without directed mob attack art declares no mob attack role. Once a measured role is
 * declared, however, its exact measurement is part of that runtime asset rather than a fallback
 * hint. The seven player sheets are always part of the current scrolling run.
 */
export function runtimeScaleReferences(
  manifest: Record<string, unknown>,
): ReadonlyMap<string, ScaleReference> {
  const entries = manifest["runtime_assets"];
  if (!Array.isArray(entries) || entries.some((entry) => !isRecord(entry))) {
    throw new Error("scrolling-preview manifest runtime_assets must be an array of objects");
  }

  const seenRoles = new Set<string>();
  const references = new Map<string, ScaleReference>();
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index] as Record<string, unknown>;
    const label = `runtime_assets[${index}]`;
    const role = entry["runtime_slot"];
    if (typeof role !== "string" || role.length === 0) {
      throw new Error(`${label}.runtime_slot must be nonempty text`);
    }
    if (seenRoles.has(role)) {
      throw new Error(`runtime_assets contains duplicate runtime_slot ${role}`);
    }
    seenRoles.add(role);

    const ownsMeasurement = runtimeRoleOwnsScaleReference(role);
    const declared = Object.prototype.hasOwnProperty.call(entry, "scale_reference");
    if (ownsMeasurement && !declared) {
      throw new Error(`runtime asset role ${role} requires scale_reference`);
    }
    if (!declared) continue;
    if (!ownsMeasurement) {
      throw new Error(`runtime asset role ${role} does not own scale_reference`);
    }

    const reference = parseScaleReference(
      entry["scale_reference"],
      `${label}.scale_reference`,
    );
    const layout = entry["layout"];
    if (!isRecord(layout)) {
      throw new Error(`${label}.layout must bind the scale_reference cell`);
    }
    const cellWidth = boundedInteger(
      layout["cell_width"],
      `${label}.layout.cell_width`,
      1,
    );
    const cellHeight = boundedInteger(
      layout["cell_height"],
      `${label}.layout.cell_height`,
      1,
    );
    const columns = boundedInteger(
      layout["columns"],
      `${label}.layout.columns`,
      1,
    );
    if (
      reference.cellWidth !== cellWidth ||
      reference.cellHeight !== cellHeight
    ) {
      throw new Error(`runtime asset role ${role} scale_reference cell does not match layout`);
    }
    if (reference.frameIndex >= columns) {
      throw new Error(`runtime asset role ${role} scale_reference frame is outside layout`);
    }
    const expectedFrameIndex = role.endsWith("-attack") ? 1 : 0;
    if (reference.frameIndex !== expectedFrameIndex) {
      throw new Error(
        `runtime asset role ${role} scale_reference frame must be ${expectedFrameIndex}`,
      );
    }
    references.set(role, reference);
  }

  for (const role of REQUIRED_PLAYER_SCALE_REFERENCE_ROLES) {
    if (!references.has(role)) {
      throw new Error(`current scrolling manifest requires measured runtime role ${role}`);
    }
  }
  return references;
}

function validateGameContractProjection(value: unknown, expectedTag: string): void {
  const projection = exactRecord(
    value,
    "game_contract",
    GAME_CONTRACT_PROJECTION_KEYS,
  );
  const binding = exactRecord(
    projection["binding"],
    "game_contract.binding",
    GAME_CONTRACT_BINDING_KEYS,
  );
  const gameId = projection["game_id"];
  if (
    projection["schema_version"] !== 1 ||
    projection["kind"] !== "resolved-game-contract-v1" ||
    projection["resolution_version"] !== "game-contract-library-resolution-v1" ||
    projection["contract_schema_version"] !== 3 ||
    projection["projection"] !== "side_view_2d" ||
    projection["recipe_resolution_version"] !== "scrolling-game-contract-resolution-v1" ||
    typeof gameId !== "string" ||
    gameId.length > 96 ||
    !GAME_ID.test(gameId)
  ) {
    throw new Error("scrolling-preview manifest game_contract identity is invalid");
  }
  boundedInteger(projection["revision"], "game_contract.revision", 1);

  if (
    binding["schema_version"] !== 1 ||
    binding["kind"] !== "game-contract-binding-v1"
  ) {
    throw new Error("scrolling-preview manifest game_contract binding is invalid");
  }
  manifestPortableRef(binding["ref"], "game_contract.binding.ref");

  const bindingSourceSha256 = manifestDigest(
    binding["source_sha256"],
    "game_contract.binding.source_sha256",
  );
  const sourceSha256 = manifestDigest(
    projection["source_sha256"],
    "game_contract.source_sha256",
  );
  const canonicalSha256 = manifestDigest(
    projection["canonical_sha256"],
    "game_contract.canonical_sha256",
  );
  manifestDigest(projection["vocabulary_sha256"], "game_contract.vocabulary_sha256");
  manifestDigest(projection["art_direction_sha256"], "game_contract.art_direction_sha256");
  const artifactSha256 = manifestDigest(
    projection["artifact_sha256"],
    "game_contract.artifact_sha256",
  );
  const canonicalBytes = boundedInteger(
    projection["canonical_bytes"],
    "game_contract.canonical_bytes",
    1,
  );
  const artifactBytes = boundedInteger(
    projection["artifact_bytes"],
    "game_contract.artifact_bytes",
    1,
  );
  if (
    bindingSourceSha256 !== sourceSha256 ||
    artifactSha256 !== canonicalSha256 ||
    projection["artifact_ref"] !== `sha256:${canonicalSha256}` ||
    artifactBytes !== canonicalBytes
  ) {
    throw new Error("scrolling-preview manifest game_contract lineage bindings disagree");
  }

  if (
    projection["rights_status"] !== "unreviewed" &&
    projection["rights_status"] !== "restricted" &&
    projection["rights_status"] !== "redistribution-approved"
  ) {
    throw new Error("scrolling-preview manifest game_contract rights_status is invalid");
  }

  const expectedPath = `game_${expectedTag}.json`;
  if (
    manifestArtifactPath(projection["path"], "game_contract.path") !== expectedPath ||
    manifestArtifactPath(
      projection["provenance_path"],
      "game_contract.provenance_path",
    ) !== `${expectedPath}.meta.json`
  ) {
    throw new Error("scrolling-preview manifest game_contract paths do not match the run tag");
  }
}

/** Validate the one current lower_snake_case scrolling-preview manifest envelope. */
export function parseScrollingManifestEnvelope(
  value: unknown,
  expectedTag: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }

  for (const key of Object.keys(value)) {
    if (!SCROLLING_MANIFEST_KEYS.has(key)) {
      throw new Error(`scrolling-preview manifest key ${key} is not supported`);
    }
  }
  if (value["schema_version"] !== SCROLLING_MANIFEST_SCHEMA_VERSION) {
    throw new Error("scrolling-preview manifest schema_version must be 7");
  }
  if (value["recipe"] !== "scrolling-preview") {
    throw new Error("scrolling-preview manifest recipe must be scrolling-preview");
  }
  if (value["tag"] !== expectedTag) {
    throw new Error(
      `scrolling-preview manifest tag must match requested tag ${expectedTag}`,
    );
  }
  validateScrollingManifestCore(value, expectedTag);

  const gameContract = value["game_contract"];
  const gameplay = value["gameplay"];
  if (gameContract === undefined) {
    if (gameplay !== undefined) {
      throw new Error("scrolling-preview manifest gameplay requires game-contract-v3");
    }
  } else {
    validateGameContractProjection(gameContract, expectedTag);
    if (
      !isRecord(gameplay) ||
      !Object.keys(gameplay).every((key) =>
        ["combat_text", "mob_population"].includes(key),
      ) ||
      !("combat_text" in gameplay)
    ) {
      throw new Error(
        "scrolling-preview manifest game-contract-v3 requires gameplay.combat_text",
      );
    }
    parseCombatTextManifest(gameplay["combat_text"]);
    if (
      "mob_population" in gameplay &&
      !isRecord(gameplay["mob_population"])
    ) {
      throw new Error(
        "scrolling-preview manifest gameplay.mob_population must be an object",
      );
    }
  }

  const mapBook = value["map_book"];
  if (
    mapBook !== undefined &&
    (!isRecord(mapBook) ||
      mapBook["schema_version"] !== 2 ||
      mapBook["kind"] !== "game-map-book-manifest-v2")
  ) {
    throw new Error(
      "scrolling-preview manifest map_book must be game-map-book-manifest-v2",
    );
  }
  return value;
}
