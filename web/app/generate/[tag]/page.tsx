// Per-run details view.
//
// Prepared packages are projected strictly from manifest bindings into an
// immutable asset explorer. Historical prompt runs retain their live SSE view
// until that independent pipeline and its evidence are retired together.

import { promises as fs } from "node:fs";
import { existsSync } from "node:fs";
import { notFound } from "next/navigation";
import GenerateView from "./GenerateView";
import PreparedAssetExplorer from "./PreparedAssetExplorer";
import {
  artifactPathFor,
  isSafeRunTag,
  readRunInput,
  readRunStatus,
  runDirFor,
} from "@/lib/shell/runs";
import type { WorldSpecLite } from "@/lib/shell/slots";
import type { TransparencyMode } from "@/lib/shell/transparency";
import { projectPreparedRuntimeAssets } from "@/lib/shell/prepared-assets";
import { readPreparedRuntimeManifest } from "@/lib/shell/prepared-runtime";

export const dynamic = "force-dynamic";

interface InitialState {
  tag: string;
  prompt: string | null;
  transparencyMode: TransparencyMode | null;
  status: "missing" | "running" | "done" | "failed";
  failedStage: string | null;
  spec: WorldSpecLite | null;
  present: string[];
}

async function loadInitial(tag: string): Promise<InitialState> {
  if (!isSafeRunTag(tag)) notFound();
  const dir = runDirFor(tag);
  const status = await readRunStatus(tag);

  const runInput = await readRunInput(tag);

  let spec: WorldSpecLite | null = null;
  const specPath = artifactPathFor(tag, `world_spec_${tag}.json`);
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
    prompt: runInput?.prompt ?? null,
    transparencyMode: runInput?.transparencyMode ?? null,
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
  if (!isSafeRunTag(tag)) notFound();
  const preparedManifest = await readPreparedRuntimeManifest(tag);
  if (preparedManifest) {
    return (
      <PreparedAssetExplorer
        model={{
          tag,
          game_id: preparedManifest.game_id,
          display_name: preparedManifest.display_name,
          revision: preparedManifest.revision,
          package_sha256: preparedManifest.package_sha256,
          artifact_count: preparedManifest.closure.artifact_count,
          groups: projectPreparedRuntimeAssets(preparedManifest),
        }}
      />
    );
  }
  const initial = await loadInitial(tag);
  return <GenerateView initial={initial} />;
}
