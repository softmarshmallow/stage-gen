import path from "node:path";
import { dialogueSceneDemoFixture } from "./demo-fixture";
import {
  loadActiveDialogueThemeFixture,
  type DialogueThemeAdapterOptions,
} from "./theme-adapter";
import type { DialogueSceneDemoFixture } from "./schema";

export function defaultDialogueThemeOptions(): DialogueThemeAdapterOptions {
  return Object.freeze({
    stateRoot: path.resolve(process.cwd(), "..", "out", "dialogue-theme-state"),
    publicRoot: path.join(process.cwd(), "public", "dialogue-scene", "themes"),
  });
}

export async function loadDialogueSceneFixture(
  options: DialogueThemeAdapterOptions = defaultDialogueThemeOptions(),
): Promise<DialogueSceneDemoFixture> {
  return (await loadActiveDialogueThemeFixture(options)) ?? dialogueSceneDemoFixture;
}
