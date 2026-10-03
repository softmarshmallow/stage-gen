// Per-run asset streaming API.
//
// Serves files from one run folder under one of the configured run roots. The viewer
// fetches artwork, sidecars and verdicts through this route — we do NOT symlink run
// roots into `web/viewer/public/` because the project rule (AGENTS.md "Fixtures")
// forbids symlinks across workspaces.
//
// Route shape: /api/assets/<root>/<tag>/<...filename-segments>
//   - <root>      : a run root's key (lib/shell/runs.ts)
//   - <tag>       : the run's root-relative path, `/` written as `~`
//   - <...path>   : one portable run-local artifact path
//
// Examples:
//   GET /api/assets/out-1a2b3c/foo/world_spec_foo.json
//   GET /api/assets/movie-sprite-4d5e6f/review~facial-4k~yuzu~run-01/render/animation.webp
//
// Path-traversal hardening: route values must already be decoded safe tokens;
// encoded separators, symlink traversal, and run-directory escapes fail.

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";
import type { RunRef } from "@/lib/shell/run-ref";
import { artifactPathFor, isSafeRunTag, rootFor, runDirFor } from "@/lib/shell/runs";
import { viewPolicy } from "@stage-gen/ui/contracts/view-context";

function contentTypeFor(filename: string): string {
  const ext = path.extname(filename).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  if (ext === ".mp3") return "audio/mpeg";
  if (ext === ".wav") return "audio/wav";
  if (ext === ".ogg") return "audio/ogg";
  if (ext === ".flac") return "audio/flac";
  if (ext === ".mp4") return "video/mp4";
  if (ext === ".ogv") return "video/ogg";
  if (ext === ".webm") return "video/webm";
  if (ext === ".glb") return "model/gltf-binary";
  if (ext === ".gltf") return "model/gltf+json";
  if (ext === ".obj") return "model/obj";
  if (ext === ".json") return "application/json; charset=utf-8";
  if (ext === ".txt") return "text/plain; charset=utf-8";
  if (ext === ".html") return "text/html; charset=utf-8";
  return "application/octet-stream";
}

/** A gnode run's view template: only these are served as HTML, and always sandboxed. */
const VIEW_TEMPLATE = /^views\/[0-9a-f]{64}\.html$/;
/** A file a view shows, kept beside it by its run. */
const VIEW_FILE = /^views\/files\/[0-9a-f]{64}(?:\.[a-z0-9]+)?$/;

/** The origins the run's gnode.yaml lets its views load from; none when it declares none. */
async function viewOrigins(runDir: string): Promise<string[]> {
  try {
    const plan = JSON.parse(await fs.readFile(path.join(runDir, "plan.json"), "utf8")) as {
      view_origins?: unknown;
    };
    const origins = Array.isArray(plan.view_origins) ? plan.view_origins : [];
    return origins.filter(
      (origin): origin is string =>
        typeof origin === "string" && origin.startsWith("https://") && new URL(origin).origin === origin,
    );
  } catch {
    return [];
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ root: string; tag: string; path: string[] }> },
) {
  const { root, tag, path: parts } = await params;
  if (!isSafeRunTag(tag) || !parts || parts.length === 0) {
    return new Response("missing tag/path", { status: 400 });
  }
  if (rootFor(root) === null) return new Response("not found", { status: 404 });
  const run: RunRef = { root, tag };
  const relative = parts.join("/");
  if (relative.toLowerCase().endsWith(".html") && !VIEW_TEMPLATE.test(relative)) {
    return new Response("forbidden", { status: 403 });
  }
  let requested: string;
  try {
    requested = artifactPathFor(run, relative);
  } catch {
    return new Response("forbidden", { status: 403 });
  }
  try {
    const file = await fs.lstat(requested);
    if (!file.isFile() || file.isSymbolicLink()) {
      return new Response("forbidden", { status: 403 });
    }
    const runRoot = await fs.realpath(runDirFor(run));
    const real = await fs.realpath(requested);
    if (!real.startsWith(`${runRoot}${path.sep}`)) {
      return new Response("forbidden", { status: 403 });
    }
    const data = await fs.readFile(requested);
    const ct = contentTypeFor(requested);
    const headers: Record<string, string> = {
      "content-type": ct,
      "x-content-type-options": "nosniff",
      "content-length": String(data.byteLength),
      // Dev-only convenience: never cache during iteration.
      "cache-control": "no-store",
    };
    if (VIEW_FILE.test(relative)) {
      // A view fetches the files it was shown (a JSON value past the inline limit, say).
      headers["access-control-allow-origin"] = "*";
    }
    if (VIEW_TEMPLATE.test(relative)) {
      // Even opened on its own, a view runs in an opaque origin and reaches nothing else.
      headers["content-security-policy"] = viewPolicy(
        new URL(request.url).origin,
        await viewOrigins(runRoot),
      );
    }
    return new Response(new Uint8Array(data), { status: 200, headers });
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException)?.code;
    if (code === "ENOENT") {
      return new Response("not found", { status: 404 });
    }
    return new Response("read error", { status: 500 });
  }
}
