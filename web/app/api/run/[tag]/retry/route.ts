// POST /api/run/<tag>/retry — re-run the pipeline targeting one missing asset.
//
// Body: { asset: string }   filename under out/<tag>/
// Response: { ok: boolean, reason?: string }
//
// The headless CLI does not yet expose a single-stage entrypoint. This removes
// the validated artifact and sidecar, then submits the original current-run
// input through the public command. Intact recipe artifacts remain cached.

import { NextRequest } from "next/server";
import { artifactPathFor, isSafeRunTag, retryAsset } from "@/lib/shell/runs";

export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ tag: string }> },
) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) {
    return Response.json({ ok: false, reason: "invalid run tag" }, { status: 400 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ ok: false, reason: "invalid JSON" }, { status: 400 });
  }
  const asset =
    typeof body === "object" && body !== null && "asset" in body
      ? String((body as Record<string, unknown>).asset ?? "")
      : "";
  try {
    artifactPathFor(tag, asset);
  } catch {
    return Response.json(
      { ok: false, reason: "asset is required and must be a bare filename" },
      { status: 400 },
    );
  }
  const result = await retryAsset({ tag, asset });
  return Response.json(result, { status: result.ok ? 200 : 400 });
}
