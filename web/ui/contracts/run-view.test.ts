import { describe, expect, test } from "bun:test";
import {
  dialogueExecutionViewFixture,
  pipelineExecutionViewFixture,
  executionViewFixture,
  failedExecutionViewFixture,
  unfinishedExecutionViewFixture,
} from "./run-view.test-fixtures";
import {
  EXECUTION_VIEW_REFUSAL,
  isExecutionViewKind,
  parseExecutionView,
  RUNNING_TRACE_STALENESS_MS,
  runLiveness,
  subjectLabel,
} from "./run-view";
import runViewFixture from "./run-view.fixture.json";

describe("parseExecutionView", () => {
  test("renders an unfamiliar pipeline identity without a recipe registration", () => {
    const document = pipelineExecutionViewFixture();
    const view = parseExecutionView(document);
    expect(view.subject.kind).toBe("pipeline-execution-view-v1");
    expect(subjectLabel(view.subject)).toBe("Material study");
    expect(view.subject.pipelineId).toBe("user.tools-material-set");
    expect(view.subject.recipe).toBeNull();
    expect(document.recipe).toBeUndefined();
    expect(document.game_id).toBeUndefined();
    expect(isExecutionViewKind("pipeline-execution-view-v1")).toBe(true);
  });

  test.each([undefined, "", "  ", "../pipeline", "pipeline/id", 5])("refuses malformed generic pipeline identity %s", (identity) => {
    expect(() => parseExecutionView({ ...pipelineExecutionViewFixture(), pipeline_id: identity })).toThrow("pipeline_id");
  });

  test("accepts unknown artifact display hints but refuses malformed artifacts", () => {
    const document = pipelineExecutionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    const artifact = (nodes[0].artifacts as Record<string, unknown>[])[0];
    artifact.display = "user-volume";
    artifact.media_type = "model/gltf-binary";
    expect(parseExecutionView(document).nodes[0].artifacts[0].display).toBe("data");
    artifact.present = "true";
    expect(() => parseExecutionView(document)).toThrow("present must be a boolean");
    artifact.present = true;
    artifact.artifact_ref = "../secret.json";
    expect(() => parseExecutionView(document)).toThrow("portable run-local");
    expect(() => parseExecutionView({ ...pipelineExecutionViewFixture(), graph_sha256: "bad" })).toThrow("SHA-256");
  });

  test("parses a finished run into camelCase runtime shapes", () => {
    const view = parseExecutionView(executionViewFixture());
    expect(view.subject.kind).toBe("sideview-platformer-execution-view-v1");
    expect(subjectLabel(view.subject)).toBe("bellweather");
    expect(view.runState).toBe("succeeded");
    expect(view.nodes).toHaveLength(4);
    expect(view.stateCounts.succeeded).toBe(4);

    const generate = view.nodes[1];
    expect(generate.nodeId).toBe("player-wayfarer-state-idle-generate");
    expect(generate.dependsOn).toEqual(["package-resolve"]);
    expect(generate.state).toBe("succeeded");
    expect(generate.cache).toBe("hit");
    expect(generate.artifacts[0].display).toBe("motion_atlas");
    expect(generate.artifacts[0].motion?.frameCount).toBe(4);
    expect(view.gaps[0].gapId).toBe("node-type-not-registered");
  });

  test("carries the typed-node fields the v3 contract added", () => {
    const view = parseExecutionView(executionViewFixture());
    const generate = view.nodes[1];
    expect(generate.typeId).toBe(
      "2d/sideview/platformer/motion_atlas.generate",
    );
    expect(generate.title).toBe("Motion atlas");
    expect(generate.archetype).toBe("image");
    expect(generate.params).toEqual({ actor_id: "wayfarer", state: "idle" });
    expect(generate.ports).toHaveLength(1);
    expect(generate.ports[0].portId).toBe("image");
    expect(generate.ports[0].kind).toBe("motion-atlas-v1");
    expect(generate.ports[0].sidecarRef).toBe(
      "content/players/wayfarer/states/idle.source.png.provenance.json",
    );
    expect(generate.card?.prompt).toContain("four-frame idle strip");
    expect(generate.card?.referenceInputs).toEqual([
      { nodeId: "package-resolve", portId: "identity" },
    ]);

    const review = view.nodes[3];
    expect(review.archetype).toBe("judge");
    expect(review.card?.schemaName).toBe("prepared_actor_review");
    expect(review.templateId).toBe("actor-pipeline@v1:wayfarer");
    // A port that declares no sidecar says so, rather than inventing one.
    expect(view.nodes[0].ports[0].sidecarRef).toBeNull();
  });

  test("keeps barrier edges as a named subset of the dependencies", () => {
    const view = parseExecutionView(executionViewFixture());
    const validate = view.nodes[2];
    expect(validate.dependsOn).toEqual([
      "player-wayfarer-state-idle-generate",
      "package-resolve",
    ]);
    expect(validate.barrierOnly).toEqual(["package-resolve"]);
    expect(view.nodes[1].barrierOnly).toEqual([]);
  });

  test("accepts the dialogue-scene kind and labels it by its scene", () => {
    const view = parseExecutionView(dialogueExecutionViewFixture());
    expect(view.subject.kind).toBe("dialogue-scene-execution-view-v1");
    expect(subjectLabel(view.subject)).toBe("mio-researcher-424f93ae7637");
    expect(view.subject.recipe).toBe("dialogue-scene");
    expect(view.nodes.map((node) => node.archetype)).toEqual([
      "source",
      "image",
      "matte",
      "package",
    ]);
    expect(view.nodes[1].card?.templateRef).toBe(
      "portrait_frame_1x1_template_v1",
    );
  });

  test("isExecutionViewKind reads any execution-view envelope and gnode's own", () => {
    for (const kind of [
      "sideview-platformer-execution-view-v1",
      "dialogue-scene-execution-view-v1",
      "universe-execution-view-v1",
      "a-producer-this-build-never-heard-of-execution-view-v1",
      "gnode-run-view-v1",
    ]) {
      expect(isExecutionViewKind(kind)).toBe(true);
    }
    for (const kind of ["someone-elses-view-v1", "execution-view-v1", "Upper-execution-view-v1", 3]) {
      expect(isExecutionViewKind(kind)).toBe(false);
    }
  });

  test("keeps every extra header field as the subject, labelled by its ids", () => {
    const document = {
      ...executionViewFixture(),
      kind: "sideview-runner-execution-view-v1",
      recipe: "sideview-runner",
      track_id: "sunpetal-sprint",
    };
    const view = parseExecutionView(document);
    expect(view.subject.kind).toBe("sideview-runner-execution-view-v1");
    expect(view.subject.recipe).toBe("sideview-runner");
    expect(view.subject.fields).toEqual({ game_id: "bellweather", track_id: "sunpetal-sprint" });
    expect(subjectLabel(view.subject)).toBe("bellweather · sunpetal-sprint");
  });

  test("labels a universe run by universe and phase", () => {
    const document = {
      ...executionViewFixture(),
      kind: "universe-execution-view-v1",
      recipe: "universe",
      universe_id: "lantern_ferry",
      phase: "gallery",
    };
    delete (document as Record<string, unknown>).game_id;
    const view = parseExecutionView(document);
    // One universe runs twice — semantic, then gallery — so the phase is what
    // tells two runs of the same world apart in the list.
    expect(subjectLabel(view.subject)).toBe("lantern_ferry · gallery");
    expect(view.subject.fields.universe_id).toBe("lantern_ferry");
  });

  test("labels by ids, not counts, and reads a joined gnode view by its graph kind", () => {
    const storefront = parseExecutionView({
      ...executionViewFixture(),
      kind: "storefront-execution-view-v1",
      recipe: "storefront",
      game_id: undefined,
      storefront_id: "quiet_orbit",
      surface_count: 4,
    });
    expect(subjectLabel(storefront.subject)).toBe("quiet_orbit");
    expect(storefront.subject.fields.surface_count).toBe(4);

    const joined = { ...executionViewFixture(), kind: "gnode-run-view-v1" } as Record<string, unknown>;
    delete joined.recipe;
    delete joined.game_id;
    joined.graph_kind = "contained-character-parts-to-rig-v1";
    const view = parseExecutionView(joined);
    expect(view.subject.recipe).toBeNull();
    expect(subjectLabel(view.subject)).toBe("contained-character-parts-to-rig-v1");
  });

  test("keeps unfinished and failed states distinct", () => {
    const unfinished = parseExecutionView(unfinishedExecutionViewFixture());
    expect(unfinished.runState).toBe("unfinished");
    expect(unfinished.nodes[1].state).toBe("running");
    expect(unfinished.nodes[2].state).toBe("pending");

    const failed = parseExecutionView(failedExecutionViewFixture());
    expect(failed.runState).toBe("failed");
    expect(failed.nodes[1].state).toBe("failed");
    expect(failed.nodes[1].error).toContain("comparison-plate-v1");
    expect(failed.nodes[2].state).toBe("skipped");
    expect(failed.nodes[2].blockedBy).toEqual([
      "player-wayfarer-state-idle-generate",
    ]);
  });

  test("refuses an unknown version with the re-export message, never migrates", () => {
    const stale = { ...executionViewFixture(), schema_version: 1 };
    expect(() => parseExecutionView(stale)).toThrow(EXECUTION_VIEW_REFUSAL);
    const alien = { ...executionViewFixture(), kind: "someone-elses-view-v1" };
    expect(() => parseExecutionView(alien)).toThrow(EXECUTION_VIEW_REFUSAL);
  });

  test("refuses the v2 document this build used to render", () => {
    // The previous contract, kind and version together. Hard drop: a v2 run is
    // re-exported, never migrated field by field.
    const v2 = {
      ...executionViewFixture(),
      schema_version: 2,
      kind: "prepared-game-execution-view-v1",
    };
    expect(() => parseExecutionView(v2)).toThrow(EXECUTION_VIEW_REFUSAL);
    expect(() => parseExecutionView(v2)).toThrow("derive it again");
  });

  test("carries a text artifact through as its own display", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    const artifacts = nodes[1].artifacts as Record<string, unknown>[];
    nodes[1] = {
      ...nodes[1],
      artifacts: [
        {
          ...artifacts[0],
          artifact_ref: "production/records/wayfarer.md",
          media_type: "text/markdown",
          display: "text",
          motion: null,
        },
      ],
    };
    const view = parseExecutionView(document);
    expect(view.nodes[1].artifacts[0].display).toBe("text");
    expect(view.nodes[1].artifacts[0].mediaType).toBe("text/markdown");
  });

  test("reads a display hint it has no view for as data, and refuses a missing one", () => {
    // The engine carries display hints as consumer text; any producer may add one.
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    const artifacts = nodes[1].artifacts as Record<string, unknown>[];
    nodes[1] = { ...nodes[1], artifacts: [{ ...artifacts[0], display: "hologram" }] };
    expect(parseExecutionView(document).nodes[1].artifacts[0].display).toBe("data");
    nodes[1] = { ...nodes[1], artifacts: [{ ...artifacts[0], display: " " }] };
    expect(() => parseExecutionView(document)).toThrow("display is invalid");
  });

  test("refuses a run_state outside the declared vocabulary", () => {
    const alien = { ...executionViewFixture(), run_state: "in flight" };
    expect(() => parseExecutionView(alien)).toThrow("run_state must be one of");
  });

  test("refuses an archetype outside the engine's closed vocabulary", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[1] = { ...nodes[1], archetype: "vibes" };
    expect(() => parseExecutionView(document)).toThrow(
      "must be null or one of",
    );
  });

  test("accepts a null archetype: the exporter admitting an unregistered type", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[1] = { ...nodes[1], archetype: null, title: null };
    const view = parseExecutionView(document);
    expect(view.nodes[1].archetype).toBeNull();
    expect(view.nodes[1].title).toBeNull();
  });

  test("refuses dangling dependencies and duplicate node ids", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[1] = { ...nodes[1], depends_on: ["missing-node"] };
    expect(() => parseExecutionView(document)).toThrow("undeclared node");

    const duplicated = executionViewFixture();
    const duplicateNodes = duplicated.nodes as Record<string, unknown>[];
    duplicateNodes[2] = {
      ...duplicateNodes[2],
      node_id: "package-resolve",
      depends_on: [],
      barrier_only: [],
      card: null,
    };
    expect(() => parseExecutionView(duplicated)).toThrow("unique");
  });

  test("refuses a barrier edge that is not a declared dependency", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[2] = { ...nodes[2], barrier_only: ["player-wayfarer-review"] };
    expect(() => parseExecutionView(document)).toThrow("not a dependency");
  });

  test("refuses a reference input that points at a port nobody declares", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[1] = {
      ...nodes[1],
      card: {
        prompt: null,
        template_ref: null,
        schema_name: null,
        reference_inputs: [{ node_id: "package-resolve", port_id: "nowhere" }],
      },
    };
    expect(() => parseExecutionView(document)).toThrow("undeclared port");

    const strayNode = executionViewFixture();
    const strayNodes = strayNode.nodes as Record<string, unknown>[];
    strayNodes[1] = {
      ...strayNodes[1],
      card: {
        prompt: null,
        template_ref: null,
        schema_name: null,
        reference_inputs: [{ node_id: "ghost", port_id: "identity" }],
      },
    };
    expect(() => parseExecutionView(strayNode)).toThrow(
      "undeclared node ghost",
    );
  });

  test("refuses duplicate port ids on one node", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[0] = {
      ...nodes[0],
      ports: [
        {
          port_id: "identity",
          artifact_ref: "a.json",
          kind: "package-identity-v1",
        },
        {
          port_id: "identity",
          artifact_ref: "b.json",
          kind: "package-identity-v1",
        },
      ],
    };
    expect(() => parseExecutionView(document)).toThrow("unique port ids");
  });
});

describe("runLiveness", () => {
  const written = Date.parse("2026-08-30T12:00:00Z");

  test("a finished run reports what its records say, whatever the clock says", () => {
    const view = parseExecutionView(executionViewFixture());
    expect(runLiveness(view, written + 10 * 365 * 24 * 60 * 60 * 1000)).toBe(
      "succeeded",
    );
    expect(
      runLiveness(parseExecutionView(failedExecutionViewFixture()), written),
    ).toBe("failed");
  });

  test("an unfinished run is running only while its trace is still fresh", () => {
    const view = parseExecutionView(unfinishedExecutionViewFixture());
    expect(runLiveness(view, written + 1_000)).toBe("running");
    expect(runLiveness(view, written + RUNNING_TRACE_STALENESS_MS)).toBe(
      "running",
    );
    expect(runLiveness(view, written + RUNNING_TRACE_STALENESS_MS + 1)).toBe(
      "interrupted",
    );
    // Days later — the case that used to read "in flight" for a dead run.
    expect(runLiveness(view, written + 3 * 24 * 60 * 60 * 1000)).toBe(
      "interrupted",
    );
  });

  test("an unfinished run with no readable stamp never claims to be running", () => {
    expect(
      runLiveness(
        parseExecutionView(unfinishedExecutionViewFixture(null)),
        written,
      ),
    ).toBe("interrupted");
  });
});

describe("the shared run-view fixture", () => {
  // The same document tests/contract/test_web_contract_fixtures.py validates against the
  // engine's RunView, so the parser and the producer read one wire format.
  test("parses as an SDK run with its cards, sidecars and artifacts", () => {
    const view = parseExecutionView(structuredClone(runViewFixture));
    expect(subjectLabel(view.subject)).toBe("Swatch sheet");
    expect(view.runState).toBe("succeeded");
    expect(view.nodes.map((node) => node.nodeId)).toEqual(["brief", "draw", "check"]);
    const draw = view.nodes[1];
    expect(draw.card?.referenceInputs).toEqual([{ nodeId: "brief", portId: "brief" }]);
    expect(draw.ports[0].sidecarRef).toBe("sheet.png.provenance.json");
    expect(draw.artifacts.map((artifact) => artifact.display)).toEqual(["image", "data"]);
    expect(view.stateCounts.succeeded).toBe(3);
  });
});
