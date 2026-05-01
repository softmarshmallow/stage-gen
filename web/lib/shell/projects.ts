// Server-side helper: enumerate completed projects under out/.
//
// A "ready" project is one whose run.json exists and reports ok === true.
// Used by the picker home page to surface a quick-demo list with direct
// Play / Details links — bypassing the prompt-and-generate flow.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import { OUT_ROOT, runJsonPathFor, runDirFor } from "./runs";

export interface ReadyProject {
  tag: string;
  prompt: string;
  endedAt: string | null;
  conceptFile: string | null;
}

export async function listReadyProjects(): Promise<ReadyProject[]> {
  if (!existsSync(OUT_ROOT)) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyProject[] = [];
  await Promise.all(
    entries.map(async (e) => {
      if (!e.isDirectory()) return;
      const tag = e.name;
      const runJson = runJsonPathFor(tag);
      if (!existsSync(runJson)) return;
      try {
        const raw = await fs.readFile(runJson, "utf8");
        const data = JSON.parse(raw);
        if (data.ok !== true) return;
        const conceptName = `concept_${tag}.png`;
        const conceptPath = path.join(runDirFor(tag), conceptName);
        const conceptFile = existsSync(conceptPath) ? conceptName : null;
        out.push({
          tag,
          prompt: typeof data.prompt === "string" ? data.prompt : "",
          endedAt: typeof data.endedAt === "string" ? data.endedAt : null,
          conceptFile,
        });
      } catch {
        // skip malformed run.json
      }
    }),
  );
  out.sort((a, b) => {
    const ax = a.endedAt ?? "";
    const bx = b.endedAt ?? "";
    return bx.localeCompare(ax);
  });
  return out;
}
