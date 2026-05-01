// GET /api/run/<tag>/events — Server-Sent Events stream for one run.
//
// Emits:
//   event: log         data: { line }                    one per pipeline stdout line
//   event: stage-start data: { wave, name, description } parsed from "[wave N] name — desc"
//   event: present     data: { files: string[] }         every poll, the file set under out/<tag>/
//   event: pipeline-done data: { ok, failedStage|null }
//   event: heartbeat   data: { t }                       every 5s so the client stays alive
//
// Strategy: tail web-run.log (poll fs.stat + read appended bytes) on a 500ms
// loop and ls() out/<tag>/ on a 1500ms loop. Stop when run.json appears AND
// the stream emits pipeline-done.

import { NextRequest } from "next/server";
import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  logPathFor,
  runDirFor,
  runJsonPathFor,
  isRunning,
} from "@/lib/shell/runs";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LOG_POLL_MS = 500;
const FILE_POLL_MS = 1500;
const HEARTBEAT_MS = 5000;

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

interface ParsedStage {
  wave: number;
  name: string;
  description: string;
}

function parseStageLine(line: string): ParsedStage | null {
  // "  [wave 1] concept — world concept image (style root)"
  const m = line.match(/\[wave\s+([\d.]+)\]\s+([^\s—-]+)\s+[—-]\s+(.+)$/);
  if (!m) return null;
  return {
    wave: Number(m[1]),
    name: m[2],
    description: m[3].trim(),
  };
}

async function listFiles(dir: string): Promise<string[]> {
  if (!existsSync(dir)) return [];
  const entries = await fs.readdir(dir);
  return entries.filter(
    (n) => !n.endsWith(".meta.json") && !n.endsWith(".log"),
  );
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ tag: string }> },
) {
  const { tag } = await params;
  const logPath = logPathFor(tag);
  const dir = runDirFor(tag);
  const runJsonPath = runJsonPathFor(tag);

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const enc = new TextEncoder();
      const send = (event: string, data: unknown) => {
        try {
          controller.enqueue(enc.encode(sse(event, data)));
        } catch {
          // closed
        }
      };

      let logOffset = 0;
      let lastFiles = new Set<string>();
      let donePosted = false;
      let aborted = false;

      const onAbort = () => {
        aborted = true;
        clearInterval(logTimer);
        clearInterval(fileTimer);
        clearInterval(heartbeatTimer);
        try {
          controller.close();
        } catch {
          // ignore
        }
      };
      req.signal.addEventListener("abort", onAbort);

      // Initial snapshots so the client doesn't have to wait for the first
      // tick.
      const initialFiles = await listFiles(dir);
      lastFiles = new Set(initialFiles);
      send("present", { files: initialFiles });

      const logTimer = setInterval(async () => {
        if (aborted) return;
        if (!existsSync(logPath)) return;
        try {
          const stat = await fs.stat(logPath);
          if (stat.size <= logOffset) return;
          const fd = await fs.open(logPath, "r");
          const len = stat.size - logOffset;
          const buf = Buffer.alloc(len);
          await fd.read(buf, 0, len, logOffset);
          await fd.close();
          logOffset = stat.size;
          const text = buf.toString("utf8");
          for (const rawLine of text.split("\n")) {
            const line = rawLine.replace(/\r$/, "");
            if (!line) continue;
            send("log", { line });
            const stage = parseStageLine(line);
            if (stage) send("stage-start", stage);
          }
        } catch {
          // transient — try again next tick
        }
      }, LOG_POLL_MS);

      const fileTimer = setInterval(async () => {
        if (aborted) return;
        try {
          const cur = await listFiles(dir);
          const curSet = new Set(cur);
          // Cheap diff — only send when set changes.
          let changed = curSet.size !== lastFiles.size;
          if (!changed) {
            for (const f of curSet) {
              if (!lastFiles.has(f)) {
                changed = true;
                break;
              }
            }
          }
          if (changed) {
            send("present", { files: cur });
            lastFiles = curSet;
          }

          // Pipeline-done detection: run.json present AND not running.
          if (!donePosted && existsSync(runJsonPath) && !isRunning(tag)) {
            donePosted = true;
            try {
              const raw = await fs.readFile(runJsonPath, "utf8");
              const data = JSON.parse(raw);
              send("pipeline-done", {
                ok: Boolean(data.ok),
                failedStage: data.failedStage ?? null,
              });
            } catch {
              send("pipeline-done", { ok: false, failedStage: "unknown" });
            }
            // Linger ~3s so the client picks up the final present diff,
            // then close.
            setTimeout(onAbort, 3000);
          }
        } catch {
          // ignore
        }
      }, FILE_POLL_MS);

      const heartbeatTimer = setInterval(() => {
        if (aborted) return;
        send("heartbeat", { t: Date.now() });
      }, HEARTBEAT_MS);
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
