// What a set-piece changes about the run while it is on, and puts back after.
//
// Both genres had one and neither had a name for it. The runner writes
// `world.locomotion = "thrust"` when the fight begins and `"run"` when it ends,
// two lines eighty apart with nothing tying them together; the platformer
// authored `track_id` on its encounter and *never applied it at all*, which is
// the same bug at the far end of the same spectrum — a swap nobody wrote is
// indistinguishable from a swap nobody reverted.
//
// A swap is a pair with an id. The ledger's whole content is that applying is
// idempotent and reverting happens once, in reverse order, so a set-piece that
// ends by any route — defeated, exhausted, abandoned because the world was torn
// down — puts the run back the way it found it.

export interface DirectorSwap {
  /** Stable name for what is being swapped, so applying twice is once. */
  readonly id: string;
  apply(): void;
  revert(): void;
}

export class SwapLedger {
  private readonly applied: DirectorSwap[] = [];

  /** Apply a swap, or do nothing if this id is already in force. */
  apply(swap: DirectorSwap): boolean {
    if (this.applied.some((entry) => entry.id === swap.id)) return false;
    swap.apply();
    this.applied.push(swap);
    return true;
  }

  inForce(id: string): boolean {
    return this.applied.some((entry) => entry.id === id);
  }

  /**
   * Put everything back, most recent first, and forget it.
   *
   * Reverse order because swaps compose: a set-piece that narrows the music and
   * then narrows it again inside a phase has to widen in the order it narrowed.
   */
  revertAll(): void {
    for (let index = this.applied.length - 1; index >= 0; index -= 1) {
      this.applied[index].revert();
    }
    this.applied.length = 0;
  }

  /** Everything in force, in the order it was applied. */
  ids(): readonly string[] {
    return this.applied.map((entry) => entry.id);
  }
}
