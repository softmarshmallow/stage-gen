// Wire-format execution-view documents for tests. Deliberately untyped
// records: the parser under test is what gives them shape.

const DIGEST = "a".repeat(64);

const ACTOR_ROOT = "content/players/wayfarer";
const ATLAS_REF = `${ACTOR_ROOT}/states/idle.source.png`;

function viewNode(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    node_id: "package-resolve",
    type_id: "2d/sideview/platformer/package.resolve",
    title: "Package capture",
    archetype: "source",
    domain: "package",
    description: "validate and capture the complete prepared package",
    params: {},
    depends_on: [],
    barrier_only: [],
    operation: "local",
    resource_id: "local",
    provider: null,
    model: null,
    retry_owner: "none",
    max_attempts: 1,
    input_sha256: [DIGEST],
    cache_key: DIGEST,
    ports: [
      {
        port_id: "identity",
        artifact_ref: "package.identity.json",
        kind: "package-identity-v1",
        sidecar_ref: null,
      },
    ],
    card: null,
    template_id: null,
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
    artifacts: [
      {
        artifact_ref: "package.identity.json",
        sha256: DIGEST,
        bytes: 384,
        media_type: "application/json",
        present: true,
        display: "data",
        motion: null,
      },
    ],
    ...overrides,
  };
}

/**
 * A four-node platformer run: resolve → paint a motion strip → admit it →
 * review the actor, all green. It carries one of everything the typed-node
 * contract added — a prompted image node, a barrier edge, a card with derived
 * reference inputs, a templated judge with a verdict port.
 */
export function executionViewFixture(): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "sideview-platformer-execution-view-v1",
    recipe: "sideview-platformer",
    game_id: "bellweather",
    graph_sha256: DIGEST,
    topology_sha256: DIGEST,
    invocation_id: "fixture-run",
    run_state: "succeeded",
    trace_modified_at: "2026-08-30T12:00:00Z",
    duration_ms: 4200,
    known_cost_usd: 0.12,
    state_counts: { pending: 0, running: 0, succeeded: 4, failed: 0, skipped: 0 },
    resources: [],
    nodes: [
      viewNode({}),
      viewNode({
        node_id: "player-wayfarer-state-idle-generate",
        type_id: "2d/sideview/platformer/motion_atlas.generate",
        title: "Motion atlas",
        archetype: "image",
        domain: "player-wayfarer",
        description: "generate motion strip idle",
        params: { actor_id: "wayfarer", state: "idle" },
        depends_on: ["package-resolve"],
        operation: "image_generation",
        resource_id: "openai-image",
        provider: "openai",
        model: "gpt-image-2",
        retry_owner: "component",
        max_attempts: 6,
        known_cost_usd: 0.12,
        ports: [
          {
            port_id: "image",
            artifact_ref: ATLAS_REF,
            kind: "motion-atlas-v1",
            sidecar_ref: `${ATLAS_REF}.provenance.json`,
          },
        ],
        card: {
          prompt: "Paint a four-frame idle strip for the wayfarer, side view, transparent.",
          template_ref: null,
          schema_name: null,
          reference_inputs: [{ node_id: "package-resolve", port_id: "identity" }],
        },
        artifacts: [
          {
            artifact_ref: ATLAS_REF,
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
        type_id: "2d/sideview/platformer/motion_atlas.validate",
        title: "Motion atlas admission",
        archetype: "validate",
        domain: "player-wayfarer",
        description: "validate motion strip idle",
        params: { actor_id: "wayfarer", state: "idle" },
        // The package edge orders this node after capture without lending it
        // lineage: the plan's own distinction, which the picture now draws.
        depends_on: ["player-wayfarer-state-idle-generate", "package-resolve"],
        barrier_only: ["package-resolve"],
        ports: [
          {
            port_id: "validation",
            artifact_ref: `${ACTOR_ROOT}/states/idle.validation.json`,
            kind: "motion-atlas-validation-v1",
            sidecar_ref: null,
          },
        ],
        card: {
          prompt: null,
          template_ref: null,
          schema_name: null,
          reference_inputs: [
            { node_id: "player-wayfarer-state-idle-generate", port_id: "image" },
          ],
        },
        artifacts: [
          {
            artifact_ref: `${ACTOR_ROOT}/states/idle.validation.json`,
            sha256: DIGEST,
            bytes: 512,
            media_type: "application/json",
            present: true,
            display: "data",
            motion: null,
          },
        ],
      }),
      viewNode({
        node_id: "player-wayfarer-review",
        type_id: "2d/sideview/platformer/actor.review",
        title: "Actor review",
        archetype: "judge",
        domain: "player-wayfarer",
        description: "review the complete wayfarer sheet",
        params: { actor_id: "wayfarer" },
        depends_on: ["player-wayfarer-state-idle-validate"],
        operation: "structured_generation",
        resource_id: "openai-structured",
        provider: "openai",
        model: "gpt-5",
        retry_owner: "component",
        max_attempts: 6,
        template_id: "actor-pipeline@v1:wayfarer",
        ports: [
          {
            port_id: "verdict",
            artifact_ref: `${ACTOR_ROOT}/review.json`,
            kind: "review-verdict-v1",
            sidecar_ref: `${ACTOR_ROOT}/review.json.meta.json`,
          },
        ],
        card: {
          prompt: "Judge identity fidelity and style coherence across every state.",
          template_ref: null,
          schema_name: "prepared_actor_review",
          reference_inputs: [
            { node_id: "player-wayfarer-state-idle-generate", port_id: "image" },
          ],
        },
        artifacts: [
          {
            artifact_ref: `${ACTOR_ROOT}/review.json`,
            sha256: DIGEST,
            bytes: 256,
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
        gap_id: "node-type-not-registered",
        detail: "plan nodes declare type ids the exporter's registry does not carry",
      },
    ],
  };
}

/**
 * The same run stopped mid-stream: nothing downstream of generate ever started.
 * Whether that reads as running or interrupted is the reader's call, made from
 * trace_modified_at — so callers set it to whatever they are testing.
 */
export function unfinishedExecutionViewFixture(
  traceModifiedAt: string | null = "2026-08-30T12:00:00Z",
): Record<string, unknown> {
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
  for (const index of [2, 3]) {
    nodes[index] = {
      ...nodes[index],
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
  }
  return {
    ...document,
    run_state: "unfinished",
    trace_modified_at: traceModifiedAt,
    duration_ms: null,
    known_cost_usd: null,
    state_counts: { pending: 2, running: 1, succeeded: 1, failed: 0, skipped: 0 },
  };
}

/** The same run with the generate node failed and everything after it skipped. */
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
  nodes[3] = {
    ...nodes[3],
    state: "skipped",
    started_offset_ms: null,
    cache: null,
    attempts: 0,
    blocked_by: ["player-wayfarer-state-idle-validate"],
    artifacts: [],
  };
  return {
    ...document,
    run_state: "failed",
    state_counts: { pending: 0, running: 0, succeeded: 1, failed: 1, skipped: 2 },
  };
}

/**
 * A dialogue-scene run: the second view kind. Its header names a scene rather
 * than a game, and its nodes exercise the matte archetype and a packaged
 * template reference the platformer fixture has no use for.
 */
export function dialogueExecutionViewFixture(): Record<string, unknown> {
  const request = {
    ...viewNode({}),
    node_id: "request-resolve",
    type_id: "2d/frontview/vn/request.resolve",
    title: "Dialogue request",
    archetype: "source",
    domain: "request",
    description: "capture the dialogue request",
    ports: [
      {
        port_id: "request",
        artifact_ref: "request.json",
        kind: "dialogue-request-v1",
        sidecar_ref: null,
      },
    ],
    artifacts: [
      {
        artifact_ref: "request.json",
        sha256: DIGEST,
        bytes: 512,
        media_type: "application/json",
        present: true,
        display: "data",
        motion: null,
      },
    ],
  };
  const concept = {
    ...viewNode({}),
    node_id: "portrait-concept-generate",
    type_id: "2d/frontview/vn/portrait_concept.generate",
    title: "Appearance concept",
    archetype: "image",
    domain: "mio",
    description: "generate the appearance concept for mio",
    params: { actor_id: "mio" },
    depends_on: ["request-resolve"],
    operation: "image_generation",
    resource_id: "openai-image",
    provider: "openai",
    model: "gpt-image-2",
    retry_owner: "component",
    max_attempts: 6,
    ports: [
      {
        port_id: "image",
        artifact_ref: "mio/concept.png",
        kind: "portrait-concept-v1",
        sidecar_ref: "mio/concept.png.meta.json",
      },
    ],
    card: {
      prompt: "Front-facing appearance concept for a young researcher, waist up.",
      template_ref: "portrait_frame_1x1_template_v1",
      schema_name: null,
      reference_inputs: [{ node_id: "request-resolve", port_id: "request" }],
    },
    artifacts: [
      {
        artifact_ref: "mio/concept.png",
        sha256: DIGEST,
        bytes: 4096,
        media_type: "image/png",
        present: true,
        display: "image",
        motion: null,
      },
    ],
  };
  const matte = {
    ...viewNode({}),
    node_id: "sprite-matte",
    type_id: "2d/frontview/vn/sprite.matte",
    title: "Sprite background removal",
    archetype: "matte",
    domain: "mio",
    description: "cut the concept free of its background",
    params: { actor_id: "mio" },
    depends_on: ["portrait-concept-generate"],
    operation: "background_removal",
    resource_id: "matte",
    provider: "bria",
    model: "rmbg-2.0",
    retry_owner: "component",
    max_attempts: 6,
    ports: [
      {
        port_id: "matte",
        artifact_ref: "mio/concept.matte.png",
        kind: "matte-raw-v1",
        sidecar_ref: "mio/concept.matte.png.meta.json",
      },
    ],
    card: {
      prompt: "Remove the background while preserving the adult character.",
      template_ref: null,
      schema_name: null,
      reference_inputs: [{ node_id: "portrait-concept-generate", port_id: "image" }],
    },
    artifacts: [
      {
        artifact_ref: "mio/concept.matte.png",
        sha256: DIGEST,
        bytes: 3072,
        media_type: "image/png",
        present: true,
        display: "image",
        motion: null,
      },
    ],
  };
  const bundle = {
    ...viewNode({}),
    node_id: "bundle-package",
    type_id: "2d/frontview/vn/bundle.package",
    title: "Dialogue bundle",
    archetype: "package",
    domain: "bundle",
    description: "assemble the dialogue bundle",
    depends_on: ["sprite-matte"],
    ports: [
      {
        port_id: "bundle",
        artifact_ref: "dialogue-bundle.json",
        kind: "dialogue-bundle-v1",
        sidecar_ref: null,
      },
    ],
    artifacts: [
      {
        artifact_ref: "dialogue-bundle.json",
        sha256: DIGEST,
        bytes: 1024,
        media_type: "application/json",
        present: true,
        display: "data",
        motion: null,
      },
    ],
  };
  return {
    schema_version: 3,
    kind: "dialogue-scene-execution-view-v1",
    recipe: "dialogue-scene",
    scene_id: "mio-researcher-424f93ae7637",
    graph_sha256: DIGEST,
    topology_sha256: DIGEST,
    invocation_id: "fixture-dialogue-run",
    run_state: "succeeded",
    trace_modified_at: "2026-08-30T12:00:00Z",
    duration_ms: 2100,
    known_cost_usd: 0.08,
    state_counts: { pending: 0, running: 0, succeeded: 4, failed: 0, skipped: 0 },
    resources: [],
    nodes: [request, concept, matte, bundle],
    gaps: [],
  };
}
