// Per-tag asset streaming API.
//
// Serves files from the repo-root `out/<tag>/` directory the pipeline writes.
// The web runtime fetches PNGs and the world spec JSON via this route — we do
// NOT symlink `out/` into `web/public/_assets/` because the project rule
// (AGENTS.md "Fixtures") forbids symlinks across workspaces.
//
// Route shape: /api/assets/<tag>/<...filename-segments>
//   - <tag>       : the per-run output directory under repo-root /out
//   - <...path>   : the file path under that directory (one or more segments)
//
// Examples:
//   GET /api/assets/foo/world_spec_foo.json
//   GET /api/assets/foo/concept_foo.png
//   GET /api/assets/foo/layer_foo_clear_peak_sky.png
//
// Path-traversal hardening: we resolve the requested path under the per-tag
// directory and reject any path that escapes the repo-root /out tree.

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

// Repo root is two levels up from web/app. Resolve once at module load.
const REPO_ROOT = path.resolve(process.cwd(), "..");
const OUT_ROOT = path.join(REPO_ROOT, "out");

function contentTypeFor(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".txt") return "text/plain; charset=utf-8";
  return "application/octet-stream";
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ tag: string; path: string[] }> },
) {
  const { tag, path: parts } = await params;
  if (!tag || !parts || parts.length === 0) {
    return new Response("missing tag/path", { status: 400 });
  }
  // Compose the requested file path under out/<tag>/...
  const requested = path.resolve(OUT_ROOT, tag, ...parts);
  // Path-traversal guard: requested must be inside OUT_ROOT.
  if (!requested.startsWith(OUT_ROOT + path.sep)) {
    return new Response("forbidden", { status: 403 });
  }
  try {
    const data = await fs.readFile(requested);
    const ct = contentTypeFor(requested);
    return new Response(new Uint8Array(data), {
      status: 200,
      headers: {
        "content-type": ct,
        "content-length": String(data.byteLength),
        // Dev-only convenience: never cache during iteration.
        "cache-control": "no-store",
      },
    });
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException)?.code;
    if (code === "ENOENT") {
      return new Response("not found", { status: 404 });
    }
    return new Response("read error", { status: 500 });
  }
}
