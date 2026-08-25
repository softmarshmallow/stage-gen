import { describe, expect, test } from "bun:test";
import {
  horizontalImageRepeats,
  parseCombatTextManifest,
  parseImageRepeatManifest,
  parseScrollingManifestEnvelope,
  resolveCombatTextManifest,
} from "./manifest";

const TAG = "storybook-preview-chroma";

const combatText = (enabled = true) => ({
  schema_version: 1,
  kind: "combat-text-v1",
  enabled,
});

const currentEnvelope = (overrides: Record<string, unknown> = {}) => ({
  schema_version: 7,
  recipe: "scrolling-preview",
  tag: TAG,
  transparency_mode: "chroma",
  artifacts: [],
  canonical_artifacts: [],
  world_spec: {
    path: `world_spec_${TAG}.json`,
    provenance_path: `world_spec_${TAG}.json.meta.json`,
  },
  runtime_assets: [],
  image_repeat: { enabled: false, status: "deferred", artifacts: [] },
  ...overrides,
});

const gameContractProjection = () => {
  const gameId = "storybook-preview";
  const sourceSha256 = "1".repeat(64);
  const canonicalSha256 = "2".repeat(64);
  const path = `game_${TAG}.json`;
  return {
    schema_version: 1,
    kind: "resolved-game-contract-v1",
    resolution_version: "game-contract-library-resolution-v1",
    binding: {
      schema_version: 1,
      kind: "game-contract-binding-v1",
      ref: `library/games/${gameId}/game.toml`,
      source_sha256: sourceSha256,
    },
    game_id: gameId,
    revision: 3,
    projection: "side_view_2d",
    source_sha256: sourceSha256,
    canonical_sha256: canonicalSha256,
    canonical_bytes: 2_048,
    vocabulary_sha256: "3".repeat(64),
    rights_status: "unreviewed",
    recipe_resolution_version: "scrolling-game-contract-resolution-v1",
    art_direction_sha256: "4".repeat(64),
    artifact_ref: `sha256:${canonicalSha256}`,
    artifact_sha256: canonicalSha256,
    artifact_bytes: 2_048,
    path,
    provenance_path: `${path}.meta.json`,
    contract_schema_version: 3,
  };
};

const v7GameManifest = () =>
  currentEnvelope({
    game_contract: gameContractProjection(),
    gameplay: { combat_text: combatText() },
  });

const SOURCE_SHA256 = "a".repeat(64);
const REPEAT_SHA256 = "b".repeat(64);
const PREVIEW_SHA256 = "c".repeat(64);
const CRITERIA_SHA256 = "d".repeat(64);
const REVIEW_SHA256 = "e".repeat(64);
const REVIEW_PROVENANCE_SHA256 = "f".repeat(64);
const PROVIDER_CANDIDATE_SHA256 = "9".repeat(64);

const scaleMetrics = (scale = 1) => ({
  scale,
  boundary_width_px: 2,
  color_mae: 0.01,
  color_p95: 0.02,
  color_max: 0.03,
  gradient_mae: 0.01,
  gradient_p95: 0.02,
  gradient_max: 0.03,
  alpha_mae: 0,
  alpha_p95: 0,
  alpha_max: 0,
  coverage_mismatch_ratio: 0,
  internal_color_p95: 0.02,
  color_limit: 0.12,
  gradient_limit: 0.18,
  alpha_limit: 0.08,
  coverage_limit: 0.1,
});

const passingJoin = (
  name: "wrap" | "source_to_repair" | "repair_to_source",
) => ({
  name,
  verdict: "pass",
  scales: [scaleMetrics(1), scaleMetrics(0.5), scaleMetrics(0.25)],
  failure_codes: [],
});

const imageRepeatArtifact = (
  axis: "x" | "y" = "x",
  decision: "admitted" | "repaired" = "admitted",
) => {
  const sourcePeriod = decision === "admitted" ? 2656 : 2272;
  const repeatSha256 = decision === "admitted" ? SOURCE_SHA256 : REPEAT_SHA256;
  const source = {
    path: "layer_storybook_foreground.png",
    provenance_path: "layer_storybook_foreground.png.meta.json",
    sha256: SOURCE_SHA256,
    bytes: 123_456,
    width: axis === "x" ? sourcePeriod : 800,
    height: axis === "x" ? 800 : sourcePeriod,
  };
  const repeat_unit = {
    path: `layer_storybook_foreground.repeat-${axis}.png`,
    provenance_path: `layer_storybook_foreground.repeat-${axis}.png.meta.json`,
    sha256: repeatSha256,
    bytes: decision === "admitted" ? source.bytes : 130_000,
    width: axis === "x" ? 2656 : 800,
    height: axis === "x" ? 800 : 2656,
  };
  return {
    schema_version: 2,
    kind: "single_axis_repeat_unit",
    axis,
    decision,
    source,
    repeat_unit,
    period_px: 2656,
    cross_axis_extent_px: 800,
    intent: {
      intended_behavior: "one continuous low-salience scrolling layer",
      alpha_policy: "preserve",
      coverage_policy: "sparse_allowed",
      criteria_sha256: CRITERIA_SHA256,
    },
    construction:
      decision === "admitted"
        ? {
            mode: "admitted",
            algorithm: "direct-wrap-admission-v2",
            source_bytes_preserved: true,
          }
        : {
            mode: "repaired",
            algorithm: "endpoint-alpha-reconstructed-anchored-repair-v4",
            context_span_px: 96,
            repair_span_px: 384,
            mask_semantics: "white_edit_black_preserve",
            immutable_regions_reimposed: true,
            endpoint_anchor_algorithm: "linear-light-premultiplied-smoothstep-v1",
            endpoint_anchor_span_px: 8,
            endpoint_anchors_reimposed: true,
            alpha_reconstruction_algorithm: "source-endpoint-alpha-smoothstep-v1",
            alpha_topology_reconstructed: true,
            provider_rgb_interior_preserved: true,
            deterministically_reconstructible: true,
            provider_candidate: {
              path: `layer_storybook_foreground.repeat-${axis}.provider-candidate.png`,
              provenance_path: `layer_storybook_foreground.repeat-${axis}.provider-candidate.png.meta.json`,
              sha256: PROVIDER_CANDIDATE_SHA256,
              bytes: 91_234,
              width: axis === "x" ? 576 : 800,
              height: axis === "x" ? 800 : 576,
            },
            provider: "openrouter",
            model: "openai/gpt-image-2",
            attempts: 1,
          },
    validation: {
      policy: {
        scales: [1, 0.5, 0.25],
        color_mae: 0.12,
        color_p95: 0.25,
        color_max: 0.45,
        gradient_mae: 0.18,
        gradient_p95: 0.35,
        gradient_max: 0.7,
        alpha_mae: 0.08,
        alpha_p95: 0.2,
        alpha_max: 0.5,
        coverage_mismatch_ratio: 0.1,
        internal_baseline_multiplier: 2,
        coverage_alpha_threshold: 0.05,
      },
      deterministic: {
        validator_version: "single-axis-continuity-v2",
        axis,
        verdict: "pass",
        alpha_policy: "preserve",
        coverage_policy: "sparse_allowed",
        source_immutable: true,
        joins:
          decision === "admitted"
            ? [passingJoin("wrap")]
            : [passingJoin("source_to_repair"), passingJoin("repair_to_source")],
        failure_codes: [],
      },
      intended_loop: {
        review_version: "intended-loop-review-v1",
        verdict: "accept",
        confidence: 0.96,
        failure_codes: [],
        evidence: "The exact three-repeat preview reads as one continuous layer.",
        judged_sha256: repeatSha256,
        preview_sha256: PREVIEW_SHA256,
        criteria_sha256: CRITERIA_SHA256,
        reviewer_provider: "openrouter",
        reviewer_model: "openai/gpt-5.4",
        independent: true,
        review_artifact: {
          path: "layer_storybook_foreground.repeat-review.json",
          provenance_path: "layer_storybook_foreground.repeat-review.json.meta.json",
          sha256: REVIEW_SHA256,
          provenance_sha256: REVIEW_PROVENANCE_SHA256,
          bytes: 2048,
        },
      },
      other_axis_status: "not_evaluated",
    },
    lineage:
      decision === "admitted"
        ? {
            mode: "admitted",
            source_sha256: SOURCE_SHA256,
            repeat_unit_sha256: repeatSha256,
          }
        : {
            mode: "repaired",
            source_sha256: SOURCE_SHA256,
            head_context_sha256: "1".repeat(64),
            tail_context_sha256: "2".repeat(64),
            conditioning_sha256: "3".repeat(64),
            mask_sha256: "4".repeat(64),
            provider_candidate_sha256: PROVIDER_CANDIDATE_SHA256,
            raw_repair_sha256: "6".repeat(64),
            provider_interior_sha256: "7".repeat(64),
            alpha_reconstructed_repair_sha256: "8".repeat(64),
            repair_sha256: "5".repeat(64),
            repeat_unit_sha256: repeatSha256,
          },
    rights_status: "unreviewed",
  };
};

const imageRepeatBlock = (...artifacts: unknown[]) => ({
  enabled: true,
  status: "available",
  artifacts,
});

describe("promoted image_repeat manifest", () => {
  test("selects only accepted X artifacts by exact canonical source path", () => {
    const x = imageRepeatArtifact("x", "repaired");
    const yBase = imageRepeatArtifact("y");
    const y = {
      ...yBase,
      source: {
        ...yBase.source,
        path: "layer_storybook_vertical.png",
        provenance_path: "layer_storybook_vertical.png.meta.json",
      },
    };
    const parsed = parseImageRepeatManifest(imageRepeatBlock(x, y));
    expect(parsed.artifacts).toHaveLength(2);
    expect(parsed.artifacts[0]).toEqual({
      schemaVersion: 2,
      kind: "single_axis_repeat_unit",
      axis: "x",
      decision: "repaired",
      sourcePath: "layer_storybook_foreground.png",
      repeatUnitPath: "layer_storybook_foreground.repeat-x.png",
      periodPx: 2656,
    });
    expect(Object.isFrozen(parsed)).toBeTrue();
    expect(Object.isFrozen(parsed.artifacts)).toBeTrue();

    const envelope = currentEnvelope({
      image_repeat: imageRepeatBlock(x, y),
    });
    expect(parseScrollingManifestEnvelope(envelope, TAG)).toBe(envelope);

    const selected = horizontalImageRepeats({
      image_repeat: imageRepeatBlock(x, y),
    });
    expect(selected.size).toBe(1);
    expect(selected.get("layer_storybook_foreground.png")?.decision).toBe(
      "repaired",
    );
    expect(selected.has("./layer_storybook_foreground.png")).toBeFalse();
    expect(selected.has("layer_storybook_vertical.png")).toBeFalse();
  });

  test("requires exact reconstructible repaired-v4 provider evidence", () => {
    const repaired = imageRepeatArtifact("x", "repaired");

    const oldAlgorithm = structuredClone(repaired);
    oldAlgorithm.construction.algorithm = "endpoint-conditioned-anchored-repair-v3";

    const missingCandidate = structuredClone(repaired);
    delete (missingCandidate.construction as Record<string, unknown>)[
      "provider_candidate"
    ];

    const falseAnchor = structuredClone(repaired);
    falseAnchor.construction.endpoint_anchors_reimposed = false;

    const falseAlphaTopology = structuredClone(repaired);
    falseAlphaTopology.construction.alpha_topology_reconstructed = false;

    const wrongAlphaAlgorithm = structuredClone(repaired);
    wrongAlphaAlgorithm.construction.alpha_reconstruction_algorithm =
      "provider-alpha-v0";

    const falseRgbResponsibility = structuredClone(repaired);
    falseRgbResponsibility.construction.provider_rgb_interior_preserved = false;

    const falseReconstruction = structuredClone(repaired);
    falseReconstruction.construction.deterministically_reconstructible = false;

    const wrongAnchorSpan = structuredClone(repaired);
    wrongAnchorSpan.construction.endpoint_anchor_span_px = 9;

    const wrongCandidateGeometry = structuredClone(repaired);
    wrongCandidateGeometry.construction.provider_candidate!.width += 1;

    const wrongCandidateLineage = structuredClone(repaired);
    wrongCandidateLineage.lineage.provider_candidate_sha256 = "0".repeat(64);

    const camelAnchor = structuredClone(repaired);
    (camelAnchor.construction as Record<string, unknown>)["endpointAnchorSpanPx"] =
      camelAnchor.construction.endpoint_anchor_span_px;
    delete (camelAnchor.construction as Record<string, unknown>)[
      "endpoint_anchor_span_px"
    ];

    for (const artifact of [
      oldAlgorithm,
      missingCandidate,
      falseAnchor,
      falseAlphaTopology,
      wrongAlphaAlgorithm,
      falseRgbResponsibility,
      falseReconstruction,
      wrongAnchorSpan,
      wrongCandidateGeometry,
      wrongCandidateLineage,
      camelAnchor,
    ]) {
      expect(() => parseImageRepeatManifest(imageRepeatBlock(artifact))).toThrow();
    }
  });

  test("keeps an absent or explicitly deferred block on the static path", () => {
    expect(horizontalImageRepeats({}).size).toBe(0);
    expect(
      horizontalImageRepeats({
        image_repeat: { enabled: false, status: "deferred", artifacts: [] },
      }).size,
    ).toBe(0);
  });

  test("fails closed for incomplete or unaccepted artifacts", () => {
    const valid = imageRepeatArtifact();
    const invalid = [
      { ...valid, schema_version: 1 },
      { ...valid, kind: "loop" },
      { ...valid, axis: "z" },
      { ...valid, decision: "pending" },
      { ...valid, period_px: 0 },
      { ...valid, source: { ...valid.source, path: "../layer.png" } },
      {
        ...valid,
        validation: {
          ...valid.validation,
          deterministic: { ...valid.validation.deterministic, axis: "y" },
        },
      },
      {
        ...valid,
        validation: {
          ...valid.validation,
          deterministic: { ...valid.validation.deterministic, verdict: "fail" },
        },
      },
      {
        ...valid,
        validation: {
          ...valid.validation,
          intended_loop: {
            ...valid.validation.intended_loop,
            independent: false,
          },
        },
      },
      {
        ...valid,
        validation: {
          ...valid.validation,
          other_axis_status: "pass",
        },
      },
    ];
    for (const artifact of invalid) {
      expect(() => parseImageRepeatManifest(imageRepeatBlock(artifact))).toThrow();
    }
    expect(() =>
      parseScrollingManifestEnvelope(
        currentEnvelope({
          image_repeat: imageRepeatBlock(invalid[0]),
        }),
        TAG,
      ),
    ).toThrow("image_repeat artifact identity is invalid");
  });

  test("requires the complete exact lower_snake_case v2 contract", () => {
    const valid = imageRepeatArtifact();

    const camelArtifact = structuredClone(valid) as Record<string, unknown>;
    camelArtifact["schemaVersion"] = camelArtifact["schema_version"];
    delete camelArtifact["schema_version"];

    const missingArtifactFields = [
      "cross_axis_extent_px",
      "intent",
      "construction",
      "lineage",
      "rights_status",
    ].map((field) => {
      const candidate = structuredClone(valid) as Record<string, unknown>;
      delete candidate[field];
      return candidate;
    });

    const missingSourceProvenance = structuredClone(valid);
    delete (missingSourceProvenance.source as Record<string, unknown>)[
      "provenance_path"
    ];
    const missingPolicy = structuredClone(valid);
    delete (missingPolicy.validation.policy as Record<string, unknown>)["color_mae"];
    const missingDeterministicVersion = structuredClone(valid);
    delete (
      missingDeterministicVersion.validation.deterministic as Record<string, unknown>
    )["validator_version"];
    const missingSemanticDigest = structuredClone(valid);
    delete (
      missingSemanticDigest.validation.intended_loop as Record<string, unknown>
    )["judged_sha256"];
    const missingLineageDigest = structuredClone(valid);
    delete (missingLineageDigest.lineage as Record<string, unknown>)[
      "repeat_unit_sha256"
    ];

    for (const artifact of [
      camelArtifact,
      ...missingArtifactFields,
      missingSourceProvenance,
      missingPolicy,
      missingDeterministicVersion,
      missingSemanticDigest,
      missingLineageDigest,
    ]) {
      expect(() => parseImageRepeatManifest(imageRepeatBlock(artifact))).toThrow(
        "must contain exactly",
      );
    }

    const unknownArtifact = { ...valid, sourcePath: valid.source.path };
    const unknownNested = structuredClone(valid);
    (
      unknownNested.validation.intended_loop as Record<string, unknown>
    )["reviewerModel"] = "openai/gpt-5.4";
    for (const artifact of [unknownArtifact, unknownNested]) {
      expect(() => parseImageRepeatManifest(imageRepeatBlock(artifact))).toThrow(
        "must contain exactly",
      );
    }

    expect(() =>
      parseImageRepeatManifest({
        ...imageRepeatBlock(valid),
        schema_version: 2,
      }),
    ).toThrow("image_repeat must contain exactly enabled, status, artifacts");
  });

  test("validates nested v2 bindings and semantic confidence before projecting", () => {
    const valid = imageRepeatArtifact();
    const noReviewArtifact = structuredClone(valid);
    delete (
      noReviewArtifact.validation.intended_loop as Record<string, unknown>
    )["review_artifact"];
    expect(() =>
      parseImageRepeatManifest(imageRepeatBlock(noReviewArtifact)),
    ).toThrow("must contain exactly");

    const lowConfidence = structuredClone(valid);
    lowConfidence.validation.intended_loop.confidence = 0.89;
    expect(() =>
      parseImageRepeatManifest(imageRepeatBlock(lowConfidence)),
    ).toThrow("not an accepted independent result");

    const wrongCriteria = structuredClone(valid);
    wrongCriteria.validation.intended_loop.criteria_sha256 = "0".repeat(64);
    expect(() => parseImageRepeatManifest(imageRepeatBlock(wrongCriteria))).toThrow(
      "bindings and lineage disagree",
    );

    const wrongGeometry = structuredClone(valid);
    wrongGeometry.repeat_unit.width += 1;
    expect(() => parseImageRepeatManifest(imageRepeatBlock(wrongGeometry))).toThrow(
      "bindings and lineage disagree",
    );

    const nullReviewArtifact = structuredClone(valid);
    (
      nullReviewArtifact.validation.intended_loop as Record<string, unknown>
    )["review_artifact"] = null;
    expect(() =>
      parseImageRepeatManifest(imageRepeatBlock(nullReviewArtifact)),
    ).toThrow("review_artifact must contain exactly");
  });

  test("rejects contradictory envelopes and duplicate X bindings", () => {
    const artifact = imageRepeatArtifact();
    for (const block of [
      { enabled: true, status: "available", artifacts: [] },
      { enabled: false, status: "deferred", artifacts: [artifact] },
      { enabled: true, status: "deferred", artifacts: [artifact] },
    ]) {
      expect(() => parseImageRepeatManifest(block)).toThrow(
        "enabled, status, and artifacts disagree",
      );
    }
    expect(() =>
      parseImageRepeatManifest(imageRepeatBlock(artifact, artifact)),
    ).toThrow("duplicate axis/source bindings");
  });
});

describe("parseScrollingManifestEnvelope", () => {
  test("accepts the complete current core and independently optional current systems", () => {
    const minimal = currentEnvelope();
    const game = v7GameManifest();
    const map = currentEnvelope({
      map_book: {
        schema_version: 2,
        kind: "game-map-book-manifest-v2",
      },
    });

    expect(parseScrollingManifestEnvelope(minimal, TAG)).toBe(minimal);
    expect(parseScrollingManifestEnvelope(game, TAG)).toBe(game);
    expect(parseScrollingManifestEnvelope(map, TAG)).toBe(map);
    expect(
      parseScrollingManifestEnvelope(
        {
          ...game,
          gameplay: {
            combat_text: combatText(false),
            mob_population: {},
          },
        },
        TAG,
      ),
    ).toEqual({
      ...game,
      gameplay: {
        combat_text: combatText(false),
        mob_population: {},
      },
    });
  });

  test("rejects non-object JSON bodies", () => {
    for (const value of [null, [], "manifest", 5]) {
      expect(() => parseScrollingManifestEnvelope(value, TAG)).toThrow(
        "must be a JSON object",
      );
    }
  });

  test.each([undefined, 1, 2, 6, 8, 2.5, "7"])(
    "rejects every non-current schema version: %p",
    (schema_version) => {
      expect(() =>
        parseScrollingManifestEnvelope(
          currentEnvelope({ schema_version }),
          TAG,
        ),
      ).toThrow("schema_version must be 7");
    },
  );

  test("rejects camelCase and unknown top-level keys", () => {
    for (const extra of [
      { schemaVersion: 7 },
      { runtimeAssets: [] },
      { music: {} },
      { future_system: {} },
    ]) {
      expect(() =>
        parseScrollingManifestEnvelope(
          currentEnvelope(extra),
          TAG,
        ),
      ).toThrow("is not supported");
    }
  });

  test("requires every current core key while optional systems remain absent", () => {
    const required = [
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
    for (const key of required) {
      const candidate = currentEnvelope() as Record<string, unknown>;
      delete candidate[key];
      expect(() => parseScrollingManifestEnvelope(candidate, TAG)).toThrow();
    }

    const parsed = parseScrollingManifestEnvelope(currentEnvelope(), TAG);
    for (const optional of [
      "character_profile",
      "game_contract",
      "gameplay",
      "village",
      "soundtrack",
      "map_book",
      "dialogue_characters",
    ]) {
      expect(optional in parsed).toBeFalse();
    }
  });

  test("validates current core value shapes and run-bound world paths", () => {
    for (const overrides of [
      { transparency_mode: "legacy" },
      { artifacts: ["../escape.json"] },
      { artifacts: ["same.json", "same.json"] },
      { canonical_artifacts: ["asset.png"] },
      { runtime_assets: ["character-idle"] },
      { image_repeat: undefined },
      { world_spec: { path: `world_spec_${TAG}.json` } },
      {
        world_spec: {
          path: "world_spec_another-run.json",
          provenance_path: "world_spec_another-run.json.meta.json",
        },
      },
    ]) {
      expect(() => parseScrollingManifestEnvelope(currentEnvelope(overrides), TAG)).toThrow();
    }
  });

  test("accepts game-contract-v3 only and rejects orphan gameplay", () => {
    for (const game_contract of [
      {},
      { contract_schema_version: 1 },
      { contract_schema_version: 2 },
      { contract_schema_version: 4 },
    ]) {
      expect(() =>
        parseScrollingManifestEnvelope(
          {
            ...v7GameManifest(),
            game_contract,
          },
          TAG,
        ),
      ).toThrow("game_contract");
    }
    expect(() =>
      parseScrollingManifestEnvelope(
        currentEnvelope({
          gameplay: { combat_text: combatText() },
        }),
        TAG,
      ),
    ).toThrow("gameplay requires game-contract-v3");
  });

  test("requires the exact current resolved game-contract projection", () => {
    const missing = gameContractProjection() as Record<string, unknown>;
    delete missing["canonical_sha256"];
    const extra = {
      ...gameContractProjection(),
      legacy_contract_version: 2,
    };
    const camel = gameContractProjection() as Record<string, unknown>;
    camel["canonicalSha256"] = camel["canonical_sha256"];
    delete camel["canonical_sha256"];

    for (const game_contract of [missing, extra, camel]) {
      expect(() =>
        parseScrollingManifestEnvelope(
          currentEnvelope({
            game_contract,
            gameplay: { combat_text: combatText() },
          }),
          TAG,
        ),
      ).toThrow("must contain exactly");
    }
  });

  test("validates game identity, binding, lineage, rights, and run-local paths", () => {
    const valid = gameContractProjection();
    const invalid = [
      { ...valid, schema_version: 2 },
      { ...valid, kind: "resolved-game-contract-v2" },
      { ...valid, resolution_version: "game-contract-library-resolution-v0" },
      { ...valid, contract_schema_version: 2 },
      { ...valid, game_id: "BadGame" },
      { ...valid, revision: Number.MAX_SAFE_INTEGER + 1 },
      { ...valid, projection: "top_down_2d" },
      { ...valid, recipe_resolution_version: "scrolling-game-contract-resolution-v0" },
      { ...valid, rights_status: "unknown" },
      {
        ...valid,
        binding: { ...valid.binding, ref: "../another-game/game.toml" },
      },
      {
        ...valid,
        binding: { ...valid.binding, source_sha256: "9".repeat(64) },
      },
      { ...valid, canonical_sha256: "not-a-digest" },
      { ...valid, artifact_sha256: "9".repeat(64) },
      { ...valid, artifact_ref: `sha256:${"9".repeat(64)}` },
      { ...valid, artifact_bytes: valid.canonical_bytes + 1 },
      { ...valid, path: "game_another-run.json" },
      { ...valid, provenance_path: "../game.json.meta.json" },
    ];

    for (const game_contract of invalid) {
      expect(() =>
        parseScrollingManifestEnvelope(
          currentEnvelope({
            game_contract,
            gameplay: { combat_text: combatText() },
          }),
          TAG,
        ),
      ).toThrow("game_contract");
    }

    const portableExternalRoot = {
      ...valid,
      binding: { ...valid.binding, ref: "games/storybook-preview/game.json" },
    };
    expect(
      parseScrollingManifestEnvelope(
        currentEnvelope({
          game_contract: portableExternalRoot,
          gameplay: { combat_text: combatText() },
        }),
        TAG,
      ),
    ).toBeDefined();
  });

  test("requires explicit valid combat text for game-contract-v3", () => {
    const base = v7GameManifest();
    for (const gameplay of [undefined, {}, { combat_text: null }]) {
      const candidate = { ...base, gameplay };
      expect(() => parseScrollingManifestEnvelope(candidate, TAG)).toThrow();
    }

    expect(() =>
      parseScrollingManifestEnvelope(
        {
          ...base,
          gameplay: {
            combat_text: { ...combatText(), enabled: "yes" },
          },
        },
        TAG,
      ),
    ).toThrow("gameplay.combat_text.enabled must be a boolean");
    expect(() =>
      parseScrollingManifestEnvelope(
        {
          ...base,
          gameplay: {
            combat_text: { ...combatText(), colour: "gold" },
          },
        },
        TAG,
      ),
    ).toThrow("must contain exactly");
  });

  test("fails closed for malformed current gameplay and map declarations", () => {
    expect(() =>
      parseScrollingManifestEnvelope(
        {
          ...v7GameManifest(),
          gameplay: { combat_text: combatText(), camera_shake: {} },
        },
        TAG,
      ),
    ).toThrow("requires gameplay.combat_text");

    expect(() =>
      parseScrollingManifestEnvelope(
        currentEnvelope({
          map_book: {
            schema_version: 1,
            kind: "game-map-book-manifest-v1",
          },
        }),
        TAG,
      ),
    ).toThrow("must be game-map-book-manifest-v2");

    expect(() =>
      parseScrollingManifestEnvelope(
        {
          ...v7GameManifest(),
          map_book: {
            schema_version: 3,
            kind: "game-map-book-manifest-v3",
          },
        },
        TAG,
      ),
    ).toThrow("must be game-map-book-manifest-v2");
  });

  test("rejects another recipe or run tag", () => {
    expect(() =>
      parseScrollingManifestEnvelope(
        currentEnvelope({ recipe: "dialogue-scene" }),
        TAG,
      ),
    ).toThrow("recipe must be scrolling-preview");
    expect(() =>
      parseScrollingManifestEnvelope(
        currentEnvelope({ tag: "another-run" }),
        TAG,
      ),
    ).toThrow(`tag must match requested tag ${TAG}`);
  });
});

describe("parseCombatTextManifest", () => {
  test("preserves an explicit default-on or opt-out policy as frozen data", () => {
    for (const enabled of [true, false]) {
      const parsed = parseCombatTextManifest(combatText(enabled));
      expect(parsed as unknown).toEqual(combatText(enabled));
      expect(Object.isFrozen(parsed)).toBeTrue();
    }
  });

  test("rejects wrong identity, missing fields, and non-boolean enabled", () => {
    expect(() => parseCombatTextManifest({ ...combatText(), schema_version: 2 })).toThrow(
      "identity is invalid",
    );
    expect(() => parseCombatTextManifest({ schema_version: 1, kind: "combat-text-v1" })).toThrow(
      "must contain exactly",
    );
    expect(() => parseCombatTextManifest({ ...combatText(), enabled: 1 })).toThrow(
      "must be a boolean",
    );
  });
});

describe("resolveCombatTextManifest", () => {
  test("defaults an absent optional policy to one frozen enabled policy", () => {
    const expected = combatText(true);
    const absentValues = [undefined, null, {}, { gameplay: {} }];

    for (const value of absentValues) {
      const resolved = resolveCombatTextManifest(value);
      expect(resolved as unknown).toEqual(expected);
      expect(Object.isFrozen(resolved)).toBeTrue();
    }
    expect(resolveCombatTextManifest(undefined)).toBe(resolveCombatTextManifest({}));
  });

  test("delegates an authored policy to the strict block parser", () => {
    const resolved = resolveCombatTextManifest({
      gameplay: { combat_text: combatText(false) },
    });

    expect(resolved as unknown).toEqual(combatText(false));
    expect(Object.isFrozen(resolved)).toBeTrue();
    expect(() =>
      resolveCombatTextManifest({
        gameplay: { combat_text: { ...combatText(), enabled: "yes" } },
      }),
    ).toThrow("gameplay.combat_text.enabled must be a boolean");
  });

  test("fails when a present manifest or gameplay container is malformed", () => {
    for (const value of [[], "manifest", 5]) {
      expect(() => resolveCombatTextManifest(value)).toThrow(
        "scrolling-preview manifest must be a JSON object",
      );
    }
    for (const gameplay of [null, [], "gameplay", 5]) {
      expect(() => resolveCombatTextManifest({ gameplay })).toThrow(
        "scrolling-preview manifest gameplay must be an object",
      );
    }
    expect(() =>
      resolveCombatTextManifest({ gameplay: { combat_text: null } }),
    ).toThrow("gameplay.combat_text must contain exactly");
  });
});
