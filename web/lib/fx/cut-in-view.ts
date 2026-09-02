// The Phaser adapter for a cut-in: apply one choreography frame to screen objects.
//
// Every object here sits in screen space at scroll factor 0 and is positioned
// from the frame's numbers each tick; no tween, no timer. The interior — the
// backdrop, the drifting stripes, the portrait — is composed into one dynamic
// texture the size of the rip group, then everything outside the frame
// plate's silhouette is erased from it with the plate's inverse alpha (Phaser
// 4 has no geometry masks in WebGL, and its mask filter is not the same
// contract across renderers). The plate is then drawn once more on top in
// multiply so its ink rim stays over the face. The published mask polygon is
// the same silhouette as geometry, for a consumer with no texture to erase
// with; here the plate itself is the mask, exactly.

import Phaser from "phaser";
import type { FxCutInFrame, FxCutInPortrait } from "@/lib/manifest/fx";
import type { CutInFrame } from "./cut-in";
import type { FxView } from "./moment-system";

export interface CutInViewOptions {
  readonly viewWidth: number;
  readonly viewHeight: number;
  /** The depth the overlay starts at; it uses this and the next few rungs. */
  readonly depth: number;
  readonly frame: FxCutInFrame;
  readonly portrait: FxCutInPortrait;
  readonly frameTextureKey: string;
  readonly portraitTextureKey: string;
  readonly title: string;
  readonly subtitle: string;
}

/** Portrait height as a fraction of the rip group's height, settled. */
export const CUT_IN_PORTRAIT_HEIGHT_FRACTION = 0.82;
/** Portrait vertical offset from the group centre, in group heights. */
export const CUT_IN_PORTRAIT_DY_FRACTION = 0.01;
/** Shadow offset under the rip, in group heights. */
export const CUT_IN_SHADOW_OFFSET_FRACTION = 0.021;
/** Stripe period, in group heights, and the stripe's slant. */
export const CUT_IN_STRIPE_PERIOD_FRACTION = 0.112;
const STRIPE_SLANT = 0.55;
const STRIPE_WIDTH_FRACTION = 0.035;
const BACKDROP_COLOR = 0xff4a1c;
const STRIPE_COLOR = 0xff7846;
const SHADOW_COLOR = 0x0a080c;
const BANNER_WIDTH = 620;
const BANNER_HEIGHT = 128;

export interface CutInView extends FxView {
  destroy(): void;
}

export function buildCutInView(scene: Phaser.Scene, options: CutInViewOptions): CutInView {
  const { viewWidth, viewHeight, depth } = options;
  // Even dimensions: a dynamic texture rounds an odd side up, which would
  // leave the eraser stretched a pixel short of the silhouette it erases.
  const groupWidth = even(viewWidth);
  const groupHeight = even((viewWidth * options.frame.canvas.height) / options.frame.canvas.width);
  const centreY = viewHeight / 2;

  const scrim = scene.add
    .rectangle(viewWidth / 2, viewHeight / 2, viewWidth, viewHeight, 0x000000, 1)
    .setScrollFactor(0)
    .setDepth(depth)
    .setAlpha(0);
  const shadow = scene.add
    .image(0, 0, options.frameTextureKey)
    .setScrollFactor(0)
    .setDepth(depth + 1);
  // Fill tint: the plate's alpha as a flat dark silhouette under the rip.
  shadow.setTint(SHADOW_COLOR).setTintMode(Phaser.TintModes.FILL);
  const plate = scene.add
    .image(0, 0, options.frameTextureKey)
    .setScrollFactor(0)
    .setDepth(depth + 2);

  // The interior, composed off-screen at the group's own resolution. The
  // eraser is the plate's inverse alpha: white where the plate is transparent.
  const stageKey = `${options.frameTextureKey}:stage`;
  const eraserKey = `${options.frameTextureKey}:eraser`;
  for (const key of [stageKey, eraserKey]) {
    if (scene.textures.exists(key)) scene.textures.remove(key);
  }
  const created = scene.textures.addDynamicTexture(stageKey, groupWidth, groupHeight);
  if (!created) throw new Error("cut-in stage texture could not be created");
  const stageTexture = created;
  scene.textures.addCanvas(eraserKey, inverseAlphaCanvas(scene, options.frameTextureKey));
  const stripes = scene.make.graphics({}, false);
  const portrait = scene.make.image({}, false).setTexture(options.portraitTextureKey);
  const eraser = scene.make
    .image({}, false)
    .setTexture(eraserKey)
    .setPosition(groupWidth / 2, groupHeight / 2)
    .setDisplaySize(groupWidth, groupHeight);
  const stage = scene.add.image(0, 0, stageKey).setScrollFactor(0).setDepth(depth + 3);

  const ink = scene.add.image(0, 0, options.frameTextureKey).setScrollFactor(0).setDepth(depth + 6);
  ink.setBlendMode("MULTIPLY");

  const banner = scene.add.graphics().setScrollFactor(0).setDepth(depth + 7);
  const title = scene.add
    .text(0, 0, options.title.toUpperCase(), {
      fontFamily: "system-ui, sans-serif",
      fontSize: "40px",
      fontStyle: "bold",
      color: "#ffffff",
    })
    .setScrollFactor(0)
    .setDepth(depth + 8);
  const subtitle = scene.add
    .text(0, 0, options.subtitle.toUpperCase(), {
      fontFamily: "system-ui, sans-serif",
      fontSize: "28px",
      color: "#ffdcc8",
    })
    .setScrollFactor(0)
    .setDepth(depth + 8);
  const objects = [scrim, shadow, plate, stage, ink, banner, title, subtitle];

  const portraitAspect = options.portrait.canvas.width / options.portrait.canvas.height;

  function drawStripes(phase: number): void {
    const period = CUT_IN_STRIPE_PERIOD_FRACTION * groupHeight;
    const stripeWidth = STRIPE_WIDTH_FRACTION * groupHeight;
    const offset = ((phase % 1) + 1) % 1;
    stripes.clear();
    stripes.fillStyle(STRIPE_COLOR, 1);
    for (let x = -groupHeight - period; x < groupWidth + period; x += period) {
      const x0 = x + offset * period;
      stripes.beginPath();
      stripes.moveTo(x0, groupHeight);
      stripes.lineTo(x0 + groupHeight * STRIPE_SLANT, 0);
      stripes.lineTo(x0 + groupHeight * STRIPE_SLANT + stripeWidth, 0);
      stripes.lineTo(x0 + stripeWidth, groupHeight);
      stripes.closePath();
      stripes.fillPath();
    }
  }

  function composeStage(frameState: CutInFrame): void {
    drawStripes(frameState.stripePhase);
    const portraitHeight = CUT_IN_PORTRAIT_HEIGHT_FRACTION * groupHeight * frameState.bustScale;
    portrait
      .setPosition(
        groupWidth / 2 + frameState.bustDx * groupWidth,
        groupHeight / 2 + CUT_IN_PORTRAIT_DY_FRACTION * groupHeight,
      )
      .setDisplaySize(portraitHeight * portraitAspect, portraitHeight);
    stageTexture.clear();
    stageTexture.fill(BACKDROP_COLOR, 1);
    stageTexture.draw([stripes, portrait]);
    stageTexture.erase(eraser);
    // Phaser 4 only queues those four calls; nothing reaches the framebuffer
    // until the buffer is rendered, and an unrendered buffer just grows.
    stageTexture.render();
  }

  function drawBanner(x: number, y: number): void {
    banner.clear();
    banner.fillStyle(0x0e0c10, 1);
    banner.beginPath();
    banner.moveTo(x + 40, y);
    banner.lineTo(x + BANNER_WIDTH, y);
    banner.lineTo(x + BANNER_WIDTH - 40, y + BANNER_HEIGHT);
    banner.lineTo(x, y + BANNER_HEIGHT);
    banner.closePath();
    banner.fillPath();
    banner.lineStyle(3, 0xffffff, 1);
    banner.beginPath();
    banner.moveTo(x + 46, y + 8);
    banner.lineTo(x + BANNER_WIDTH - 8, y + 8);
    banner.lineTo(x + BANNER_WIDTH - 46, y + BANNER_HEIGHT - 8);
    banner.lineTo(x + 8, y + BANNER_HEIGHT - 8);
    banner.closePath();
    banner.strokePath();
    title.setPosition(x + 70, y + 16);
    subtitle.setPosition(x + 70, y + 70);
  }

  return {
    sync(frameState: CutInFrame): void {
      for (const object of objects) object.setVisible(true);
      const scale = frameState.ripScale;
      const cx = viewWidth / 2 + frameState.ripX * viewWidth;
      const cy = centreY;
      const width = groupWidth * scale;
      const height = groupHeight * scale;
      const shadowOffset = CUT_IN_SHADOW_OFFSET_FRACTION * height;

      scrim.setAlpha(frameState.dim);
      shadow.setPosition(cx + shadowOffset, cy + shadowOffset).setDisplaySize(width, height);
      plate.setPosition(cx, cy).setDisplaySize(width, height);
      composeStage(frameState);
      stage.setPosition(cx, cy).setDisplaySize(width, height);
      ink.setPosition(cx, cy).setDisplaySize(width, height);
      drawBanner(
        viewWidth - BANNER_WIDTH - 40 + frameState.bannerX * viewWidth,
        viewHeight - BANNER_HEIGHT - 36,
      );
    },
    hide(): void {
      for (const object of objects) object.setVisible(false);
    },
    destroy(): void {
      for (const object of objects) object.destroy();
      stripes.destroy();
      portrait.destroy();
      eraser.destroy();
      stageTexture.destroy();
      scene.textures.remove(eraserKey);
    },
  };
}

function even(value: number): number {
  const rounded = Math.round(value);
  return rounded % 2 === 0 ? rounded : rounded + 1;
}

/** White wherever the plate is transparent, transparent wherever it is painted. */
function inverseAlphaCanvas(scene: Phaser.Scene, frameTextureKey: string): HTMLCanvasElement {
  const source = scene.textures.get(frameTextureKey).getSourceImage() as
    | HTMLImageElement
    | HTMLCanvasElement;
  const canvas = document.createElement("canvas");
  canvas.width = source.width;
  canvas.height = source.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("cut-in eraser canvas has no 2d context");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.globalCompositeOperation = "destination-out";
  context.drawImage(source, 0, 0);
  return canvas;
}

/** The view a scene uses when the manifest plays no moment: nothing to draw. */
export const HIDDEN_FX_VIEW: FxView = Object.freeze({
  sync: () => undefined,
  hide: () => undefined,
});
