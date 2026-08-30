import { describe, expect, test } from "bun:test";
import {
  executionViewFixture,
  failedExecutionViewFixture,
  inFlightExecutionViewFixture,
} from "@/lib/shell/execution-view.fixture";
import { EXECUTION_VIEW_REFUSAL, parseExecutionView } from "./execution-view";

describe("parseExecutionView", () => {
  test("parses a finished run into camelCase runtime shapes", () => {
    const view = parseExecutionView(executionViewFixture());
    expect(view.gameId).toBe("bellweather");
    expect(view.ok).toBe(true);
    expect(view.nodes).toHaveLength(3);
    expect(view.stateCounts.succeeded).toBe(3);

    const generate = view.nodes[1];
    expect(generate.nodeId).toBe("player-wayfarer-state-idle-generate");
    expect(generate.dependsOn).toEqual(["package-resolve"]);
    expect(generate.state).toBe("succeeded");
    expect(generate.cache).toBe("hit");
    expect(generate.artifacts[0].display).toBe("motion_atlas");
    expect(generate.artifacts[0].motion?.frameCount).toBe(4);
    expect(view.gaps[0].gapId).toBe("edge-kinds-not-distinguished");
  });

  test("keeps in-flight and failed states distinct", () => {
    const inFlight = parseExecutionView(inFlightExecutionViewFixture());
    expect(inFlight.ok).toBeNull();
    expect(inFlight.nodes[1].state).toBe("running");
    expect(inFlight.nodes[2].state).toBe("pending");

    const failed = parseExecutionView(failedExecutionViewFixture());
    expect(failed.ok).toBe(false);
    expect(failed.nodes[1].state).toBe("failed");
    expect(failed.nodes[1].error).toContain("comparison-plate-v1");
    expect(failed.nodes[2].state).toBe("skipped");
    expect(failed.nodes[2].blockedBy).toEqual(["player-wayfarer-state-idle-generate"]);
  });

  test("refuses an unknown version with the re-export message, never migrates", () => {
    const stale = { ...executionViewFixture(), schema_version: 2 };
    expect(() => parseExecutionView(stale)).toThrow(EXECUTION_VIEW_REFUSAL);
    const alien = { ...executionViewFixture(), kind: "someone-elses-view-v1" };
    expect(() => parseExecutionView(alien)).toThrow(EXECUTION_VIEW_REFUSAL);
  });

  test("refuses dangling dependencies and duplicate node ids", () => {
    const document = executionViewFixture();
    const nodes = document.nodes as Record<string, unknown>[];
    nodes[1] = { ...nodes[1], depends_on: ["missing-node"] };
    expect(() => parseExecutionView(document)).toThrow("undeclared node");

    const duplicated = executionViewFixture();
    const duplicateNodes = duplicated.nodes as Record<string, unknown>[];
    duplicateNodes[2] = { ...duplicateNodes[2], node_id: "package-resolve", depends_on: [] };
    expect(() => parseExecutionView(duplicated)).toThrow("unique");
  });
});
