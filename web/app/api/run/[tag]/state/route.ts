// GET /api/run/<tag>/state — initial state snapshot for the generation view.
//
// Returns:
//   {
//     tag, prompt | null,
//     status: "missing" | "running" | "done" | "failed",
//     spec: WorldSpecLite | null,
//     present: string[]   // filenames that exist under out/<tag>/
//   }
//
// The client uses this to populate the grid on first paint without waiting
// for the SSE stream — important for cached runs (TC-124).

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import { runDirFor, runJsonPathFor, readRunStatus } from "@/lib/shell/runs";
import type { WorldSpecLite } from "@/lib/shell/slots";

export const runtime = "nodejs";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ tag: string }> },
) {
  const { tag } = await params;
  const dir = runDirFor(tag);
  const status = await readRunStatus(tag);

  let prompt: string | null = null;
  if (existsSync(runJsonPathFor(tag))) {
    try {
      const raw = await fs.readFile(runJsonPathFor(tag), "utf8");
      prompt = JSON.parse(raw).prompt ?? null;
    } catch {
      // ignore
    }
  }

  let spec: WorldSpecLite | null = null;
  const specPath = path.join(dir, `world_spec_${tag}.json`);
  if (existsSync(specPath)) {
    try {
      const raw = await fs.readFile(specPath, "utf8");
      const parsed = JSON.parse(raw);
      spec = {
        layers: parsed.layers ?? [],
        mobs: parsed.mobs ?? [],
        obstacles: parsed.obstacles ?? [],
        items: parsed.items ?? [],
      };
    } catch {
      // ignore
    }
  }

  let present: string[] = [];
  if (existsSync(dir)) {
    const entries = await fs.readdir(dir);
    present = entries.filter(
      (n) => !n.endsWith(".meta.json") && !n.endsWith(".log"),
    );
  }

  return Response.json({
    tag,
    prompt,
    status: status.status,
    failedStage: status.failedStage ?? null,
    spec,
    present,
  });
}
