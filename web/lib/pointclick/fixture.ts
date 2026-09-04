import { uiAtlasFixtureBlock } from "@/lib/shell/prepared-runtime.fixture";

/** One deliberately small, solvable room manifest for the pure tests. */

export function roomManifestFixture(): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "pointclick-room-runtime-v3",
    room_id: "test_room",
    display_name: "Test Room",
    revision: 1,
    room_sha256: "a".repeat(64),
    cover: "references/cover.png",
    scene: { width: 1280, height: 720, backdrop: "assets/backdrop.png" },
    hotspots: [
      {
        id: "bench",
        label: "Bench",
        art: "scenery",
        region: { x: 0.1, y: 0.5, w: 0.3, h: 0.3 },
        hidden: false,
        sprite: null,
      },
      {
        id: "chest",
        label: "Chest",
        art: "sprite",
        region: { x: 0.6, y: 0.5, w: 0.2, h: 0.3 },
        hidden: false,
        sprite: "assets/hotspots/chest.png",
      },
      {
        id: "prize",
        label: "Prize",
        art: "sprite",
        region: { x: 0.65, y: 0.45, w: 0.1, h: 0.1 },
        hidden: true,
        sprite: "assets/hotspots/prize.png",
      },
    ],
    items: [{ id: "key", label: "Key", icon: "assets/items/key.png" }],
    interactions: [
      {
        on: { verb: "inspect", hotspot: "bench", item: null },
        requires: [],
        effects: [],
        narration: "A sturdy bench.",
      },
      {
        on: { verb: "use", hotspot: "bench", item: null },
        requires: [],
        effects: [{ grant_item: "key" }],
        narration: "You find a key under the bench.",
      },
      {
        on: { verb: "use", hotspot: "chest", item: "key" },
        requires: [],
        effects: [{ set_flag: "chest_open" }, { reveal_hotspot: "prize" }],
        narration: "The chest opens.",
      },
      {
        on: { verb: "use", hotspot: "prize", item: null },
        requires: ["chest_open"],
        effects: [{ set_flag: "prize_taken" }],
        narration: "You take the prize.",
      },
    ],
    win: { requires: ["prize_taken"], narration: "The room is finished." },
    ui: uiAtlasFixtureBlock(),
  };
}
