import { describe, expect, test } from "bun:test";
import { type Catalog, parseCatalog } from "@stage-gen/ui/contracts/catalog";
import catalogFixture from "@stage-gen/ui/contracts/catalog.fixture.json";
import { groupRuns, isGameRun, type RunIdentity, workflowOf } from "./run-groups";

const NONE: RunIdentity = {
  document: null,
  kind: null,
  viewKind: null,
  graphKind: null,
};

/** The fixture's workflow, plus made-up workflows: two workflow files and one other graph kind. */
function catalog(): Catalog {
  const document = structuredClone(catalogFixture) as Record<string, unknown>;
  const workflows = document.workflows as Record<string, unknown>[];
  const first = workflows[0];
  const like = (id: string, identity: Record<string, unknown>) => ({
    ...structuredClone(first),
    id,
    folder: id.replace(/-/g, "_"),
    identity,
    manifest: { ...(first.manifest as Record<string, unknown>), id, examples: [] },
    examples: [],
  });
  workflows.push(
    like("figure-rig", { graph_kinds: ["contained-figure-rig-v1"] }),
    like("strip-loop", { graph_kinds: ["gnode-graph-v2"] }),
    like("tile-set", { graph_kinds: ["gnode-graph-v2"] }),
  );
  return parseCatalog(document);
}

describe("which workflow a run belongs to", () => {
  const known = catalog();

  test("a workflow run by the workflow its plan names, never by the shared graph kind", () => {
    const gnode = { ...NONE, document: "plan.json", kind: "gnode-graph-v2" };
    expect(workflowOf({ ...gnode, workflowId: "tile-set" }, known)).toBe("tile-set");
    expect(workflowOf({ ...gnode, workflowId: "strip-loop" }, known)).toBe("strip-loop");
    expect(workflowOf({ ...gnode, workflowId: "swatch-sheet" }, known)).toBe("swatch-sheet");
    expect(workflowOf({ ...gnode, workflowId: "someone-elses" }, known)).toBeNull();
    expect(workflowOf({ ...gnode, workflowId: "figure-rig" }, known)).toBeNull();
  });

  test("a run that carries only a view by the graph kind it was joined from", () => {
    expect(workflowOf({ ...NONE, viewKind: "gnode-run-view-v1", graphKind: "contained-figure-rig-v1" }, known)).toBe(
      "figure-rig",
    );
    expect(workflowOf({ ...NONE, document: "graph.json", kind: "contained-figure-rig-v1" }, known)).toBe(
      "figure-rig",
    );
    expect(workflowOf({ ...NONE, viewKind: "gnode-run-view-v1", graphKind: "unknown-v1" }, known)).toBeNull();
  });

  test("runs no workflow claims are game runs when a game wrote them, else other", () => {
    expect(isGameRun({ ...NONE, document: "manifest.json", kind: "prepared-game-runtime-v12" })).toBe(true);
    expect(isGameRun({ ...NONE, document: "case.json" })).toBe(true);
    expect(isGameRun({ ...NONE, document: "graph.json", kind: "contained-rig-review-calibration-v1" })).toBe(false);

    const run = { document: "plan.json", kind: "gnode-graph-v2", workflowId: "tile-set" };
    const entries = [
      { name: "old", identity: { ...NONE, ...run }, updatedAt: "2026-09-01T00:00:00.000Z" },
      { name: "new", identity: { ...NONE, ...run }, updatedAt: "2026-09-30T00:00:00.000Z" },
      { name: "game", identity: { ...NONE, document: "manifest.json" }, updatedAt: null },
      { name: "calibration", identity: { ...NONE, kind: "contained-rig-review-calibration-v1" }, updatedAt: null },
    ];
    const groups = groupRuns(entries, known);
    expect(groups.workflows.map((group) => group.workflow.id)).toEqual([
      "swatch-sheet",
      "figure-rig",
      "strip-loop",
      "tile-set",
    ]);
    expect(groups.workflows[3].runs.map((entry) => entry.name)).toEqual(["new", "old"]);
    expect(groups.workflows[0].runs).toEqual([]);
    expect(groups.game.map((entry) => entry.name)).toEqual(["game"]);
    expect(groups.other.map((entry) => entry.name)).toEqual(["calibration"]);
  });

  test("without a catalog every run is a game run or another run", () => {
    const groups = groupRuns([{ identity: { ...NONE, document: "bundle.json" }, updatedAt: null }], null);
    expect(groups.workflows).toEqual([]);
    expect(groups.game).toHaveLength(1);
  });
});
