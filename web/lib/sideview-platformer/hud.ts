// The platformer's instantiation of the `hud` family.
//
// Four readouts — the floating gauge bar, the stat log, the combat text and the
// defeat panel — and what they have in common is exactly what the family says:
// none of them owns a slice. The bar is a picture of `vitals`, the log a
// picture of `progression`'s edges, the numbers a picture of what `combat` just
// resolved, the panel a picture of `checkpoints`.
//
// What is *not* done here, and it is a scope statement rather than an omission:
// none of the four takes the family's `HudReadout<World>` port, because this
// genre has no world to hand one. The scene still holds the state — that is the
// wrapper's own stated limit, "declared and not held, typed `?: never`; each
// becomes real storage on the step that extracts its class" — so a readout here
// is handed explicit arguments instead of a world. The runner, which does have
// a world, is where the port is instantiated today.

import { parseHudBlock, type HudBlockView } from "@/lib/families/hud";
import type { BlockTable } from "@/lib/manifest/blocks";
import { PREPARED_RUNTIME_BLOCKS } from "@/lib/manifest/prepared-manifest";

/**
 * The block the readouts depend on, and it is not `ui`.
 *
 * `ui.toml` is art direction — sheets, nine-slice geometry, icon grids — and
 * belongs to the `ui` family; the runner does not publish it at all. What a
 * readout needs from a package is whether it exists to be drawn:
 * `[gameplay] combat_text.enabled` decides that damage numbers appear over an
 * actor, and `[gameplay] progression.enabled` that the stat log has anything to
 * say.
 */
export const PLATFORMER_HUD_BLOCK = Object.freeze({
  block: "gameplay",
  version: PREPARED_RUNTIME_BLOCKS.gameplay,
});

/** Gate the platformer's hud block. Refuses by naming `gameplay`. */
export function parsePlatformerHudBlock(blocks: BlockTable): HudBlockView {
  return parseHudBlock(blocks, PLATFORMER_HUD_BLOCK);
}
