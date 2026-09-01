// Platformer-owned loaders on top of the shared side-view asset layer.
//
// What stays here is exactly what depends on this runtime's raster contract:
// the producer-verified repeat and foreground measurements from ./foreground.
// The generic fetch / canvas / trim / sheet primitives live in
// `@/lib/sideview/assets` and are imported by every consumer directly.

import type Phaser from "phaser";

import {
  fetchImage,
  registerCanvas,
  transparencyCanvas,
  type LoadedParallaxLayer,
} from "@/lib/sideview/assets";
import { copyImageToCanvas } from "@/lib/sideview/image-ops";
import type { PreviewTransparencyPolicy } from "@/lib/shell/transparency";
import {
  measureVerifiedForegroundRepeat,
  prepareForegroundRaster,
  type PreparedForegroundRaster,
} from "./foreground";

export type LoadedForegroundLayer = LoadedParallaxLayer &
  Readonly<{
    foreground: Pick<
      PreparedForegroundRaster,
      | "sourceWidth"
      | "sourceHeight"
      | "contentBounds"
      | "meaningfulContentBounds"
      | "contactStrip"
      | "contactSourceY"
      | "repeatPeriod"
      | "overlap"
    >;
  }>;

/** Prepare one vertically trimmed, premultiplied periodic foreground canvas. */
export async function loadForegroundLayer(
  url: string,
  key: string,
  overlapPx: number,
  textures: Phaser.Textures.TextureManager,
  policy: PreviewTransparencyPolicy,
): Promise<LoadedForegroundLayer> {
  const image = await fetchImage(url);
  const source = transparencyCanvas(image, policy);
  const sourceContext = source.getContext("2d", { willReadFrequently: true });
  if (!sourceContext) {
    throw new Error("foreground preparation requires a 2d source canvas");
  }
  const prepared = prepareForegroundRaster(
    {
      width: source.width,
      height: source.height,
      data: sourceContext.getImageData(0, 0, source.width, source.height).data,
    },
    overlapPx,
  );
  const canvas = document.createElement("canvas");
  canvas.width = prepared.width;
  canvas.height = prepared.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("foreground preparation requires a 2d target canvas");
  }
  const imageData = context.createImageData(prepared.width, prepared.height);
  imageData.data.set(prepared.data);
  context.putImageData(imageData, 0, 0);
  registerCanvas(textures, key, canvas);
  return {
    key,
    canvas,
    width: canvas.width,
    height: canvas.height,
    opaque: false,
    foreground: {
      sourceWidth: prepared.sourceWidth,
      sourceHeight: prepared.sourceHeight,
      contentBounds: prepared.contentBounds,
      meaningfulContentBounds: prepared.meaningfulContentBounds,
      contactStrip: prepared.contactStrip,
      contactSourceY: prepared.contactSourceY,
      repeatPeriod: prepared.repeatPeriod,
      overlap: prepared.overlap,
    },
  };
}

/** Load one producer-verified repeat period without edge treatment or pixel rewriting. */
export async function loadVerifiedRepeatLayer(
  url: string,
  key: string,
  opaque: boolean,
  periodPx: number,
  textures: Phaser.Textures.TextureManager,
): Promise<LoadedParallaxLayer> {
  const image = await fetchImage(url);
  const canvas = copyImageToCanvas(image);
  if (canvas.width !== periodPx) {
    throw new Error("verified repeat decoded width does not match period_px");
  }
  registerCanvas(textures, key, canvas);
  return {
    key,
    canvas,
    width: canvas.width,
    height: canvas.height,
    opaque,
  };
}

/** Load and measure a verified foreground while preserving the full repeat-unit canvas. */
export async function loadVerifiedForegroundRepeat(
  url: string,
  key: string,
  periodPx: number,
  textures: Phaser.Textures.TextureManager,
): Promise<LoadedForegroundLayer> {
  const image = await fetchImage(url);
  const canvas = copyImageToCanvas(image);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("verified foreground requires a 2d canvas");
  }
  const foreground = measureVerifiedForegroundRepeat(
    {
      width: canvas.width,
      height: canvas.height,
      data: context.getImageData(0, 0, canvas.width, canvas.height).data,
    },
    periodPx,
  );
  registerCanvas(textures, key, canvas);
  return {
    key,
    canvas,
    width: canvas.width,
    height: canvas.height,
    opaque: false,
    foreground,
  };
}
