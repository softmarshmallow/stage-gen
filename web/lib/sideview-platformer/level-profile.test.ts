import { describe, expect, test } from "bun:test";
import {
  assertScrollingDemoLevelProfileSupported,
  parseLevelProfile,
  scrollingDemoLevelCapabilities,
} from "./level-profile";

export const combatFieldProfile = () => ({
  schema_version: 1,
  kind: "level-profile-v1",
  role: "combat_field",
  view: {
    projection: "orthographic_2d",
    viewpoint: "side_on",
  },
  camera: {
    tracking_mode: "player_follow",
    framing_mode: "dead_zone",
    scroll_axes: ["horizontal", "vertical"],
  },
  traversal: {
    ground_model: "heightfield",
    platform_model: "one_way",
    affordances: [
      "ground_move",
      "jump",
      "air_jump",
      "drop_through",
      "climb",
    ],
  },
  mechanisms: {
    encounter_model: "continuous_population",
    combat_model: "real_time_action",
    loot_model: "defeat_drops",
    interaction_model: "none",
    transition_model: "bidirectional_portals",
  },
});

export const socialHubProfile = () => ({
  schema_version: 1,
  kind: "level-profile-v1",
  role: "social_hub",
  view: {
    projection: "orthographic_2d",
    viewpoint: "side_on",
  },
  camera: {
    tracking_mode: "player_follow",
    framing_mode: "dead_zone",
    scroll_axes: ["horizontal"],
  },
  traversal: {
    ground_model: "heightfield",
    platform_model: "none",
    affordances: ["ground_move", "jump"],
  },
  mechanisms: {
    encounter_model: "none",
    combat_model: "none",
    loot_model: "none",
    interaction_model: "proximity_dialogue",
    transition_model: "bidirectional_portals",
  },
});

describe("level-profile-v1", () => {
  test("strictly parses and deeply freezes both implemented semantic profiles", () => {
    for (const source of [socialHubProfile(), combatFieldProfile()]) {
      const parsed = parseLevelProfile(source);
      expect(parsed as unknown).toEqual(source);
      expect(Object.isFrozen(parsed)).toBeTrue();
      expect(Object.isFrozen(parsed.view)).toBeTrue();
      expect(Object.isFrozen(parsed.camera)).toBeTrue();
      expect(Object.isFrozen(parsed.camera.scroll_axes)).toBeTrue();
      expect(Object.isFrozen(parsed.traversal)).toBeTrue();
      expect(Object.isFrozen(parsed.traversal.affordances)).toBeTrue();
      expect(Object.isFrozen(parsed.mechanisms)).toBeTrue();
      expect(() => assertScrollingDemoLevelProfileSupported(parsed)).not.toThrow();
    }
  });

  test("rejects unknown, missing, and unsupported singleton fields", () => {
    expect(() =>
      parseLevelProfile({ ...combatFieldProfile(), camera_angle: "side_on" }),
    ).toThrow("level_profile.camera_angle is not a supported key");

    const missingView = combatFieldProfile();
    delete (missingView as { view?: unknown }).view;
    expect(() => parseLevelProfile(missingView)).toThrow("level_profile.view is required");

    const topDown = combatFieldProfile();
    topDown.view.viewpoint = "top_down";
    expect(() => parseLevelProfile(topDown)).toThrow(
      'level_profile.view.viewpoint must equal "side_on"',
    );
  });

  test("requires canonical unique axes and affordances", () => {
    const reversedAxes = combatFieldProfile();
    reversedAxes.camera.scroll_axes = ["vertical", "horizontal"];
    expect(() => parseLevelProfile(reversedAxes)).toThrow("must use canonical order");

    const duplicate = combatFieldProfile();
    duplicate.traversal.affordances = ["ground_move", "jump", "jump"];
    expect(() => parseLevelProfile(duplicate)).toThrow("must not contain duplicates");

    const unsupported = combatFieldProfile();
    unsupported.traversal.affordances = ["ground_move", "wall_run"];
    expect(() => parseLevelProfile(unsupported)).toThrow(
      "level_profile.traversal.affordances[1] must be one of",
    );
  });

  test("validates local dependency rules without inferring behavior from role", () => {
    const airWithoutJump = combatFieldProfile();
    airWithoutJump.traversal.affordances = ["ground_move", "air_jump"];
    expect(() => parseLevelProfile(airWithoutJump)).toThrow("air_jump requires jump");

    const platformlessLadder = socialHubProfile();
    platformlessLadder.traversal.affordances = ["ground_move", "jump", "climb"];
    expect(() => parseLevelProfile(platformlessLadder)).toThrow(
      "climb require platform_model one_way",
    );

    const lootWithoutCombat = socialHubProfile();
    lootWithoutCombat.mechanisms.loot_model = "defeat_drops";
    expect(() => parseLevelProfile(lootWithoutCombat)).toThrow(
      "defeat_drops requires real_time_action combat",
    );

    const quietHub = socialHubProfile();
    quietHub.mechanisms.interaction_model = "none";
    const parsed = parseLevelProfile(quietHub);
    expect(parsed.role).toBe("social_hub");
    expect(() => assertScrollingDemoLevelProfileSupported(parsed)).toThrow(
      "role social_hub has an unsupported mechanism combination",
    );
  });

  test("keeps schema acceptance separate from the current demo capability matrix", () => {
    const groundCombat = combatFieldProfile();
    groundCombat.traversal.platform_model = "none";
    groundCombat.traversal.affordances = ["ground_move", "jump"];
    const parsed = parseLevelProfile(groundCombat);

    expect(parsed.role).toBe("combat_field");
    expect(() => assertScrollingDemoLevelProfileSupported(parsed)).toThrow(
      "role combat_field has an unsupported mechanism combination",
    );
  });

  test("requires a profile and derives explicit player abilities", () => {
    expect(() => scrollingDemoLevelCapabilities(undefined)).toThrow(
      "level_profile is required",
    );
    expect(scrollingDemoLevelCapabilities(parseLevelProfile(socialHubProfile()))).toEqual({
      maximumAirJumps: 0,
      combatEnabled: false,
      horizontalDeadZoneEnabled: true,
      verticalCameraTrackingEnabled: false,
    });
    expect(scrollingDemoLevelCapabilities(parseLevelProfile(combatFieldProfile()))).toEqual({
      maximumAirJumps: 1,
      combatEnabled: true,
      horizontalDeadZoneEnabled: true,
      verticalCameraTrackingEnabled: true,
    });
  });
});
