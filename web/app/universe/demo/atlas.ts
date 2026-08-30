// Shared between the atlas viewport and the placeholder shown while its
// browser-only implementation loads: the two must occupy the same box, or
// the workspace reflows the moment the map arrives.
export const mapSurface =
  "h-[min(72vh,850px)] min-h-[620px] w-full max-[720px]:h-full " +
  "max-[720px]:min-h-0";
