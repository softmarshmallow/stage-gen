import { describe, expect, test } from "bun:test";
import { type Catalog, parseCatalog } from "@stage-gen/ui/contracts/catalog";
import catalogFixture from "@stage-gen/ui/contracts/catalog.fixture.json";
import { groupRuns, isGameRun, type RunIdentity, workflowOf } from "./run-groups";

const NONE: RunIdentity = {
  document: null,
  kind: null,
  pipelineId: null,
  recipe: null,
  viewKind: null,
  graphKind: null,
};

/** The fixture's SDK workflow, plus three made-up workflows, one per kind of identity. */
function catalog(): Catalog {
  const document = structuredClone(catalogFixture) as Record<string, unknown>;
  const workflows = document.workflows as Record<string, unknown>[];
  const sdk = workflows[0];
  const like = (id: string, identity: Record<string, unknown>) => ({
    ...structuredClone(sdk),
    id,
    folder: id.replace(/-/g, "_"),
    identity,
    manifest: { ...(sdk.manifest as Record<string, unknown>), id, examples: [] },
    examples: [],
  });
  workflows.push(
    like("tiny-world", {
      graph_kinds: ["tiny-world-execution-graph-v2"],
      graph_document: {
        recipe: "tiny-world",
        view_kind: "tiny-world-execution-view-v1",
        legacy_graph_identities: [[1, "tiny-world-execution-graph-v1"]],
      },
    }),
    like("figure-rig", { graph_kinds: ["contained-figure-rig-v1"] }),
    like("face-moves", { graph_kinds: ["face-moves-v2"], plan_kinds: ["face-moves-plan-v1"] }),
  );
  return parseCatalog(document);
}

describe("which workflow a run belongs to", () => {
  const known = catalog();

  test("an SDK run by its pipeline id, never by the shared SDK graph kind alone", () => {
    const sdk = { ...NONE, document: "execution-plan.json", kind: "pipeline-execution-graph-v1" };
    expect(workflowOf({ ...sdk, pipelineId: "swatch-sheet" }, known)).toBe("swatch-sheet");
    expect(workflowOf({ ...sdk, pipelineId: "someone.elses" }, known)).toBeNull();
    expect(workflowOf({ ...NONE, viewKind: "pipeline-execution-view-v1", pipelineId: "swatch-sheet" }, known)).toBe(
      "swatch-sheet",
    );
  });

  test("a graph-document run by its graph kind, a legacy kind, its literal or its view kind", () => {
    expect(workflowOf({ ...NONE, kind: "tiny-world-execution-graph-v2" }, known)).toBe("tiny-world");
    expect(workflowOf({ ...NONE, kind: "tiny-world-execution-graph-v1" }, known)).toBe("tiny-world");
    expect(workflowOf({ ...NONE, recipe: "tiny-world" }, known)).toBe("tiny-world");
    expect(workflowOf({ ...NONE, viewKind: "tiny-world-execution-view-v1" }, known)).toBe("tiny-world");
  });

  test("a joined run by the graph kind its view came from, a prepared run by its plan kind", () => {
    expect(workflowOf({ ...NONE, document: "graph.json", kind: "contained-figure-rig-v1" }, known)).toBe(
      "figure-rig",
    );
    expect(workflowOf({ ...NONE, viewKind: "gnode-run-view-v1", graphKind: "face-moves-v2" }, known)).toBe(
      "face-moves",
    );
    expect(workflowOf({ ...NONE, document: "plan.json", kind: "face-moves-plan-v1" }, known)).toBe("face-moves");
  });

  test("runs no workflow claims are game runs when a game wrote them, else other", () => {
    expect(isGameRun({ ...NONE, recipe: "pointclick-room" })).toBe(true);
    expect(isGameRun({ ...NONE, document: "manifest.json", kind: "prepared-game-runtime-v12" })).toBe(true);
    expect(isGameRun({ ...NONE, document: "graph.json", kind: "contained-rig-review-calibration-v1" })).toBe(false);

    const entries = [
      { name: "old", identity: { ...NONE, recipe: "tiny-world" }, updatedAt: "2026-09-01T00:00:00.000Z" },
      { name: "new", identity: { ...NONE, recipe: "tiny-world" }, updatedAt: "2026-09-30T00:00:00.000Z" },
      { name: "game", identity: { ...NONE, recipe: "pointclick-room" }, updatedAt: null },
      { name: "calibration", identity: { ...NONE, kind: "contained-rig-review-calibration-v1" }, updatedAt: null },
    ];
    const groups = groupRuns(entries, known);
    expect(groups.workflows.map((group) => group.workflow.id)).toEqual([
      "swatch-sheet",
      "tiny-world",
      "figure-rig",
      "face-moves",
    ]);
    expect(groups.workflows[1].runs.map((entry) => entry.name)).toEqual(["new", "old"]);
    expect(groups.workflows[0].runs).toEqual([]);
    expect(groups.game.map((entry) => entry.name)).toEqual(["game"]);
    expect(groups.other.map((entry) => entry.name)).toEqual(["calibration"]);
  });

  test("without a catalog every run is a game run or another run", () => {
    const groups = groupRuns([{ identity: { ...NONE, recipe: "tiny-world" }, updatedAt: null }], null);
    expect(groups.workflows).toEqual([]);
    expect(groups.game).toHaveLength(1);
  });
});
