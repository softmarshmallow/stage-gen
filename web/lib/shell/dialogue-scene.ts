// Server-side helper: read and enumerate visual-novel scene runs.
//
// A scene run is played straight out of `out/<tag>/`, the way a room is. That is
// now the only way a scene is played: the install-a-theme path and the DOM
// preview route it fed were retired with the beat list they were built around.

import { promises as fs } from "node:fs";
import path from "node:path";
import {
  parseDialogueSceneBundle,
  projectDialogueSceneFixture,
} from "@/lib/dialogue-scene/bundle";
import type { DialogueSceneFixture } from "@/lib/dialogue-scene/schema";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT, runDirFor } from "./runs";

const BUNDLE_NAME = "bundle.json";

async function readJson(file: string): Promise<unknown | null> {
  try {
    return JSON.parse(await fs.readFile(file, "utf8")) as unknown;
  } catch {
    return null;
  }
}

/**
 * The run's own bundle, projected for playing in place.
 *
 * A run whose bundle is absent is simply not a scene run here; a bundle that is
 * present and invalid still throws, because that is a contract violation rather
 * than a run this build declines to read.
 */
export async function readSceneFixture(tag: string): Promise<DialogueSceneFixture | null> {
  if (!isSafeRunTag(tag)) return null;
  const document = await readJson(path.join(runDirFor(tag), BUNDLE_NAME));
  if (document === null) return null;
  const bundle = parseDialogueSceneBundle(document);
  return projectDialogueSceneFixture(bundle, (asset) => `/api/assets/${tag}/${asset.path}`);
}

export interface ReadyScene {
  tag: string;
  gameId: string;
  title: string;
  /** Run-relative ref of the authored plate every image was drawn against. */
  styleReference: string;
  /** How many drawable actors and stages the scene carries, for the index row. */
  actors: number;
  stages: number;
}

export async function listReadyScenes(): Promise<ReadyScene[]> {
  if (!(await assertSafeOutRoot())) return [];
  const entries = await fs.readdir(OUT_ROOT, { withFileTypes: true });
  const out: ReadyScene[] = [];
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isDirectory() || !isSafeRunTag(entry.name)) return;
      const document = await readJson(path.join(runDirFor(entry.name), BUNDLE_NAME));
      if (document === null) return;
      let bundle;
      try {
        bundle = parseDialogueSceneBundle(document);
      } catch {
        // A bundle this build cannot read is not a playable scene. The run
        // viewer still lists the run; only the play link is withheld.
        return;
      }
      const style = bundle.assets.find((asset) => asset.role === "style");
      out.push({
        tag: entry.name,
        gameId: bundle.gameId,
        title: bundle.sceneData.title,
        styleReference: style?.path ?? "",
        actors: bundle.sceneData.actors.length,
        stages: bundle.sceneData.stages.length,
      });
    }),
  );
  return out.sort((left, right) => left.tag.localeCompare(right.tag));
}
