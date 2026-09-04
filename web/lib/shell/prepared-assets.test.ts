import { describe, expect, test } from "bun:test";
import {
  parsePreparedRuntimeManifest,
  PREPARED_RUNTIME_BLOCKS,
} from "@/lib/manifest/prepared-manifest";
import { INVENTORY_GRID_4X2_V1 } from "@/lib/manifest/inventory-layout";
import { UI_ATLAS_FIXTURE_ROLES } from "./prepared-runtime.fixture";
import { projectPreparedRuntimeAssets } from "./prepared-assets";

const DIGEST = "a".repeat(64);

function image(path: string, role = "asset") {
  return {
    path,
    sha256: DIGEST,
    bytes: 100,
    media_type: "image/png",
    role,
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
    role: "asset",
  };
}

function record(path: string) {
  return {
    path,
    sha256: DIGEST,
    bytes: 300,
    media_type: "application/json",
    role: "provenance",
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
    projectile: image("content/projectiles/pebble.png"),
    track: audio("soundtrack/meadow.mp3"),
    inventoryPanel: image("ui/inventory_panel.png"),
    panelFrame: image("ui/panel_frame.png"),
    buttonSheet: image("ui/button_rect.png"),
    iconSheet: image("ui/preview_icons.png"),
  };
  // Published by the run and bound by nothing: the closure is wider than the bindings, which is
  // the shape a real package has and the one this projection has to survive.
  const provenance = [
    image("content/players/hero/motion-rebase-plate.png", "provenance"),
    record("maps/meadow/terrain.json"),
  ];
  const closure = [...Object.values(assets), ...provenance].reverse();
  return {
    schema_version: 11,
    kind: "prepared-game-runtime-v11",
    blocks: { ...PREPARED_RUNTIME_BLOCKS },
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
    scale: {
      unit: "player_height",
      player_height_tiles: 2.4,
      minimum: 0.25,
      steps: [0.25, 0.5, 0.75, 1, 1.5, 2, 3],
      ranks: { common: 0.5, uncommon: 0.65, elite: 0.85, boss: 1.5 },
    },
    maps: [
      {
        map_id: "meadow",
        revision: 1,
        display_name: "Sunny Meadow",
        role: "safe_village_hub",
        camera: { mode: "player_follow", follow_axes: ["x"] },
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
          anchor: "bottom",
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
          anchor: "bottom",
          playback: {
            mode: "loop",
            canonical_frame_indices: [0, 1, 2, 3],
            frames_per_second: 6,
          },
          asset: assets.playerCrouch,
        },
      },
      calibration: {
        height_units: 1,
        height_units_source: "definition",
        source_px_per_unit: 600,
        measured_sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        subject_extent_px: 600,
        baseline_state: "idle",
        state_rebase: { idle: 1, crouch: 1.09 },
        plate_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
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
        calibration: {
          height_units: 0.5,
          height_units_source: "rank",
          source_px_per_unit: 400,
          measured_sha256: "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
          subject_extent_px: 200,
        },
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
            anchor: "bottom",
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
        calibration: {
          height_units: 1.0,
          height_units_source: "authored",
          source_px_per_unit: 500,
          measured_sha256: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
          subject_extent_px: 500,
        },
        npc_id: "guide",
        display_name: "Village Guide",
        role: "guide",
        world: {
          source_facing: "front",
          runtime_mirror: false,
          columns: 4,
          rows: 1,
          source_frame_count: 4,
          anchor: "bottom",
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
        calibration: {
          height_units: 3.0,
          height_units_source: "authored",
          source_px_per_unit: 300,
          measured_sha256: "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
          subject_extent_px: 900,
        },
        prop_id: "signpost",
        display_name: "Signpost",
        ground_contact_y_normalized: 0.75,
        asset: assets.prop,
      },
    ],
    items: [
      {
        calibration: {
          height_units: 0.25,
          height_units_source: "authored",
          source_px_per_unit: 800,
          measured_sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          subject_extent_px: 200,
        },
        item_id: "coin",
        display_name: "Coin",
        item_kind: "currency",
        asset: assets.item,
      },
    ],
    projectiles: [
      {
        calibration: {
          height_units: 0.2,
          height_units_source: "authored",
          source_px_per_unit: 700,
          measured_sha256: "1111111111111111111111111111111111111111111111111111111111111111",
          subject_extent_px: 140,
        },
        projectile_id: "pebble",
        display_name: "Sling Pebble",
        silhouette: "round",
        flight: "arc",
        impact: "puff",
        asset: assets.projectile,
      },
    ],
    ui: {
      inventory_panel: {
        ...INVENTORY_GRID_4X2_V1,
        asset: assets.inventoryPanel,
      },
      panel_frame: { ...UI_ATLAS_FIXTURE_ROLES.panel_frame, asset: assets.panelFrame },
      button_rect: { ...UI_ATLAS_FIXTURE_ROLES.button_rect, asset: assets.buttonSheet },
      preview_icons: { ...UI_ATLAS_FIXTURE_ROLES.preview_icons, asset: assets.iconSheet },
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
    scenarios: [],
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

  test("the declared camera is parsed, and an axis this scene cannot drive is rejected", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    expect(manifest.maps[0]!.camera).toEqual({
      mode: "player_follow",
      follow_axes: ["x"],
    });

    // Every rejection matters for the same reason: the scene sizes the camera's world box from
    // this field, so a value it silently accepted would strand the player outside the frame
    // rather than fail loudly at load.
    for (const [camera, message] of [
      [undefined, /map camera must be an object/],
      [{ mode: "cinematic_rail", follow_axes: ["x"] }, /camera mode is unsupported/],
      [{ mode: "player_follow", follow_axes: ["z"] }, /follow axis is invalid/],
      [{ mode: "player_follow", follow_axes: ["x", "x"] }, /follow_axes must be unique/],
      [{ mode: "player_follow", follow_axes: ["y", "x"] }, /canonical x, y order/],
    ] as const) {
      const broken = structuredClone(preparedManifestFixture());
      if (camera === undefined) delete (broken.maps[0] as Record<string, unknown>).camera;
      else (broken.maps[0] as Record<string, unknown>).camera = camera;
      expect(() => parsePreparedRuntimeManifest(broken)).toThrow(message);
    }
  });

  test("an empty axis list is a single-screen camera, not a malformed one", () => {
    const fixed = structuredClone(preparedManifestFixture());
    (fixed.maps[0] as Record<string, unknown>).camera = {
      mode: "player_follow",
      follow_axes: [],
    };
    expect(parsePreparedRuntimeManifest(fixed).maps[0]!.camera.follow_axes).toEqual([]);
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
      "projectiles",
      "ui",
      "soundtrack",
      "provenance",
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
    // The whole closure is accounted for, each artifact under the role it was published as.
    expect(cards).toHaveLength(manifest.closure.artifact_count);
    expect(new Set(paths).size).toBe(paths.length);
    expect(new Set(paths)).toEqual(
      new Set(manifest.closure.artifacts.map((artifact) => artifact.path)),
    );
    expect(groups.filter((entry) => entry.role === "provenance")).toHaveLength(1);
    expect(cards.find((asset) => asset.path === "soundtrack/meadow.mp3")).toEqual({
      path: "soundtrack/meadow.mp3",
      label: "Meadow Theme",
      media_type: "audio/mpeg",
      bytes: 200,
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
  test("lists provenance under its own role instead of presenting it as content", () => {
    const manifest = parsePreparedRuntimeManifest(preparedManifestFixture());
    const groups = projectPreparedRuntimeAssets(manifest);

    const provenance = groups.find((entry) => entry.group_id === "provenance");
    expect(provenance?.role).toBe("provenance");
    // Listed in the order the producer published them, which is the closure's own order.
    expect(provenance?.assets.map((asset) => asset.path)).toEqual([
      "maps/meadow/terrain.json",
      "content/players/hero/motion-rebase-plate.png",
    ]);
    // A judged plate is a PNG under `content/`, so no media type or path convention could have
    // separated it from the artwork it was composed from. The declared role does.
    expect(provenance?.assets[1]?.media_type).toBe("image/png");
    expect(
      groups
        .filter((entry) => entry.role === "asset")
        .flatMap((entry) => entry.assets.map((asset) => asset.path)),
    ).not.toContain("content/players/hero/motion-rebase-plate.png");
  });

  test("lists an asset it cannot group yet rather than refusing to render the page", () => {
    // This is the whole failure mode the role vocabulary exists to stop: a package grows an
    // artifact family before this view learns it. Showing the run minus one card beats showing
    // nobody anything.
    const grown = structuredClone(preparedManifestFixture());
    grown.closure.artifacts.push(image("content/pets/moth.png"));
    grown.closure.artifact_count = grown.closure.artifacts.length;

    const groups = projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(grown));
    const ungrouped = groups.find((entry) => entry.group_id === "ungrouped");
    expect(ungrouped?.role).toBe("asset");
    expect(ungrouped?.assets.map((asset) => asset.path)).toEqual([
      "content/pets/moth.png",
    ]);
    expect(groups.flatMap((entry) => entry.assets)).toHaveLength(
      grown.closure.artifact_count,
    );
  });

  test("rejects a binding onto an artifact published as provenance", () => {
    // The judged plate is shaped exactly like the artwork, so only the role catches this.
    const misbound = structuredClone(preparedManifestFixture());
    misbound.items[0]!.asset = image(
      "content/players/hero/motion-rebase-plate.png",
      "provenance",
    );
    misbound.closure.artifacts = misbound.closure.artifacts.filter(
      (artifact) => artifact.path !== "content/items/coin.png",
    );
    misbound.closure.artifact_count = misbound.closure.artifacts.length;

    expect(() =>
      projectPreparedRuntimeAssets(parsePreparedRuntimeManifest(misbound)),
    ).toThrow(
      "prepared asset binding resolves to a provenance artifact: content/players/hero/motion-rebase-plate.png",
    );
  });

  test("rejects a closure artifact with no declared role", () => {
    const roleless = structuredClone(preparedManifestFixture());
    delete (roleless.closure.artifacts[0] as { role?: string }).role;

    expect(() => parsePreparedRuntimeManifest(roleless)).toThrow(
      "closure.artifacts[0].role is invalid",
    );
  });
});
