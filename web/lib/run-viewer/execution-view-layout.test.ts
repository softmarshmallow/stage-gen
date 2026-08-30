import { describe, expect, test } from "bun:test";
import { layoutExecutionGraph } from "./execution-view-layout";

const DIAMOND = [
  { nodeId: "root", domain: "package", dependsOn: [] },
  { nodeId: "left", domain: "maps", dependsOn: ["root"] },
  { nodeId: "right", domain: "maps", dependsOn: ["root"] },
  { nodeId: "join", domain: "manifest", dependsOn: ["left", "right"] },
];

describe("layoutExecutionGraph", () => {
  test("columns are longest-path depth and lanes group domains", () => {
    const layout = layoutExecutionGraph(DIAMOND);
    const byId = new Map(layout.nodes.map((node) => [node.id, node]));
    expect(byId.get("root")?.column).toBe(0);
    expect(byId.get("left")?.column).toBe(1);
    expect(byId.get("right")?.column).toBe(1);
    expect(byId.get("join")?.column).toBe(2);

    expect(layout.lanes.map((lane) => lane.domain)).toEqual(["package", "maps", "manifest"]);
    const mapsLane = layout.lanes[1];
    const left = byId.get("left");
    const right = byId.get("right");
    expect(left && left.y >= mapsLane.y).toBe(true);
    expect(right && right.y <= mapsLane.y + mapsLane.height).toBe(true);
    // Same lane, same column: the two chips stack instead of overlapping.
    expect(left?.x).toBe(right?.x);
    expect(left?.y).not.toBe(right?.y);
  });

  test("edges run from the source chip's right edge to the target's left edge", () => {
    const layout = layoutExecutionGraph(DIAMOND);
    const edge = layout.edges.find((entry) => entry.from === "root" && entry.to === "left");
    const byId = new Map(layout.nodes.map((node) => [node.id, node]));
    const root = byId.get("root");
    const left = byId.get("left");
    expect(edge).toBeDefined();
    expect(edge?.x1).toBe((root?.x ?? 0) + layout.chipWidth);
    expect(edge?.x2).toBe(left?.x ?? 0);
    expect(layout.edges).toHaveLength(4);
  });

  test("collapsing a domain contracts its nodes into one chip and dedupes edges", () => {
    const layout = layoutExecutionGraph(DIAMOND, new Set(["maps"]));
    expect(layout.nodes).toHaveLength(3);
    const collapsed = layout.nodes.find((node) => node.id === "domain:maps");
    expect([...(collapsed?.memberIds ?? [])].sort()).toEqual(["left", "right"]);
    // root → maps and maps → join each appear exactly once.
    expect(layout.edges).toHaveLength(2);
    expect(layout.edges.map((edge) => `${edge.from}->${edge.to}`).sort()).toEqual([
      "domain:maps->join",
      "root->domain:maps",
    ]);
  });

  test("a barrier dependency is placed as an edge that says it is one", () => {
    const layout = layoutExecutionGraph([
      { nodeId: "root", domain: "package", dependsOn: [] },
      { nodeId: "paint", domain: "maps", dependsOn: ["root"] },
      {
        nodeId: "admit",
        domain: "maps",
        dependsOn: ["paint", "root"],
        barrierOnly: ["root"],
      },
    ]);
    const barrier = layout.edges.find((edge) => edge.from === "root" && edge.to === "admit");
    const lineage = layout.edges.find((edge) => edge.from === "paint" && edge.to === "admit");
    expect(barrier?.barrier).toBe(true);
    expect(lineage?.barrier).toBe(false);
    // A graph that never names a barrier draws none.
    expect(layoutExecutionGraph(DIAMOND).edges.every((edge) => !edge.barrier)).toBe(true);
  });

  test("a contracted edge is lineage when any edge folded into it was", () => {
    // Collapsing merges two members' edges to the same target. Calling the
    // result a barrier would hide the lineage the pair actually carries.
    const layout = layoutExecutionGraph(
      [
        { nodeId: "root", domain: "package", dependsOn: [] },
        { nodeId: "lineage", domain: "maps", dependsOn: ["root"] },
        { nodeId: "barrier", domain: "maps", dependsOn: ["root"], barrierOnly: ["root"] },
      ],
      new Set(["maps"]),
    );
    expect(layout.edges).toHaveLength(1);
    expect(layout.edges[0].barrier).toBe(false);

    const allBarriers = layoutExecutionGraph(
      [
        { nodeId: "root", domain: "package", dependsOn: [] },
        { nodeId: "one", domain: "maps", dependsOn: ["root"], barrierOnly: ["root"] },
        { nodeId: "two", domain: "maps", dependsOn: ["root"], barrierOnly: ["root"] },
      ],
      new Set(["maps"]),
    );
    expect(allBarriers.edges[0].barrier).toBe(true);
  });

  test("an empty graph lays out to an empty canvas without throwing", () => {
    const layout = layoutExecutionGraph([]);
    expect(layout.nodes).toHaveLength(0);
    expect(layout.edges).toHaveLength(0);
    expect(layout.lanes).toHaveLength(0);
  });

  test("collapsing a domain that a dependency chain re-enters does not crash", () => {
    // The real room shape: room -> hotspots -> room. Contracting "room" folds
    // this legal acyclic document into a cyclic layout graph; the back-edge is
    // a layout artifact and must be broken, not thrown.
    const REENTRANT = [
      { nodeId: "resolve", domain: "room", dependsOn: [] },
      { nodeId: "style", domain: "room", dependsOn: ["resolve"] },
      { nodeId: "sprite", domain: "hotspots", dependsOn: ["style"] },
      { nodeId: "bundle", domain: "room", dependsOn: ["sprite", "style"] },
    ];
    const layout = layoutExecutionGraph(REENTRANT, new Set(["room"]));
    expect(layout.nodes.map((node) => node.id).sort()).toEqual(["domain:room", "sprite"]);
    const layoutAll = layoutExecutionGraph(REENTRANT, new Set(["room", "hotspots"]));
    expect(layoutAll.nodes).toHaveLength(2);
  });

  test("a single-node domain never contracts into a synthetic super-chip", () => {
    const layout = layoutExecutionGraph(DIAMOND, new Set(["package", "manifest"]));
    // package and manifest each hold one node: they keep their real ids, so
    // selection and the inspector keep working.
    expect(layout.nodes.map((node) => node.id).sort()).toEqual([
      "join",
      "left",
      "right",
      "root",
    ]);
    expect(layout.nodes.every((node) => node.memberIds.length === 1)).toBe(true);
  });
});
