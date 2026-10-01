import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  artifactPathFor,
  discoverRuns,
  findRepoRoot,
  isSafeRunTag,
  rootKey,
  runDirFor,
  runRoots,
} from "./runs";
import { relativeOf, runHref, tagFor } from "./run-ref";

const CHECKOUT = path.resolve(import.meta.dir, "../../../..");

const saved = {
  STAGE_GEN_REPO_ROOT: process.env.STAGE_GEN_REPO_ROOT,
  STAGE_GEN_RUN_ROOTS: process.env.STAGE_GEN_RUN_ROOTS,
};
const scratch: string[] = [];

afterEach(async () => {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  await Promise.all(scratch.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function tempDir(prefix: string): Promise<string> {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), prefix)));
  scratch.push(dir);
  return dir;
}

async function write(file: string, document: unknown = {}): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, typeof document === "string" ? document : JSON.stringify(document));
}

describe("repository root", () => {
  test("is found from web/ and web/viewer with no setting", () => {
    for (const start of ["web", "web/viewer", "web/viewer/lib/shell"]) {
      expect(findRepoRoot(path.join(CHECKOUT, start), {})).toBe(CHECKOUT);
    }
  });

  test("skips a pyproject that names another project and refuses when none is found", async () => {
    const root = await tempDir("stage-gen-root-");
    const nested = path.join(root, "checkout", "web", "viewer");
    await mkdir(nested, { recursive: true });
    await writeFile(path.join(root, "checkout", "web", "pyproject.toml"), '[project]\nname = "stage-gen-web"\n');
    await writeFile(
      path.join(root, "checkout", "pyproject.toml"),
      '[build-system]\nrequires = []\n\n[project]\nname = "stage-gen"\nversion = "0"\n\n[tool.uv]\nname = "x"\n',
    );
    expect(findRepoRoot(nested, {})).toBe(path.join(root, "checkout"));
    await writeFile(
      path.join(root, "checkout", "pyproject.toml"),
      '[project]\nversion = "0"\n\n[tool.other]\nname = "stage-gen"\n',
    );
    expect(() => findRepoRoot(nested, {})).toThrow("no stage-gen checkout");
  });

  test("an explicit STAGE_GEN_REPO_ROOT wins over the walk", () => {
    expect(findRepoRoot(path.join(CHECKOUT, "web"), { STAGE_GEN_REPO_ROOT: " /elsewhere " })).toBe(
      path.resolve("/elsewhere"),
    );
  });
});

describe("run roots", () => {
  test("default to out/ of the checkout when stage-gen view set none", () => {
    delete process.env.STAGE_GEN_REPO_ROOT;
    delete process.env.STAGE_GEN_RUN_ROOTS;
    const [only, ...rest] = runRoots();
    expect(rest).toEqual([]);
    expect(only.label).toBe("out");
    expect(path.basename(only.dir)).toBe("out");
  });

  test("are read from STAGE_GEN_RUN_ROOTS in order, once each, with distinct keys", async () => {
    const first = await tempDir("stage-gen-out-");
    const second = await tempDir("stage-gen-runs-");
    process.env.STAGE_GEN_RUN_ROOTS = [first, second, first].join(path.delimiter);
    const roots = runRoots();
    expect(roots.map((root) => root.dir)).toEqual([first, second]);
    expect(roots[0].key).toMatch(/^stage-gen-out-[a-z0-9-]*-[0-9a-f]{6}$/);
    expect(roots[0].key).not.toBe(roots[1].key);
    // Two folders with one name are told apart by their real paths.
    expect(rootKey("/a/out")).not.toBe(rootKey("/b/out"));
    expect(rootKey("/a/movie_sprite")).toMatch(/^movie-sprite-[0-9a-f]{6}$/);
  });
});

describe("run names", () => {
  test("a tag is a root-relative path with ~ for /, up to four folders deep", () => {
    expect(tagFor("review/facial-4k/yuzu/run-01")).toBe("review~facial-4k~yuzu~run-01");
    expect(relativeOf("review~facial-4k~yuzu~run-01")).toBe("review/facial-4k/yuzu/run-01");
    expect(runHref({ root: "out-1a2b3c", tag: "a~b" }, "artifacts")).toBe("/runs/out-1a2b3c/a~b/artifacts");
    expect(isSafeRunTag("rain-dark-stone-0123abcd")).toBe(true);
    expect(isSafeRunTag("Explicit_Tag.v3")).toBe(true);
    expect(isSafeRunTag("review~facial-4k~yuzu~run-01")).toBe(true);
    expect(isSafeRunTag("a".repeat(128))).toBe(true);
    expect(isSafeRunTag("a".repeat(129))).toBe(false);
    expect(isSafeRunTag("a~b~c~d~e")).toBe(false);
    for (const tag of [
      "",
      ".",
      "..",
      "a~..",
      "a~~b",
      "~a",
      "../escape",
      "safe/escape",
      "safe\\escape",
      "%2e%2e",
      "safe%2Fescape",
      "safe%252Fescape",
    ]) {
      expect(isSafeRunTag(tag)).toBe(false);
    }
  });

  test("resolve inside their root and refuse traversal, unknown roots and escapes", async () => {
    const root = await tempDir("stage-gen-out-");
    process.env.STAGE_GEN_RUN_ROOTS = root;
    const key = runRoots()[0].key;
    const run = { root: key, tag: "review~yuzu~run-01" };
    const runDir = runDirFor(run);
    expect(runDir).toBe(path.join(root, "review", "yuzu", "run-01"));
    expect(artifactPathFor(run, "render/animation.webp")).toBe(path.join(runDir, "render", "animation.webp"));
    expect(() => runDirFor({ root: key, tag: "../escape" })).toThrow("invalid run tag");
    expect(() => runDirFor({ root: "elsewhere-000000", tag: "a" })).toThrow("unknown run root");
    for (const name of ["", ".hidden", "..", "../secret", "nested\\asset.png", "asset%2Fsecret.png"]) {
      expect(() => artifactPathFor(run, name)).toThrow("invalid artifact path");
    }
  });
});

describe("run discovery", () => {
  test("finds every run shape under several roots, as stage_gen.runs.discover does", async () => {
    const out = await tempDir("stage-gen-out-");
    const spikes = await tempDir("stage-gen-spikes-");
    await write(path.join(out, "sdk-run", "execution-plan.json"), { kind: "pipeline-execution-graph-v1" });
    await write(path.join(out, "game-run", "manifest.json"), { kind: "prepared-game-runtime-v12" });
    await write(path.join(out, "view-only", "execution-view.json"), { kind: "x" });
    await write(path.join(spikes, "canary-01", "wren-01", "graph.json"));
    await write(path.join(spikes, "canary-01", "wren-01", "trace.jsonl"), "");
    await write(path.join(spikes, "review", "facial-4k", "yuzu", "run-01", "plan.json"));
    await write(path.join(spikes, "review", "facial-4k", "yuzu", "run-01", "execution.json"));
    // A sub-run is part of its run, not a run of its own.
    await write(path.join(spikes, "review", "facial-4k", "yuzu", "run-01", "portrait", "plan.json"));
    await write(path.join(spikes, "review", "facial-4k", "yuzu", "run-01", "portrait", "execution.json"));
    await write(path.join(spikes, "scratch", "notes.txt"), "not a run");
    await write(path.join(spikes, "graph-only", "graph.json"));
    process.env.STAGE_GEN_RUN_ROOTS = [out, spikes].join(path.delimiter);

    const found = await discoverRuns();

    expect(found.map((entry) => [entry.root.dir, entry.relative])).toEqual([
      [out, "game-run"],
      [out, "sdk-run"],
      [out, "view-only"],
      [spikes, "canary-01/wren-01"],
      [spikes, "review/facial-4k/yuzu/run-01"],
    ]);
    expect(found[4].run.tag).toBe("review~facial-4k~yuzu~run-01");
  });

  test("skips the example store, hidden folders, node_modules, links out and deep folders", async () => {
    const out = await tempDir("stage-gen-out-");
    const elsewhere = await tempDir("stage-gen-elsewhere-");
    await write(path.join(out, "examples", "movie-sprite", "yuzu-idle", "manifest.json"));
    await write(path.join(out, ".cache", "run", "execution-plan.json"));
    await write(path.join(out, "node_modules", "pkg", "manifest.json"));
    await write(path.join(out, "a", "b", "c", "d", "e", "execution-plan.json"));
    await write(path.join(elsewhere, "outside", "execution-plan.json"));
    await symlink(elsewhere, path.join(out, "linked"));
    await write(path.join(out, "batch", "examples", "execution-plan.json"));
    process.env.STAGE_GEN_RUN_ROOTS = out;

    expect((await discoverRuns()).map((entry) => entry.relative)).toEqual(["batch/examples"]);
  });

  test("a root that does not exist has no runs", async () => {
    const root = await tempDir("stage-gen-out-");
    process.env.STAGE_GEN_RUN_ROOTS = path.join(root, "missing");
    expect(await discoverRuns()).toEqual([]);
  });
});
