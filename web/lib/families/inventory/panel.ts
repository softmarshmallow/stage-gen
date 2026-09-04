// The port the bag mirrors itself onto: a panel that pictures what is carried.
//
// Deliberately one method. The two drawn bags in the repository disagree about
// almost everything — the platformer's is a fixed 4x2 grid keyed by catalog
// index, the room's is a left-packed strip keyed by carried order — and the one
// thing both can answer is "this slot now holds this many of this kind, or
// nothing". Anything richer would be the platformer's panel wearing a port's
// name.
export interface InventoryPanelView {
  /**
   * Show `count` of `kindIndex` at `slotIndex`, or empty the slot at zero.
   *
   * Idempotent by contract: the bag calls it with the count *after* the
   * operation rather than with a delta, so a view that missed an update cannot
   * drift, and a grant of three is one call rather than three.
   */
  setSlot(slotIndex: number, kindIndex: number, count: number): void;
}

/** A bag with nothing drawing it: the headless boot, and every test that is not about the panel. */
export const NO_INVENTORY_PANEL: InventoryPanelView = Object.freeze({
  setSlot: () => undefined,
});
