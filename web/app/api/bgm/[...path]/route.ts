// BGM fixtures streaming API.
//
// Serves files from repo-root `fixtures/bgm/` (mp3 tracks + index.json).
// Same shape as /api/assets but rooted at fixtures/bgm/ instead of out/<tag>/.
//
// Examples:
//   GET /api/bgm/index.json
//   GET /api/bgm/ck_martin_mountain_climbing.mp3

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const BGM_ROOT = path.join(REPO_ROOT, "fixtures", "bgm");

function contentTypeFor(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ext === ".mp3") return "audio/mpeg";
  if (ext === ".ogg") return "audio/ogg";
  if (ext === ".json") return "application/json; charset=utf-8";
  return "application/octet-stream";
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path: parts } = await params;
  if (!parts || parts.length === 0) {
    return new Response("missing path", { status: 400 });
  }
  const requested = path.resolve(BGM_ROOT, ...parts);
  if (!requested.startsWith(BGM_ROOT + path.sep)) {
    return new Response("forbidden", { status: 403 });
  }
  try {
    const data = await fs.readFile(requested);
    return new Response(new Uint8Array(data), {
      status: 200,
      headers: {
        "content-type": contentTypeFor(requested),
        "content-length": String(data.byteLength),
        "cache-control": "no-store",
      },
    });
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException)?.code;
    if (code === "ENOENT") return new Response("not found", { status: 404 });
    return new Response("read error", { status: 500 });
  }
}
