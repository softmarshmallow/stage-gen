// Generation view (per-tag).
//
// Server component fetches the initial state snapshot (status, prompt,
// world spec if present, list of files on disk) so the first paint already
// reflects cached runs near-instantly (TC-124). The client island then
// subscribes to the SSE stream for live updates.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import GenerateView from "./GenerateView";
import { runDirFor, runJsonPathFor, readRunStatus } from "@/lib/shell/runs";
import type { WorldSpecLite } from "@/lib/shell/slots";

export const dynamic = "force-dynamic";

interface InitialState {
  tag: string;
  prompt: string | null;
  status: "missing" | "running" | "done" | "failed";
  failedStage: string | null;
  spec: WorldSpecLite | null;
  present: string[];
}

async function loadInitial(tag: string): Promise<InitialState> {
  const dir = runDirFor(tag);
  const status = await readRunStatus(tag);

  let prompt: string | null = null;
  if (existsSync(runJsonPathFor(tag))) {
    try {
      const raw = await fs.readFile(runJsonPathFor(tag), "utf8");
      prompt = JSON.parse(raw).prompt ?? null;
    } catch {
      // ignore
    }
  }

  let spec: WorldSpecLite | null = null;
  const specPath = path.join(dir, `world_spec_${tag}.json`);
  if (existsSync(specPath)) {
    try {
      const raw = await fs.readFile(specPath, "utf8");
      const parsed = JSON.parse(raw);
      spec = {
        layers: parsed.layers ?? [],
        mobs: parsed.mobs ?? [],
        obstacles: parsed.obstacles ?? [],
        items: parsed.items ?? [],
      };
    } catch {
      // ignore
    }
  }

  let present: string[] = [];
  if (existsSync(dir)) {
    const entries = await fs.readdir(dir);
    present = entries.filter(
      (n) => !n.endsWith(".meta.json") && !n.endsWith(".log"),
    );
  }

  return {
    tag,
    prompt,
    status: status.status,
    failedStage: status.failedStage ?? null,
    spec,
    present,
  };
}

export default async function GeneratePage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  const initial = await loadInitial(tag);
  return <GenerateView initial={initial} />;
}
