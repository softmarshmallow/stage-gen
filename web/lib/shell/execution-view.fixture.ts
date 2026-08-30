// Wire-format execution-view documents for tests. Deliberately untyped
// records: the parser under test is what gives them shape.

const DIGEST = "a".repeat(64);

function viewNode(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    node_id: "package-resolve",
    domain: "package",
    description: "validate and capture the complete prepared package",
    depends_on: [],
    operation: "local",
    resource_id: "local",
    provider: null,
    model: null,
    retry_owner: "none",
    max_attempts: 1,
    input_sha256: [DIGEST],
    cache_key: DIGEST,
    outputs: ["package.identity.json"],
    estimated_duration_seconds: 0.1,
    estimated_cost_low_usd: 0,
    estimated_cost_high_usd: 0,
    state: "succeeded",
    started_offset_ms: 0,
    ended_offset_ms: 1,
    queue_ms: 0,
    duration_ms: 1,
    cache: "hit",
    attempts: 1,
    provider_operations: 0,
    known_cost_usd: 0,
    error: null,
    blocked_by: [],
    artifacts: [],
    ...overrides,
  };
}

/** A three-node run: resolve → generate motion strip → validate, all green. */
export function executionViewFixture(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "prepared-game-execution-view-v1",
    recipe: "scrolling-preview",
    game_id: "bellweather",
    graph_sha256: DIGEST,
    topology_sha256: DIGEST,
    invocation_id: "fixture-run",
    ok: true,
    duration_ms: 4200,
    known_cost_usd: 0.12,
    state_counts: { pending: 0, running: 0, succeeded: 3, failed: 0, skipped: 0 },
    resources: [],
    nodes: [
      viewNode({}),
      viewNode({
        node_id: "player-wayfarer-state-idle-generate",
        domain: "player-wayfarer",
        description: "generate motion strip idle",
        depends_on: ["package-resolve"],
        operation: "image_generation",
        resource_id: "openai-image",
        provider: "openai",
        model: "gpt-image-2",
        retry_owner: "component",
        max_attempts: 6,
        known_cost_usd: 0.12,
        artifacts: [
          {
            artifact_ref: "content/players/wayfarer/states/idle.source.png",
            sha256: DIGEST,
            bytes: 2048,
            media_type: "image/png",
            present: true,
            display: "motion_atlas",
            motion: {
              frame_count: 4,
              mode: null,
              frames_per_second: null,
              canonical_frame_indices: [],
            },
          },
        ],
      }),
      viewNode({
        node_id: "player-wayfarer-state-idle-validate",
        domain: "player-wayfarer",
        description: "validate motion strip idle",
        depends_on: ["player-wayfarer-state-idle-generate"],
        artifacts: [
          {
            artifact_ref: "content/players/wayfarer/states/idle.validation.json",
            sha256: DIGEST,
            bytes: 512,
            media_type: "application/json",
            present: true,
            display: "data",
            motion: null,
          },
        ],
      }),
    ],
    gaps: [
      {
        gap_id: "edge-kinds-not-distinguished",
        detail: "plan depends_on does not distinguish lineage edges from cache barriers",
      },
    ],
  };
}

/** The same run interrupted: validate never started, generate still running. */
export function inFlightExecutionViewFixture(): Record<string, unknown> {
  const document = executionViewFixture();
  const nodes = document.nodes as Record<string, unknown>[];
  nodes[1] = {
    ...nodes[1],
    state: "running",
    ended_offset_ms: null,
    queue_ms: null,
    duration_ms: null,
    cache: null,
    attempts: null,
    known_cost_usd: null,
    artifacts: [],
  };
  nodes[2] = {
    ...nodes[2],
    state: "pending",
    started_offset_ms: null,
    ended_offset_ms: null,
    queue_ms: null,
    duration_ms: null,
    cache: null,
    attempts: null,
    provider_operations: null,
    known_cost_usd: null,
    artifacts: [],
  };
  return {
    ...document,
    ok: null,
    duration_ms: null,
    known_cost_usd: null,
    state_counts: { pending: 1, running: 1, succeeded: 1, failed: 0, skipped: 0 },
  };
}

/** The same run with the generate node failed and the validate node skipped. */
export function failedExecutionViewFixture(): Record<string, unknown> {
  const document = executionViewFixture();
  const nodes = document.nodes as Record<string, unknown>[];
  nodes[1] = {
    ...nodes[1],
    state: "failed",
    error: "comparison-plate-v1: plate would be 1686x4060, past the pixel ceiling",
    artifacts: [],
  };
  nodes[2] = {
    ...nodes[2],
    state: "skipped",
    started_offset_ms: null,
    cache: null,
    attempts: 0,
    blocked_by: ["player-wayfarer-state-idle-generate"],
    artifacts: [],
  };
  return {
    ...document,
    ok: false,
    state_counts: { pending: 0, running: 0, succeeded: 1, failed: 1, skipped: 1 },
  };
}
