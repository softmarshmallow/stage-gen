import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import {
  executionViewFixture,
  pipelineExecutionViewFixture,
  unfinishedExecutionViewFixture,
} from "@stage-gen/ui/contracts/run-view.test-fixtures";
import { type ViewerEnv, viewerEnv } from "@/lib/test-support/viewer-env";
import Home from "./page";
import WorkflowPage from "./workflows/[id]/page";

let env: ViewerEnv;

beforeAll(async () => {
  env = await viewerEnv();
  await env.write("swatch-old", {
    "execution-plan.json": { kind: "pipeline-execution-graph-v1", pipeline_id: "swatch-sheet" },
    "execution-view.json": { ...pipelineExecutionViewFixture(), pipeline_id: "swatch-sheet" },
  });
  await env.write("batch~swatch-live", {
    "execution-plan.json": { kind: "pipeline-execution-graph-v1", pipeline_id: "swatch-sheet" },
    "execution-view.json": {
      ...unfinishedExecutionViewFixture(new Date().toISOString()),
      kind: "pipeline-execution-view-v1",
      pipeline_id: "swatch-sheet",
      title: "Swatch sheet",
    },
  });
  await env.write("bellweather-m21", {
    "execution-plan.json": { kind: "sideview-platformer-execution-graph-v2", recipe: "sideview-platformer" },
  });
  await env.write("calibration-01", {
    "plan.json": { gnode: "plan/v1", workflow: { id: "no-such-workflow" } },
    "events.jsonl": "",
  });
  await env.write("old-platformer", { "execution-view.json": executionViewFixture() });
});

afterAll(async () => {
  await env.restore();
});

describe("home", () => {
  test("groups runs under each workflow's title and promise, newest first", async () => {
    const markup = renderToStaticMarkup(await Home());
    expect(markup).toContain("Swatch sheet");
    expect(markup).toContain("One brief in. A checked sheet of material swatches out.");
    expect(markup).toContain('href="/workflows/swatch-sheet"');
    expect(markup).toContain("2 runs");
    expect(markup).toContain("1 running");
    expect(markup).toContain(`href="/runs/${env.run("swatch-old").root}/batch~swatch-live"`);
    expect(markup).toContain("batch/swatch-live");
    expect(markup.indexOf("batch/swatch-live")).toBeLessThan(markup.indexOf("swatch-old"));
    // Liveness and last change are on every row.
    expect(markup).toContain(">running<");
    expect(markup).toContain("just now");
    expect(markup).toContain("refreshing while a run is live");
  });

  test("lists game runs and other runs after the workflows, folded", async () => {
    const markup = renderToStaticMarkup(await Home());
    expect(markup.indexOf("Game runs")).toBeGreaterThan(markup.indexOf("Swatch sheet"));
    expect(markup).toContain("view not exported");
    expect(markup).toContain("bellweather-m21");
    expect(markup).toContain("old-platformer");
    expect(markup).toContain("Other runs");
    expect(markup).toContain("calibration-01");
    expect(markup).not.toContain("stage-gen generate");
  });
});

describe("workflow page", () => {
  test("shows the promise, copyable commands, the offline plan and the workflow's runs", async () => {
    const markup = renderToStaticMarkup(
      await WorkflowPage({ params: Promise.resolve({ id: "swatch-sheet" }) }),
    );
    expect(markup).toContain("One brief in. A checked sheet of material swatches out.");
    expect(markup).toContain("uv run gnode plan swatch-sheet --inputs");
    expect(markup).toContain("gnode schema swatch-sheet");
    expect(markup).toContain("[ copy ]");
    // The plan is drawn by the run viewer, embedded and with nothing run.
    expect(markup).toContain("planned offline");
    expect(markup).toContain("Draw the swatch sheet");
    expect(markup).toContain("data-graph-surface");
    expect(markup).toContain("absolute top-3 right-3 bottom-3");
    expect(markup).toContain("batch/swatch-live");
  });

  test("an unknown workflow is not found", async () => {
    await expect(WorkflowPage({ params: Promise.resolve({ id: "no-such-workflow" }) })).rejects.toThrow();
  });
});
