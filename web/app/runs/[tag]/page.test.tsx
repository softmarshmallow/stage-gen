import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  executionViewFixture,
  failedExecutionViewFixture,
  inFlightExecutionViewFixture,
} from "@/lib/shell/execution-view.fixture";
import { runDirFor } from "@/lib/shell/runs";
import MotionPlayer from "./MotionPlayer";
import RunPage from "./page";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

async function writeRun(tag: string, document: Record<string, unknown>): Promise<void> {
  const runDir = runDirFor(tag);
  cleanup.push(runDir);
  await mkdir(runDir, { recursive: true });
  await writeFile(path.join(runDir, "execution-view.json"), JSON.stringify(document), "utf8");
}

describe("run view route", () => {
  test("renders the graph chips, states, and run facts for a finished run", async () => {
    const tag = `run-view-page-${process.pid}`;
    await writeRun(tag, executionViewFixture());

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));

    expect(markup).toContain("package-resolve");
    expect(markup).toContain("player-wayfarer-state-idle-generate");
    expect(markup).toContain("3 succeeded");
    expect(markup).toContain("bellweather");
    expect(markup).toContain("edge-kinds-not-distinguished");
    expect(markup).toContain(`href="/runs"`);
    // Wire snake_case never leaks into the page markup as attribute soup.
    expect(markup).not.toContain("node_id");
  });

  test("keeps failed and skipped visible with the failure text on the summary strip", async () => {
    const tag = `run-view-page-failed-${process.pid}`;
    await writeRun(tag, failedExecutionViewFixture());

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("1 failed");
    expect(markup).toContain("1 skipped");
    expect(markup).toContain("failed");
  });

  test("shows in-flight runs as in flight, not done", async () => {
    const tag = `run-view-page-inflight-${process.pid}`;
    await writeRun(tag, inFlightExecutionViewFixture());

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("in flight");
    expect(markup).toContain("1 running");
    expect(markup).toContain("1 pending");
  });

  test("puts the graph full-bleed under a floating panel that owns the trackpad", async () => {
    const tag = `run-view-page-canvas-${process.pid}`;
    await writeRun(tag, executionViewFixture());

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));

    // Full-bleed canvas with the inspector floating over it, not beside it.
    expect(markup).toContain("fixed inset-0 overflow-hidden");
    expect(markup).toContain('aria-label="Node inspector"');
    expect(markup).toContain("fixed top-3 right-3 bottom-3");
    // The surface owns pan and pinch, so the browser never spends a
    // two-finger swipe on back-navigation or a pinch on page zoom.
    expect(markup).toContain("data-graph-surface");
    expect(markup).toContain("touch-none overscroll-none");
    // Camera lives in a transform, not in a scroll offset.
    expect(markup).toContain("scale(1)");
  });

  test("refuses an unknown schema version with the re-export message", async () => {
    const tag = `run-view-page-stale-${process.pid}`;
    await writeRun(tag, { ...executionViewFixture(), schema_version: 99 });

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("re-export this run");
    expect(markup).toContain("stage-gen export-view");
    expect(markup).not.toContain("package-resolve");
  });
});

describe("MotionPlayer", () => {
  test("initial markup shows frame one and the play control", () => {
    const markup = renderToStaticMarkup(
      <MotionPlayer
        url="/api/assets/tag/content/players/wayfarer/states/idle.png"
        frameCount={4}
        framesPerSecond={null}
        label="idle strip"
      />,
    );
    expect(markup).toContain("1/4");
    expect(markup).toContain("▶");
    expect(markup).toContain("alpha-checker");
    expect(markup).toContain("frame 1 of 4");
  });
});
