import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { NextRequest } from "next/server";
import { runDirFor } from "@/lib/shell/runs";
import { tagFor } from "@/lib/shell/tag";
import { POST } from "./route";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

function request(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("run API wire contract", () => {
  test("accepts and returns lower_snake_case fields for a current cached run", async () => {
    const prompt = `current API run ${process.pid}`;
    const tag = tagFor(prompt, "ai");
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({
        schema_version: 3,
        kind: "recipe_run_v3",
        recipe: "scrolling-preview",
        input: { prompt, transparency_mode: "ai" },
        tag,
        run_dir: tag,
        started_at: "2026-08-25T00:00:00Z",
        ended_at: "2026-08-25T00:00:01Z",
        duration_ms: 1_000,
        ok: true,
        stages: [
          { stage: "concept", ok: true, duration_ms: 1_000, artifacts: ["concept.png"] },
        ],
      }),
      "utf8",
    );

    const response = await POST(request({ prompt, transparency_mode: "ai" }));
    const body = (await response.json()) as Record<string, unknown>;

    expect(response.status).toBe(200);
    expect(body).toEqual({ tag, status: "cached", transparency_mode: "ai" });
    expect(body).not.toHaveProperty("transparencyMode");
  });

  test("rejects the retired camelCase request field", async () => {
    const response = await POST(
      request({ prompt: "legacy API request", transparencyMode: "ai" }),
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({
      error: "request body.transparencyMode is not a supported key",
    });
  });
});
