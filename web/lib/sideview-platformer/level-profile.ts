// Engine-neutral authored level classification for the optional scrolling demo.
//
// The producer describes a level through orthogonal view, camera, traversal, and
// gameplay-mechanism dimensions. This module validates that portable contract and
// separately states which complete combinations the current web demo can run. A
// descriptive role never enables gameplay by implication, and accepting a schema
// value never claims that every consumer implements it.

export const LEVEL_ROLES = ["social_hub", "combat_field"] as const;
export type LevelRole = (typeof LEVEL_ROLES)[number];

export const LEVEL_SCROLL_AXES = ["horizontal", "vertical"] as const;
export type LevelScrollAxis = (typeof LEVEL_SCROLL_AXES)[number];

export const LEVEL_AFFORDANCES = [
  "ground_move",
  "jump",
  "air_jump",
  "drop_through",
  "climb",
] as const;
export type LevelAffordance = (typeof LEVEL_AFFORDANCES)[number];

export type LevelProfile = Readonly<{
  schema_version: 1;
  kind: "level-profile-v1";
  role: LevelRole;
  view: Readonly<{
    projection: "orthographic_2d";
    viewpoint: "side_on";
  }>;
  camera: Readonly<{
    tracking_mode: "player_follow";
    framing_mode: "dead_zone";
    scroll_axes: readonly LevelScrollAxis[];
  }>;
  traversal: Readonly<{
    ground_model: "heightfield";
    platform_model: "none" | "one_way";
    affordances: readonly LevelAffordance[];
  }>;
  mechanisms: Readonly<{
    encounter_model: "none" | "continuous_population";
    combat_model: "none" | "real_time_action";
    loot_model: "none" | "defeat_drops";
    interaction_model: "none" | "proximity_dialogue";
    transition_model: "bidirectional_portals";
  }>;
}>;

export type ScrollingDemoLevelCapabilities = Readonly<{
  maximumAirJumps: 0 | 1;
  combatEnabled: boolean;
  horizontalDeadZoneEnabled: boolean;
  verticalCameraTrackingEnabled: boolean;
}>;

const ROOT_KEYS = [
  "schema_version",
  "kind",
  "role",
  "view",
  "camera",
  "traversal",
  "mechanisms",
] as const;
const VIEW_KEYS = ["projection", "viewpoint"] as const;
const CAMERA_KEYS = ["tracking_mode", "framing_mode", "scroll_axes"] as const;
const TRAVERSAL_KEYS = ["ground_model", "platform_model", "affordances"] as const;
const MECHANISM_KEYS = [
  "encounter_model",
  "combat_model",
  "loot_model",
  "interaction_model",
  "transition_model",
] as const;

const SOCIAL_HUB_SCROLL_AXES = ["horizontal"] as const;
const COMBAT_FIELD_SCROLL_AXES = ["horizontal", "vertical"] as const;
const SOCIAL_HUB_AFFORDANCES = ["ground_move", "jump"] as const;
const COMBAT_FIELD_AFFORDANCES = LEVEL_AFFORDANCES;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fail(path: string, message: string): never {
  throw new Error(`${path} ${message}`);
}

function expectRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) return fail(path, "must be an object");
  return value;
}

function expectExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
  path: string,
): void {
  const expectedSet = new Set(expected);
  for (const key of Object.keys(value)) {
    if (!expectedSet.has(key)) fail(`${path}.${key}`, "is not a supported key");
  }
  for (const key of expected) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      fail(`${path}.${key}`, "is required");
    }
  }
}

function expectLiteral<const Value extends string | number>(
  value: unknown,
  expected: Value,
  path: string,
): Value {
  if (value !== expected) return fail(path, `must equal ${JSON.stringify(expected)}`);
  return expected;
}

function expectMember<const Values extends readonly string[]>(
  value: unknown,
  allowed: Values,
  path: string,
): Values[number] {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    return fail(path, `must be one of ${allowed.join(", ")}`);
  }
  return value as Values[number];
}

function expectCanonicalMembers<const Values extends readonly string[]>(
  value: unknown,
  allowed: Values,
  path: string,
): readonly Values[number][] {
  if (!Array.isArray(value) || value.length === 0) {
    return fail(path, "must be a non-empty array");
  }
  const members = value.map((item, index) =>
    expectMember(item, allowed, `${path}[${index}]`),
  );
  if (new Set(members).size !== members.length) {
    return fail(path, "must not contain duplicates");
  }
  const order = new Map(allowed.map((item, index) => [item, index]));
  for (let index = 1; index < members.length; index += 1) {
    if (order.get(members[index - 1]!)! >= order.get(members[index]!)!) {
      return fail(path, `must use canonical order ${allowed.join(", ")}`);
    }
  }
  return Object.freeze(members);
}

function sameMembers(
  actual: readonly string[],
  expected: readonly string[],
): boolean {
  return (
    actual.length === expected.length &&
    actual.every((value, index) => value === expected[index])
  );
}

/** Parse and deeply freeze one canonical level-profile-v1 projection. */
export function parseLevelProfile(
  value: unknown,
  path = "level_profile",
): LevelProfile {
  const root = expectRecord(value, path);
  expectExactKeys(root, ROOT_KEYS, path);

  const schemaVersion = expectLiteral(root["schema_version"], 1, `${path}.schema_version`);
  const kind = expectLiteral(root["kind"], "level-profile-v1", `${path}.kind`);
  const role = expectMember(root["role"], LEVEL_ROLES, `${path}.role`);

  const rawView = expectRecord(root["view"], `${path}.view`);
  expectExactKeys(rawView, VIEW_KEYS, `${path}.view`);
  const view = Object.freeze({
    projection: expectLiteral(
      rawView["projection"],
      "orthographic_2d",
      `${path}.view.projection`,
    ),
    viewpoint: expectLiteral(rawView["viewpoint"], "side_on", `${path}.view.viewpoint`),
  });

  const rawCamera = expectRecord(root["camera"], `${path}.camera`);
  expectExactKeys(rawCamera, CAMERA_KEYS, `${path}.camera`);
  const camera = Object.freeze({
    tracking_mode: expectLiteral(
      rawCamera["tracking_mode"],
      "player_follow",
      `${path}.camera.tracking_mode`,
    ),
    framing_mode: expectLiteral(
      rawCamera["framing_mode"],
      "dead_zone",
      `${path}.camera.framing_mode`,
    ),
    scroll_axes: expectCanonicalMembers(
      rawCamera["scroll_axes"],
      LEVEL_SCROLL_AXES,
      `${path}.camera.scroll_axes`,
    ),
  });

  const rawTraversal = expectRecord(root["traversal"], `${path}.traversal`);
  expectExactKeys(rawTraversal, TRAVERSAL_KEYS, `${path}.traversal`);
  const platformModel = expectMember(
    rawTraversal["platform_model"],
    ["none", "one_way"] as const,
    `${path}.traversal.platform_model`,
  );
  const affordances = expectCanonicalMembers(
    rawTraversal["affordances"],
    LEVEL_AFFORDANCES,
    `${path}.traversal.affordances`,
  );
  if (affordances.includes("air_jump") && !affordances.includes("jump")) {
    fail(`${path}.traversal.affordances`, "air_jump requires jump");
  }
  if (
    platformModel === "none" &&
    (affordances.includes("drop_through") || affordances.includes("climb"))
  ) {
    fail(
      `${path}.traversal.affordances`,
      "drop_through and climb require platform_model one_way",
    );
  }
  const traversal = Object.freeze({
    ground_model: expectLiteral(
      rawTraversal["ground_model"],
      "heightfield",
      `${path}.traversal.ground_model`,
    ),
    platform_model: platformModel,
    affordances,
  });

  const rawMechanisms = expectRecord(root["mechanisms"], `${path}.mechanisms`);
  expectExactKeys(rawMechanisms, MECHANISM_KEYS, `${path}.mechanisms`);
  const combatModel = expectMember(
    rawMechanisms["combat_model"],
    ["none", "real_time_action"] as const,
    `${path}.mechanisms.combat_model`,
  );
  const lootModel = expectMember(
    rawMechanisms["loot_model"],
    ["none", "defeat_drops"] as const,
    `${path}.mechanisms.loot_model`,
  );
  if (lootModel === "defeat_drops" && combatModel === "none") {
    fail(`${path}.mechanisms.loot_model`, "defeat_drops requires real_time_action combat");
  }
  const mechanisms = Object.freeze({
    encounter_model: expectMember(
      rawMechanisms["encounter_model"],
      ["none", "continuous_population"] as const,
      `${path}.mechanisms.encounter_model`,
    ),
    combat_model: combatModel,
    loot_model: lootModel,
    interaction_model: expectMember(
      rawMechanisms["interaction_model"],
      ["none", "proximity_dialogue"] as const,
      `${path}.mechanisms.interaction_model`,
    ),
    transition_model: expectLiteral(
      rawMechanisms["transition_model"],
      "bidirectional_portals",
      `${path}.mechanisms.transition_model`,
    ),
  });

  return Object.freeze({
    schema_version: schemaVersion,
    kind,
    role,
    view,
    camera,
    traversal,
    mechanisms,
  });
}

/**
 * Fail closed unless the authored profile matches a complete combination the
 * current scrolling demo implements. Geometry remains selected by the static
 * stage blueprint; this gate prevents that blueprint from contradicting the
 * producer's portable level declaration.
 */
export function assertScrollingDemoLevelProfileSupported(
  profile: LevelProfile,
  path = "level_profile",
): void {
  const common =
    profile.camera.tracking_mode === "player_follow" &&
    profile.camera.framing_mode === "dead_zone" &&
    profile.view.projection === "orthographic_2d" &&
    profile.view.viewpoint === "side_on" &&
    profile.traversal.ground_model === "heightfield" &&
    profile.mechanisms.transition_model === "bidirectional_portals";
  if (!common) fail(path, "is not supported by the scrolling demo");

  const supported =
    profile.role === "social_hub"
      ? profile.traversal.platform_model === "none" &&
        sameMembers(profile.camera.scroll_axes, SOCIAL_HUB_SCROLL_AXES) &&
        sameMembers(profile.traversal.affordances, SOCIAL_HUB_AFFORDANCES) &&
        profile.mechanisms.encounter_model === "none" &&
        profile.mechanisms.combat_model === "none" &&
        profile.mechanisms.loot_model === "none" &&
        profile.mechanisms.interaction_model === "proximity_dialogue"
      : profile.traversal.platform_model === "one_way" &&
        sameMembers(profile.camera.scroll_axes, COMBAT_FIELD_SCROLL_AXES) &&
        sameMembers(profile.traversal.affordances, COMBAT_FIELD_AFFORDANCES) &&
        profile.mechanisms.encounter_model === "continuous_population" &&
        profile.mechanisms.combat_model === "real_time_action" &&
        profile.mechanisms.loot_model === "defeat_drops" &&
        profile.mechanisms.interaction_model === "none";
  if (!supported) fail(path, `role ${profile.role} has an unsupported mechanism combination`);
}

/** Translate portable level semantics into the optional demo's player ability budget. */
export function scrollingDemoLevelCapabilities(
  profile: LevelProfile | undefined,
): ScrollingDemoLevelCapabilities {
  if (profile === undefined) {
    throw new Error("level_profile is required for scrolling-demo capabilities");
  }
  return Object.freeze({
    maximumAirJumps: profile.traversal.affordances.includes("air_jump") ? 1 : 0,
    combatEnabled: profile.mechanisms.combat_model === "real_time_action",
    horizontalDeadZoneEnabled: profile.camera.framing_mode === "dead_zone",
    verticalCameraTrackingEnabled: profile.camera.scroll_axes.includes("vertical"),
  });
}
