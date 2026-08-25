import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import type { NextRequest } from "next/server";
import { runDirFor } from "@/lib/shell/runs";
import { GET } from "./route";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

describe("run state API", () => {
  test("projects a validated summary through lower_snake_case public fields", async () => {
    const tag = `test-state-api-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "run.json"),
      JSON.stringify({
        schema_version: 3,
        kind: "recipe_run_v3",
        recipe: "scrolling-preview",
        input: { prompt: "state API fixture", transparency_mode: "ai" },
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

    const response = await GET(
      new Request(`http://localhost/api/run/${tag}/state`) as NextRequest,
      { params: Promise.resolve({ tag }) },
    );
    const body = (await response.json()) as Record<string, unknown>;

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      tag,
      prompt: "state API fixture",
      status: "done",
      failed_stage: null,
    });
    expect(body).not.toHaveProperty("failedStage");
  });
});
