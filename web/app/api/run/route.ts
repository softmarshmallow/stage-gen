// POST /api/run — kick off (or attach to) a pipeline run for one prompt.
//
// Body: { prompt: string, transparency_mode?: "native" | "ai" | "chroma" }
// Response (200):
//   { tag: string, status: "started" | "running" | "cached", transparency_mode: string }
//
// Behaviour:
//   - Computes the deterministic tag from prompt + transparency mode (same
//     contract as the headless recipe). Modes never share a cache directory.
//   - If run.json already shows ok=true → status="cached", no spawn.
//   - If a process is already live for this tag → status="running".
//   - Otherwise spawns the headless recipe as a background subprocess and returns
//     immediately with status="started".

import { NextRequest } from "next/server";
import { tagFor } from "@/lib/shell/tag";
import { startRun, readRunStatus } from "@/lib/shell/runs";
import { parseWebRunInput } from "@/lib/shell/transparency";

// Pipeline subprocess spawning needs the Node runtime.
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }
  let input;
  try {
    input = parseWebRunInput(body);
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : String(error) },
      { status: 400 },
    );
  }

  const tag = tagFor(input.prompt, input.transparencyMode);
  const status = await readRunStatus(tag);

  if (status.status === "done" && status.ok) {
    return Response.json({ tag, status: "cached", transparency_mode: input.transparencyMode });
  }
  if (status.status === "running") {
    return Response.json({ tag, status: "running", transparency_mode: input.transparencyMode });
  }

  const { started } = await startRun({ ...input, tag });
  return Response.json({
    tag,
    status: started ? "started" : "running",
    transparency_mode: input.transparencyMode,
  });
}
