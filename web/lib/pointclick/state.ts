/**
 * The room's whole gameplay as one pure reducer.
 *
 * This is deliberately the same state machine the Python solvability proof
 * searched — {flags, inventory, revealed, fired} with the same availability
 * rules — so a room the proof admits is a room this runtime can finish. No
 * timers, no physics, no hidden state: every transition is a click.
 */

import {
  carried,
  consume,
  EMPTY_BAG,
  grant,
  UNLIMITED,
  type CountedBag,
} from "@/lib/families/inventory";
import type { RoomManifest, Verb } from "./contract";

export interface RoomPlayState {
  readonly flags: readonly string[];
  /**
   * What the player carries, as the `inventory` family's counted bag.
   *
   * It was a sorted `readonly string[]` used as a set, which looked like a
   * second inventory model and is not one: the room's authored vocabulary
   * grants one (`grant_item`) and removes the stack (`remove_item`), so a
   * counted bag with every quantity 1 and no capacity reads back as exactly the
   * set this used to be. `selectedItem` stays below and does *not* move with
   * it — it is an interaction latch, cleared by every interaction whether an
   * item was involved or not, and no rule about what is carried reads it.
   */
  readonly inventory: CountedBag;
  readonly revealed: readonly string[];
  readonly fired: readonly number[];
  readonly selectedItem: string | null;
  readonly narration: string;
  readonly solved: boolean;
}

export const MISS_LINE = "Nothing happens.";
export const MISS_WITH_ITEM_LINE = "That doesn't work here.";

/**
 * Every flag this room can read or write, from its own interactions and its win.
 *
 * A room does not declare a flag list the way a scenario does, so the vocabulary
 * is recovered from the document: it is exactly the set of names the reducer can
 * ever compare against.
 */
export function roomFlagVocabulary(manifest: RoomManifest): ReadonlySet<string> {
  const flags = new Set<string>(manifest.win.requires);
  for (const interaction of manifest.interactions) {
    for (const flag of interaction.requires) flags.add(flag);
    for (const effect of interaction.effects) {
      if (effect.set_flag !== undefined) flags.add(effect.set_flag);
    }
  }
  return flags;
}

/**
 * The room as the player finds it, optionally with facts an earlier beat set.
 *
 * `carried` is the case's shared fact set. Only names this room actually uses
 * are seeded — a fact it never mentions cannot change what it does, and putting
 * it in the state would put a name in the machine the solvability proof never
 * searched. A room that begins already solved is a case-authoring error, not
 * something to paper over here: the win flag belongs to the room's own exit.
 */
export function initialState(
  manifest: RoomManifest,
  carried: readonly string[] = [],
): RoomPlayState {
  const vocabulary = roomFlagVocabulary(manifest);
  const flags = [...new Set(carried.filter((flag) => vocabulary.has(flag)))].sort();
  return {
    flags,
    inventory: EMPTY_BAG,
    revealed: [],
    fired: [],
    selectedItem: null,
    narration: manifest.displayName,
    solved: manifest.win.requires.every((flag) => flags.includes(flag)),
  };
}

export function hotspotVisible(
  manifest: RoomManifest,
  state: RoomPlayState,
  hotspotId: string,
): boolean {
  const hotspot = manifest.hotspots.find((spot) => spot.id === hotspotId);
  if (hotspot === undefined) {
    return false;
  }
  return !hotspot.hidden || state.revealed.includes(hotspotId);
}

function interactionAvailable(
  manifest: RoomManifest,
  state: RoomPlayState,
  index: number,
  verb: Verb,
  hotspotId: string,
  item: string | null,
): boolean {
  const interaction = manifest.interactions[index];
  if (interaction.on.verb !== verb || interaction.on.hotspot !== hotspotId) {
    return false;
  }
  if ((interaction.on.item ?? null) !== item) {
    return false;
  }
  if (interaction.effects.length > 0 && state.fired.includes(index)) {
    return false;
  }
  if (interaction.requires.some((flag) => !state.flags.includes(flag))) {
    return false;
  }
  if (item !== null && carried(state.inventory, item) < 1) {
    return false;
  }
  return hotspotVisible(manifest, state, hotspotId);
}

function applyInteraction(
  manifest: RoomManifest,
  state: RoomPlayState,
  index: number,
): RoomPlayState {
  const interaction = manifest.interactions[index];
  const flags = new Set(state.flags);
  let inventory = state.inventory;
  const revealed = new Set(state.revealed);
  for (const effect of interaction.effects) {
    if (effect.set_flag !== undefined) {
      flags.add(effect.set_flag);
    }
    if (effect.grant_item !== undefined) {
      // The unit grant, and the sentence that keeps this bag a set: a room's
      // item is carried or it is not, so a second `grant_item` for the same
      // name is the no-op `Set.add` always was rather than a second unit.
      if (carried(inventory, effect.grant_item) < 1) {
        inventory = grant(inventory, effect.grant_item, 1, UNLIMITED).bag;
      }
    }
    if (effect.remove_item !== undefined) {
      // `remove_item` takes the stack, however deep it is.
      inventory = consume(inventory, effect.remove_item, carried(inventory, effect.remove_item)).bag;
    }
    if (effect.reveal_hotspot !== undefined) {
      revealed.add(effect.reveal_hotspot);
    }
  }
  const fired =
    interaction.effects.length > 0 ? [...state.fired, index].sort((a, b) => a - b) : state.fired;
  const solved = manifest.win.requires.every((flag) => flags.has(flag));
  const narration =
    solved && !state.solved
      ? `${interaction.narration} ${manifest.win.narration}`
      : interaction.narration;
  return {
    flags: [...flags].sort(),
    inventory,
    revealed: [...revealed].sort(),
    fired,
    selectedItem: null,
    narration,
    solved,
  };
}

/** Perform one explicit verb on a hotspot; misses narrate rather than throw. */
export function interact(
  manifest: RoomManifest,
  state: RoomPlayState,
  verb: Verb,
  hotspotId: string,
  item: string | null = null,
): RoomPlayState {
  for (let index = 0; index < manifest.interactions.length; index += 1) {
    if (interactionAvailable(manifest, state, index, verb, hotspotId, item)) {
      return applyInteraction(manifest, state, index);
    }
  }
  return {
    ...state,
    selectedItem: null,
    narration: item === null ? MISS_LINE : MISS_WITH_ITEM_LINE,
  };
}

/**
 * Resolve one primary click the way a player expects: a held item tries
 * use-with-item; otherwise an available bare `use` wins, else `inspect`.
 */
export function clickHotspot(
  manifest: RoomManifest,
  state: RoomPlayState,
  hotspotId: string,
): RoomPlayState {
  if (state.selectedItem !== null) {
    return interact(manifest, state, "use", hotspotId, state.selectedItem);
  }
  const bareUse = manifest.interactions.some((interaction, index) =>
    interactionAvailable(manifest, state, index, "use", hotspotId, null),
  );
  return interact(manifest, state, bareUse ? "use" : "inspect", hotspotId);
}

export function inspectHotspot(
  manifest: RoomManifest,
  state: RoomPlayState,
  hotspotId: string,
): RoomPlayState {
  return interact(manifest, state, "inspect", hotspotId);
}

export function selectItem(state: RoomPlayState, itemId: string | null): RoomPlayState {
  if (itemId !== null && carried(state.inventory, itemId) < 1) {
    return state;
  }
  return { ...state, selectedItem: state.selectedItem === itemId ? null : itemId };
}
