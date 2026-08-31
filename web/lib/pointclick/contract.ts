/**
 * The point-and-click room runtime contract: `pointclick-room-runtime-v2`.
 *
 * One strict, hand-written validating parser in the house style: unknown
 * kinds are refused with a re-generate hint, shapes are checked field by
 * field, and the parsed document is deep-frozen. The runtime renders a room
 * from this document alone.
 */

export const POINTCLICK_RUNTIME_KIND = "pointclick-room-runtime-v2";
export const POINTCLICK_RUNTIME_SCHEMA_VERSION = 1;

export const POINTCLICK_REFUSAL =
  "unsupported point-and-click room manifest; regenerate this room with a current stage-gen " +
  "(stage-gen pointclick-room generate)";

export type Verb = "inspect" | "use";

export interface RoomRegion {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

export interface RoomHotspot {
  readonly id: string;
  readonly label: string;
  readonly art: "sprite" | "scenery";
  readonly region: RoomRegion;
  readonly hidden: boolean;
  readonly sprite: string | null;
}

export interface RoomItem {
  readonly id: string;
  readonly label: string;
  readonly icon: string;
}

export interface RoomEffect {
  readonly set_flag?: string;
  readonly grant_item?: string;
  readonly remove_item?: string;
  readonly reveal_hotspot?: string;
}

export interface RoomTrigger {
  readonly verb: Verb;
  readonly hotspot: string;
  readonly item: string | null;
}

export interface RoomInteraction {
  readonly on: RoomTrigger;
  readonly requires: readonly string[];
  readonly effects: readonly RoomEffect[];
  readonly narration: string;
}

export interface RoomManifest {
  readonly roomId: string;
  readonly displayName: string;
  readonly revision: number;
  readonly roomSha256: string;
  /** The key art every image in this room was generated against. */
  readonly cover: string;
  readonly scene: { readonly width: number; readonly height: number; readonly backdrop: string };
  readonly hotspots: readonly RoomHotspot[];
  readonly items: readonly RoomItem[];
  readonly interactions: readonly RoomInteraction[];
  readonly win: { readonly requires: readonly string[]; readonly narration: string };
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new Error(`${label} must be an integer`);
  }
  return value;
}

function unit(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error(`${label} must be a number in [0, 1]`);
  }
  return value;
}

function array(value: unknown, label: string): readonly unknown[] {
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be an array`);
  }
  return value;
}

function ids(value: unknown, label: string): readonly string[] {
  return array(value, label).map((entry, index) => text(entry, `${label}[${index}]`));
}

function region(value: unknown, label: string): RoomRegion {
  const raw = record(value, label);
  return {
    x: unit(raw.x, `${label}.x`),
    y: unit(raw.y, `${label}.y`),
    w: unit(raw.w, `${label}.w`),
    h: unit(raw.h, `${label}.h`),
  };
}

function verb(value: unknown, label: string): Verb {
  if (value !== "inspect" && value !== "use") {
    throw new Error(`${label} must be "inspect" or "use"`);
  }
  return value;
}

export function parseRoomManifest(value: unknown): RoomManifest {
  const raw = record(value, "room manifest");
  if (
    raw.kind !== POINTCLICK_RUNTIME_KIND ||
    raw.schema_version !== POINTCLICK_RUNTIME_SCHEMA_VERSION
  ) {
    throw new Error(POINTCLICK_REFUSAL);
  }
  const scene = record(raw.scene, "scene");
  const hotspots = array(raw.hotspots, "hotspots").map((entry, index): RoomHotspot => {
    const spot = record(entry, `hotspots[${index}]`);
    const art = spot.art;
    if (art !== "sprite" && art !== "scenery") {
      throw new Error(`hotspots[${index}].art must be "sprite" or "scenery"`);
    }
    const sprite = spot.sprite === null ? null : text(spot.sprite, `hotspots[${index}].sprite`);
    if ((art === "sprite") !== (sprite !== null)) {
      throw new Error(`hotspots[${index}] sprite ref must match its art declaration`);
    }
    return {
      id: text(spot.id, `hotspots[${index}].id`),
      label: text(spot.label, `hotspots[${index}].label`),
      art,
      region: region(spot.region, `hotspots[${index}].region`),
      hidden: spot.hidden === true,
      sprite,
    };
  });
  const items = array(raw.items, "items").map((entry, index) => {
    const item = record(entry, `items[${index}]`);
    return {
      id: text(item.id, `items[${index}].id`),
      label: text(item.label, `items[${index}].label`),
      icon: text(item.icon, `items[${index}].icon`),
    };
  });
  const hotspotIds = new Set(hotspots.map((spot) => spot.id));
  const itemIds = new Set(items.map((item) => item.id));
  if (hotspotIds.size !== hotspots.length || itemIds.size !== items.length) {
    throw new Error("room manifest ids must be unique");
  }
  const interactions = array(raw.interactions, "interactions").map((entry, index) => {
    const interaction = record(entry, `interactions[${index}]`);
    const on = record(interaction.on, `interactions[${index}].on`);
    const hotspot = text(on.hotspot, `interactions[${index}].on.hotspot`);
    if (!hotspotIds.has(hotspot)) {
      throw new Error(`interactions[${index}] names unknown hotspot ${hotspot}`);
    }
    const item =
      on.item === null || on.item === undefined
        ? null
        : text(on.item, `interactions[${index}].on.item`);
    if (item !== null && !itemIds.has(item)) {
      throw new Error(`interactions[${index}] names unknown item ${item}`);
    }
    const effects = array(interaction.effects, `interactions[${index}].effects`).map(
      (effect, effectIndex) => {
        const raw = record(effect, `interactions[${index}].effects[${effectIndex}]`);
        const keys = Object.keys(raw);
        if (keys.length !== 1) {
          throw new Error(`interactions[${index}].effects[${effectIndex}] must declare one action`);
        }
        const [key] = keys;
        const target = text(raw[key], `interactions[${index}].effects[${effectIndex}].${key}`);
        switch (key) {
          case "set_flag":
            return { set_flag: target };
          case "grant_item":
          case "remove_item":
            if (!itemIds.has(target)) {
              throw new Error(`effect names unknown item ${target}`);
            }
            return key === "grant_item" ? { grant_item: target } : { remove_item: target };
          case "reveal_hotspot":
            if (!hotspotIds.has(target)) {
              throw new Error(`effect names unknown hotspot ${target}`);
            }
            return { reveal_hotspot: target };
          default:
            throw new Error(`unknown effect ${key}`);
        }
      },
    );
    return {
      on: { verb: verb(on.verb, `interactions[${index}].on.verb`), hotspot, item },
      requires: ids(interaction.requires, `interactions[${index}].requires`),
      effects,
      narration: text(interaction.narration, `interactions[${index}].narration`),
    };
  });
  const win = record(raw.win, "win");
  const manifest: RoomManifest = {
    roomId: text(raw.room_id, "room_id"),
    displayName: text(raw.display_name, "display_name"),
    revision: integer(raw.revision, "revision"),
    roomSha256: text(raw.room_sha256, "room_sha256"),
    cover: text(raw.cover, "cover"),
    scene: {
      width: integer(scene.width, "scene.width"),
      height: integer(scene.height, "scene.height"),
      backdrop: text(scene.backdrop, "scene.backdrop"),
    },
    hotspots,
    items,
    interactions,
    win: {
      requires: ids(win.requires, "win.requires"),
      narration: text(win.narration, "win.narration"),
    },
  };
  return Object.freeze(manifest);
}
