// Server-side helper: read and enumerate visual-novel scene runs.
//
// A scene run is played straight out of `out/<tag>/`, the way a room is. The
// install/activate path still exists for pinning one scene as the site's active
// theme; this is the other thing you want most of the time - open the run you
// just generated and look at it.

import { promises as fs } from "node:fs";
import path from "node:path";
import type { DialogueSceneDemoFixture } from "@/lib/dialogue-scene/schema";
import {
  parseDialogueSceneBundleV4,
  projectDialogueSceneFixture,
} from "@/lib/dialogue-scene/theme-adapter";
import { assertSafeOutRoot, isSafeRunTag, OUT_ROOT, runDirFor } from "./runs";

const BUNDLE_NAME = "bundle.json";
const PROFILE_NAME = "character-profile.json";

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
export async function readSceneFixture(
  tag: string,
): Promise<DialogueSceneDemoFixture | null> {
  if (!isSafeRunTag(tag)) return null;
  const directory = runDirFor(tag);
  const document = await readJson(path.join(directory, BUNDLE_NAME));
  if (document === null) return null;
  const bundle = parseDialogueSceneBundleV4(document);
  const profile = await readJson(path.join(directory, PROFILE_NAME));
  if (profile === null || typeof profile !== "object") {
    throw new Error(`scene run ${tag} is missing its character profile`);
  }
  const identity = profile as { profile_id?: unknown; revision?: unknown };
  if (typeof identity.profile_id !== "string" || typeof identity.revision !== "number") {
    throw new Error(`scene run ${tag} character profile has no usable identity`);
  }
  return projectDialogueSceneFixture(
    bundle,
    { profile_id: identity.profile_id, revision: identity.revision },
    (asset) => `/api/assets/${tag}/${asset.path}`,
  );
}

export interface ReadyScene {
  tag: string;
  gameId: string;
  title: string;
  /** Run-relative ref of the authored plate every image was drawn against. */
  identityReference: string;
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
        bundle = parseDialogueSceneBundleV4(document);
      } catch {
        // A bundle this build cannot read is not a playable scene. The run
        // viewer still lists the run; only the play link is withheld.
        return;
      }
      out.push({
        tag: entry.name,
        gameId: bundle.game_id,
        title: bundle.scene_data.title,
        identityReference: bundle.identity_reference.path,
      });
    }),
  );
  return out.sort((left, right) => left.tag.localeCompare(right.tag));
}
