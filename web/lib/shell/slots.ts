// Expected-artifact slot enumeration for a per-tag run.
//
// The generation view shows one square slot per expected artifact. A slot
// either holds a file URL (asset present) or shows loading.gif (pending).
//
// Two views of "expected":
//   1) Pre-spec — before world_spec_<tag>.json exists, we don't know L (layer
//      count) or M (obstacle count). We seed a sensible default (L=5, M=3,
//      N=8) so the grid renders something immediately.
//   2) Post-spec — once the JSON is on disk, we re-compute with the real
//      counts and the layer ids the agent invented.

export interface SlotDef {
  /** Stable id used by the React keying + retry route. */
  id: string;
  /** Short label shown under the slot. */
  label: string;
  /** Section header the slot belongs to. */
  section: string;
  /**
   * Filenames to look for under out/<tag>/. The first match wins.
   * Order matters: post-processed names should appear *before* their
   * raw counterparts so the post version replaces the raw in place.
   */
  filenames: string[];
}

export interface WorldSpecLite {
  layers: { id: string; opaque: boolean; z_index: number }[];
  mobs: unknown[];
  obstacles: unknown[];
  items: unknown[];
}

const STATES = ["idle", "walk", "run", "jump", "crawl"] as const;

function layerSlots(tag: string, spec: WorldSpecLite | null): SlotDef[] {
  if (spec && spec.layers.length > 0) {
    // Sort by z_index so background-most appears first in the grid.
    const sorted = [...spec.layers].sort((a, b) => a.z_index - b.z_index);
    return sorted.map((l, i) => ({
      id: `layer-${l.id}`,
      label: l.opaque ? `sky (${l.id})` : `L${i} ${l.id}`,
      section: "layers",
      filenames: [`layer_${tag}_${l.id}.png`],
    }));
  }
  // Pre-spec default — 5 layers, the deepest is the opaque skybox. We don't
  // know the painter's invented ids yet so the slots will stay on
  // loading.gif until world-spec lands; at that point the post-spec slot
  // set replaces this one.
  return Array.from({ length: 5 }, (_, i) => ({
    id: `layer-pending-${i}`,
    label: i === 0 ? "sky" : `L${i}`,
    section: "layers",
    filenames: [],
  }));
}

function mobSlots(tag: string, n: number): SlotDef[] {
  const out: SlotDef[] = [];
  for (let i = 0; i < n; i++) {
    out.push({
      id: `mob-concept-${i}`,
      label: `mob ${i}`,
      section: "mobs",
      filenames: [`mob_concept_${tag}_${i}.png`],
    });
  }
  for (let i = 0; i < n; i++) {
    out.push({
      id: `mob-idle-${i}`,
      label: `idle ${i}`,
      section: "mob anims",
      filenames: [`mob_${tag}_${i}_idle.png`],
    });
  }
  for (let i = 0; i < n; i++) {
    out.push({
      id: `mob-hurt-${i}`,
      label: `hurt ${i}`,
      section: "mob anims",
      filenames: [`mob_${tag}_${i}_hurt.png`],
    });
  }
  return out;
}

function obstacleSlots(tag: string, m: number): SlotDef[] {
  return Array.from({ length: m }, (_, i) => ({
    id: `obstacles-${i}`,
    label: `obstacles ${i}`,
    section: "obstacles",
    filenames: [`obstacles_${tag}_${i}.png`],
  }));
}

function characterSlots(tag: string): SlotDef[] {
  // For each state, list the post-processed (sliced) filename FIRST so it
  // replaces the raw master sheet preview in place. The combined master
  // sheet is its own slot (so the user can see the big sheet appear).
  const states: SlotDef[] = STATES.map((s) => ({
    id: `char-${s}`,
    label: s,
    section: "character anims",
    filenames: [`character_${tag}-fromcombined_${s}.png`],
  }));
  return [
    {
      id: "char-concept",
      label: "turnaround",
      section: "character",
      filenames: [`character_concept_${tag}.png`],
    },
    {
      id: "char-combined",
      label: "master sheet",
      section: "character",
      filenames: [`character_${tag}_combined.png`],
    },
    {
      id: "char-attack",
      label: "attack",
      section: "character",
      filenames: [`character_${tag}_attack.png`],
    },
    ...states,
  ];
}

export function expectedSlots(
  tag: string,
  spec: WorldSpecLite | null,
): SlotDef[] {
  const N = spec ? spec.mobs.length : 8;
  const M = spec ? spec.obstacles.length : 3;
  return [
    {
      id: "concept",
      label: "world concept",
      section: "concept",
      filenames: [`concept_${tag}.png`],
    },
    {
      id: "tileset",
      label: "ground tileset",
      section: "world",
      filenames: [`tileset_${tag}.png`],
    },
    {
      id: "items",
      label: "items",
      section: "world",
      filenames: [`items_${tag}.png`],
    },
    {
      id: "inventory",
      label: "inventory",
      section: "world",
      filenames: [`inventory_${tag}.png`],
    },
    {
      id: "portal",
      label: "portal",
      section: "world",
      filenames: [`portal_${tag}.png`],
    },
    ...layerSlots(tag, spec),
    ...obstacleSlots(tag, M),
    ...characterSlots(tag),
    ...mobSlots(tag, N),
  ];
}

/** Group slots by section preserving insertion order. */
export function groupSlots(slots: SlotDef[]): { section: string; slots: SlotDef[] }[] {
  const order: string[] = [];
  const map = new Map<string, SlotDef[]>();
  for (const s of slots) {
    if (!map.has(s.section)) {
      order.push(s.section);
      map.set(s.section, []);
    }
    map.get(s.section)!.push(s);
  }
  return order.map((section) => ({ section, slots: map.get(section)! }));
}
