import { realpath } from "node:fs/promises";
import { resolve, sep } from "node:path";
import type { StageGenConfig, TransparencyMode } from "./config.ts";
import {
  generatePrepared,
  prepareGenerateRequest,
  type PreparedGenerateRequest,
} from "./service.ts";
import { listRecipes } from "./recipes.ts";
import type { RunSummary } from "./types.ts";
import { generateImageArtifact } from "./capabilities.ts";
import type { ImageAspectRatio } from "@stage-gen/image-generation";
import {
  assertSafePathSegment,
  resolveRelativePathWithinRoot,
  resolveWritablePathWithinRoot,
} from "./paths.ts";

const MAX_JSON_BODY_BYTES = 64 * 1024;

type RunState = "queued" | "running" | "done" | "failed" | "cancelled";

interface RunRecord {
  id: string;
  recipe: string;
  tag: string;
  transparencyMode: TransparencyMode;
  status: RunState;
  events: string[];
  summary?: RunSummary;
  error?: string;
  controller: AbortController;
  subscribers: Set<ReadableStreamDefaultController<Uint8Array>>;
}

export interface StageGenServer {
  fetch(request: Request): Promise<Response>;
}

export type PreparedRunExecutor = (
  prepared: PreparedGenerateRequest,
  config: StageGenConfig,
  log?: (line: string) => void,
  signal?: AbortSignal,
) => Promise<RunSummary>;

export interface CreateStageGenServerOptions {
  /** Test/application seam; production defaults to the generic service. */
  executePrepared?: PreparedRunExecutor;
}

export function createStageGenServer(
  config: StageGenConfig,
  options: CreateStageGenServerOptions = {},
): StageGenServer {
  const runs = new Map<string, RunRecord>();
  const encoder = new TextEncoder();
  const executePrepared = options.executePrepared ?? generatePrepared;

  function emit(record: RunRecord, event: string, data: unknown): void {
    const frame = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
    record.events.push(frame);
    const bytes = encoder.encode(frame);
    for (const subscriber of record.subscribers) {
      try {
        subscriber.enqueue(bytes);
      } catch {
        record.subscribers.delete(subscriber);
      }
    }
  }

  function finishSubscribers(record: RunRecord): void {
    for (const subscriber of record.subscribers) {
      try {
        subscriber.close();
      } catch {
        // already closed
      }
    }
    record.subscribers.clear();
  }

  async function startRun(body: unknown): Promise<Response> {
    if (!body || typeof body !== "object") {
      return json({ error: "request body must be an object" }, 400);
    }
    const request = body as {
      recipe?: unknown;
      input?: unknown;
      transparencyMode?: unknown;
    };
    const recipeId = String(request.recipe ?? "scrolling-preview");
    let prepared: PreparedGenerateRequest;
    try {
      prepared = prepareGenerateRequest(
        {
          recipe: recipeId,
          input: request.input,
          transparencyMode: request.transparencyMode,
        },
        config,
      );
    } catch (error) {
      return json({ error: message(error) }, 400);
    }
    let tag: string;
    try {
      tag = assertSafePathSegment(prepared.tag, "recipe tag");
    } catch (error) {
      return json({ error: message(error) }, 400);
    }
    const id = `${prepared.recipe.id}--${tag}`;
    const existing = runs.get(id);
    if (existing && (existing.status === "queued" || existing.status === "running")) {
      return json(publicRecord(existing), 200);
    }

    const record: RunRecord = {
      id,
      recipe: prepared.recipe.id,
      tag,
      transparencyMode: prepared.input.transparencyMode,
      status: "queued",
      events: [],
      controller: new AbortController(),
      subscribers: new Set(),
    };
    runs.set(id, record);
    queueMicrotask(async () => {
      if (record.controller.signal.aborted) {
        record.status = "cancelled";
        record.error = message(record.controller.signal.reason);
        emit(record, "run-status", { status: record.status, error: record.error });
        finishSubscribers(record);
        return;
      }
      record.status = "running";
      emit(record, "run-status", { status: record.status });
      try {
        record.summary = await executePrepared(
          prepared,
          config,
          (line) => emit(record, "log", { line }),
          record.controller.signal,
        );
        record.status = record.controller.signal.aborted
          ? "cancelled"
          : record.summary.ok
            ? "done"
            : "failed";
        if (!record.summary.ok) record.error = record.summary.failedStage;
      } catch (error) {
        record.status = record.controller.signal.aborted ? "cancelled" : "failed";
        record.error = message(error);
      }
      emit(record, "run-status", {
        status: record.status,
        error: record.error ?? null,
      });
      finishSubscribers(record);
    });
    return json(publicRecord(record), 202);
  }

  return {
    async fetch(request: Request): Promise<Response> {
      const url = new URL(request.url);
      if (request.method === "GET" && url.pathname === "/healthz") {
        return json({ ok: true, service: "stage-gen" });
      }
      if (request.method === "GET" && url.pathname === "/v1/recipes") {
        return json({ recipes: listRecipes() });
      }
      if (request.method === "POST" && url.pathname === "/v1/runs") {
        try {
          return startRun(await readJsonBody(request));
        } catch (error) {
          return requestError(error);
        }
      }
      if (request.method === "GET" && url.pathname === "/v1/capabilities") {
        return json({ capabilities: ["generate-image", "remove-background", "generate-music"] });
      }
      if (
        request.method === "POST" &&
        url.pathname === "/v1/capabilities/generate-image"
      ) {
        let body: unknown;
        try {
          body = await readJsonBody(request);
        } catch (error) {
          return requestError(error);
        }
        if (!body || typeof body !== "object") {
          return json({ error: "request body must be an object" }, 400);
        }
        const value = body as {
          prompt?: unknown;
          outputPath?: unknown;
          aspectRatio?: unknown;
        };
        const prompt = typeof value.prompt === "string" ? value.prompt.trim() : "";
        const outputPath =
          typeof value.outputPath === "string" ? value.outputPath.trim() : "";
        const aspectRatio = value.aspectRatio ?? "1:1";
        if (!prompt || !outputPath) {
          return json({ error: "prompt and outputPath are required" }, 400);
        }
        if (
          typeof aspectRatio !== "string" ||
          (aspectRatio !== "auto" && !/^[1-9]\d*:[1-9]\d*$/.test(aspectRatio))
        ) {
          return json({ error: "aspectRatio must be auto or positive <width>:<height>" }, 400);
        }
        let output: string;
        try {
          output = await resolveWritablePathWithinRoot(config.outDir, outputPath, "outputPath");
        } catch (error) {
          return json({ error: message(error) }, 400);
        }
        try {
          const result = await generateImageArtifact(
            {
              prompt,
              outputPath: output,
              aspectRatio: aspectRatio as ImageAspectRatio,
            },
            config,
            request.signal,
          );
          return json(result, 201);
        } catch (error) {
          return json({ error: message(error) }, 502);
        }
      }

      const match = url.pathname.match(
        /^\/v1\/runs\/([^/]+)(?:\/(events|artifacts|cancel)(?:\/(.+))?)?$/,
      );
      if (match) {
        let runId: string;
        try {
          runId = decodeURIComponent(match[1]);
        } catch {
          return json({ error: "invalid run id" }, 400);
        }
        const record = runs.get(runId);
        if (!record) return json({ error: "run not found" }, 404);
        if (request.method === "GET" && !match[2]) return json(publicRecord(record));
        if (request.method === "POST" && match[2] === "cancel" && !match[3]) {
          if (record.status === "queued" || record.status === "running") {
            record.controller.abort(new Error("run cancelled by request"));
          }
          return json(publicRecord(record), 202);
        }
        if (request.method === "GET" && match[2] === "events") {
          return eventStream(record, request.signal, encoder);
        }
        if (request.method === "GET" && match[2] === "artifacts" && match[3]) {
          if (!record.summary) return json({ error: "run has no artifacts" }, 409);
          let name: string;
          try {
            name = assertSafePathSegment(decodeURIComponent(match[3]), "artifact name");
          } catch (error) {
            return json({ error: message(error) }, 400);
          }
          const lexicalPath = resolveRelativePathWithinRoot(
            record.summary.runDir,
            name,
            "artifact name",
          );
          let root: string;
          let path: string;
          try {
            [root, path] = await Promise.all([
              realpath(record.summary.runDir),
              realpath(lexicalPath),
            ]);
          } catch {
            return json({ error: "artifact not found" }, 404);
          }
          if (!path.startsWith(`${root}${sep}`)) return json({ error: "forbidden" }, 403);
          const file = Bun.file(path);
          if (!(await file.exists())) return json({ error: "artifact not found" }, 404);
          return new Response(file);
        }
      }
      return json({ error: "not found" }, 404);
    },
  };
}

function eventStream(
  record: RunRecord,
  signal: AbortSignal,
  encoder: TextEncoder,
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of record.events) controller.enqueue(encoder.encode(frame));
      if (
        record.status === "done" ||
        record.status === "failed" ||
        record.status === "cancelled"
      ) {
        controller.close();
        return;
      }
      record.subscribers.add(controller);
      signal.addEventListener(
        "abort",
        () => {
          record.subscribers.delete(controller);
          try {
            controller.close();
          } catch {
            // already closed
          }
        },
        { once: true },
      );
    },
  });
  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
    },
  });
}

function publicRecord(record: RunRecord) {
  return {
    id: record.id,
    recipe: record.recipe,
    tag: record.tag,
    transparencyMode: record.transparencyMode,
    status: record.status,
    error: record.error ?? null,
    summary: record.summary ?? null,
  };
}

function json(value: unknown, status = 200): Response {
  return Response.json(value, { status });
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

class RequestBodyError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "RequestBodyError";
  }
}

async function readJsonBody(request: Request): Promise<unknown> {
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_JSON_BODY_BYTES) {
    throw new RequestBodyError(`request body exceeds ${MAX_JSON_BODY_BYTES} bytes`, 413);
  }
  if (!request.body) throw new RequestBodyError("invalid JSON", 400);

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_JSON_BODY_BYTES) {
      await reader.cancel();
      throw new RequestBodyError(`request body exceeds ${MAX_JSON_BODY_BYTES} bytes`, 413);
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new RequestBodyError("invalid JSON", 400);
  }
}

function requestError(error: unknown): Response {
  return error instanceof RequestBodyError
    ? json({ error: error.message }, error.status)
    : json({ error: message(error) }, 400);
}

export interface ServeStageGenOptions {
  port?: number;
  hostname?: string;
  /** Required for any non-loopback bind. */
  allowPublic?: boolean;
}

export function resolveServerBinding(options: ServeStageGenOptions = {}): {
  hostname: string;
  port: number;
} {
  const hostname = options.hostname?.trim() || "127.0.0.1";
  const port = options.port ?? 4317;
  if (!isLoopbackHostname(hostname) && options.allowPublic !== true) {
    throw new Error("non-loopback --host requires the explicit --public flag");
  }
  return { hostname, port };
}

function isLoopbackHostname(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "::1" || hostname === "localhost";
}

export function serveStageGen(config: StageGenConfig, options: ServeStageGenOptions = {}) {
  const binding = resolveServerBinding(options);
  const app = createStageGenServer(config);
  return Bun.serve({ ...binding, fetch: app.fetch });
}
