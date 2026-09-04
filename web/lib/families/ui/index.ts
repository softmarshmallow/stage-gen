// The `ui` family: widgets, their geometry, and the sheets they are cut from.
//
// This directory was `lib/ui-atlas/`, and the composition table's note about it
// was exact: "genre-free by construction and five of its six files import
// Phaser — it is a family with a view half that has not been named as one".
// Naming it is the whole of this move. Nothing about the loader, the nine-slice
// widget, the button, the icon, the contrast rule or the presentation fallback
// changed; they are a family's view half now instead of a directory beside two
// genres, and the family gates the block they are cut from.

export { textPlateLayout, type TextPlateKnobs, type TextPlateLayout } from "./text-plate";
export { parseUiBlock, type UiBlockBinding, type UiBlockView } from "./manifest";
