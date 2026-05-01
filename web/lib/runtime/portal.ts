// Portal system (Phase 7).
//
// Splits the 2:1 portal sheet into entry (left half) and exit (right half),
// alpha-bbox-crops each, places them at world start / end, and emits a
// stage-advance event when the player overlaps the EXIT (TC-089).

import Phaser from "phaser";

export type PortalKind = "entry" | "exit";

export interface PortalSpec {
  kind: PortalKind;
  x: number; // world X (sprite centre)
  y: number; // world Y (feet on ground baseline)
  sprite: Phaser.GameObjects.Image;
  bboxHalf: { x: number; y: number; w: number; h: number };
}

export interface PortalSystemOpts {
  scene: Phaser.Scene;
  /** Texture key holding the chroma-keyed full 2:1 portal sheet. */
  portalKey: string;
  tilePx: number;
  baselineY: number;
  /** Heightmap accessor, used to bottom-anchor each portal. */
  heightFn: (col: number) => number;
  stageWidthPx: number;
}

const PORTAL_HEIGHT_TILES = 3.6;

export class PortalSystem {
  readonly portals: PortalSpec[] = [];
  private opts: PortalSystemOpts;
  private exitFired = false;

  constructor(opts: PortalSystemOpts) {
    this.opts = opts;
    this.build();
  }

  private build() {
    const scene = this.opts.scene;
    if (!scene.textures.exists(this.opts.portalKey)) return;

    const tex = scene.textures.get(this.opts.portalKey);
    const src = tex.getSourceImage(0) as HTMLImageElement | HTMLCanvasElement;
    const fullW = (src as { width: number }).width;
    const fullH = (src as { height: number }).height;
    const halfW = Math.floor(fullW / 2);

    // Register each half as a frame so we can crop with bbox.
    for (const kind of ["entry", "exit"] as PortalKind[]) {
      const startX = kind === "entry" ? 0 : halfW;
      const bbox = computeBbox(src, startX, 0, halfW, fullH);
      const frameName = `portal_${kind}`;
      // Use bbox to define a tighter sub-frame.
      tex.add(frameName, 0, bbox.x, bbox.y, bbox.w, bbox.h);

      const targetH = PORTAL_HEIGHT_TILES * this.opts.tilePx;
      const aspect = bbox.w / Math.max(1, bbox.h);

      // Place entry near world start, exit near world end.
      const col =
        kind === "entry"
          ? 3
          : Math.floor(this.opts.stageWidthPx / this.opts.tilePx) - 4;
      const colH = this.opts.heightFn(col);
      const surfaceY = this.opts.baselineY - colH * this.opts.tilePx;
      const x = col * this.opts.tilePx + this.opts.tilePx / 2;
      const y = surfaceY;

      const sprite = scene.add.image(x, y, this.opts.portalKey, frameName);
      sprite.setOrigin(0.5, 1.0);
      sprite.setDisplaySize(targetH * aspect, targetH);
      sprite.setDepth(750);

      this.portals.push({ kind, x, y, sprite, bboxHalf: bbox });
    }
  }

  /** Test whether `playerX` overlaps the exit portal's footprint. */
  checkExit(playerX: number, playerY: number): boolean {
    void playerY;
    const exit = this.portals.find((p) => p.kind === "exit");
    if (!exit || this.exitFired) return false;
    const w = (exit.sprite.displayWidth ?? 64) * 0.6;
    if (Math.abs(playerX - exit.x) < w) {
      this.exitFired = true;
      return true;
    }
    return false;
  }

  snapshot() {
    return this.portals.map((p) => ({
      kind: p.kind,
      x: p.x,
      y: p.y,
      w: p.sprite.displayWidth,
      h: p.sprite.displayHeight,
    }));
  }
}

// --- helpers ---

function computeBbox(
  src: HTMLImageElement | HTMLCanvasElement,
  x0: number,
  y0: number,
  w: number,
  h: number,
): { x: number; y: number; w: number; h: number } {
  // Build a temporary canvas covering only the half, read alpha, find bbox.
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { x: x0, y: y0, w, h };
  ctx.drawImage(src as CanvasImageSource, -x0, -y0);
  const id = ctx.getImageData(0, 0, w, h);
  const px = id.data;
  let minX = w,
    minY = h,
    maxX = -1,
    maxY = -1;
  for (let y = 0; y < h; y++) {
    const rowOffset = y * w * 4;
    for (let x = 0; x < w; x++) {
      const a = px[rowOffset + x * 4 + 3];
      if (a > 8) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0) return { x: x0, y: y0, w, h };
  return {
    x: x0 + minX,
    y: y0 + minY,
    w: maxX - minX + 1,
    h: maxY - minY + 1,
  };
}
