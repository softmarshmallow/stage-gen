import { describe, expect, test } from "bun:test";
import { executionViewFixture } from "@/lib/shell/execution-view.fixture";
import {
  type ExecutionViewNode,
  parseExecutionView,
  type ViewArchetype,
} from "./execution-view";
import {
  isPrompted,
  nodeChipLabel,
  nodeHeading,
  resolveReferenceInputs,
  sidecarRefFor,
  verdictPort,
} from "./execution-view-node";

function fixtureNodes(): {
  nodes: readonly ExecutionViewNode[];
  byId: ReadonlyMap<string, ExecutionViewNode>;
} {
  const nodes = parseExecutionView(executionViewFixture()).nodes;
  return { nodes, byId: new Map(nodes.map((node) => [node.nodeId, node])) };
}

describe("nodeHeading", () => {
  test("prefers the registry title", () => {
    const { nodes } = fixtureNodes();
    expect(nodeHeading(nodes[1])).toBe("Motion atlas");
  });

  test("falls back to the tail of the taxonomy path, then to the id", () => {
    const { nodes } = fixtureNodes();
    const untitled = { ...nodes[1], title: null };
    expect(nodeHeading(untitled)).toBe("platformer/motion_atlas.generate");
    expect(nodeHeading({ ...untitled, typeId: "orphan" })).toBe("orphan");
    expect(nodeHeading({ ...untitled, typeId: "" })).toBe(untitled.nodeId);
  });
});

describe("nodeChipLabel", () => {
  test("disambiguates two instances of one type by their most specific param", () => {
    const { nodes } = fixtureNodes();
    expect(nodeChipLabel(nodes[1])).toBe("Motion atlas · idle");
    // state beats actor_id: the actor is already the lane, the state is not.
    expect(nodeChipLabel({ ...nodes[1], params: { actor_id: "wayfarer" } })).toBe(
      "Motion atlas · wayfarer",
    );
    expect(nodeChipLabel({ ...nodes[1], params: {} })).toBe("Motion atlas");
  });

  test("an untitled node keeps its id rather than inventing a name", () => {
    const { nodes } = fixtureNodes();
    expect(nodeChipLabel({ ...nodes[1], title: null })).toBe(nodes[1].nodeId);
  });
});

describe("sidecarRefFor", () => {
  test("prefers the port's declared pairing over the naming convention", () => {
    const { nodes } = fixtureNodes();
    expect(sidecarRefFor(nodes[1], nodes[1].artifacts[0].artifactRef)).toBe(
      "content/players/wayfarer/states/idle.source.png.provenance.json",
    );
  });

  test("falls back to the convention for an artifact no port covers", () => {
    const { nodes } = fixtureNodes();
    expect(sidecarRefFor(nodes[1], "stray/extra.png")).toBe("stray/extra.png.meta.json");
    // A port that declares no sidecar is not a declaration to honour.
    expect(sidecarRefFor(nodes[0], "package.identity.json")).toBe(
      "package.identity.json.meta.json",
    );
  });
});

describe("resolveReferenceInputs", () => {
  test("joins a card reference to the upstream port and its written artifact", () => {
    const { nodes, byId } = fixtureNodes();
    const resolved = resolveReferenceInputs(nodes[3].card, byId);
    expect(resolved).toHaveLength(1);
    expect(resolved[0].node?.nodeId).toBe("player-wayfarer-state-idle-generate");
    expect(resolved[0].port?.kind).toBe("motion-atlas-v1");
    expect(resolved[0].artifact?.present).toBe(true);
  });

  test("a reference whose run has not written the artifact resolves to the port alone", () => {
    const { nodes, byId } = fixtureNodes();
    const pending = new Map(byId);
    pending.set("player-wayfarer-state-idle-generate", {
      ...nodes[1],
      state: "pending",
      artifacts: [],
    });
    const resolved = resolveReferenceInputs(nodes[3].card, pending);
    expect(resolved[0].port?.artifactRef).toBe(
      "content/players/wayfarer/states/idle.source.png",
    );
    expect(resolved[0].artifact).toBeNull();
  });

  test("a node with no card has nothing to resolve", () => {
    const { byId } = fixtureNodes();
    expect(resolveReferenceInputs(null, byId)).toHaveLength(0);
  });
});

describe("verdictPort", () => {
  test("offers a succeeded judge's written answer", () => {
    const { nodes } = fixtureNodes();
    expect(verdictPort(nodes[3])?.portId).toBe("verdict");
  });

  test("offers nothing for a non-judge, an unfinished judge, or an unwritten answer", () => {
    const { nodes } = fixtureNodes();
    expect(verdictPort(nodes[1])).toBeNull();
    expect(verdictPort({ ...nodes[3], state: "failed" })).toBeNull();
    expect(verdictPort({ ...nodes[3], artifacts: [] })).toBeNull();
  });

  test("recognises a reading as well as a verdict", () => {
    const { nodes } = fixtureNodes();
    const reading = {
      ...nodes[3],
      ports: [{ ...nodes[3].ports[0], portId: "reading", kind: "rebase-reading-v1" }],
    };
    expect(verdictPort(reading)?.portId).toBe("reading");
  });
});

describe("isPrompted", () => {
  test("only the archetypes a prompt actually defines", () => {
    const prompted: readonly ViewArchetype[] = ["image", "matte", "music", "structured", "judge"];
    const local: readonly ViewArchetype[] = [
      "source",
      "transform",
      "validate",
      "review",
      "package",
    ];
    expect(prompted.every(isPrompted)).toBe(true);
    expect(local.some(isPrompted)).toBe(false);
    expect(isPrompted(null)).toBe(false);
  });
});
