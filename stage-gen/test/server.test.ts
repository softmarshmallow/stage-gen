import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createStageGenServer,
  resolveServerBinding,
} from "../src/server.ts";

const app = createStageGenServer({
  outDir: "out",
  imageModel: "test/image",
  textModel: "test/text",
  musicModel: "test/music",
  backgroundRemovalModel: "test/remove",
  transparencyMode: "ai",
  stageTimeoutMs: 1_000,
  capabilityTimeoutMs: 1_000,
});

describe("headless HTTP boundary", () => {
  test("exposes health without provider credentials", async () => {
    const response = await app.fetch(new Request("http://localhost/healthz"));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, service: "stage-gen" });
  });

  test("lists recipes and rejects malformed runs", async () => {
    const recipes = await app.fetch(new Request("http://localhost/v1/recipes"));
    expect(recipes.status).toBe(200);
    expect(JSON.stringify(await recipes.json())).toContain("scrolling-preview");

    const invalid = await app.fetch(
      new Request("http://localhost/v1/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ recipe: "scrolling-preview", input: {} }),
      }),
    );
    expect(invalid.status).toBe(400);
  });

  test("round-trips transparency mode and applies conditional capability checks", async () => {
    const captured: string[] = [];
    const local = createStageGenServer(
      { ...appConfig(), openRouterApiKey: "test" },
      {
        async executePrepared(prepared) {
          captured.push(prepared.input.transparencyMode);
          const now = new Date(0).toISOString();
          return {
            recipe: prepared.recipe.id,
            input: prepared.input,
            tag: prepared.tag,
            runDir: "/unused",
            startedAt: now,
            endedAt: now,
            durationMs: 0,
            ok: true,
            stages: [],
          };
        },
      },
    );

    const chroma = await local.fetch(
      runRequest({ input: { prompt: "neutral asset" }, transparencyMode: "chroma" }),
    );
    expect(chroma.status).toBe(202);
    expect(await chroma.json()).toMatchObject({
      transparencyMode: "chroma",
      tag: expect.stringMatching(/-chroma$/),
    });
    await new Promise<void>((resolve) => queueMicrotask(resolve));
    expect(captured).toEqual(["chroma"]);

    const ai = await local.fetch(
      runRequest({ input: { prompt: "neutral asset" }, transparencyMode: "ai" }),
    );
    expect(ai.status).toBe(400);
    expect(JSON.stringify(await ai.json())).toContain("FAL_KEY");
  });

  test("rejects invalid HTTP mode before missing capabilities", async () => {
    const invalid = await app.fetch(
      runRequest({ input: { prompt: "neutral asset" }, transparencyMode: "none" }),
    );
    expect(invalid.status).toBe(400);
    expect(await invalid.json()).toEqual({
      error: "transparencyMode must be ai or chroma",
    });
  });

  test("advertises image generation and rejects unsafe output paths before any call", async () => {
    const capabilities = await app.fetch(
      new Request("http://localhost/v1/capabilities"),
    );
    expect(capabilities.status).toBe(200);
    expect(JSON.stringify(await capabilities.json())).toContain("generate-image");

    const unsafe = await app.fetch(
      new Request("http://localhost/v1/capabilities/generate-image", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          prompt: "neutral icon",
          outputPath: "../outside.png",
          aspectRatio: "1:1",
        }),
      }),
    );
    expect(unsafe.status).toBe(400);
    expect(await unsafe.json()).toEqual({
      error: "outputPath contains an unsafe path segment",
    });
  });

  test("rejects request bodies beyond the bounded JSON limit", async () => {
    const oversized = await app.fetch(
      new Request("http://localhost/v1/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ input: { prompt: "x".repeat(70_000) } }),
      }),
    );
    expect(oversized.status).toBe(413);
  });

  test("rejects output paths through a symlinked parent", async () => {
    const root = await mkdtemp(join(tmpdir(), "stage-gen-server-root-"));
    const outside = await mkdtemp(join(tmpdir(), "stage-gen-server-outside-"));
    await mkdir(root, { recursive: true });
    await symlink(outside, join(root, "link"), "dir");
    const local = createStageGenServer({ ...appConfig(), outDir: root });
    try {
      const response = await local.fetch(
        new Request("http://localhost/v1/capabilities/generate-image", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            prompt: "neutral icon",
            outputPath: "link/out.png",
            aspectRatio: "1:1",
          }),
        }),
      );
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: "outputPath has a symlinked parent" });
    } finally {
      await Promise.all([
        rm(root, { recursive: true, force: true }),
        rm(outside, { recursive: true, force: true }),
      ]);
    }
  });

  test("defaults to loopback and gates every public bind", () => {
    expect(resolveServerBinding()).toEqual({ hostname: "127.0.0.1", port: 4317 });
    expect(() => resolveServerBinding({ hostname: "0.0.0.0" })).toThrow("--public");
    expect(resolveServerBinding({ hostname: "0.0.0.0", allowPublic: true })).toEqual({
      hostname: "0.0.0.0",
      port: 4317,
    });
  });

});

function appConfig() {
  return {
    outDir: "out",
    imageModel: "test/image",
    textModel: "test/text",
    musicModel: "test/music",
    backgroundRemovalModel: "test/remove",
    transparencyMode: "ai" as const,
    stageTimeoutMs: 1_000,
    capabilityTimeoutMs: 1_000,
  };
}

function runRequest(body: unknown): Request {
  return new Request("http://localhost/v1/runs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
