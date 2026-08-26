import { describe, expect, test } from "bun:test";
import { parsePreparedRuntimeManifest } from "@/lib/runtime/prepared-manifest";
import { projectPreparedRuntimeAssets } from "./prepared-assets";

const DIGEST = "a".repeat(64);

function image(path: string) {
  return {
    path,
    sha256: DIGEST,
    bytes: 100,
    media_type: "image/png",
    width: 128,
    height: 64,
  };
}

function audio(path: string) {
  return {
    path,
    sha256: DIGEST,
    bytes: 200,
    media_type: "audio/mpeg",
  };
}

function preparedManifestFixture() {
  const assets = {
    sky: image("maps/meadow/layers/sky.png"),
    foreground: image("maps/meadow/layers/flowers.png"),
    ground: image("maps/meadow/ground.png"),
    playerConcept: image("content/players/hero/concept.png"),
    playerIdle: image("content/players/hero/states/idle.png"),
    playerDialogue: image("content/players/hero/dialogue.png"),
    mobConcept: image("content/mobs/slime/concept.png"),
    mobIdle: image("content/mobs/slime/states/idle.png"),
    npcWorld: image("content/npcs/guide/world.png"),
    npcDialogue: image("content/npcs/guide/dialogue.png"),
    prop: image("content/props/signpost.png"),
    item: image("content/items/coin.png"),
    track: audio("soundtrack/meadow.mp3"),
  };
  const closure = Object.values(assets).reverse();
  return {
    schema_version: 1,
    kind: "prepared-game-runtime-v1",
    game_id: "fixture",
    revision: 1,
    display_name: "Fixture Game",
    package_sha256: DIGEST,
    entry_map_id: "meadow",
    entry_spawn_id: "west_gate",
    maps: [
      {
        map_id: "meadow",
        revision: 1,
        display_name: "Sunny Meadow",
        role: "safe_village_hub",
        hostile_population_enabled: false,
        track_ids: ["meadow_theme"],
        layers: [
          {
            layer_id: "flower_frame",
            plane: "foreground",
            order: 0,
            parallax: 1.2,
            alpha_mode: "transparent",
            asset: assets.foreground,
          },
          {
            layer_id: "blue_sky",
            plane: "background",
            order: 0,
            parallax: 0,
            alpha_mode: "opaque",
            asset: assets.sky,
          },
        ],
        ground: { mode: "tileset-12x4-v1", asset: assets.ground },
      },
    ],
    player: {
      player_id: "hero",
      display_name: "Hero",
      concept: assets.playerConcept,
      states: {
        idle: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          asset: assets.playerIdle,
        },
      },
      dialogue: {
        columns: 1,
        rows: 1,
        index_order: "row_major",
        expressions: ["neutral"],
        asset: assets.playerDialogue,
      },
    },
    mobs: [
      {
        mob_id: "slime",
        display_name: "Sun Slime",
        rank: "common",
        concept: assets.mobConcept,
        states: {
          idle: {
            source_facing: "right",
            runtime_mirror: true,
            columns: 4,
            rows: 1,
            asset: assets.mobIdle,
          },
        },
      },
    ],
    npcs: [
      {
        npc_id: "guide",
        display_name: "Village Guide",
        role: "guide",
        world: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          asset: assets.npcWorld,
        },
        dialogue: {
          columns: 1,
          rows: 1,
          index_order: "row_major",
          expressions: ["neutral"],
          asset: assets.npcDialogue,
        },
      },
    ],
    props: [
      {
        prop_id: "signpost",
        display_name: "Signpost",
        asset: assets.prop,
      },
    ],
    items: [
      {
        item_id: "coin",
        display_name: "Coin",
        item_kind: "currency",
        asset: assets.item,
      },
    ],
    soundtrack: {
      playback: { selection: "shuffle", no_immediate_repeat: true },
      tracks: [
        {
          track_id: "meadow_theme",
          display_name: "Meadow Theme",
          asset: assets.track,
        },
      ],
    },
    gameplay: {},
    sequences: [],
    closure: {
      artifact_count: closure.length,
      artifacts_sha256: DIGEST,
      artifacts: closure,
    },
  };
}

describe("prepared runtime asset projection", () => {
  test("retains explicit player and mob concept bindings", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());

    expect(manifest.player.concept.path).toBe(
      "content/players/hero/concept.png",
    );
    expect(manifest.mobs[0]?.concept.path).toBe(
      "content/mobs/slime/concept.png",
    );
  });

  test("projects every semantic binding exactly once in stable group order", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    const groups = projectPreparedRuntimeAssets(manifest);

    expect(groups.map((entry) => entry.group_id)).toEqual([
      "map-meadow",
      "player-hero",
      "mob-slime",
      "npc-guide",
      "props",
      "items",
      "soundtrack",
    ]);
    expect(groups[0]?.assets.map((asset) => asset.path)).toEqual([
      "maps/meadow/layers/sky.png",
      "maps/meadow/ground.png",
      "maps/meadow/layers/flowers.png",
    ]);
    expect(groups[0]?.assets.map((asset) => asset.transparent)).toEqual([
      false,
      true,
      true,
    ]);

    const cards = groups.flatMap((entry) => entry.assets);
    const paths = cards.map((asset) => asset.path);
    expect(cards).toHaveLength(manifest.closure.artifact_count);
    expect(new Set(paths).size).toBe(paths.length);
    expect(new Set(paths)).toEqual(
      new Set(manifest.closure.artifacts.map((artifact) => artifact.path)),
    );
    expect(cards.at(-1)).toEqual({
      path: "soundtrack/meadow.mp3",
      label: "Meadow Theme",
      media_type: "audio/mpeg",
      transparent: false,
    });
    expect(Object.isFrozen(groups)).toBeTrue();
    expect(groups.every(Object.isFrozen)).toBeTrue();
    expect(groups.every((entry) => Object.isFrozen(entry.assets))).toBeTrue();
    expect(cards.every(Object.isFrozen)).toBeTrue();
  });

  test("rejects missing, extra, divergent, and duplicate closure bindings", () => {
    const missing = structuredClone(preparedManifestFixture());
    missing.closure.artifacts = missing.closure.artifacts.filter(
      (artifact) => artifact.path !== "content/props/signpost.png",
    );
    missing.closure.artifact_count = missing.closure.artifacts.length;
    expect(() =>
      projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(missing)),
    ).toThrow(
      "prepared asset is missing from closure: content/props/signpost.png",
    );

    const extra = structuredClone(preparedManifestFixture());
    extra.closure.artifacts.push(image("content/props/extra.png"));
    extra.closure.artifact_count = extra.closure.artifacts.length;
    expect(() =>
      projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(extra)),
    ).toThrow(
      "prepared asset closure contains an unbound artifact: content/props/extra.png",
    );

    const divergent = structuredClone(preparedManifestFixture());
    const divergentIndex = divergent.closure.artifacts.findIndex(
      (artifact) => artifact.path === "content/items/coin.png",
    );
    const divergentItem = divergent.closure.artifacts[divergentIndex];
    if (divergentIndex < 0 || !divergentItem) {
      throw new Error("fixture item is missing");
    }
    divergent.closure.artifacts[divergentIndex] = {
      ...divergentItem,
      bytes: divergentItem.bytes + 1,
    };
    expect(() =>
      projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(divergent)),
    ).toThrow(
      "prepared asset metadata disagrees with closure: content/items/coin.png",
    );

    const duplicateClosure = structuredClone(preparedManifestFixture());
    duplicateClosure.closure.artifacts.push(
      structuredClone(duplicateClosure.closure.artifacts[0]!),
    );
    duplicateClosure.closure.artifact_count =
      duplicateClosure.closure.artifacts.length;
    expect(() =>
      projectPreparedRuntimeAssets(
        parsePreparedRuntimeManifest(duplicateClosure),
      ),
    ).toThrow("prepared asset closure contains duplicate path");

    const duplicateBinding = structuredClone(preparedManifestFixture());
    duplicateBinding.items[0]!.asset = duplicateBinding.props[0]!.asset;
    duplicateBinding.closure.artifacts = duplicateBinding.closure.artifacts.filter(
      (artifact) => artifact.path !== "content/items/coin.png",
    );
    duplicateBinding.closure.artifact_count =
      duplicateBinding.closure.artifacts.length;
    expect(() =>
      projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(duplicateBinding)),
    ).toThrow(
      "prepared asset binding path is used more than once: content/props/signpost.png",
    );
  });
});
