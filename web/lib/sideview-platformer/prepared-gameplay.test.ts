import { describe, expect, test } from "bun:test";
import { parseScenarioProgram } from "@/lib/scenario/program";
import {
  assertPreparedGameplayManifestClosure,
  parsePreparedGameplayContract,
} from "./prepared-gameplay";
import type { PreparedRuntimeManifest } from "@/lib/manifest/prepared-manifest";

function gameplayFixture(): Record<string, unknown> {
  return {
    schema_version: 1,
    kind: "gameplay-contract-v1",
    game_id: "fixture-game",
    revision: 1,
    entry_map_id: "village-map",
    entry_spawn_id: "village_start",
    navigation: {
      allowed_movements: ["move_left", "move_right", "jump", "crouch", "climb"],
      logical_world_wrap: false,
      fall_recovery: "last_safe_ground",
    },
    player: {
      player_id: "hero",
      starting_level: 1,
      starting_health: 10,
      starting_item_ids: ["welcome_tart"],
    },
    progression: {
      enabled: true,
      maximum_level: 20,
      experience_curve: "gentle_rpg_v1",
      stat_growth: "balanced_novice_v1",
    },
    inventory: { currency_item_id: "gold_coin", starting_capacity: 24 },
    combat: {
      enabled: true,
      basic_action: "basic_attack",
      secondary_action: "skill_cast",
      contact_damage: true,
      critical_profile: "standard_v1",
      lethal_presentation: false,
      defeat_presentation: "story_beast_disperses_into_page_light",
    },
    combat_text: { enabled: true },
    map_uses: [
      {
        map_id: "village-map",
        role: "safe_village_hub",
        hostile_population_enabled: false,
        track_ids: ["village_theme"],
      },
      {
        map_id: "road-map",
        role: "scrolling_hunting_route",
        hostile_population_enabled: true,
        track_ids: ["road_theme", "boss_theme"],
      },
    ],
    spawns: [
      {
        spawn_id: "village_start",
        map_id: "village-map",
        anchor: "west_gate",
        normalized_x: 0.1,
      },
      {
        spawn_id: "road_start",
        map_id: "road-map",
        anchor: "west_gate",
        normalized_x: 0.1,
      },
    ],
    transitions: [
      {
        transition_id: "village_to_road",
        from_map_id: "village-map",
        from_anchor: "east_gate",
        to_map_id: "road-map",
        to_spawn_id: "road_start",
      },
    ],
    mob_population: {
      update_interval_ms: 250,
      max_spawn_batch_per_update: 2,
      maps: [
        {
          map_id: "road-map",
          seed_salt: 7,
          zones: [
            {
              zone_id: "road_zone",
              surface: "terrain",
              left_fraction: 0.1,
              right_fraction: 0.9,
              initial_population: 1,
              target_population: 2,
              population_cap: 3,
              respawn_delay_ms: 1000,
              spawn_table: [{ mob_id: "slime", weight: 1 }],
            },
          ],
        },
      ],
    },
    boss_encounters: [
      {
        encounter_id: "road_boss",
        map_id: "road-map",
        anchor: "east_gate",
        mob_id: "giant_slime",
        track_id: "boss_theme",
        respawn_policy: "quest_reset_only",
      },
    ],
    loot_rules: [
      {
        mob_id: "slime",
        item_id: "gold_coin",
        chance: 0.5,
        quantity_min: 1,
        quantity_max: 2,
      },
    ],
    npc_placements: [
      {
        map_id: "village-map",
        npc_id: "baker",
        anchor: "bakery",
        normalized_x: 0.3,
      },
    ],
    prop_placements: [
      {
        map_id: "village-map",
        prop_id: "village_well",
        anchor: "square",
        normalized_x: 0.5,
      },
    ],
    interactions: [
      {
        interaction_id: "meet_baker",
        map_id: "village-map",
        actor_id: "baker",
        scenario_id: "meet_baker",
        outcomes: [{ outcome_id: "greeted", effect_ids: [] }],
      },
    ],
    quests: [
      {
        quest_id: "first_quest",
        display_name: "The First Quest",
        start_effect_id: "start_first_quest",
        completion_item_id: "gold_coin",
        completion_count: 3,
        completion_effect_id: "complete_first_quest",
      },
    ],
    effects: [
      {
        effect_id: "start_first_quest",
        operation: "set_quest_state",
        quest_id: "first_quest",
        state: "active",
      },
      {
        effect_id: "complete_first_quest",
        operation: "set_quest_state",
        quest_id: "first_quest",
        state: "completed",
      },
      {
        effect_id: "grant_welcome_tart",
        operation: "grant_item",
        item_id: "welcome_tart",
        quantity: 1,
      },
    ],
  };
}

function manifestFixture(): Record<string, unknown> {
  return {
    game_id: "fixture-game",
    entry_map_id: "village-map",
    entry_spawn_id: "village_start",
    maps: [
      {
        map_id: "village-map",
        role: "safe_village_hub",
        camera: { mode: "player_follow", follow_axes: ["x"] },
        hostile_population_enabled: false,
        track_ids: ["village_theme"],
        portal: {
          endpoints: [
            { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
            { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
          ],
        },
      },
      {
        map_id: "road-map",
        role: "scrolling_hunting_route",
        camera: { mode: "player_follow", follow_axes: ["x", "y"] },
        hostile_population_enabled: true,
        track_ids: ["road_theme", "boss_theme"],
        portal: {
          endpoints: [
            { anchor: "west_gate", normalized_x: 0.1, role: "entry" },
            { anchor: "east_gate", normalized_x: 0.9, role: "exit" },
          ],
        },
      },
    ],
    player: { player_id: "hero" },
    mobs: [{ mob_id: "slime" }, { mob_id: "giant_slime" }],
    npcs: [{ npc_id: "baker" }],
    props: [{ prop_id: "village_well" }],
    items: [{ item_id: "welcome_tart" }, { item_id: "gold_coin" }],
    soundtrack: {
      tracks: [
        { track_id: "village_theme" },
        { track_id: "road_theme" },
        { track_id: "boss_theme" },
      ],
    },
    projectiles: [{ projectile_id: "paperwing_dart" }],
    scenarios: [
      parseScenarioProgram({
        schema_version: 1,
        kind: "scenario-program-v1",
        game_id: "village-game",
        scenario_id: "meet_baker",
        display_name: "Meet the Baker",
        revision: 1,
        script_sha256: "0".repeat(64),
        entry: "greeting",
        cast: [{ actor_id: "baker", expressions: ["neutral"] }],
        stages: [{ stage_id: "village", brief: "The village square" }],
        endings: [{ outcome_id: "greeted", label: "You said hello" }],
        blocks: [
          {
            label: "greeting",
            statements: [
              { kind: "stage", stage: "village" },
              { kind: "show", actor: "baker", expression: "neutral", slot: "center" },
              { kind: "line", speaker: "baker", text: "Fresh bread today." },
              { kind: "end", outcome: "greeted" },
            ],
          },
        ],
      }),
    ],
  };
}

function assertFixtureClosure(
  manifest = manifestFixture(),
  gameplay = gameplayFixture(),
): void {
  assertPreparedGameplayManifestClosure(
    manifest as unknown as PreparedRuntimeManifest,
    parsePreparedGameplayContract(gameplay),
  );
}

function records(value: unknown): Record<string, unknown>[] {
  return value as Record<string, unknown>[];
}

function child(value: Record<string, unknown>, key: string): Record<string, unknown> {
  return value[key] as Record<string, unknown>;
}

describe("gameplay-contract-v1 prepared runtime boundary", () => {
  test("parses the complete contract and deeply freezes runtime collections", () => {
    const parsed = parsePreparedGameplayContract(gameplayFixture());

    expect(parsed.kind).toBe("gameplay-contract-v1");
    expect(parsed.entry_spawn_id).toBe("village_start");
    expect(parsed.mob_population.maps[0]?.zones[0]?.target_population).toBe(2);
    expect(parsed.effects[2]?.operation).toBe("grant_item");
    expect(Object.isFrozen(parsed)).toBeTrue();
    expect(Object.isFrozen(parsed.navigation.allowed_movements)).toBeTrue();
    expect(Object.isFrozen(parsed.mob_population.maps[0]?.zones[0]?.spawn_table)).toBeTrue();
    expect(Object.isFrozen(parsed.effects)).toBeTrue();
  });

  test("rejects missing, unknown, and incorrectly typed fields", () => {
    const missing = gameplayFixture();
    delete (missing.combat as Record<string, unknown>).secondary_action;
    expect(() => parsePreparedGameplayContract(missing)).toThrow(
      "gameplay.combat.secondary_action is required",
    );

    const unknown = gameplayFixture();
    (unknown.inventory as Record<string, unknown>).panel_asset = "inventory.png";
    expect(() => parsePreparedGameplayContract(unknown)).toThrow(
      "gameplay.inventory.panel_asset is not a supported key",
    );

    const coerced = gameplayFixture();
    (coerced.player as Record<string, unknown>).starting_health = "10";
    expect(() => parsePreparedGameplayContract(coerced)).toThrow(
      "gameplay.player.starting_health must be a safe integer",
    );
  });

  test("rejects dangling map, spawn, quest, and effect identities", () => {
    const badMap = gameplayFixture();
    (badMap.npc_placements as Record<string, unknown>[])[0]!.map_id = "missing-map";
    expect(() => parsePreparedGameplayContract(badMap)).toThrow(
      "gameplay.npc_placements[0].map_id does not resolve",
    );

    const badSpawn = gameplayFixture();
    (badSpawn.transitions as Record<string, unknown>[])[0]!.to_spawn_id = "missing_spawn";
    expect(() => parsePreparedGameplayContract(badSpawn)).toThrow(
      "gameplay.transitions[0].to_spawn_id does not resolve",
    );

    const badQuest = gameplayFixture();
    (badQuest.effects as Record<string, unknown>[])[0]!.quest_id = "missing_quest";
    expect(() => parsePreparedGameplayContract(badQuest)).toThrow(
      "gameplay.effects[0].quest_id does not resolve",
    );

    const badEffect = gameplayFixture();
    (badEffect.quests as Record<string, unknown>[])[0]!.completion_effect_id = "missing_effect";
    expect(() => parsePreparedGameplayContract(badEffect)).toThrow(
      "gameplay.quests[0].completion_effect_id does not resolve",
    );
  });

  test("rejects contradictory roles and invalid population geometry", () => {
    const role = gameplayFixture();
    (role.map_uses as Record<string, unknown>[])[0]!.hostile_population_enabled = true;
    expect(() => parsePreparedGameplayContract(role)).toThrow(
      "role contradicts hostile_population_enabled",
    );

    const population = gameplayFixture();
    const populationMaps = (population.mob_population as Record<string, unknown>)
      .maps as Record<string, unknown>[];
    const zones = populationMaps[0]!.zones as Record<string, unknown>[];
    zones[0]!.target_population = 4;
    expect(() => parsePreparedGameplayContract(population)).toThrow(
      "population must satisfy initial <= target <= population_cap",
    );
  });

  test("accepts a gameplay graph whose manifest catalogs close exactly", () => {
    expect(() => assertFixtureClosure()).not.toThrow();
  });

  test("rejects mismatched game, entry, and player identities", () => {
    const game = manifestFixture();
    game.game_id = "other-game";
    expect(() => assertFixtureClosure(game)).toThrow(
      "gameplay.game_id does not match manifest.game_id",
    );

    const entryMap = manifestFixture();
    entryMap.entry_map_id = "road-map";
    expect(() => assertFixtureClosure(entryMap)).toThrow(
      "gameplay.entry_map_id does not match manifest.entry_map_id",
    );

    const entrySpawn = manifestFixture();
    entrySpawn.entry_spawn_id = "road_start";
    expect(() => assertFixtureClosure(entrySpawn)).toThrow(
      "gameplay.entry_spawn_id does not match manifest.entry_spawn_id",
    );

    const player = manifestFixture();
    child(player, "player").player_id = "other_hero";
    expect(() => assertFixtureClosure(player)).toThrow(
      "gameplay.player.player_id does not match manifest.player.player_id",
    );
  });

  test("rejects manifest map-set and duplicated map-projection drift", () => {
    const missingMap = manifestFixture();
    records(missingMap.maps).pop();
    expect(() => assertFixtureClosure(missingMap)).toThrow(
      "gameplay.map_uses must cover manifest.maps exactly",
    );

    const role = manifestFixture();
    records(role.maps)[0]!.role = "scrolling_hunting_route";
    expect(() => assertFixtureClosure(role)).toThrow(
      "gameplay.map_uses[0].role does not match the prepared manifest",
    );

    const hostile = manifestFixture();
    records(hostile.maps)[0]!.hostile_population_enabled = true;
    expect(() => assertFixtureClosure(hostile)).toThrow(
      "gameplay.map_uses[0].hostile_population_enabled does not match the prepared manifest",
    );

    const trackOrder = manifestFixture();
    records(trackOrder.maps)[1]!.track_ids = ["boss_theme", "road_theme"];
    expect(() => assertFixtureClosure(trackOrder)).toThrow(
      "gameplay.map_uses[1].track_ids does not match the prepared manifest",
    );
  });

  test("requires gameplay spawn and transition anchors to close over map portals", () => {
    const missingSpawnPortal = manifestFixture();
    const village = records(missingSpawnPortal.maps)[0]!;
    records(child(village, "portal").endpoints).shift();
    expect(() => assertFixtureClosure(missingSpawnPortal)).toThrow(
      "gameplay.spawns[0].anchor does not resolve to a map portal endpoint",
    );

    const divergentSpawn = manifestFixture();
    const road = records(divergentSpawn.maps)[1]!;
    records(child(road, "portal").endpoints)[0]!.normalized_x = 0.2;
    expect(() => assertFixtureClosure(divergentSpawn)).toThrow(
      "gameplay.spawns[1].normalized_x does not match its map portal endpoint",
    );

    const missingTransitionPortal = manifestFixture();
    const sourceMap = records(missingTransitionPortal.maps)[0]!;
    records(child(sourceMap, "portal").endpoints).pop();
    expect(() => assertFixtureClosure(missingTransitionPortal)).toThrow(
      "gameplay.transitions[0].from_anchor does not resolve to a map portal endpoint",
    );
  });

  test("rejects every unresolved external gameplay reference category", () => {
    const mob = gameplayFixture();
    const population = child(mob, "mob_population");
    const populationMap = records(population.maps)[0]!;
    const zone = records(populationMap.zones)[0]!;
    records(zone.spawn_table)[0]!.mob_id = "missing_mob";
    expect(() => assertFixtureClosure(manifestFixture(), mob)).toThrow(
      "gameplay.mob_population.maps[0].zones[0].spawn_table[0].mob_id does not resolve to manifest mobs",
    );

    const npc = gameplayFixture();
    records(npc.npc_placements)[0]!.npc_id = "missing_npc";
    expect(() => assertFixtureClosure(manifestFixture(), npc)).toThrow(
      "gameplay.npc_placements[0].npc_id does not resolve to manifest npcs",
    );

    const prop = gameplayFixture();
    records(prop.prop_placements)[0]!.prop_id = "missing_prop";
    expect(() => assertFixtureClosure(manifestFixture(), prop)).toThrow(
      "gameplay.prop_placements[0].prop_id does not resolve to manifest props",
    );

    const item = gameplayFixture();
    child(item, "player").starting_item_ids = ["missing_item"];
    expect(() => assertFixtureClosure(manifestFixture(), item)).toThrow(
      "gameplay.player.starting_item_ids[0] does not resolve to manifest items",
    );

    const track = gameplayFixture();
    records(track.boss_encounters)[0]!.track_id = "missing_track";
    expect(() => assertFixtureClosure(manifestFixture(), track)).toThrow(
      "gameplay.boss_encounters[0].track_id does not resolve to manifest soundtrack tracks",
    );

    const scenario = gameplayFixture();
    records(scenario.interactions)[0]!.scenario_id = "missing_scenario";
    expect(() => assertFixtureClosure(manifestFixture(), scenario)).toThrow(
      "gameplay.interactions[0].scenario_id does not resolve to manifest scenarios",
    );

    // An effect bound to an ending the story cannot reach is dead authoring.
    const outcome = gameplayFixture();
    (records(outcome.interactions)[0]!.outcomes as Record<string, unknown>[])[0]!.outcome_id =
      "never_reached";
    expect(() => assertFixtureClosure(manifestFixture(), outcome)).toThrow(
      "does not resolve to an ending of scenario meet_baker",
    );
  });

  test("rejects duplicate manifest catalog and scenario identities", () => {
    const cases: readonly (readonly [
      path: string,
      mutate: (manifest: Record<string, unknown>) => void,
    ])[] = [
      ["manifest.maps.map_id values must be unique", (manifest) => {
        records(manifest.maps).push({ ...records(manifest.maps)[0]! });
      }],
      ["manifest.mobs.mob_id values must be unique", (manifest) => {
        records(manifest.mobs).push({ mob_id: "slime" });
      }],
      ["manifest.npcs.npc_id values must be unique", (manifest) => {
        records(manifest.npcs).push({ npc_id: "baker" });
      }],
      ["manifest.props.prop_id values must be unique", (manifest) => {
        records(manifest.props).push({ prop_id: "village_well" });
      }],
      ["manifest.items.item_id values must be unique", (manifest) => {
        records(manifest.items).push({ item_id: "gold_coin" });
      }],
      ["manifest.soundtrack.tracks.track_id values must be unique", (manifest) => {
        records(child(manifest, "soundtrack").tracks).push({ track_id: "boss_theme" });
      }],
      ["manifest.scenarios.scenario_id values must be unique", (manifest) => {
        (manifest.scenarios as unknown[]).push((manifest.scenarios as unknown[])[0]!);
      }],
    ];

    for (const [message, mutate] of cases) {
      const manifest = manifestFixture();
      mutate(manifest);
      expect(() => assertFixtureClosure(manifest)).toThrow(message);
    }
  });
});

describe("a manifest published before a defaulted field existed", () => {
  test("the exact combat block a shipped run carries still parses", () => {
    // Copied from `out/bellweather-loop-v5/manifest.json`. Thirty-two of the thirty-four runs on
    // disk carry this block, and every one of them was unreadable while a missing key failed as
    // hard as an unknown one — a defect introduced by adding `critical_profile`, not by this
    // change, and repaired here because the same shape is about to be added twice more.
    const root = gameplayFixture();
    root.combat = {
      enabled: true,
      basic_action: "basic_attack",
      secondary_action: "skill_cast",
      contact_damage: true,
      lethal_presentation: false,
      defeat_presentation: "story_beast_disperses_into_page_light",
    };

    const gameplay = parsePreparedGameplayContract(root);

    expect(gameplay.combat.critical_profile).toBe("none");
    expect(gameplay.combat.weapon_class).toBe("melee_dps_v1");
    expect(gameplay.combat.projectile_id).toBeNull();
    expect(gameplay.combat.number_scale).toBe("unit_v1");
  });

  test("the number scale is read when named and refused outside its vocabulary", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), number_scale: "arcade_v1" };
    expect(parsePreparedGameplayContract(root).combat.number_scale).toBe("arcade_v1");

    root.combat = { ...(root.combat as object), number_scale: "huge_v1" };
    expect(() => parsePreparedGameplayContract(root)).toThrow("number_scale");
  });

  test("the sweep is a swinging class, so it names nothing to throw", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), weapon_class: "melee_sweep_v1" };
    expect(parsePreparedGameplayContract(root).combat.weapon_class).toBe("melee_sweep_v1");

    root.combat = {
      ...(root.combat as object),
      weapon_class: "melee_sweep_v1",
      projectile_id: "paperwing_dart",
    };
    expect(() => parsePreparedGameplayContract(root)).toThrow("projectile_id");
  });

  test("a key that is present is still validated exactly as strictly", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), critical_profile: "constant_v1" };

    expect(() => parsePreparedGameplayContract(root)).toThrow("critical_profile");
  });

  test("a required key with no default is still required", () => {
    const root = gameplayFixture();
    const combat = { ...(root.combat as Record<string, unknown>) };
    delete combat.contact_damage;
    root.combat = combat;

    expect(() => parsePreparedGameplayContract(root)).toThrow("is required");
  });

  test("an unknown key is still refused, because it describes a rule this reader drops", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), stamina_profile: "brisk_v1" };

    expect(() => parsePreparedGameplayContract(root)).toThrow("is not a supported key");
  });
});

describe("the weapon class a package fights with", () => {
  test("both members of the taxonomy parse", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), weapon_class: "melee_dps_v1" };
    expect(parsePreparedGameplayContract(root).combat.weapon_class).toBe("melee_dps_v1");

    root.combat = {
      ...(root.combat as object),
      weapon_class: "ranged_dps_v1",
      projectile_id: "paperwing_dart",
    };
    const ranged = parsePreparedGameplayContract(root).combat;
    expect(ranged.weapon_class).toBe("ranged_dps_v1");
    expect(ranged.projectile_id).toBe("paperwing_dart");
  });

  test("a class outside the taxonomy is refused rather than defaulted", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), weapon_class: "hitscan_dps_v1" };

    expect(() => parsePreparedGameplayContract(root)).toThrow("weapon_class");
  });

  test("an explicit null projectile means the same as an absent one", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), projectile_id: null };

    expect(parsePreparedGameplayContract(root).combat.projectile_id).toBeNull();
  });

  test("a projectile id that is not a snake identifier is refused", () => {
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), projectile_id: "Throwing-Stone" };

    expect(() => parsePreparedGameplayContract(root)).toThrow("projectile_id");
  });
});

describe("the projectile must be in the catalog the manifest published", () => {
  test("a class naming a projectile the package did not draw is refused at load", () => {
    // The same closure question the currency already answers. Finding this out at the first throw
    // instead of at load would mean a package that looks fine until someone plays it.
    const root = gameplayFixture();
    root.combat = {
      ...(root.combat as object),
      weapon_class: "ranged_dps_v1",
      projectile_id: "missing_throwable",
    };

    expect(() => assertFixtureClosure(manifestFixture(), root)).toThrow(
      "gameplay.combat.projectile_id does not resolve to manifest projectiles",
    );
  });

  test("a class naming a projectile the package did draw resolves", () => {
    const root = gameplayFixture();
    root.combat = {
      ...(root.combat as object),
      weapon_class: "ranged_dps_v1",
      projectile_id: "paperwing_dart",
    };

    expect(() => assertFixtureClosure(manifestFixture(), root)).not.toThrow();
  });
});

describe("the reader mirrors the pairing Python enforces", () => {
  test("a throwing class with nothing to throw is refused at load", () => {
    // Unmirrored, such a manifest parses clean, installs no projectile pool, and then declines
    // every attack for the rest of the run with nothing logged.
    const root = gameplayFixture();
    root.combat = { ...(root.combat as object), weapon_class: "ranged_dps_v1" };

    expect(() => parsePreparedGameplayContract(root)).toThrow(
      "must be named by a throwing weapon_class and by no other",
    );
  });

  test("a swinging class naming a projectile is refused too", () => {
    const root = gameplayFixture();
    root.combat = {
      ...(root.combat as object),
      weapon_class: "melee_dps_v1",
      projectile_id: "throwing_stone",
    };

    expect(() => parsePreparedGameplayContract(root)).toThrow(
      "must be named by a throwing weapon_class and by no other",
    );
  });

  test("a manifest predating both fields still parses as an unarmed-projectile melee package", () => {
    const root = gameplayFixture();
    const combat = { ...(root.combat as Record<string, unknown>) };
    delete combat.weapon_class;
    delete combat.projectile_id;
    root.combat = combat;

    const gameplay = parsePreparedGameplayContract(root);
    expect(gameplay.combat.weapon_class).toBe("melee_dps_v1");
    expect(gameplay.combat.projectile_id).toBeNull();
  });
});
