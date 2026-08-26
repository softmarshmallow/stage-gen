// Per-tag asset streaming API.
//
// Serves files from the repo-root `out/<tag>/` directory the pipeline writes.
// The optional web preview fetches PNGs and the world spec JSON via this route — we do
// NOT symlink `out/` into `web/public/_assets/` because the project rule
// (AGENTS.md "Fixtures") forbids symlinks across workspaces.
//
// Route shape: /api/assets/<tag>/<...filename-segments>
//   - <tag>       : the per-run output directory under repo-root /out
//   - <...path>   : one portable run-local artifact path
//
// Examples:
//   GET /api/assets/foo/world_spec_foo.json
//   GET /api/assets/foo/concept_foo.png
//   GET /api/assets/foo/layer_foo_clear_peak_sky.png
//
// Path-traversal hardening: route values must already be decoded safe tokens;
// encoded separators, symlink traversal, and run-directory escapes fail.

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";
import { artifactPathFor, isSafeRunTag, runDirFor } from "@/lib/shell/runs";

function contentTypeFor(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  if (ext === ".mp3") return "audio/mpeg";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".txt") return "text/plain; charset=utf-8";
  return "application/octet-stream";
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ tag: string; path: string[] }> },
) {
  const { tag, path: parts } = await params;
  if (!isSafeRunTag(tag) || !parts || parts.length === 0) {
    return new Response("missing tag/path", { status: 400 });
  }
  let requested: string;
  try {
    requested = artifactPathFor(tag, parts.join("/"));
  } catch {
    return new Response("forbidden", { status: 403 });
  }
  try {
    const file = await fs.lstat(requested);
    if (!file.isFile() || file.isSymbolicLink()) {
      return new Response("forbidden", { status: 403 });
    }
    const runRoot = await fs.realpath(runDirFor(tag));
    const real = await fs.realpath(requested);
    if (!real.startsWith(`${runRoot}${path.sep}`)) {
      return new Response("forbidden", { status: 403 });
    }
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
