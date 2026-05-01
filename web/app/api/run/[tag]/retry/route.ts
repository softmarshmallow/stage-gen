// POST /api/run/<tag>/retry — re-run the pipeline targeting one missing asset.
//
// Body: { asset: string }   filename under out/<tag>/
// Response: { ok: boolean, reason?: string }
//
// Implementation notes: we don't yet have a single-stage CLI entrypoint, so
// this just removes the named file and re-spawns `bun run pipeline`. Every
// generator stages skip-if-exists, so only the deleted asset is regenerated
// (TC-123 verified that re-runs are no-ops when nothing is missing).

import { NextRequest } from "next/server";
import { retryAsset } from "@/lib/shell/runs";

export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ tag: string }> },
) {
  const { tag } = await params;
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
  if (!asset || asset.includes("/") || asset.includes("..")) {
    return Response.json(
      { ok: false, reason: "asset is required and must be a bare filename" },
      { status: 400 },
    );
  }
  const result = await retryAsset({ tag, asset });
  return Response.json(result, { status: result.ok ? 200 : 400 });
}
