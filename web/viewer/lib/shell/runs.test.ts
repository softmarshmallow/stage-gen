import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { artifactPathFor, findRepoRoot, isSafeRunTag, outRoot, runDirFor } from "./runs";

const CHECKOUT = path.resolve(import.meta.dir, "../../../..");

describe("repository root", () => {
  test("is found from web/ and web/viewer with no setting", () => {
    for (const start of ["web", "web/viewer", "web/viewer/lib/shell"]) {
      expect(findRepoRoot(path.join(CHECKOUT, start), {})).toBe(CHECKOUT);
    }
  });

  test("the test process, started anywhere in the checkout, reads runs from its out/", () => {
    // Run with no setting at all, whatever the caller's shell exports.
    const saved = {
      STAGE_GEN_REPO_ROOT: process.env.STAGE_GEN_REPO_ROOT,
      STAGE_GEN_OUT_DIR: process.env.STAGE_GEN_OUT_DIR,
    };
    delete process.env.STAGE_GEN_REPO_ROOT;
    delete process.env.STAGE_GEN_OUT_DIR;
    try {
      expect(outRoot()).toBe(path.join(CHECKOUT, "out"));
    } finally {
      for (const [name, value] of Object.entries(saved)) {
        if (value !== undefined) process.env[name] = value;
      }
    }
  });

  test("skips a pyproject that names another project and refuses when none is found", async () => {
    const scratch = await mkdtemp(path.join(tmpdir(), "stage-gen-root-"));
    try {
      const nested = path.join(scratch, "checkout", "web", "viewer");
      await mkdir(nested, { recursive: true });
      await writeFile(
        path.join(scratch, "checkout", "web", "pyproject.toml"),
        '[project]\nname = "stage-gen-web"\n',
      );
      await writeFile(
        path.join(scratch, "checkout", "pyproject.toml"),
        '[build-system]\nrequires = []\n\n[project]\nname = "stage-gen"\nversion = "0"\n\n[tool.uv]\nname = "x"\n',
      );
      expect(findRepoRoot(nested, {})).toBe(path.join(scratch, "checkout"));
      await writeFile(
        path.join(scratch, "checkout", "pyproject.toml"),
        '[project]\nversion = "0"\n\n[tool.other]\nname = "stage-gen"\n',
      );
      expect(() => findRepoRoot(nested, {})).toThrow("no stage-gen checkout");
    } finally {
      await rm(scratch, { recursive: true, force: true });
    }
  });

  test("an explicit STAGE_GEN_REPO_ROOT wins over the walk", () => {
    expect(findRepoRoot(path.join(CHECKOUT, "web"), { STAGE_GEN_REPO_ROOT: " /elsewhere " })).toBe(
      path.resolve("/elsewhere"),
    );
  });
});

describe("run directory boundary", () => {
  test("accepts generated tags and rejects traversal or encoded separators", () => {
    expect(isSafeRunTag("rain-dark-stone-0123abcd")).toBe(true);
    expect(isSafeRunTag("Explicit_Tag.v3")).toBe(true);
    expect(isSafeRunTag("a")).toBe(true);
    expect(isSafeRunTag("a".repeat(128))).toBe(true);
    expect(isSafeRunTag("a".repeat(129))).toBe(false);

    for (const tag of [
      "",
      ".",
      "..",
      "../escape",
      "safe/escape",
      "safe\\escape",
      "%2e%2e",
      "safe%2Fescape",
      "safe%252Fescape",
    ]) {
      expect(isSafeRunTag(tag)).toBe(false);
      expect(() => runDirFor(tag)).toThrow("invalid run tag");
    }
  });

  test("resolves portable nested artifacts inside the selected run", () => {
    const tag = "neutral-run-0123abcd";
    const runDir = runDirFor(tag);
    expect(path.dirname(artifactPathFor(tag, "manifest.json"))).toBe(runDir);
    expect(
      artifactPathFor(tag, "content/players/wayfarer/states/idle.png"),
    ).toBe(
      path.join(runDir, "content", "players", "wayfarer", "states", "idle.png"),
    );

    for (const name of [
      "",
      ".hidden",
      "..",
      "../secret",
      "nested\\asset.png",
      "asset%2Fsecret.png",
      "asset%252Fsecret.png",
    ]) {
      expect(() => artifactPathFor(tag, name)).toThrow("invalid artifact path");
    }
  });
});
