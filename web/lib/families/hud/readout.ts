// The `hud` family: readouts as views over slices.
//
// The composition table's entry for this family is "nothing" in the slice
// column, and that is the whole ruling. A HUD owns no state: a health bar is a
// picture of `vitals`, a score line is a picture of `score`, a stat log is a
// picture of `progression`'s edges, and a defeat panel is a picture of
// `checkpoints`. Anything a readout has to *remember* is a slice somebody else
// owns, and the moment a readout starts remembering, two things disagree about
// what is true.
//
// So what the family owns is the shared drawing (`gauge-bar.ts`, the capsule
// every bounded resource on screen is read off) and the shape of a readout: a
// port that is handed the world and draws, and can be told to stop. The runner
// already had this shape and called it `HudView`; the platformer has four of
// them and named none.

/**
 * A readout over one world.
 *
 * `sync` is handed the world rather than a prepared view-model on purpose: a
 * readout that took a view-model would need something to *build* the model, and
 * that something is a second place where "what is true" is decided.
 */
export interface HudReadout<World> {
  sync(world: World): void;
  /**
   * Stop drawing.
   *
   * Optional because a readout with nothing to hide is an ordinary answer — a
   * bar a package cannot ever change is not drawn at all — and a required
   * method every second implementation stubs out is a port that has learnt
   * nothing.
   */
  hide?(): void;
}

/** A HUD with nothing drawing it: a headless boot, an order test, a replay harness. */
export function silentReadout<World>(): HudReadout<World> {
  return { sync: () => undefined, hide: () => undefined };
}
