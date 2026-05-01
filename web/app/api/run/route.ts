// POST /api/run — kick off (or attach to) a pipeline run for one prompt.
//
// Body: { prompt: string }
// Response (200):
//   { tag: string, status: "started" | "running" | "cached" | "failed" }
//
// Behaviour:
//   - Computes the deterministic tag from the prompt (same logic as
//     pipeline/src/tag.ts). Same prompt → same tag → same dir.
//   - If run.json already shows ok=true → status="cached", no spawn.
//   - If a process is already live for this tag → status="running".
//   - Otherwise spawns the pipeline as a background subprocess and returns
//     immediately with status="started".

import { NextRequest } from "next/server";
import { tagFor } from "@/lib/shell/tag";
import { startRun, readRunStatus } from "@/lib/shell/runs";

// Pipeline subprocess spawning needs the Node runtime.
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }
  const prompt =
    typeof body === "object" && body !== null && "prompt" in body
      ? String((body as Record<string, unknown>).prompt ?? "").trim()
      : "";
  if (!prompt) {
    return Response.json({ error: "prompt is required" }, { status: 400 });
  }

  const tag = tagFor(prompt);
  const status = await readRunStatus(tag);

  if (status.status === "done" && status.ok) {
    return Response.json({ tag, status: "cached" });
  }
  if (status.status === "running") {
    return Response.json({ tag, status: "running" });
  }

  const { started } = await startRun({ prompt, tag });
  return Response.json({ tag, status: started ? "started" : "running" });
}
