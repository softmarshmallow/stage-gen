import type {
  PreparedRuntimeManifest,
  RuntimeArtifact,
  RuntimeArtifactRole,
} from "@/lib/manifest/prepared-manifest";

export type PreparedAssetCard = Readonly<{
  path: string;
  label: string;
  media_type: string;
  bytes: number;
  width?: number;
  height?: number;
  transparent: boolean;
}>;

export type PreparedAssetGroup = Readonly<{
  group_id: string;
  label: string;
  /** What the producer published these for. Provenance is listed, never presented as content. */
  role: RuntimeArtifactRole;
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
  role: RuntimeArtifactRole;
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
  role: RuntimeArtifactRole = "asset",
): BoundGroup {
  return Object.freeze({
    group_id: groupId,
    label,
    role,
    assets: Object.freeze([...assets]),
  });
}

function sameArtifact(left: RuntimeArtifact, right: RuntimeArtifact): boolean {
  return (
    left.path === right.path &&
    left.sha256 === right.sha256 &&
    left.bytes === right.bytes &&
    left.media_type === right.media_type &&
    left.role === right.role &&
    left.width === right.width &&
    left.height === right.height
  );
}

/**
 * Reconcile what this view binds against the closure the producer published.
 *
 * Throws only on a self-contradictory manifest, which the producer already refuses to write: a
 * binding it never published, a binding whose metadata disagrees with the closure, or a binding
 * onto something published as provenance. Everything else is returned rather than thrown -- an
 * artifact this view has not learned to group is the view falling behind the package, and a
 * details page that cannot show one asset should say so, not refuse to render the other hundred.
 */
function accountForClosure(
  groups: readonly BoundGroup[],
  manifest: PreparedRuntimeManifest,
): readonly RuntimeArtifact[] {
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
      if (closureArtifact.role !== "asset") {
        throw new Error(
          `prepared asset binding resolves to a ${closureArtifact.role} artifact: ${artifact.path}`,
        );
      }
    }
  }

  return Object.freeze(
    manifest.closure.artifacts.filter((artifact) => !boundPaths.has(artifact.path)),
  );
}

function card(asset: BoundAsset): PreparedAssetCard {
  const { artifact } = asset;
  return Object.freeze({
    path: artifact.path,
    label: asset.label,
    media_type: artifact.media_type,
    bytes: artifact.bytes,
    ...(artifact.width === undefined ? {} : { width: artifact.width }),
    ...(artifact.height === undefined ? {} : { height: artifact.height }),
    transparent: asset.transparent,
  });
}

/**
 * Project the prepared runtime's explicit stable-ID bindings into an asset
 * explorer model. No filename convention participates in classification: an
 * artifact is grouped because the manifest binds it, and listed as provenance
 * because the producer published it under that role.
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
        ...(map.climbable
          ? [bound(map.climbable.asset, "Climbable atlas", true)]
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

  if (manifest.projectiles.length > 0) {
    groups.push(
      group(
        "projectiles",
        "Projectiles",
        manifest.projectiles.map((projectile) =>
          bound(projectile.asset, projectile.display_name, true),
        ),
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

  // The closure is accounted for in full: whatever no group above claimed is listed under the
  // role it was published as, so nothing published can disappear from this page unremarked.
  const unclaimed = accountForClosure(groups, manifest);
  const ungrouped = unclaimed.filter((artifact) => artifact.role === "asset");
  const provenance = unclaimed.filter((artifact) => artifact.role === "provenance");
  if (ungrouped.length > 0) {
    groups.push(
      group(
        "ungrouped",
        "Ungrouped assets",
        ungrouped.map((artifact) => bound(artifact, artifact.path, true)),
      ),
    );
  }
  if (provenance.length > 0) {
    groups.push(
      group(
        "provenance",
        "Provenance",
        provenance.map((artifact) => bound(artifact, artifact.path, true)),
        "provenance",
      ),
    );
  }

  return Object.freeze(
    groups.map((entry) =>
      Object.freeze({
        group_id: entry.group_id,
        label: entry.label,
        role: entry.role,
        assets: Object.freeze(entry.assets.map(card)),
      }),
    ),
  );
}
