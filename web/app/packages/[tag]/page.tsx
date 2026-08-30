// Per-package asset explorer.
//
// Projects one published prepared-runtime manifest into its bound closure artifacts.
// It reads the same validated manifest the preview boots from, and generates nothing.

import { notFound } from "next/navigation";
import PreparedAssetExplorer from "./PreparedAssetExplorer";
import { projectPreparedRuntimeAssets } from "@/lib/shell/prepared-assets";
import { readPreparedRuntimeManifest } from "@/lib/shell/prepared-runtime";
import { isSafeRunTag } from "@/lib/shell/runs";

export const dynamic = "force-dynamic";

export default async function PackagePage({
  params,
}: {
  params: Promise<{ tag: string }>;
}) {
  const { tag } = await params;
  if (!isSafeRunTag(tag)) notFound();
  const manifest = await readPreparedRuntimeManifest(tag);
  if (!manifest) notFound();
  return (
    <PreparedAssetExplorer
      model={{
        tag,
        game_id: manifest.game_id,
        display_name: manifest.display_name,
        revision: manifest.revision,
        package_sha256: manifest.package_sha256,
        artifact_count: manifest.closure.artifact_count,
        groups: projectPreparedRuntimeAssets(manifest),
      }}
    />
  );
}
