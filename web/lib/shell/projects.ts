// Server-side helper: enumerate completed projects under out/.
//
// A "ready" project is one whose run.json exists and reports ok === true.
// Used by the picker home page to surface a quick-demo list with direct
// Preview / Details links — bypassing the prompt-and-generate flow.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import {
  assertSafeOutRoot,
  artifactPathFor,
  isSafeRunTag,
  OUT_ROOT,
  promptFromRunSummary,
  readRunSummary,
  runJsonPathFor,
} from "./runs";

export interface ReadyProject {
  tag: string;
  prompt: string;
  endedAt: string | null;
  conceptFile: string | null;
}

export async function listReadyProjects(): Promise<ReadyProject[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyProject[] = [];
  await Promise.all(
    entries.map(async (e) => {
      if (!e.isDirectory()) return;
      const tag = e.name;
      if (!isSafeRunTag(tag)) return;
      const runJson = runJsonPathFor(tag);
      if (!existsSync(runJson)) return;
      try {
        const summary = await readRunSummary(tag);
        if (summary?.ok !== true) return;
        const conceptName = `concept_${tag}.png`;
        const conceptPath = artifactPathFor(tag, conceptName);
        const conceptFile = existsSync(conceptPath) ? conceptName : null;
        out.push({
          tag,
          prompt: promptFromRunSummary(summary) ?? "",
          endedAt: summary.ended_at,
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
