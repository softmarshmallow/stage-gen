export const GAMEPLAY_AUTOMATION_VERSION = "gameplay-v1";
export const GAMEPLAY_FIXTURE_METADATA_FILE = "fixture.gameplay-v1.json";

const GAMEPLAY_RUNTIME_ASSET_KEYS = Object.freeze([
  "layer_sky",
  "layer_ridges",
  "layer_foreground",
  "tileset",
  "ladder",
  "items",
  "mob_0_idle",
  "mob_0_hurt",
  "mob_concept_0",
  "character_concept",
  "character_idle",
  "character_walk",
  "character_run",
  "character_jump",
  "character_climb",
  "character_crawl",
  "character_attack",
  "inventory",
  "portal",
  "concept",
]);

export function gameplayRequiredAssetKeys(
  worldName: string,
): readonly string[] {
  if (!worldName || worldName !== worldName.trim()) {
    throw new Error("gameplay world name must be stable nonempty text");
  }
  return Object.freeze(
    [`spec:${worldName}`, ...GAMEPLAY_RUNTIME_ASSET_KEYS].sort(),
  );
}

export type GameplayFixture = Readonly<{
  outRoot: string;
  runDir: string;
  tag: string;
  route: string;
  files: readonly string[];
  digest: string;
}>;
