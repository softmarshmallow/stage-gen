import { describe, expect, test } from "bun:test";
import { parsePreparedRuntimeManifest } from "@/lib/runtime/prepared-manifest";
import { INVENTORY_GRID_4X2_V1 } from "@/lib/runtime/inventory-layout";
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
    climbable: image("maps/meadow/climbable.png"),
    portal: image("maps/meadow/portal.png"),
    playerConcept: image("content/players/hero/concept.png"),
    playerIdle: image("content/players/hero/states/idle.png"),
    playerCrouch: image("content/players/hero/states/crouch.png"),
    playerDialogue: image("content/players/hero/dialogue.png"),
    mobConcept: image("content/mobs/slime/concept.png"),
    mobIdle: image("content/mobs/slime/states/idle.png"),
    npcWorld: image("content/npcs/guide/world.png"),
    npcDialogue: image("content/npcs/guide/dialogue.png"),
    prop: image("content/props/signpost.png"),
    item: image("content/items/coin.png"),
    track: audio("soundtrack/meadow.mp3"),
    inventoryPanel: image("ui/inventory_panel.png"),
  };
  const closure = Object.values(assets).reverse();
  return {
    schema_version: 9,
    kind: "prepared-game-runtime-v9",
    game_id: "fixture",
    revision: 1,
    display_name: "Fixture Game",
    package_sha256: DIGEST,
    presentation: {
      view_profile: "side_view_2d",
      gameplay_space: "side_plane",
      contact_shadows: {
        enabled: true,
        opacity: 0.18,
        softness_screen_pixels: 6,
      },
    },
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
            placement: {
              vertical_anchor: "canvas_cover",
              vertical_offset: 0,
              vertical_offset_source: "measured",
              source_height: 1024,
              trimmed_height: 1024,
              trimmed_top: 0,
            },
            presentation: {
              contrast: 1,
              saturation: 1,
              atmosphere_color: "#ffffff",
              atmosphere_strength: 0,
              detail_blur_screen_pixels: 0,
            },
            asset: assets.foreground,
          },
          {
            layer_id: "blue_sky",
            plane: "background",
            order: 0,
            parallax: 0,
            alpha_mode: "opaque",
            placement: {
              vertical_anchor: "canvas_cover",
              vertical_offset: 0,
              vertical_offset_source: "measured",
              source_height: 1024,
              trimmed_height: 1024,
              trimmed_top: 0,
            },
            presentation: {
              contrast: 1,
              saturation: 1,
              atmosphere_color: "#ffffff",
              atmosphere_strength: 0,
              detail_blur_screen_pixels: 0,
            },
            asset: assets.sky,
          },
        ],
        ground: {
          mode: "terrain-atlas-3x3-minimal-v1",
          occupancy: ["0000000000", "1111111111"],
          vertical_fit: "floor_to_screen_bottom",
          walk_surface_row: 0,
          asset: assets.ground,
        },
        climbable: {
          mode: "climbable-atlas-v1",
          asset: assets.climbable,
          index_order: "left_to_right",
          variants: [
            {
              variant_id: "meadow_ladder",
              role: "ladder",
              cell_index: 0,
              cell: { x: 0, y: 0, width: 256, height: 1280 },
            },
          ],
          placements: [
            {
              climbable_id: "meadow_ladder",
              variant_id: "meadow_ladder",
              normalized_x: 0.5,
              bottom_surface: "terrain",
              rise_tiles: 4,
            },
          ],
        },
        portal: {
          mode: "portal-pair-1x2-v1",
          asset: assets.portal,
          endpoints: [
            { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
            { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
          ],
        },
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
          source_frame_count: 4,
          playback: {
            mode: "hold",
            canonical_frame_indices: [0],
          },
          asset: assets.playerIdle,
        },
        crouch: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          source_frame_count: 4,
          playback: {
            mode: "loop",
            canonical_frame_indices: [0, 1, 2, 3],
            frames_per_second: 6,
          },
          asset: assets.playerCrouch,
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
            source_frame_count: 4,
            playback: {
              mode: "loop",
              canonical_frame_indices: [0, 1, 2, 3],
              frames_per_second: 6,
            },
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
          source_facing: "front",
          runtime_mirror: false,
          columns: 4,
          rows: 1,
          source_frame_count: 4,
          playback: {
            mode: "hold",
            canonical_frame_indices: [0],
          },
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
        ground_contact_y_normalized: 0.75,
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
    ui: {
      inventory_panel: {
        ...INVENTORY_GRID_4X2_V1,
        asset: assets.inventoryPanel,
      },
    },
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
  test("requires an explicit normalized prop ground contact", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    expect(manifest.props[0]?.ground_contact_y_normalized).toBe(0.75);

    const missing = structuredClone(preparedManifestFixture());
    delete (missing.props[0] as { ground_contact_y_normalized?: number })
      .ground_contact_y_normalized;
    expect(() => parsePreparedRuntimeManifest(missing)).toThrow(
      "props[0].ground_contact_y_normalized must be a finite number",
    );

    const belowCanvas = structuredClone(preparedManifestFixture());
    belowCanvas.props[0]!.ground_contact_y_normalized = 1.01;
    expect(() => parsePreparedRuntimeManifest(belowCanvas)).toThrow(
      "props[0].ground_contact_y_normalized must be a finite number",
    );
  });

  test("retains explicit player and mob concept bindings", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());

    expect(manifest.player.concept.path).toBe(
      "content/players/hero/concept.png",
    );
    expect(manifest.mobs[0]?.concept.path).toBe(
      "content/mobs/slime/concept.png",
    );
  });

  test("validates playback independently from source-frame sampling", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    expect(manifest.player.states.idle?.source_frame_count).toBe(4);
    expect(manifest.player.states.idle?.playback).toEqual({
      mode: "hold",
      canonical_frame_indices: [0],
    });

    const unavailable = structuredClone(preparedManifestFixture());
    unavailable.player.states.idle.playback.canonical_frame_indices = [4];
    expect(() => parsePreparedRuntimeManifest(unavailable)).toThrow(
      "playback canonical frame selection is invalid",
    );

    const timedHold = structuredClone(preparedManifestFixture());
    (
      timedHold.player.states.idle.playback as {
        frames_per_second?: number;
      }
    ).frames_per_second = 4;
    expect(() => parsePreparedRuntimeManifest(timedHold)).toThrow(
      "playback shape is invalid for hold",
    );
  });

  test("parses exact map-owned terrain, climbable, and portal contracts", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    const map = manifest.maps[0]!;
    expect(map.ground.occupancy).toEqual([
      "0000000000",
      "1111111111",
    ]);
    expect(map.climbable?.placements[0]).toEqual({
      climbable_id: "meadow_ladder",
      variant_id: "meadow_ladder",
      normalized_x: 0.5,
      bottom_surface: "terrain",
      rise_tiles: 4,
    });
    expect(map.portal?.endpoints).toEqual([
      { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
      { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
    ]);
    expect(Object.isFrozen(map.ground.occupancy)).toBeTrue();
    expect(Object.isFrozen(map.climbable?.placements)).toBeTrue();
    expect(Object.isFrozen(map.portal?.endpoints)).toBeTrue();

    const occupancy = structuredClone(preparedManifestFixture());
    occupancy.maps[0]!.ground.occupancy = ["10", "1"];
    expect(() => parsePreparedRuntimeManifest(occupancy)).toThrow(
      "ground.occupancy must be a 2-64 row, 8-512 column zero-one rectangle",
    );

    const climbable = structuredClone(preparedManifestFixture());
    climbable.maps[0]!.climbable.placements[0]!.rise_tiles = 3;
    expect(() => parsePreparedRuntimeManifest(climbable)).toThrow(
      "climbable placement geometry is invalid",
    );

    const undeclared = structuredClone(preparedManifestFixture());
    undeclared.maps[0]!.climbable.placements[0]!.variant_id = "not_declared";
    expect(() => parsePreparedRuntimeManifest(undeclared)).toThrow(
      "climbable placement names an undeclared variant",
    );

    // Cell index is roster index; a manifest that disagrees is rejected rather than trusted.
    const misindexed = structuredClone(preparedManifestFixture());
    misindexed.maps[0]!.climbable.variants[0]!.cell_index = 3;
    expect(() => parsePreparedRuntimeManifest(misindexed)).toThrow(
      "climbable variant cell_index must equal its roster index",
    );

    const portal = structuredClone(preparedManifestFixture());
    portal.maps[0]!.portal.endpoints[1]!.role = "entry";
    expect(() => parsePreparedRuntimeManifest(portal)).toThrow(
      "portal endpoints must have unique anchors, positions, and roles",
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
      "ui",
      "soundtrack",
    ]);
    expect(groups[0]?.assets.map((asset) => asset.path)).toEqual([
      "maps/meadow/layers/sky.png",
      "maps/meadow/ground.png",
      "maps/meadow/climbable.png",
      "maps/meadow/portal.png",
      "maps/meadow/layers/flowers.png",
    ]);
    expect(groups[0]?.assets.map((asset) => asset.transparent)).toEqual([
      false,
      true,
      true,
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
