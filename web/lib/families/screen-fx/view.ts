// The silent view, in a file with no engine in it.
//
// It lived at the bottom of `cut-in-view.ts`, which imports Phaser, so every
// consumer that wanted *nothing drawn* had to import a renderer to say so: a
// headless boot, a replay harness and the runner's own order test all pull in
// Phaser to reach two functions that return undefined. A default has no
// business carrying the dependency of the thing it is a default for.
//
// The one thing this file may never do is import an engine. A `FxView` is two
// methods; a scene supplies a real one, and everybody else supplies this.

import type { FxView } from "./moment-system";

/** The view a host uses when the manifest plays no moment: nothing to draw. */
export const HIDDEN_FX_VIEW: FxView = Object.freeze({
  sync: () => undefined,
  hide: () => undefined,
});
