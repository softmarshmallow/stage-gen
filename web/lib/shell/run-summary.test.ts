import { describe, expect, test } from "bun:test";
import {
  parseRecipeRunSummaryBytes,
  parseRecipeRunSummary,
  parseRecipeRunSummaryText,
  RECIPE_RUN_KIND,
  RECIPE_RUN_SCHEMA_VERSION,
  runCompletionPayload,
} from "./run-summary";

function successfulRun(): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "recipe_run_v3",
    recipe: "scrolling-preview",
    input: {
      prompt: "moonlit ruins",
      transparency_mode: "ai",
      game: { schema_version: 1, kind: "game-contract-binding-v1" },
    },
    tag: "moonlit-ruins-1234abcd-ai",
    run_dir: "moonlit-ruins-1234abcd-ai",
    started_at: "2026-08-25T01:02:03.123456Z",
    ended_at: "2026-08-25T01:02:04.123456Z",
    duration_ms: 1_000,
    ok: true,
    stages: [
      {
        stage: "concept",
        ok: true,
        duration_ms: 1_000,
        artifacts: ["concept.png"],
      },
    ],
  };
}

function failedRun(): Record<string, unknown> {
  return {
    ...successfulRun(),
    ended_at: "2026-08-25T01:02:05Z",
    duration_ms: 2_000,
    ok: false,
    failed_stage: "layers",
    stages: [
      {
        stage: "concept",
        ok: true,
        duration_ms: 1_000,
        artifacts: ["concept.png"],
      },
      {
        stage: "layers",
        ok: false,
        duration_ms: 1_000,
        artifacts: [],
        error: "provider response was invalid",
      },
    ],
  };
}

describe("recipe run summary v3", () => {
  test("parses the exact successful contract and preserves arbitrary JSON input", () => {
    const parsed = parseRecipeRunSummary(successfulRun());

    expect(parsed.schema_version).toBe(RECIPE_RUN_SCHEMA_VERSION);
    expect(parsed.kind).toBe(RECIPE_RUN_KIND);
    expect(parsed.ok).toBeTrue();
    expect(parsed.input).toEqual({
      prompt: "moonlit ruins",
      transparency_mode: "ai",
      game: { schema_version: 1, kind: "game-contract-binding-v1" },
    });
    expect(parsed.stages).toEqual([
      {
        stage: "concept",
        ok: true,
        duration_ms: 1_000,
        artifacts: ["concept.png"],
      },
    ]);
  });

  test("parses one final failed stage bound by failed_stage", () => {
    const parsed = parseRecipeRunSummary(failedRun());
    expect(parsed).toMatchObject({
      ok: false,
      failed_stage: "layers",
      stages: [
        { stage: "concept", ok: true },
        {
          stage: "layers",
          ok: false,
          artifacts: [],
          error: "provider response was invalid",
        },
      ],
    });
    expect(runCompletionPayload(parsed)).toEqual({
      ok: false,
      failed_stage: "layers",
    });
    expect(runCompletionPayload(parseRecipeRunSummary(successfulRun()))).toEqual({
      ok: true,
      failed_stage: null,
    });
  });

  test("rejects unversioned, v2, camelCase, and unknown top-level contracts", () => {
    const missingVersion = successfulRun();
    delete missingVersion["schema_version"];
    expect(() => parseRecipeRunSummary(missingVersion)).toThrow(
      "run_summary.schema_version is required",
    );

    expect(() =>
      parseRecipeRunSummary({
        ...successfulRun(),
        schema_version: 2,
        kind: "dialogue_run_v2",
      }),
    ).toThrow("run_summary.schema_version must equal 3");

    const camel = successfulRun();
    camel["runDir"] = camel["run_dir"];
    delete camel["run_dir"];
    expect(() => parseRecipeRunSummary(camel)).toThrow(
      "run_summary.runDir is not a supported key",
    );

    expect(() => parseRecipeRunSummary({ ...successfulRun(), extra: true })).toThrow(
      "run_summary.extra is not a supported key",
    );
  });

  test("requires only the current input transparency_mode spelling", () => {
    const camel = successfulRun();
    camel["input"] = { prompt: "moonlit ruins", transparencyMode: "ai" };
    expect(() => parseRecipeRunSummary(camel)).toThrow(
      "run_summary.input.transparencyMode is not supported; use transparency_mode",
    );

    const missing = successfulRun();
    missing["input"] = { prompt: "moonlit ruins" };
    expect(() => parseRecipeRunSummary(missing)).toThrow(
      "run_summary.input.transparency_mode must be native, ai, or chroma",
    );

    const invalid = successfulRun();
    invalid["input"] = { prompt: "moonlit ruins", transparency_mode: "legacy" };
    expect(() => parseRecipeRunSummary(invalid)).toThrow(
      "run_summary.input.transparency_mode must be native, ai, or chroma",
    );

    const camelField = successfulRun();
    camelField["input"] = {
      prompt: "moonlit ruins",
      transparency_mode: "ai",
      mapBook: {},
    };
    expect(() => parseRecipeRunSummary(camelField)).toThrow(
      "run_summary.input.mapBook must use lower_snake_case",
    );

    const unsafeInteger = successfulRun();
    unsafeInteger["input"] = {
      prompt: "moonlit ruins",
      transparency_mode: "ai",
      nested: { seed: Number.MAX_SAFE_INTEGER + 1 },
    };
    expect(() => parseRecipeRunSummary(unsafeInteger)).toThrow(
      "run_summary.input.nested.seed must keep integers within the JSON safe-integer range",
    );

    const nonJsonObject = successfulRun();
    nonJsonObject["input"] = {
      prompt: "moonlit ruins",
      transparency_mode: "ai",
      nested: new Date("2026-08-25T00:00:00Z"),
    };
    expect(() => parseRecipeRunSummary(nonJsonObject)).toThrow(
      "run_summary.input.nested must be JSON data",
    );
  });

  test("requires exact stage fields and lower-case stage identifiers", () => {
    const durationAlias = successfulRun();
    durationAlias["stages"] = [
      { stage: "concept", ok: true, durationMs: 1, artifacts: [] },
    ];
    expect(() => parseRecipeRunSummary(durationAlias)).toThrow(
      "run_summary.stages[0].durationMs is not a supported key",
    );

    const unexpected = successfulRun();
    unexpected["stages"] = [
      { stage: "concept", ok: true, duration_ms: 1, artifacts: [], error: "none" },
    ];
    expect(() => parseRecipeRunSummary(unexpected)).toThrow(
      "run_summary.stages[0].error is not a supported key",
    );

    const badId = successfulRun();
    badId["stages"] = [
      { stage: "Concept Art", ok: true, duration_ms: 1, artifacts: [] },
    ];
    expect(() => parseRecipeRunSummary(badId)).toThrow(
      "run_summary.stages[0].stage must be a lower-case hyphenated identifier",
    );
  });

  test("enforces success and failure ownership invariants", () => {
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), failed_stage: "concept" }),
    ).toThrow("run_summary.failed_stage is not a supported key");

    const failedStageInSuccess = successfulRun();
    failedStageInSuccess["stages"] = [
      {
        stage: "concept",
        ok: false,
        duration_ms: 1,
        artifacts: [],
        error: "failed",
      },
    ];
    expect(() => parseRecipeRunSummary(failedStageInSuccess)).toThrow(
      "run_summary.stages must all succeed",
    );

    const noFailure = failedRun();
    noFailure["stages"] = [
      { stage: "concept", ok: true, duration_ms: 1, artifacts: [] },
    ];
    expect(() => parseRecipeRunSummary(noFailure)).toThrow(
      "run_summary.stages must end with exactly one failed stage",
    );

    const nonFinalFailure = failedRun();
    nonFinalFailure["stages"] = [
      {
        stage: "layers",
        ok: false,
        duration_ms: 1,
        artifacts: [],
        error: "failed",
      },
      { stage: "manifest", ok: true, duration_ms: 1, artifacts: [] },
    ];
    expect(() => parseRecipeRunSummary(nonFinalFailure)).toThrow(
      "run_summary.stages must end with exactly one failed stage",
    );

    expect(() =>
      parseRecipeRunSummary({ ...failedRun(), failed_stage: "concept" }),
    ).toThrow("run_summary.failed_stage must match the final failed stage");

    const failedWithArtifact = failedRun();
    failedWithArtifact["stages"] = [
      {
        stage: "layers",
        ok: false,
        duration_ms: 1,
        artifacts: ["partial.png"],
        error: "failed",
      },
    ];
    expect(() => parseRecipeRunSummary(failedWithArtifact)).toThrow(
      "run_summary.stages[0].artifacts must be empty for a failed stage",
    );
  });

  test("rejects duplicate stages and invalid timing fields", () => {
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), stages: [] }),
    ).toThrow("run_summary.stages must contain at least one executed stage");
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), stages: new Array(1) }),
    ).toThrow("run_summary.stages[0] must be an object");

    const duplicate = successfulRun();
    duplicate["stages"] = [
      { stage: "concept", ok: true, duration_ms: 1, artifacts: [] },
      { stage: "concept", ok: true, duration_ms: 1, artifacts: [] },
    ];
    expect(() => parseRecipeRunSummary(duplicate)).toThrow(
      "run_summary.stages must contain unique stage identifiers",
    );

    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), duration_ms: -1 }),
    ).toThrow("run_summary.duration_ms must be a non-negative safe integer");
    expect(() =>
      parseRecipeRunSummary({
        ...successfulRun(),
        ended_at: "2026-08-25T01:02:02Z",
      }),
    ).toThrow("run_summary.ended_at must not precede started_at");
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), started_at: "not-a-date" }),
    ).toThrow("run_summary.started_at must be a valid UTC timestamp ending in Z");
    for (const started_at of [
      "2026-02-30T01:02:03Z",
      "2026-08-25T24:00:00Z",
      "2026-08-25T01:60:00Z",
      "2026-08-25T01:02:60Z",
    ]) {
      expect(() =>
        parseRecipeRunSummary({ ...successfulRun(), started_at }),
      ).toThrow("run_summary.started_at must be a valid UTC timestamp ending in Z");
    }
    expect(
      parseRecipeRunSummary({
        ...successfulRun(),
        started_at: "2026-08-25T01:02:03.123456Z",
      }).started_at,
    ).toBe("2026-08-25T01:02:03.123456Z");
    expect(() =>
      parseRecipeRunSummary({
        ...successfulRun(),
        started_at: "2026-08-25T01:02:03.1234567Z",
      }),
    ).toThrow("run_summary.started_at must be a valid UTC timestamp ending in Z");
  });

  test("matches producer path and trimmed-text bounds", () => {
    expect(() => parseRecipeRunSummary({ ...successfulRun(), tag: "../escape" })).toThrow(
      "run_summary.tag must be one safe path segment",
    );
    expect(() => parseRecipeRunSummary({ ...successfulRun(), tag: "a".repeat(129) })).toThrow(
      "run_summary.tag must be one safe path segment",
    );
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), run_dir: " current " }),
    ).toThrow("run_summary.run_dir must be a non-empty trimmed string");
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), run_dir: "current\0escape" }),
    ).toThrow("run_summary.run_dir must be a non-empty trimmed string");
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), run_dir: "out/current" }),
    ).toThrow("run_summary.run_dir must be one safe path segment");
    expect(() =>
      parseRecipeRunSummary({ ...successfulRun(), run_dir: "another-run" }),
    ).toThrow("run_summary.run_dir must equal run_summary.tag");

    const paddedArtifact = successfulRun();
    paddedArtifact["stages"] = [
      { stage: "concept", ok: true, duration_ms: 1, artifacts: [" concept.png "] },
    ];
    expect(() => parseRecipeRunSummary(paddedArtifact)).toThrow(
      "run_summary.stages[0].artifacts[0] must be a non-empty trimmed string",
    );

    for (const artifact of [
      "/absolute.png",
      "~/private.png",
      "../escape.png",
      "nested/../escape.png",
      "nested\\asset.png",
      ".hidden.png",
      "nested/.hidden/asset.png",
      "https://example.invalid/asset.png",
      "asset.png?token=secret",
      "asset.png#fragment",
      "nested/asset with spaces.png",
      "nested/%2e%2e/asset.png",
      `${"a".repeat(129)}.png`,
    ]) {
      const invalidArtifact = successfulRun();
      invalidArtifact["stages"] = [
        { stage: "concept", ok: true, duration_ms: 1, artifacts: [artifact] },
      ];
      expect(() => parseRecipeRunSummary(invalidArtifact)).toThrow(
        "must be a portable relative POSIX path",
      );
    }
    const duplicateArtifact = successfulRun();
    duplicateArtifact["stages"] = [
      {
        stage: "concept",
        ok: true,
        duration_ms: 1,
        artifacts: ["concept.png", "concept.png"],
      },
    ];
    expect(() => parseRecipeRunSummary(duplicateArtifact)).toThrow(
      "run_summary.stages[0].artifacts must not contain duplicate paths",
    );

    const paddedError = failedRun();
    paddedError["stages"] = [
      {
        stage: "layers",
        ok: false,
        duration_ms: 1,
        artifacts: [],
        error: " failed ",
      },
    ];
    expect(() => parseRecipeRunSummary(paddedError)).toThrow(
      "run_summary.stages[0].error must be a non-empty trimmed string",
    );

    const nulError = failedRun();
    nulError["stages"] = [
      {
        stage: "layers",
        ok: false,
        duration_ms: 1,
        artifacts: [],
        error: "failed\0secret",
      },
    ];
    expect(() => parseRecipeRunSummary(nulError)).toThrow(
      "run_summary.stages[0].error must be a non-empty trimmed string",
    );
  });

  test("rejects invalid and duplicate-key JSON before contract validation", () => {
    expect(() => parseRecipeRunSummaryText("{")).toThrow(
      "run summary must be valid JSON",
    );
    const duplicate = JSON.stringify(successfulRun()).replace(
      '"schema_version":3',
      '"schema_version":3,"schema_version":3',
    );
    expect(() => parseRecipeRunSummaryText(duplicate)).toThrow(
      "run summary is not valid JSON: duplicate JSON key: schema_version",
    );
    const escapedDuplicate = JSON.stringify(successfulRun()).replace(
      '"prompt":"moonlit ruins"',
      '"prompt":"moonlit ruins","\\u0070rompt":"again"',
    );
    expect(() => parseRecipeRunSummaryText(escapedDuplicate)).toThrow(
      "run summary is not valid JSON: duplicate JSON key: prompt",
    );
    expect(() =>
      parseRecipeRunSummaryBytes(Uint8Array.from([0x7b, 0xff, 0x7d])),
    ).toThrow("run summary must be valid UTF-8 JSON");
    expect(() =>
      parseRecipeRunSummaryBytes(
        Uint8Array.from([0xef, 0xbb, 0xbf, ...new TextEncoder().encode("{}")]),
      ),
    ).toThrow("run summary must be BOM-free UTF-8 JSON");
  });
});
