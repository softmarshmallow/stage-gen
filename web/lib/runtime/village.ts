// Village hub data adapter and resident placement.
//
// The village is a stage over the run's own art rather than a second world: it shares the
// tileset, the parallax layers, the portal pair, and the player. What makes it read as a town
// instead of another hunting ground is entirely data - a manifest block naming the settlement
// and its residents, and a placement plan that stands those residents on flat ground along the
// route the player already walks between the two portals.
//
// Everything here is pure, so the hub can be asserted without a browser: the scene turns a
// placement into a sprite and an interaction target into a "▲ Talk" prompt, but the decisions
// about *where* and *who* are made here and are testable on their own.
//
// Wire format: the manifest is a persisted public contract and uses `lower_snake_case`
// (`one_liner`, `role_label`, `fixtures_theme`). This module is the one boundary that
// translates it into the runtime's camelCase shape, exactly as `parseScaleReference` does for
// the scale references published beside each sheet. Nothing downstream of here should ever see
// a wire key again.

import { slopeAt } from "./heightmap";
import { verticalSpawnAllowed } from "./vertical";

const VILLAGE_KEYS = [
  "schema_version",
  "name",
  "one_liner",
  "fixtures_theme",
  "render",
  "npcs",
] as const;
const RENDER_KEYS = ["frames", "orientation", "animation", "state"] as const;
const NPC_KEYS = ["slot", "name", "role_label", "lines"] as const;
const VILLAGE_NPC_COUNT = 4;
const VILLAGE_LINE_COUNT = 3;
const STABLE_STATE = /^[a-z][a-z0-9_-]{0,63}$/;

/**
 * Columns kept clear at each end of the village.
 *
 * The portals stand at column 3 and at (last - 4), each roughly two tiles wide and 3.6 tiles
 * tall, and a player arriving through one steps out onto the portal's own column. A resident
 * standing there would be inside the portal mouth: overlapped by its art, and close enough that
 * the talk prompt competes with the stage-advance trigger for the same key press. Six columns
 * clears both portal bodies and the arrival step-out with a tile to spare.
 */
const VILLAGE_EDGE_MARGIN_COLUMNS = 6;

/**
 * How close the player must stand before a resident will talk, in world pixels.
 *
 * One and a half tiles. Short enough that the prompt names exactly one resident at the village's
 * default spacing - four residents across a 200-column stage land roughly 47 columns (3000px)
 * apart, so two can never both be in range - and long enough that the player can stop walking
 * anywhere in front of a resident and still be able to speak to them, rather than having to
 * land on a single pixel column.
 */
export const NPC_INTERACT_RANGE_PX = 96;

/**
 * How this run's residents were drawn, and therefore how they must be loaded.
 *
 * `orientation` is not decoration. A `side` resident is drawn facing one edge and the runtime
 * mirrors the sprite to turn it toward the player; a `front` resident already faces the player,
 * and mirroring one reverses whatever is asymmetric about it - the hand a tool is held in, the
 * side an apron ties on - for no gain.
 */
export type VillageRenderProfile = Readonly<{
  /** Cells the sheet is sliced into. 1 for a still, 4 for an idle strip. */
  frames: number;
  orientation: "side" | "front" | "three_quarter";
  animation: "strip" | "still";
  /** Suffix in `npc_<tag>_<slot>_<state>.png`. */
  state: string;
}>;

export type VillageNpcSpec = Readonly<{
  /** Position in the run's NPC order; also the suffix of `npc_<tag>_<slot>_<state>.png`. */
  slot: number;
  name: string;
  roleLabel: string;
  /** Greeting, remark, farewell - shown one per `advance()` in the dialogue box. */
  lines: readonly string[];
}>;

export type VillageSpec = Readonly<{
  name: string;
  oneLiner: string;
  fixturesTheme: string;
  render: VillageRenderProfile;
  npcs: readonly VillageNpcSpec[];
}>;

/**
 * Read the village out of a run's manifest.
 *
 * Returns null when a current run has no village block - a supported state, not a fault.
 *
 * Validation is all-or-nothing per block. A declared malformed village throws; it never becomes
 * an apparently valid run with a different stage book.
 */
export function parseVillageManifest(value: unknown): VillageSpec | null {
  const manifest = plainObject(value);
  if (!manifest) {
    throw new Error("scrolling-preview manifest must be a JSON object");
  }
  if (manifest["schema_version"] !== 7) {
    throw new Error("scrolling-preview manifest schema_version must be 7");
  }
  if (!("village" in manifest)) return null;
  const block = exactRecord(manifest["village"], VILLAGE_KEYS, "village");
  if (block["schema_version"] !== 2) {
    return declaredVillageError("schema_version must be 2");
  }
  const name = requiredString(block["name"], "name");
  const oneLiner = requiredString(block["one_liner"], "one_liner");
  const fixturesTheme = requiredString(block["fixtures_theme"], "fixtures_theme");
  const render = parseRenderProfile(block["render"]);
  const rawNpcs = block["npcs"];
  if (!Array.isArray(rawNpcs) || rawNpcs.length !== VILLAGE_NPC_COUNT) {
    return declaredVillageError("npcs must contain exactly four residents");
  }
  const npcs: VillageNpcSpec[] = [];
  for (const [index, raw] of rawNpcs.entries()) {
    const npc = parseNpc(raw, index);
    npcs.push(npc);
  }
  return Object.freeze({
    name,
    oneLiner,
    fixturesTheme,
    render,
    npcs: Object.freeze(npcs),
  });
}

function parseRenderProfile(value: unknown): VillageRenderProfile {
  const raw = exactRecord(value, RENDER_KEYS, "village.render");
  const frames = raw["frames"];
  const orientation = raw["orientation"];
  const animation = raw["animation"];
  const state = requiredString(raw["state"], "render.state");
  if (
    typeof frames !== "number" ||
    !Number.isInteger(frames) ||
    frames < 1 ||
    frames > 64
  ) {
    return declaredVillageError("render.frames is invalid");
  }
  if (
    orientation !== "side" &&
    orientation !== "front" &&
    orientation !== "three_quarter"
  ) {
    return declaredVillageError("render.orientation is invalid");
  }
  if (animation !== "strip" && animation !== "still") {
    return declaredVillageError("render.animation is invalid");
  }
  if (!STABLE_STATE.test(state)) {
    return declaredVillageError("render.state is invalid");
  }
  // A still has exactly one cell and a strip has more than one. The two fields are published
  // separately and could disagree; a sheet loaded under the wrong one of them is silently wrong
  // art, so a block that contradicts itself is refused rather than reconciled.
  if ((animation === "still") !== (frames === 1)) {
    return declaredVillageError("render animation and frames disagree");
  }
  return Object.freeze({ frames, orientation, animation, state });
}

export type NpcPlacement = Readonly<{
  slot: number;
  /** Terrain column the resident stands on. */
  column: number;
  /** World X of the resident's centre, at the column's midpoint. */
  x: number;
}>;

/**
 * Choose where each resident stands.
 *
 * Deterministic and pure: the same heightmap and the same reserved columns always produce the
 * same town, so a village looks the same on every visit and a probe can assert it without a
 * screenshot. The rules, in order:
 *
 *  - Only flat columns are candidates, using the same `slopeAt` definition of flat that obstacle
 *    and mob placement use. A resident standing on a slope column is bottom-anchored to a
 *    surface their neighbours do not share, and reads as sunk into the hill.
 *  - Reserved columns are skipped through `verticalSpawnAllowed`, the same gate mobs and
 *    obstacles pass, so a resident can never be spawned underneath a platform deck or across a
 *    ladder axis even on a village that did lay a platform graph.
 *  - The first and last `VILLAGE_EDGE_MARGIN_COLUMNS` are excluded so nobody stands in a portal.
 *  - The rest are spread evenly across the remaining span by candidate index, not by column, so
 *    a heightmap whose flat ground is bunched at one end still yields residents the player walks
 *    past one at a time rather than a crowd in the middle and an empty half.
 *
 * When two residents land on the same candidate - only possible on a map with fewer flat
 * candidates than residents - the later one walks forward to the next free candidate, then
 * backward, and is dropped if the town genuinely has nowhere left to put it. Returning fewer
 * placements is honest; stacking two residents on one column is not.
 */
export function planNpcPlacements(
  input: Readonly<{
    npcCount: number;
    heights: readonly number[];
    tilePx: number;
    reservedColumns: ReadonlySet<number>;
    worldWidthPx: number;
  }>,
): readonly NpcPlacement[] {
  const { npcCount, heights, tilePx, reservedColumns, worldWidthPx } = input;
  if (!Number.isSafeInteger(npcCount) || npcCount < 0) {
    throw new Error("npc count must be a non-negative safe integer");
  }
  if (!Number.isFinite(tilePx) || tilePx <= 0) {
    throw new Error("npc placement requires a positive tile size");
  }
  if (!Number.isFinite(worldWidthPx) || worldWidthPx <= 0) {
    throw new Error("npc placement requires a positive world width");
  }
  if (heights.length === 0) {
    throw new Error("npc placement requires at least one terrain column");
  }
  if (npcCount === 0) return Object.freeze([] as NpcPlacement[]);

  // `slopeAt` reads a mutable array; copy once per plan rather than casting away the caller's
  // readonly guarantee, which is the only thing stopping this from reshaping their heightmap.
  const columns = [...heights];
  const lastRenderedColumn =
    Math.min(columns.length, Math.floor(worldWidthPx / tilePx)) - 1;
  const candidates: number[] = [];
  for (
    let column = VILLAGE_EDGE_MARGIN_COLUMNS;
    column <= lastRenderedColumn - VILLAGE_EDGE_MARGIN_COLUMNS;
    column += 1
  ) {
    if (slopeAt(columns, column) !== "flat") continue;
    if (!verticalSpawnAllowed(reservedColumns, column)) continue;
    candidates.push(column);
  }
  if (candidates.length === 0) return Object.freeze([] as NpcPlacement[]);

  const placements: NpcPlacement[] = [];
  const takenIndices = new Set<number>();
  for (let slot = 0; slot < npcCount; slot += 1) {
    // Half-step offsets keep the row centred: residents sit inside the span rather than one
    // standing on its very first candidate column and the rest trailing off the far end.
    const ideal = Math.min(
      candidates.length - 1,
      Math.floor(((slot + 0.5) * candidates.length) / npcCount),
    );
    const index = firstFreeIndex(candidates.length, ideal, takenIndices);
    if (index === null) break;
    takenIndices.add(index);
    const column = candidates[index]!;
    placements.push(
      Object.freeze({
        slot,
        column,
        x: column * tilePx + tilePx / 2,
      }),
    );
  }
  return Object.freeze(placements);
}

/**
 * The slot of the nearest resident within talking range, or null when there is nobody to talk to.
 *
 * Pure, and called every frame, so it reports rather than throws: a non-finite player X during a
 * teardown frame means "no target this frame", not a crash that takes the update loop with it.
 *
 * Ties resolve to the earlier entry. A player standing exactly between two residents would
 * otherwise have the prompt flicker between them as floating-point noise moved the comparison,
 * and a prompt that cannot decide who it points at is worse than one that always picks the same
 * neighbour.
 */
export function npcInteractionTarget(
  playerX: number,
  npcs: readonly Readonly<{ slot: number; x: number }>[],
): number | null {
  if (!Number.isFinite(playerX)) return null;
  let nearestSlot: number | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const npc of npcs) {
    if (!Number.isFinite(npc.x)) continue;
    const distance = Math.abs(npc.x - playerX);
    if (distance > NPC_INTERACT_RANGE_PX) continue;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestSlot = npc.slot;
    }
  }
  return nearestSlot;
}

// ---------- internals ----------

function plainObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    actual.every((key) => expected.includes(key))
  );
}

function exactRecord(
  value: unknown,
  keys: readonly string[],
  label: string,
): Record<string, unknown> {
  const record = plainObject(value);
  if (!record || !hasExactKeys(record, keys)) {
    return declaredVillageError(`${label} keys are invalid`);
  }
  return record;
}

function requiredString(value: unknown, label: string): string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.trim() !== value
  ) {
    return declaredVillageError(`${label} must be a non-empty canonical string`);
  }
  return value;
}

function declaredVillageError(message: string): never {
  throw new Error(`invalid declared village: ${message}`);
}

function parseNpc(value: unknown, expectedSlot: number): VillageNpcSpec {
  const record = exactRecord(value, NPC_KEYS, `village.npcs[${expectedSlot}]`);
  const slot = record["slot"];
  if (slot !== expectedSlot) {
    return declaredVillageError("npc slots must be unique, contiguous, and ordered");
  }
  const name = requiredString(record["name"], `npcs[${expectedSlot}].name`);
  const roleLabel = requiredString(
    record["role_label"],
    `npcs[${expectedSlot}].role_label`,
  );
  const rawLines = record["lines"];
  if (!Array.isArray(rawLines) || rawLines.length !== VILLAGE_LINE_COUNT) {
    return declaredVillageError("each npc must contain exactly three lines");
  }
  const lines: string[] = [];
  for (const [lineIndex, rawLine] of rawLines.entries()) {
    const line = requiredString(
      rawLine,
      `npcs[${expectedSlot}].lines[${lineIndex}]`,
    );
    lines.push(line);
  }
  return Object.freeze({
    slot,
    name,
    roleLabel,
    lines: Object.freeze(lines),
  });
}

function firstFreeIndex(
  count: number,
  start: number,
  taken: ReadonlySet<number>,
): number | null {
  for (let index = start; index < count; index += 1) {
    if (!taken.has(index)) return index;
  }
  for (let index = start - 1; index >= 0; index -= 1) {
    if (!taken.has(index)) return index;
  }
  return null;
}
