import { afterAll, afterEach, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  dialogueExecutionViewFixture,
  pipelineExecutionViewFixture,
  executionViewFixture,
  failedExecutionViewFixture,
  unfinishedExecutionViewFixture,
} from "@stage-gen/ui/contracts/run-view.test-fixtures";
import {
  type ExecutionViewNode,
  parseExecutionView,
} from "@stage-gen/ui/contracts/run-view";
import type { RunRef } from "@/lib/shell/run-ref";
import { runDirFor, runRoots, viewKey } from "@/lib/shell/runs";
import NodeInspector from "./Inspector";
import MotionPlayer from "./MotionPlayer";
import { parseViewContexts } from "@stage-gen/ui/contracts/view-context";
import RunPage from "./page";
import RunViewer from "./RunViewer";

function inspect(
  nodes: readonly ExecutionViewNode[],
  nodeId: string,
  run: RunRef = { root: "out-000000", tag: "fixture-tag" },
  contexts: unknown = null,
): string {
  const byId = new Map(nodes.map((node) => [node.nodeId, node]));
  const node = byId.get(nodeId);
  if (!node) throw new Error(`fixture has no node ${nodeId}`);
  const views = contexts === null ? null : parseViewContexts(contexts);
  return renderToStaticMarkup(
    <NodeInspector
      run={run}
      node={node}
      nodesById={byId}
      liveness="succeeded"
      onSelect={() => {}}
      view={views?.views.find((item) => item.nodeId === nodeId) ?? null}
    />,
  );
}

const TEMPLATE = `views/${"a".repeat(64)}.html`;

function viewContexts(nodeId: string) {
  return {
    kind: "gnode-view-contexts-v1",
    view_origins: [],
    views: [
      {
        kind: "gnode-view-context-v1",
        scope: "node",
        node_id: nodeId,
        template: TEMPLATE,
        step: { path: "compose", title: "Compose the scrolling background", status: "succeeded", with: {} },
        run: { id: "run", workflow: "looping-parallax", status: "succeeded", cost_usd: 0 },
        inputs: { layers: { sky: { kind: "image/png", digest: "b".repeat(64), size: 3, key: "sky", ref: `views/files/${"b".repeat(64)}.png` } } },
        outputs: {},
        facts: {},
      },
    ],
  };
}

// Every run these tests write sits under a temporary root, never under out/.
const saved = {
  STAGE_GEN_RUN_ROOTS: process.env.STAGE_GEN_RUN_ROOTS,
  STAGE_GEN_VIEW_CACHE: process.env.STAGE_GEN_VIEW_CACHE,
};
let base = "";
const cleanup: string[] = [];

beforeAll(async () => {
  base = await realpath(await mkdtemp(path.join(tmpdir(), "stage-gen-run-page-")));
  process.env.STAGE_GEN_RUN_ROOTS = path.join(base, "out");
  process.env.STAGE_GEN_VIEW_CACHE = path.join(base, "views");
});

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

afterAll(async () => {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  await rm(base, { recursive: true, force: true });
});

function runOf(tag: string): RunRef {
  return { root: runRoots()[0].key, tag };
}

async function writeFiles(tag: string, files: Readonly<Record<string, unknown>>): Promise<RunRef> {
  const run = runOf(tag);
  const runDir = runDirFor(run);
  cleanup.push(runDir);
  for (const [name, document] of Object.entries(files)) {
    await mkdir(path.dirname(path.join(runDir, name)), { recursive: true });
    await writeFile(path.join(runDir, name), JSON.stringify(document), "utf8");
  }
  return run;
}

async function writeRun(tag: string, document: Record<string, unknown>): Promise<RunRef> {
  return writeFiles(tag, { "execution-view.json": document });
}

async function page(run: RunRef, view?: string): Promise<string> {
  return renderToStaticMarkup(
    await RunPage({
      params: Promise.resolve(run),
      searchParams: Promise.resolve(view ? { view } : {}),
    }),
  );
}

describe("run view route", () => {
  test("renders a custom pipeline, and a step's own view in a sandboxed frame", async () => {
    const document = pipelineExecutionViewFixture();
    const tag = `run-view-custom-${process.pid}`;
    const view = parseExecutionView(document);
    const contexts = viewContexts(view.nodes[0].nodeId);
    const run = await writeFiles(tag, {
      "execution-view.json": document,
      "view-contexts.json": contexts,
    });
    const markup = await page(run);
    expect(markup).toContain("Material study");
    expect(markup).toContain("user.tools-material-set");
    expect(markup).not.toContain(">game<");
    const inspector = inspect(view.nodes, view.nodes[0].nodeId, run, contexts);
    expect(inspector).toContain('sandbox="allow-scripts"');
    expect(inspector).toContain(`src="/api/assets/${run.root}/${tag}/${TEMPLATE}"`);
    expect(inspector).toContain('title="Compose the scrolling background"');
    expect(inspect(view.nodes, view.nodes[0].nodeId, run)).not.toContain("<iframe");
  });

  test("a view contexts file this build cannot read refuses the page, not crashes it", async () => {
    const document = pipelineExecutionViewFixture();
    const run = await writeFiles(`run-view-bad-views-${process.pid}`, {
      "execution-view.json": document,
      "view-contexts.json": { kind: "gnode-view-contexts-v0", views: [] },
    });
    expect(await page(run)).toContain("unsupported view contexts");
  });

  test("renders the graph chips, states, and run facts for a finished run", async () => {
    const tag = `run-view-page-${process.pid}`;
    const run = await writeRun(tag, executionViewFixture());

    const markup = await page(run);

    expect(markup).toContain("package-resolve");
    expect(markup).toContain("player-wayfarer-state-idle-generate");
    expect(markup).toContain("4 succeeded");
    expect(markup).toContain("bellweather");
    expect(markup).toContain("node-type-not-registered");
    expect(markup).toContain(`href="/"`);
    // Wire snake_case never leaks into the page markup as attribute soup.
    expect(markup).not.toContain("node_id");
  });

  test("chips wear the node's title, disambiguated, with the id still on hover", () => {
    const view = parseExecutionView(executionViewFixture());
    const markup = renderToStaticMarkup(
      <RunViewer run={runOf("fixture")} view={view} liveness="succeeded" />,
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
    const run = await writeRun(tag, failedExecutionViewFixture());

    const markup = await page(run);
    expect(markup).toContain("1 failed");
    expect(markup).toContain("2 skipped");
    expect(markup).toContain("failed");
  });

  test("shows a stopped run as interrupted, not as still running", async () => {
    const tag = `run-view-page-stopped-${process.pid}`;
    const run = await writeRun(
      tag,
      unfinishedExecutionViewFixture(new Date(Date.now() - 3 * 86_400_000).toISOString()),
    );

    const markup = await page(run);
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
    const run = await writeRun(tag, unfinishedExecutionViewFixture(new Date().toISOString()));

    const markup = await page(run);
    expect(markup).toContain("· running ·");
    expect(markup).toContain("1 running");
    expect(markup).not.toContain("abandoned");
  });

  test("puts the graph full-bleed under a floating panel that owns the trackpad", async () => {
    const tag = `run-view-page-canvas-${process.pid}`;
    const run = await writeRun(tag, executionViewFixture());

    const markup = await page(run);

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

  test("draws a nested run from the view stage-gen view derived into its cache", async () => {
    const run = runOf("review~yuzu~run-01");
    const runDir = runDirFor(run);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(path.join(runDir, "plan.json"), "{}", "utf8");
    await writeFile(path.join(runDir, "events.jsonl"), "", "utf8");
    const cached = path.join(process.env.STAGE_GEN_VIEW_CACHE ?? "", viewKey(runDir));
    cleanup.push(cached);
    await mkdir(cached, { recursive: true });
    await writeFile(path.join(cached, "execution-view.json"), JSON.stringify(executionViewFixture()), "utf8");

    const markup = await page(run);
    expect(markup).toContain("review/yuzu/run-01");
    expect(markup).toContain("player-wayfarer-state-idle-generate");
    expect(markup).toContain(`/runs/${run.root}/review~yuzu~run-01/artifacts`);
  });

  test("a game run without a view says its game exports one", async () => {
    const run = await writeFiles("bellweather-m21", {
      "execution-plan.json": { kind: "sideview-platformer-execution-graph-v2", recipe: "sideview-platformer" },
    });
    const markup = await page(run);
    expect(markup).toContain("View not exported");
    expect(markup).toContain("demo-games export-view --run");
    expect(markup).toContain("game run");
  });

  test("a run without a view says so and how a view is made", async () => {
    const run = await writeFiles("prepared-01", {
      "plan.json": { gnode: "plan/v1" },
      "events.jsonl": "",
    });
    const markup = await page(run);
    expect(markup).toContain("has no view yet");
    expect(markup).toContain("--write-view");
    // Asked for the graph, a run without a view refuses instead of guessing.
    expect(await page(run, "graph")).toContain("no execution view to draw");
  });

  test("refuses an unknown run root or an unsafe tag", async () => {
    await expect(page({ root: "nowhere-000000", tag: "x" })).rejects.toThrow();
    await expect(page(runOf("a~.."))).rejects.toThrow();
  });

  test("refuses an unknown schema version with the re-derive message", async () => {
    const tag = `run-view-page-stale-${process.pid}`;
    const run = await writeRun(tag, { ...executionViewFixture(), schema_version: 99 });

    const markup = await page(run);
    expect(markup).toContain("derive it again");
    expect(markup).toContain("stage-gen inspect RUN --write-view");
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
    const markup = inspect(platformer, "player-wayfarer-state-idle-validate", {
      root: "out-1a2b3c",
      tag: "batch~run-tag",
    });
    expect(markup).toContain(
      'src="/api/assets/out-1a2b3c/batch~run-tag/content/players/wayfarer/states/idle.source.png"',
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
