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

  test("an empty graph lays out to an empty canvas without throwing", () => {
    const layout = layoutExecutionGraph([]);
    expect(layout.nodes).toHaveLength(0);
    expect(layout.edges).toHaveLength(0);
    expect(layout.lanes).toHaveLength(0);
  });
});
