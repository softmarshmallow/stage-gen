import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  dialogueExecutionViewFixture,
  executionViewFixture,
  failedExecutionViewFixture,
  unfinishedExecutionViewFixture,
} from "@/lib/shell/execution-view.fixture";
import {
  type ExecutionViewNode,
  parseExecutionView,
} from "@/lib/run-viewer/execution-view";
import { runDirFor } from "@/lib/shell/runs";
import NodeInspector from "./Inspector";
import MotionPlayer from "./MotionPlayer";
import RunPage from "./page";
import RunViewer from "./RunViewer";

function inspect(
  nodes: readonly ExecutionViewNode[],
  nodeId: string,
  tag = "fixture-tag",
): string {
  const byId = new Map(nodes.map((node) => [node.nodeId, node]));
  const node = byId.get(nodeId);
  if (!node) throw new Error(`fixture has no node ${nodeId}`);
  return renderToStaticMarkup(
    <NodeInspector
      tag={tag}
      node={node}
      nodesById={byId}
      liveness="succeeded"
      onSelect={() => {}}
    />,
  );
}

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
    expect(markup).toContain("4 succeeded");
    expect(markup).toContain("bellweather");
    expect(markup).toContain("node-type-not-registered");
    expect(markup).toContain(`href="/runs"`);
    // Wire snake_case never leaks into the page markup as attribute soup.
    expect(markup).not.toContain("node_id");
  });

  test("chips wear the node's title, disambiguated, with the id still on hover", () => {
    const view = parseExecutionView(executionViewFixture());
    const markup = renderToStaticMarkup(
      <RunViewer tag="fixture" view={view} liveness="succeeded" />,
    );
    expect(markup).toContain("Motion atlas · idle");
    expect(markup).toContain("Motion atlas admission · idle");
    expect(markup).toContain(`title="player-wayfarer-state-idle-generate"`);
    // The barrier edge is drawn, and drawn differently from the lineage edges.
    expect(markup).toContain('stroke-dasharray="4 4"');
    expect(markup.match(/stroke-dasharray="4 4"/g)).toHaveLength(1);
  });

  test("keeps failed and skipped visible with the failure text on the summary strip", async () => {
    const tag = `run-view-page-failed-${process.pid}`;
    await writeRun(tag, failedExecutionViewFixture());

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("1 failed");
    expect(markup).toContain("2 skipped");
    expect(markup).toContain("failed");
  });

  test("shows a stopped run as interrupted, not as still running", async () => {
    const tag = `run-view-page-stopped-${process.pid}`;
    await writeRun(
      tag,
      unfinishedExecutionViewFixture(new Date(Date.now() - 3 * 86_400_000).toISOString()),
    );

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("interrupted");
    expect(markup).not.toContain("in flight");
    // The node started and nobody finished it. Calling that "running" three days
    // later is the same lie one level down.
    expect(markup).toContain("1 abandoned");
    expect(markup).not.toContain("1 running");
    expect(markup).toContain("2 pending");
    // The evidence behind the verdict is on the page, not just the verdict.
    expect(markup).toContain("last event");
  });

  test("a run whose trace is still fresh is shown as running", async () => {
    const tag = `run-view-page-running-${process.pid}`;
    await writeRun(tag, unfinishedExecutionViewFixture(new Date().toISOString()));

    const markup = renderToStaticMarkup(await RunPage({ params: Promise.resolve({ tag }) }));
    expect(markup).toContain("· running ·");
    expect(markup).toContain("1 running");
    expect(markup).not.toContain("abandoned");
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

describe("node inspector, per archetype", () => {
  const platformer = parseExecutionView(executionViewFixture()).nodes;
  const dialogue = parseExecutionView(dialogueExecutionViewFixture()).nodes;

  test("every node leads with its title, type id, params and ports", () => {
    const markup = inspect(platformer, "player-wayfarer-state-idle-generate");
    expect(markup).toContain("Motion atlas");
    expect(markup).toContain("2d/sideview/platformer/motion_atlas.generate");
    expect(markup).toContain("actor_id");
    expect(markup).toContain("wayfarer");
    expect(markup).toContain("motion-atlas-v1");
    // The archetype is named, so a reader can tell which view they are in.
    expect(markup).toContain("image");
  });

  test("an image node shows its prompt, and its reference input as a thumbnail", () => {
    const markup = inspect(platformer, "player-wayfarer-state-idle-generate");
    expect(markup).toContain("definition");
    expect(markup).toContain("four-frame idle strip");
    expect(markup).toContain("reference inputs (1)");
    expect(markup).toContain("package-resolve");
    expect(markup).toContain("package-identity-v1");
  });

  test("a pending upstream reference reads as a port, not as a broken image", () => {
    const pending = parseExecutionView(unfinishedExecutionViewFixture()).nodes;
    const markup = inspect(pending, "player-wayfarer-state-idle-validate");
    expect(markup).toContain("reference inputs (1)");
    expect(markup).toContain("not written yet");
    expect(markup).not.toContain("<img");
  });

  test("a judge node shows its schema, its template, and offers to read the verdict", () => {
    const markup = inspect(platformer, "player-wayfarer-review");
    expect(markup).toContain("prepared_actor_review");
    expect(markup).toContain("actor-pipeline@v1:wayfarer");
    expect(markup).toContain("read verdict");
    // The raw artifact stays one click away whatever the panel does with it.
    expect(markup).toContain("{ } open");
    expect(markup).toContain("review-verdict-v1");
  });

  test("a resolved reference renders the upstream artwork as a clickable thumbnail", () => {
    const markup = inspect(platformer, "player-wayfarer-state-idle-validate", "run-tag");
    expect(markup).toContain(
      'src="/api/assets/run-tag/content/players/wayfarer/states/idle.source.png"',
    );
    expect(markup).toContain("alpha-checker");
    expect(markup).not.toContain("not written yet");
    expect(markup).not.toContain("not on disk");
  });

  test("a validate node gets ports and references but never a prompt block", () => {
    const markup = inspect(platformer, "player-wayfarer-state-idle-validate");
    expect(markup).toContain("motion-atlas-validation-v1");
    expect(markup).toContain("reference inputs (1)");
    expect(markup).not.toContain("<summary");
    expect(markup).not.toContain("read verdict");
    // A barrier dependency is marked as one in the facts, not silently equal.
    expect(markup).toContain("cache barrier");
  });

  test("a source node has no definition beyond the ports it fills", () => {
    const markup = inspect(platformer, "package-resolve");
    expect(markup).toContain("package-identity-v1");
    expect(markup).not.toContain("reference inputs");
    expect(markup).not.toContain("<summary");
  });

  test("the dialogue recipe's own archetypes render from the same switch", () => {
    const concept = inspect(dialogue, "portrait-concept-generate");
    expect(concept).toContain("portrait_frame_1x1_template_v1");
    expect(concept).toContain("Front-facing appearance concept");

    const matte = inspect(dialogue, "sprite-matte");
    expect(matte).toContain("matte");
    expect(matte).toContain("Remove the background");
    expect(matte).toContain("matte-raw-v1");

    const bundle = inspect(dialogue, "bundle-package");
    expect(bundle).toContain("dialogue-bundle-v1");
    expect(bundle).not.toContain("<summary");
  });

  test("provenance is fetched from the port's declared sidecar, not a guess", () => {
    const markup = inspect(platformer, "player-wayfarer-state-idle-generate");
    // The declared pairing is .provenance.json here; the convention would have
    // guessed .meta.json and 404ed.
    expect(markup).toContain("load provenance");
    expect(markup).not.toContain("idle.source.png.meta.json");
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
