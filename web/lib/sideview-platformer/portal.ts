// Portal system (Phase 7).
//
// Splits the 2:1 portal sheet into entry (left half) and exit (right half),
// alpha-bbox-crops each, and places them at explicit map-owned anchors. The
// standalone runtime keeps its historical world-start/world-end defaults;
// prepared games always supply anchors and separate gameplay destinations.
// Both ends can be live, so the pair is the run's actual travel mechanism
// rather than one end-of-stage tripwire (TC-089).
//
// Standing in a portal is not using it. Travel needs a deliberate press, which
// is what lets a route run past a portal, double back through one, or fight
// beside one without the stage changing underneath the player.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import { terrainSurfaceY } from "./terrain";
import type { PortalEnd } from "./stages";

export type PortalKind = PortalEnd;

export interface PortalSpec {
  /** Stable map-local identity used by prepared-game transition wiring. */
  portalId: string;
  kind: PortalKind;
  x: number; // world X (sprite centre)
  y: number; // world Y (feet on ground baseline)
  sprite: Phaser.GameObjects.Image;
  bboxHalf: { x: number; y: number; w: number; h: number };
  /** Stage this end travels to, or null when the end is sealed. */
  destinationIndex: number | null;
  /**
   * Whether the end may fire. An end the player is standing in starts inert
   * and arms once they step clear, so arriving through a portal cannot bounce
   * them straight back out of it.
   */
  armed: boolean;
}

export interface PortalSystemOpts {
  scene: Phaser.Scene;
  /** Texture key holding the canonical-alpha full 2:1 portal sheet. */
  portalKey: string;
  tilePx: number;
  baselineY: number;
  /** Heightmap accessor, used to bottom-anchor each portal. */
  heightFn: (col: number) => number;
  stageWidthPx: number;
  /** Destination stage index per end; null seals that end. */
  destinations: Readonly<Record<PortalKind, number | null>>;
  /**
   * Explicit map-owned endpoints. Omission retains the mature standalone
   * runtime's historical west/east pair.
   */
  endpoints?: readonly PortalEndpointPlacement[];
}

export type PortalEndpointPlacement = Readonly<{
  portalId: string;
  kind: PortalKind;
  /** World-space centre X resolved from the map's authored anchor. */
  x: number;
  /** Texture containing one isolated endpoint or the historical 1x2 pair. */
  portalKey: string;
  sourceFrame: "full" | PortalKind;
  destinationIndex: number | null;
}>;

export type PortalActivation = Readonly<{
  portalId: string;
  kind: PortalKind;
  destinationIndex: number;
}>;

export type PortalTick = Readonly<{
  nowMs: number;
  playerX: number;
  playerFootY: number;
  /** A fresh press of the enter key this frame, not the key being held. */
  enterRequested: boolean;
  /** Whether the idle shimmer should run; automation owns presentation itself. */
  shimmer: boolean;
}>;

const PORTAL_HEIGHT_TILES = 3.6;
/** Slack around the portal body when testing whether a player is inside it. */
const PORTAL_CONTACT_TOLERANCE = 32;
/** Fraction of the sprite's width that counts as the mouth. */
const PORTAL_MOUTH_WIDTH_RATIO = 0.6;
const PORTAL_SHIMMER_PERIOD_MS = 2800;
const PORTAL_SHIMMER_ALPHA_CENTER = 0.985;
const PORTAL_SHIMMER_ALPHA_AMPLITUDE = 0.015;
/** Height above a portal's base that its prompt floats at. */
const PORTAL_PROMPT_RISE = 24;
const PORTAL_PROMPT_TEXT = "UP to enter";

export type PortalIdlePresentation = Readonly<{
  /** Fixed to avoid temporal texture resampling of the authored portal raster. */
  scale: 1;
  alpha: number;
}>;

/** Resolve the subtle active-state shimmer without changing raster scale. */
export function portalIdlePresentation(nowMs: number): PortalIdlePresentation {
  if (!Number.isFinite(nowMs) || nowMs < 0) {
    throw new Error("portal presentation time must be finite and nonnegative");
  }
  const phase = (nowMs % PORTAL_SHIMMER_PERIOD_MS) / PORTAL_SHIMMER_PERIOD_MS;
  const wave = Math.sin(phase * Math.PI * 2);
  return Object.freeze({
    scale: 1,
    alpha:
      PORTAL_SHIMMER_ALPHA_CENTER +
      wave * PORTAL_SHIMMER_ALPHA_AMPLITUDE,
  });
}

export class PortalSystem {
  readonly portals: PortalSpec[] = [];
  private opts: PortalSystemOpts;
  private firedPortalId: string | null = null;
  private prompt?: Phaser.GameObjects.Text;
  private presentationLocked = false;
  private readonly baseDisplaySizes = new Map<
    string,
    Readonly<{ width: number; height: number }>
  >();

  constructor(opts: PortalSystemOpts) {
    this.opts = opts;
    this.build();
  }

  private build() {
    const scene = this.opts.scene;
    const endpoints = this.opts.endpoints ?? this.defaultEndpoints();

    for (const endpoint of endpoints) {
      if (!scene.textures.exists(endpoint.portalKey)) continue;
      const tex = scene.textures.get(endpoint.portalKey);
      const src = tex.getSourceImage() as HTMLImageElement | HTMLCanvasElement;
      const fullW = (src as { width: number }).width;
      const fullH = (src as { height: number }).height;
      const halfW = Math.floor(fullW / 2);
      const isolated = endpoint.sourceFrame === "full";
      const startX =
        isolated || endpoint.sourceFrame === "entry" ? 0 : halfW;
      const sourceW = isolated ? fullW : halfW;
      const bbox = computeBbox(src, startX, 0, sourceW, fullH);
      const frameName = `portal_${endpoint.portalId}`;
      // Use bbox to define a tighter sub-frame.
      if (tex.has(frameName)) tex.remove(frameName);
      tex.add(frameName, 0, bbox.x, bbox.y, bbox.w, bbox.h);

      const targetH = PORTAL_HEIGHT_TILES * this.opts.tilePx;
      const aspect = bbox.w / Math.max(1, bbox.h);

      const { x, y } = portalEndpointSurfacePosition({
        x: endpoint.x,
        tilePx: this.opts.tilePx,
        baselineY: this.opts.baselineY,
        stageWidthPx: this.opts.stageWidthPx,
        heightFn: this.opts.heightFn,
      });

      const sprite = scene.add.image(x, y, endpoint.portalKey, frameName);
      sprite.setOrigin(0.5, 1.0);
      sprite.setDisplaySize(targetH * aspect, targetH);
      sprite.setDepth(SCENE_CONTENT_DEPTH.portal);

      this.baseDisplaySizes.set(endpoint.portalId, {
        width: targetH * aspect,
        height: targetH,
      });

      this.portals.push({
        portalId: endpoint.portalId,
        kind: endpoint.kind,
        x,
        y,
        sprite,
        bboxHalf: bbox,
        destinationIndex: endpoint.destinationIndex,
        armed: false,
      });
    }
  }

  private defaultEndpoints(): readonly PortalEndpointPlacement[] {
    const finalColumn =
      Math.floor(this.opts.stageWidthPx / this.opts.tilePx) - 4;
    return Object.freeze([
      Object.freeze({
        portalId: "entry",
        kind: "entry" as const,
        x: 3 * this.opts.tilePx + this.opts.tilePx / 2,
        portalKey: this.opts.portalKey,
        sourceFrame: "entry" as const,
        destinationIndex: this.opts.destinations.entry,
      }),
      Object.freeze({
        portalId: "exit",
        kind: "exit" as const,
        x: finalColumn * this.opts.tilePx + this.opts.tilePx / 2,
        portalKey: this.opts.portalKey,
        sourceFrame: "exit" as const,
        destinationIndex: this.opts.destinations.exit,
      }),
    ]);
  }

  portalAt(kind: PortalKind): PortalSpec | undefined {
    return this.portals.find((portal) => portal.kind === kind);
  }

  portalById(portalId: string): PortalSpec | undefined {
    return this.portals.find((portal) => portal.portalId === portalId);
  }

  /** Apply deterministic automation-only emphasis without changing source art. */
  applyAutomationPresentation(scale: number, alpha: number): void {
    this.presentationLocked = true;
    for (const portal of this.portals) {
      const base = this.baseDisplaySizes.get(portal.portalId);
      if (!base) continue;
      portal.sprite.setDisplaySize(base.width * scale, base.height * scale);
      portal.sprite.setAlpha(alpha);
    }
  }

  /**
   * One per-frame tick: arming, presentation, prompt, and the travel a press
   * asks for.
   *
   * Arming and the prompt advance whether or not the key was pressed, so a
   * player who walks in, waits, and then presses is treated the same as one
   * who presses on contact.
   */
  update(tick: PortalTick): PortalActivation | null {
    const usable = this.advanceContact(tick.playerX, tick.playerFootY);
    this.showPrompt(usable);
    if (tick.shimmer) this.shimmer(tick.nowMs);
    if (!usable || !tick.enterRequested || this.firedPortalId !== null) return null;
    this.firedPortalId = usable.portalId;
    return Object.freeze({
      portalId: usable.portalId,
      kind: usable.kind,
      destinationIndex: usable.destinationIndex,
    });
  }

  /**
   * Idle shimmer so an open portal reads as running rather than painted on.
   *
   * A sealed end is left exactly as its art was authored. Dimming it was worse
   * than saying nothing: the opening stage's entry portal is the first thing
   * on screen, and a washed-out arch there reads as a broken asset rather than
   * as a door with nothing behind it.
   *
   * Skipped once automation has taken presentation over, because that path
   * owns scale and alpha outright and the two would fight frame by frame.
   */
  private shimmer(nowMs: number): void {
    if (this.presentationLocked) return;
    const presentation = portalIdlePresentation(nowMs);
    for (const portal of this.portals) {
      const base = this.baseDisplaySizes.get(portal.portalId);
      if (!base || portal.destinationIndex === null) continue;
      portal.sprite.setDisplaySize(base.width, base.height);
      portal.sprite.setAlpha(presentation.alpha);
    }
  }

  /**
   * Advance arming and report the end a press would use right now.
   *
   * An end the player is standing in starts inert and arms once they step
   * clear, so arriving through a portal leaves them free to walk out rather
   * than holding a live door under their feet.
   */
  private advanceContact(
    playerX: number,
    playerFootY: number,
  ): Readonly<{
    portalId: string;
    kind: PortalKind;
    destinationIndex: number;
  }> | null {
    let usable: Readonly<{
      portalId: string;
      kind: PortalKind;
      destinationIndex: number;
    }> | null = null;
    for (const portal of this.portals) {
      if (!this.contains(portal, playerX, playerFootY)) {
        portal.armed = true;
        continue;
      }
      if (!portal.armed || portal.destinationIndex === null || usable) continue;
      usable = {
        portalId: portal.portalId,
        kind: portal.kind,
        destinationIndex: portal.destinationIndex,
      };
    }
    return usable;
  }

  /** Say which key opens the door, above the door it opens. */
  private showPrompt(
    usable: Readonly<{ portalId: string }> | null,
  ): void {
    const portal = usable ? this.portalById(usable.portalId) : undefined;
    if (!portal || this.firedPortalId !== null) {
      this.prompt?.setVisible(false);
      return;
    }
    if (!this.prompt) {
      this.prompt = this.opts.scene.add.text(0, 0, PORTAL_PROMPT_TEXT, {
        fontFamily: "monospace",
        fontSize: "18px",
        color: "#f4f4f4",
        backgroundColor: "#000000a0",
        padding: { x: 8, y: 4 },
      });
      this.prompt.setOrigin(0.5, 1);
      this.prompt.setDepth(SCENE_CONTENT_DEPTH.effect);
    }
    this.prompt.setPosition(
      portal.x,
      portal.y - portal.sprite.displayHeight - PORTAL_PROMPT_RISE,
    );
    this.prompt.setVisible(true);
  }

  /** True while the player's feet are inside `portal`'s mouth. */
  private contains(portal: PortalSpec, playerX: number, playerY: number): boolean {
    return portalMouthContainsFoot({
      portalX: portal.x,
      portalFootY: portal.y,
      width: portal.sprite.displayWidth || 64,
      height: portal.sprite.displayHeight || 64,
      playerX,
      playerFootY: playerY,
    });
  }

  snapshot() {
    return this.portals.map((p) => ({
      portalId: p.portalId,
      kind: p.kind,
      x: p.x,
      y: p.y,
      w: p.sprite.displayWidth,
      h: p.sprite.displayHeight,
    }));
  }

  destroy(): void {
    this.prompt?.destroy();
    this.prompt = undefined;
    for (const portal of this.portals) portal.sprite.destroy();
    this.portals.length = 0;
    this.baseDisplaySizes.clear();
  }
}

// --- helpers ---

/** Resolve one explicit map anchor onto the same terrain surface as actors. */
export function portalEndpointSurfacePosition(input: Readonly<{
  x: number;
  tilePx: number;
  baselineY: number;
  stageWidthPx: number;
  heightFn: (column: number) => number;
}>): Readonly<{ x: number; y: number }> {
  for (const value of [
    input.x,
    input.tilePx,
    input.baselineY,
    input.stageWidthPx,
  ]) {
    if (!Number.isFinite(value)) {
      throw new Error("portal endpoint placement values must be finite");
    }
  }
  if (
    input.tilePx <= 0 ||
    input.stageWidthPx <= 0 ||
    input.x < 0 ||
    input.x > input.stageWidthPx
  ) {
    throw new Error("portal endpoint placement is outside its world");
  }
  const column = Math.min(
    Math.floor(input.stageWidthPx / input.tilePx) - 1,
    Math.floor(input.x / input.tilePx),
  );
  const columnHeight = input.heightFn(column);
  if (!Number.isFinite(columnHeight)) {
    throw new Error("portal endpoint terrain height must be finite");
  }
  return Object.freeze({
    x: input.x,
    y: terrainSurfaceY(columnHeight, input.tilePx, input.baselineY),
  });
}

/**
 * Whether a player's feet are inside a portal's mouth.
 *
 * Both axes matter. Testing X alone meant any deck sharing the portal's column
 * counted as standing in it, so a player four tiles up on an upper platform
 * fell through to the next stage without ever touching the thing.
 */
export function portalMouthContainsFoot(input: Readonly<{
  portalX: number;
  /** Portal base, where its bottom edge meets the ground. */
  portalFootY: number;
  width: number;
  height: number;
  playerX: number;
  playerFootY: number;
}>): boolean {
  for (const value of [
    input.portalX,
    input.portalFootY,
    input.width,
    input.height,
    input.playerX,
    input.playerFootY,
  ]) {
    if (!Number.isFinite(value)) throw new Error("portal contact values must be finite");
  }
  if (input.width <= 0 || input.height <= 0) {
    throw new Error("portal contact footprint must be positive");
  }
  const halfWidth = input.width * PORTAL_MOUTH_WIDTH_RATIO * 0.5;
  if (Math.abs(input.playerX - input.portalX) > halfWidth) return false;
  return (
    input.playerFootY <= input.portalFootY + PORTAL_CONTACT_TOLERANCE &&
    input.playerFootY >= input.portalFootY - input.height - PORTAL_CONTACT_TOLERANCE
  );
}

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
