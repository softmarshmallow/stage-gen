import type {
  PreparedRuntimeManifest,
  RuntimeArtifact,
} from "@/lib/runtime/prepared-manifest";

export type PreparedAssetCard = Readonly<{
  path: string;
  label: string;
  media_type: string;
  width?: number;
  height?: number;
  transparent: boolean;
}>;

export type PreparedAssetGroup = Readonly<{
  group_id: string;
  label: string;
  assets: readonly PreparedAssetCard[];
}>;

type BoundAsset = Readonly<{
  artifact: RuntimeArtifact;
  label: string;
  transparent: boolean;
}>;

type BoundGroup = Readonly<{
  group_id: string;
  label: string;
  assets: readonly BoundAsset[];
}>;

function titleFromId(value: string): string {
  const words = value.replaceAll(/[_-]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function bound(
  artifact: RuntimeArtifact,
  label: string,
  transparent: boolean,
): BoundAsset {
  return Object.freeze({ artifact, label, transparent });
}

function group(
  groupId: string,
  label: string,
  assets: readonly BoundAsset[],
): BoundGroup {
  return Object.freeze({
    group_id: groupId,
    label,
    assets: Object.freeze([...assets]),
  });
}

function sameArtifact(left: RuntimeArtifact, right: RuntimeArtifact): boolean {
  return (
    left.path === right.path &&
    left.sha256 === right.sha256 &&
    left.bytes === right.bytes &&
    left.media_type === right.media_type &&
    left.width === right.width &&
    left.height === right.height
  );
}

function validateExactClosure(
  groups: readonly BoundGroup[],
  manifest: PreparedRuntimeManifest,
): void {
  if (manifest.closure.artifact_count !== manifest.closure.artifacts.length) {
    throw new Error("prepared asset closure count disagrees with its artifacts");
  }

  const closureByPath = new Map<string, RuntimeArtifact>();
  for (const artifact of manifest.closure.artifacts) {
    if (closureByPath.has(artifact.path)) {
      throw new Error(`prepared asset closure contains duplicate path: ${artifact.path}`);
    }
    closureByPath.set(artifact.path, artifact);
  }

  const boundPaths = new Set<string>();
  for (const projectedGroup of groups) {
    for (const asset of projectedGroup.assets) {
      const { artifact } = asset;
      if (boundPaths.has(artifact.path)) {
        throw new Error(
          `prepared asset binding path is used more than once: ${artifact.path}`,
        );
      }
      boundPaths.add(artifact.path);
      const closureArtifact = closureByPath.get(artifact.path);
      if (!closureArtifact) {
        throw new Error(`prepared asset is missing from closure: ${artifact.path}`);
      }
      if (!sameArtifact(artifact, closureArtifact)) {
        throw new Error(
          `prepared asset metadata disagrees with closure: ${artifact.path}`,
        );
      }
    }
  }

  for (const path of closureByPath.keys()) {
    if (!boundPaths.has(path)) {
      throw new Error(`prepared asset closure contains an unbound artifact: ${path}`);
    }
  }
}

function card(asset: BoundAsset): PreparedAssetCard {
  const { artifact } = asset;
  return Object.freeze({
    path: artifact.path,
    label: asset.label,
    media_type: artifact.media_type,
    ...(artifact.width === undefined ? {} : { width: artifact.width }),
    ...(artifact.height === undefined ? {} : { height: artifact.height }),
    transparent: asset.transparent,
  });
}

/**
 * Project the prepared runtime's explicit stable-ID bindings into an asset
 * explorer model. No filename convention participates in classification.
 */
export function projectPreparedRuntimeAssets(
  manifest: PreparedRuntimeManifest,
): readonly PreparedAssetGroup[] {
  const groups: BoundGroup[] = [];

  for (const map of manifest.maps) {
    const background = map.layers
      .filter((layer) => layer.plane === "background")
      .sort((left, right) => left.order - right.order)
      .map((layer) =>
        bound(
          layer.asset,
          `Background: ${titleFromId(layer.layer_id)}`,
          layer.alpha_mode === "transparent",
        ),
      );
    const foreground = map.layers
      .filter((layer) => layer.plane === "foreground")
      .sort((left, right) => left.order - right.order)
      .map((layer) =>
        bound(
          layer.asset,
          `Foreground: ${titleFromId(layer.layer_id)}`,
          layer.alpha_mode === "transparent",
        ),
      );
    groups.push(
      group(`map-${map.map_id}`, `Map: ${map.display_name}`, [
        ...background,
        bound(map.ground.asset, "Ground atlas", true),
        ...(map.ladder
          ? [bound(map.ladder.asset, "Ladder", true)]
          : []),
        ...(map.portal
          ? [bound(map.portal.asset, "Portal pair", true)]
          : []),
        ...foreground,
      ]),
    );
  }

  groups.push(
    group(`player-${manifest.player.player_id}`, `Player: ${manifest.player.display_name}`, [
      bound(manifest.player.concept, "Concept", true),
      ...Object.entries(manifest.player.states)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([state, binding]) =>
          bound(binding.asset, titleFromId(state), true),
        ),
      bound(manifest.player.dialogue.asset, "Dialogue atlas", true),
    ]),
  );

  for (const mob of manifest.mobs) {
    groups.push(
      group(`mob-${mob.mob_id}`, `Mob: ${mob.display_name}`, [
        bound(mob.concept, "Concept", true),
        ...Object.entries(mob.states)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([state, binding]) =>
            bound(binding.asset, titleFromId(state), true),
          ),
      ]),
    );
  }

  for (const npc of manifest.npcs) {
    groups.push(
      group(`npc-${npc.npc_id}`, `NPC: ${npc.display_name}`, [
        bound(npc.world.asset, "World motion", true),
        bound(npc.dialogue.asset, "Dialogue atlas", true),
      ]),
    );
  }

  if (manifest.props.length > 0) {
    groups.push(
      group(
        "props",
        "Props",
        manifest.props.map((prop) => bound(prop.asset, prop.display_name, true)),
      ),
    );
  }

  if (manifest.items.length > 0) {
    groups.push(
      group(
        "items",
        "Items",
        manifest.items.map((item) => bound(item.asset, item.display_name, true)),
      ),
    );
  }

  groups.push(
    group("ui", "UI", [
      bound(manifest.ui.inventory_panel.asset, "Inventory panel", true),
    ]),
  );

  if (manifest.soundtrack.tracks.length > 0) {
    groups.push(
      group(
        "soundtrack",
        "Soundtrack",
        manifest.soundtrack.tracks.map((track) =>
          bound(track.asset, track.display_name, false),
        ),
      ),
    );
  }

  validateExactClosure(groups, manifest);
  return Object.freeze(
    groups.map((entry) =>
      Object.freeze({
        group_id: entry.group_id,
        label: entry.label,
        assets: Object.freeze(entry.assets.map(card)),
      }),
    ),
  );
}
