// Stage plan for the scrolling preview.
//
// A run's asset directory paints one world; this splits that world into an
// ordered set of stages the exit portal actually travels between. Everything
// here is pure so the plan can be asserted without a browser: the scene reads
// a plan and rebuilds its heightmap, platform graph, and spawn density from
// it, and the portal reads it to know where each of its two ends leads.
//
// The plan is a *book* built per run rather than a module constant, because a
// run's own artifacts decide which stages it may offer. A run generated
// without the village opt-in has no `npc_<tag>_<i>_idle.png` and no `village`
// manifest block, so handing it a village stage would drop the player into an
// empty town with no residents, no fixtures, and no way to tell that the town
// was never generated in the first place. Building the book takes that
// decision at the one place that knows the answer - the scene, once it has
// read the manifest - instead of asking a module-level constant to be correct
// for every run at once.

import {
  assertScrollingDemoLevelProfileSupported,
  parseLevelProfile,
  type LevelProfile,
} from "./level-profile";

/**
 * What a stage is for.
 *
 * "village" is the hub the player returns to and talks in; "hunting" is a
 * world with mobs, climbables, and loot. The distinction is not cosmetic: the
 * scene skips mob spawning and the vertical feature transaction outright on a
 * village, so a stage that lies about its kind gets a town full of monsters.
 */
export type StageKind = "village" | "hunting";

/** Static gameplay layouts that authored map identities may select. */
export const STAGE_LAYOUT_KINDS = Object.freeze([
  "ascent",
  "gauntlet",
  "spires",
] as const);
export type StageLayoutKind = (typeof STAGE_LAYOUT_KINDS)[number];

export type AuthoredMapSpec = Readonly<{
  mapId: string;
  displayName: string;
  soundtrackTrackIds: readonly string[];
  levelProfile: LevelProfile;
}>;

export type AuthoredMapBook = Readonly<{
  gameId: string;
  revision: number;
  entryMapId: string;
  maps: readonly AuthoredMapSpec[];
}>;

export type StagePlan = Readonly<{
  /** Zero-based position in the run's stage order. */
  index: number;
  /** Stable lowercase id, safe for probes, logs, and event payloads. */
  id: string;
  /** Short human label shown on the stage banner. */
  name: string;
  /** Platform-graph shape this stage lays into its terrain. */
  layout: StageLayoutKind;
  /** Mixed into the run's terrain seed so each stage gets its own heightmap. */
  seedSalt: number;
  /**
   * Every nth flat run that may host a mob. Lower is denser, so difficulty
   * rises across the plan without touching per-mob health or speed. Zero on a
   * stage that spawns no mobs at all: the village skips mob spawning entirely
   * rather than striding a loop that is required to find nothing.
   */
  mobRunStride: number;
  /** Whether this stage is the hub or a hunting ground. */
  kind: StageKind;
  /** Village terrain is flat so the town reads as a town. */
  terrain: "rolling" | "flat";
  /** Village has no climbables or upper platforms. */
  vertical: boolean;
  /** Authored game-global track identities allowed on this map. */
  soundtrackTrackIds?: readonly string[];
  /** Canonical authored level semantics. */
  levelProfile?: LevelProfile;
}>;

/** A plan before it knows which book it sits in, and therefore its index. */
type StageBlueprint = Omit<StagePlan, "index">;

/**
 * The three hunting stages over one asset set.
 *
 * The first keeps the run's own terrain seed, so the first hunting ground
 * anyone sees is still the world the generator produced for this tag. Later
 * stages salt that seed and switch platform layout, which changes terrain,
 * platform graph, prop placement, and mob spacing together rather than only
 * reskinning them.
 */
const HUNTING_BLUEPRINTS: readonly StageBlueprint[] = Object.freeze(
  ([
    {
      id: "stage-1-approach",
      name: "The Approach",
      layout: "ascent",
      seedSalt: 0,
      mobRunStride: 2,
      kind: "hunting",
      terrain: "rolling",
      vertical: true,
    },
    {
      id: "stage-2-gauntlet",
      name: "The Gauntlet",
      layout: "gauntlet",
      seedSalt: 0x9e3779b9,
      mobRunStride: 2,
      kind: "hunting",
      terrain: "rolling",
      vertical: true,
    },
    {
      id: "stage-3-spires",
      name: "The Spires",
      layout: "spires",
      seedSalt: 0x85ebca6b,
      mobRunStride: 1,
      kind: "hunting",
      terrain: "rolling",
      vertical: true,
    },
  ] satisfies StageBlueprint[]).map((blueprint) => Object.freeze(blueprint)),
);

/**
 * The settlement, when the run generated one.
 *
 * `layout` is inert while `vertical` is false - the scene never runs the
 * platform-graph transaction on a village - but it stays a real
 * `StageLayoutKind` rather than a null or an empty string so every plan
 * in the book has the same shape and no caller has to special-case reading it.
 *
 * The salt is non-zero on purpose. Zero is the sentinel that hands a stage the
 * run's authored terrain (see `stageTerrainSeed`), and that terrain belongs to
 * the hunting ground the generator actually drew; the village is flat ground
 * this adapter invents, so it takes a salt of its own.
 */
const VILLAGE_BLUEPRINT: StageBlueprint = Object.freeze({
  id: "village-hub",
  name: "Village",
  layout: "ascent",
  seedSalt: 0x27d4eb2f,
  mobRunStride: 0,
  kind: "village",
  terrain: "flat",
  vertical: false,
} satisfies StageBlueprint);

const BLUEPRINT_BY_ID: ReadonlyMap<string, StageBlueprint> = new Map(
  [VILLAGE_BLUEPRINT, ...HUNTING_BLUEPRINTS].map((blueprint) => [
    blueprint.id,
    blueprint,
  ]),
);

const MAP_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const GAME_ID = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/;
const TRACK_ID = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAP_BOOK_KEYS = [
  "schema_version",
  "kind",
  "game_id",
  "revision",
  "entry_map_id",
  "source",
  "soundtrack",
  "maps",
] as const;
const MAP_SOURCE_KEYS = [
  "path",
  "provenance_path",
  "source_sha256",
  "canonical_sha256",
] as const;
const SOUNDTRACK_BINDING_KEYS = ["source_sha256", "canonical_sha256"] as const;
const MAP_ENTRY_KEYS = [
  "map_id",
  "revision",
  "display_name",
  "soundtrack_track_ids",
  "source_ref",
  "source_sha256",
  "canonical_sha256",
  "level_profile",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    actual.every((key) => expected.includes(key))
  );
}

function isPortablePath(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.trim() !== value ||
    value.startsWith("/") ||
    value.includes("\\") ||
    value.includes(":") ||
    value.includes("?") ||
    value.includes("#") ||
    value.includes("%")
  ) {
    return false;
  }
  return value
    .split("/")
    .every(
      (segment) => segment.length > 0 && segment !== "." && segment !== "..",
    );
}

function declaredMapBookError(message: string): never {
  throw new Error(`invalid declared map_book: ${message}`);
}

/**
 * Parse the map book only when a manifest declares one.
 *
 * Absence leaves stage selection to the caller. A declared malformed block
 * throws instead of silently falling back to hardcoded stages, because that
 * would display a different ordered game than the producer published.
 */
export function parseMapBookManifest(value: unknown): AuthoredMapBook | null {
  if (!isRecord(value)) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }
  const declared = Object.prototype.hasOwnProperty.call(value, "map_book");
  if (value["schema_version"] !== 7) {
    if (declared) {
      return declaredMapBookError("parent manifest schema_version must be 7");
    }
    throw new Error("scrolling-preview manifest schema_version must be 7");
  }
  if (!declared) return null;
  const block = value["map_book"];
  if (!isRecord(block)) return declaredMapBookError("block must be an object");
  if (!hasExactKeys(block, MAP_BOOK_KEYS)) {
    return declaredMapBookError("block keys are invalid");
  }
  const gameId = block["game_id"];
  const revision = block["revision"];
  const entryMapId = block["entry_map_id"];
  if (
    block["schema_version"] !== 2 ||
    block["kind"] !== "game-map-book-manifest-v2" ||
    typeof gameId !== "string" ||
    gameId.length > 96 ||
    !GAME_ID.test(gameId) ||
    !Number.isSafeInteger(revision) ||
    (revision as number) < 1 ||
    typeof entryMapId !== "string" ||
    !MAP_ID.test(entryMapId)
  ) {
    return declaredMapBookError("identity is invalid");
  }

  const source = block["source"];
  const soundtrackBinding = block["soundtrack"];
  if (
    !isRecord(source) ||
    !hasExactKeys(source, MAP_SOURCE_KEYS) ||
    !isPortablePath(source["path"]) ||
    !isPortablePath(source["provenance_path"]) ||
    source["provenance_path"] !== `${source["path"]}.meta.json` ||
    typeof source["source_sha256"] !== "string" ||
    !SHA256.test(source["source_sha256"]) ||
    typeof source["canonical_sha256"] !== "string" ||
    !SHA256.test(source["canonical_sha256"]) ||
    !isRecord(soundtrackBinding) ||
    !hasExactKeys(soundtrackBinding, SOUNDTRACK_BINDING_KEYS) ||
    typeof soundtrackBinding["source_sha256"] !== "string" ||
    !SHA256.test(soundtrackBinding["source_sha256"]) ||
    typeof soundtrackBinding["canonical_sha256"] !== "string" ||
    !SHA256.test(soundtrackBinding["canonical_sha256"])
  ) {
    return declaredMapBookError("source binding is invalid");
  }

  const soundtrack = value["soundtrack"];
  if (
    !isRecord(soundtrack) ||
    soundtrack["schema_version"] !== 2 ||
    soundtrack["kind"] !== "game-soundtrack-manifest-v2" ||
    soundtrack["game_id"] !== gameId
  ) {
    return declaredMapBookError("requires the matching map-aware soundtrack projection");
  }
  const soundtrackSource = soundtrack["source"];
  if (
    !isRecord(soundtrackSource) ||
    soundtrackSource["source_sha256"] !== soundtrackBinding["source_sha256"] ||
    soundtrackSource["canonical_sha256"] !==
      soundtrackBinding["canonical_sha256"]
  ) {
    return declaredMapBookError("soundtrack digest binding does not match");
  }
  const rawTracks = soundtrack["tracks"];
  if (!Array.isArray(rawTracks) || rawTracks.length < 2 || rawTracks.length > 64) {
    return declaredMapBookError("soundtrack tracks are missing");
  }
  const availableTrackIds = new Set<string>();
  for (const rawTrack of rawTracks) {
    if (
      !isRecord(rawTrack) ||
      typeof rawTrack["track_id"] !== "string" ||
      rawTrack["track_id"].length > 64 ||
      availableTrackIds.has(rawTrack["track_id"]) ||
      !TRACK_ID.test(rawTrack["track_id"])
    ) {
      return declaredMapBookError("soundtrack track identity is invalid");
    }
    availableTrackIds.add(rawTrack["track_id"]);
  }

  const rawMaps = block["maps"];
  if (!Array.isArray(rawMaps) || rawMaps.length < 2 || rawMaps.length > 64) {
    return declaredMapBookError("maps must contain between 2 and 64 entries");
  }
  const maps: AuthoredMapSpec[] = [];
  const mapIds = new Set<string>();
  for (const [mapIndex, rawMap] of rawMaps.entries()) {
    if (!isRecord(rawMap)) return declaredMapBookError("map entry must be an object");
    if (!hasExactKeys(rawMap, MAP_ENTRY_KEYS)) {
      return declaredMapBookError("map entry keys are invalid");
    }
    const mapId = rawMap["map_id"];
    const displayName = rawMap["display_name"];
    const mapRevision = rawMap["revision"];
    const sourceRef = rawMap["source_ref"];
    const sourceSha256 = rawMap["source_sha256"];
    const canonicalSha256 = rawMap["canonical_sha256"];
    const rawTrackIds = rawMap["soundtrack_track_ids"];
    if (
      typeof mapId !== "string" ||
      mapId.length > 96 ||
      !MAP_ID.test(mapId) ||
      mapIds.has(mapId) ||
      typeof displayName !== "string" ||
      displayName.length === 0 ||
      displayName.length > 160 ||
      displayName.trim() !== displayName ||
      !Number.isSafeInteger(mapRevision) ||
      (mapRevision as number) < 1 ||
      !isPortablePath(sourceRef) ||
      typeof sourceSha256 !== "string" ||
      !SHA256.test(sourceSha256) ||
      typeof canonicalSha256 !== "string" ||
      !SHA256.test(canonicalSha256) ||
      !Array.isArray(rawTrackIds) ||
      rawTrackIds.length < 2 ||
      rawTrackIds.length > 64 ||
      sourceRef !== `library/games/${gameId}/maps/${mapId}.toml`
    ) {
      return declaredMapBookError("map entry is invalid");
    }
    let levelProfile: LevelProfile;
    try {
      levelProfile = parseLevelProfile(
        rawMap["level_profile"],
        `map_book.maps[${mapIndex}].level_profile`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "is invalid";
      return declaredMapBookError(message);
    }
    const trackIds: string[] = [];
    for (const trackId of rawTrackIds) {
      if (
        typeof trackId !== "string" ||
        trackId.length > 64 ||
        !TRACK_ID.test(trackId) ||
        trackIds.includes(trackId) ||
        !availableTrackIds.has(trackId)
      ) {
        return declaredMapBookError("map soundtrack_track_ids are invalid");
      }
      trackIds.push(trackId);
    }
    mapIds.add(mapId);
    maps.push(
      Object.freeze({
        mapId,
        displayName,
        soundtrackTrackIds: Object.freeze(trackIds),
        levelProfile,
      }),
    );
  }
  if (maps[0]?.mapId !== entryMapId) {
    return declaredMapBookError("entry_map_id must equal the first map_id");
  }
  return Object.freeze({
    gameId,
    revision: revision as number,
    entryMapId,
    maps: Object.freeze(maps),
  });
}

/**
 * The ordered stage book for one run.
 *
 * The village, when present, opens the book at index 0 and pushes every
 * hunting stage down by one. That placement is what makes it a hub rather than
 * a side room: the entry portal is sealed at index 0, and the exit wraps from
 * the last stage back to index 0, so a full circuit of the hunting grounds
 * returns the player to the town they set out from.
 */
export function buildStageBook(
  input: Readonly<{
    hasVillage: boolean;
    mapBook?: AuthoredMapBook | null;
  }>,
): readonly StagePlan[] {
  const blueprints: readonly StageBlueprint[] = input.mapBook
    ? input.mapBook.maps.map((gameMap) => {
        const blueprint = BLUEPRINT_BY_ID.get(gameMap.mapId);
        if (!blueprint) {
          throw new Error(`map book names unsupported map_id ${gameMap.mapId}`);
        }
        const profile = gameMap.levelProfile;
        assertScrollingDemoLevelProfileSupported(
          profile,
          `map ${gameMap.mapId} level_profile`,
        );
        const authoredKind: StageKind =
          profile.role === "social_hub" ? "village" : "hunting";
        const authoredVertical = profile.traversal.platform_model === "one_way";
        if (
          blueprint.kind !== authoredKind ||
          blueprint.vertical !== authoredVertical
        ) {
          throw new Error(
            `map ${gameMap.mapId} level_profile contradicts its scrolling-demo geometry`,
          );
        }
        return Object.freeze({
          ...blueprint,
          name: gameMap.displayName,
          kind: authoredKind,
          vertical: authoredVertical,
          mobRunStride:
            profile.mechanisms.encounter_model === "none"
              ? 0
              : blueprint.mobRunStride,
          soundtrackTrackIds: gameMap.soundtrackTrackIds,
          levelProfile: profile,
        });
      })
    : input.hasVillage
      ? [VILLAGE_BLUEPRINT, ...HUNTING_BLUEPRINTS]
      : HUNTING_BLUEPRINTS;
  const villageCount = blueprints.filter(
    (blueprint) => blueprint.kind === "village",
  ).length;
  if (input.mapBook && villageCount !== (input.hasVillage ? 1 : 0)) {
    throw new Error("map book village identity does not match generated village assets");
  }
  return Object.freeze(
    blueprints.map((blueprint, index) => Object.freeze({ ...blueprint, index })),
  );
}

/** Fail closed when a profiled stage book and its continuous-population policy diverge. */
export function assertContinuousPopulationCoverage(
  book: readonly StagePlan[],
  populationMapIds: readonly string[],
): void {
  const profiled = book.filter((stage) => stage.levelProfile !== undefined);
  if (profiled.length === 0) return;
  const required = new Set(
    profiled
      .filter(
        (stage) =>
          stage.levelProfile?.mechanisms.encounter_model === "continuous_population",
      )
      .map((stage) => stage.id),
  );
  const actual = new Set(populationMapIds);
  if (
    actual.size !== populationMapIds.length ||
    actual.size !== required.size ||
    [...required].some((mapId) => !actual.has(mapId))
  ) {
    const missing = [...required].filter((mapId) => !actual.has(mapId)).sort();
    const unexpected = [...actual].filter((mapId) => !required.has(mapId)).sort();
    throw new Error(
      "mob population must exactly cover level-profile continuous_population stages; " +
        `missing: ${missing.join(", ") || "none"}; ` +
        `unexpected: ${unexpected.join(", ") || "none"}`,
    );
  }
}

/**
 * The book a run without a village gets.
 *
 * Kept as a named export because a run with no village opt-in is the default
 * and several offline callers - the gameplay harness among them - describe a
 * fixed three-stage world that has no manifest to consult.
 */
export const STAGE_PLANS: readonly StagePlan[] = buildStageBook({
  hasVillage: false,
});

export function stagePlanAt(book: readonly StagePlan[], index: number): StagePlan {
  const plan = book[index];
  if (!plan) throw new Error(`stage index ${index} is outside the plan`);
  return plan;
}

/**
 * Clamp an arbitrary index onto a book.
 *
 * Restart payloads and query strings reach the scene as plain numbers, and a
 * stage that silently fell off the end would leave the run with no world at
 * all rather than an obvious first stage. An empty book has no in-range answer
 * to give, so it returns 0 and leaves `stagePlanAt` to raise the real fault
 * rather than inventing a negative index that would read the array backwards.
 */
export function normalizeStageIndex(
  book: readonly StagePlan[],
  value: unknown,
): number {
  if (book.length === 0) return 0;
  if (typeof value !== "number" || !Number.isSafeInteger(value)) return 0;
  if (value < 0) return 0;
  return value >= book.length ? book.length - 1 : value;
}

/** Deterministic per-stage terrain seed derived from the run's own seed. */
export function stageTerrainSeed(baseSeed: number, plan: StagePlan): number {
  if (!Number.isSafeInteger(baseSeed)) {
    throw new Error("stage terrain seed requires a safe integer base seed");
  }
  // Keep the run's authored terrain for the one stage the generator actually
  // drew it for instead of hashing it away, then mix for the rest so no later
  // stage can collide with it. That stage is the first *hunting* stage, which
  // is the world the world-spec describes - not whichever stage happens to
  // open the book. With a village in front of it the authored terrain still
  // belongs to the hunting ground, and the village's own non-zero salt is what
  // keeps the two from swapping.
  if (plan.seedSalt === 0) return baseSeed;
  const mixed = Math.imul(baseSeed ^ plan.seedSalt, 0x01000193) >>> 0;
  return mixed === 0 ? plan.seedSalt >>> 0 : mixed;
}

export type PortalEnd = "entry" | "exit";

/**
 * Where a portal end leads, or null when that end is sealed.
 *
 * The exit wraps from the last stage back to the first, so the forward portal
 * is never a locked door; the entry is the way back and has nowhere to go from
 * the opening stage, which is the one end that is genuinely sealed.
 */
export function portalDestination(
  book: readonly StagePlan[],
  index: number,
  end: PortalEnd,
): StagePlan | null {
  const current = normalizeStageIndex(book, index);
  if (end === "entry") {
    return current === 0 ? null : stagePlanAt(book, current - 1);
  }
  return stagePlanAt(book, (current + 1) % book.length);
}
