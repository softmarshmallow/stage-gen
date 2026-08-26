import type { RuntimeArtifact } from "@/lib/runtime/prepared-manifest";

const HASH = "a".repeat(64);

function artifact(path: string, mediaType = "image/png"): RuntimeArtifact {
  return {
    path,
    sha256: HASH,
    bytes: 128,
    media_type: mediaType,
    width: 64,
    height: 64,
  };
}

export function preparedRuntimeManifestFixture(): Record<string, unknown> {
  const background = artifact("maps/village/background.png");
  const ground = artifact("maps/village/ground.png");
  const playerConcept = artifact("content/player/concept.png");
  const playerIdle = artifact("content/player/states/idle.png");
  const playerDialogue = artifact("content/player/dialogue.png");
  const artifacts = [
    background,
    ground,
    playerConcept,
    playerIdle,
    playerDialogue,
  ];

  return {
    schema_version: 1,
    kind: "prepared-game-runtime-v1",
    game_id: "prepared_fixture",
    revision: 1,
    display_name: "Prepared Fixture",
    package_sha256: "b".repeat(64),
    entry_map_id: "village",
    entry_spawn_id: "arrival",
    maps: [
      {
        map_id: "village",
        revision: 1,
        display_name: "Village",
        role: "safe_village_hub",
        hostile_population_enabled: false,
        track_ids: [],
        layers: [
          {
            layer_id: "blue_sky",
            plane: "background",
            order: 0,
            parallax: 0.1,
            alpha_mode: "opaque",
            asset: background,
          },
        ],
        ground: { mode: "tileset-12x4-v1", asset: ground },
      },
    ],
    player: {
      player_id: "hero",
      display_name: "Hero",
      concept: playerConcept,
      states: {
        idle: {
          source_facing: "right",
          runtime_mirror: true,
          columns: 4,
          rows: 1,
          asset: playerIdle,
        },
      },
      dialogue: {
        columns: 1,
        rows: 1,
        index_order: "row_major",
        expressions: ["neutral"],
        asset: playerDialogue,
      },
    },
    mobs: [],
    npcs: [],
    props: [],
    items: [],
    soundtrack: {
      playback: { selection: "shuffle", no_immediate_repeat: true },
      tracks: [],
    },
    gameplay: {},
    sequences: [],
    closure: {
      artifact_count: artifacts.length,
      artifacts_sha256: "c".repeat(64),
      artifacts,
    },
  };
}
