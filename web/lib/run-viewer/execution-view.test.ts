import { describe, expect, test } from "bun:test";
import {
  executionViewFixture,
  failedExecutionViewFixture,
  unfinishedExecutionViewFixture,
} from "@/lib/shell/execution-view.fixture";
import {
  EXECUTION_VIEW_REFUSAL,
  parseExecutionView,
  RUNNING_TRACE_STALENESS_MS,
  runLiveness,
} from "./execution-view";

describe("parseExecutionView", () => {
  test("parses a finished run into camelCase runtime shapes", () => {
    const view = parseExecutionView(executionViewFixture());
    expect(view.gameId).toBe("bellweather");
    expect(view.runState).toBe("succeeded");
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

describe("runLiveness", () => {
  const written = Date.parse("2026-08-30T12:00:00Z");

  test("a finished run reports what its records say, whatever the clock says", () => {
    const view = parseExecutionView(executionViewFixture());
    expect(runLiveness(view, written + 10 * 365 * 24 * 60 * 60 * 1000)).toBe("succeeded");
    expect(runLiveness(parseExecutionView(failedExecutionViewFixture()), written)).toBe("failed");
  });

  test("an unfinished run is running only while its trace is still fresh", () => {
    const view = parseExecutionView(unfinishedExecutionViewFixture());
    expect(runLiveness(view, written + 1_000)).toBe("running");
    expect(runLiveness(view, written + RUNNING_TRACE_STALENESS_MS)).toBe("running");
    expect(runLiveness(view, written + RUNNING_TRACE_STALENESS_MS + 1)).toBe("interrupted");
    // Days later — the case that used to read "in flight" for a dead run.
    expect(runLiveness(view, written + 3 * 24 * 60 * 60 * 1000)).toBe("interrupted");
  });

  test("an unfinished run with no readable stamp never claims to be running", () => {
    expect(runLiveness(parseExecutionView(unfinishedExecutionViewFixture(null)), written)).toBe(
      "interrupted",
    );
  });
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
    expect(failed.nodes[2].blockedBy).toEqual(["player-wayfarer-state-idle-generate"]);
  });

  test("refuses an unknown version with the re-export message, never migrates", () => {
    const stale = { ...executionViewFixture(), schema_version: 1 };
    expect(() => parseExecutionView(stale)).toThrow(EXECUTION_VIEW_REFUSAL);
    const alien = { ...executionViewFixture(), kind: "someone-elses-view-v1" };
    expect(() => parseExecutionView(alien)).toThrow(EXECUTION_VIEW_REFUSAL);
  });

  test("refuses a run_state outside the declared vocabulary", () => {
    const alien = { ...executionViewFixture(), run_state: "in flight" };
    expect(() => parseExecutionView(alien)).toThrow("run_state must be one of");
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
