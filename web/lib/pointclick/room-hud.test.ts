import { describe, expect, test } from "bun:test";
import { containRect } from "@/lib/shell/hud-geometry";
import {
  canvasSize,
  HUD_BAND_HEIGHT,
  HUD_MARGIN,
  hotspotRect,
  hudBarRect,
  INVENTORY_SLOT_GAP,
  INVENTORY_SLOT_SIZE,
  inventoryCapacity,
  inventorySlotRects,
  LONG_PRESS_MS,
  narrationRect,
  resolveVerb,
  verbButtonRects,
  winPanelRect,
} from "./room-hud";

const STAGE = { width: 1280, height: 720 };

describe("resolveVerb", () => {
  test("a plain tap acts and a held tap looks, in either mode", () => {
    expect(resolveVerb("act", { secondary: false, heldMs: 10 })).toBe("use");
    expect(resolveVerb("act", { secondary: false, heldMs: LONG_PRESS_MS })).toBe("inspect");
    expect(resolveVerb("look", { secondary: false, heldMs: 10 })).toBe("inspect");
    // Touch has no second button and no hover: the long press has to reach
    // inspect from the mode the player is already in, not only from "act".
    expect(resolveVerb("look", { secondary: false, heldMs: LONG_PRESS_MS })).toBe("inspect");
  });

  test("the secondary button always inspects", () => {
    expect(resolveVerb("act", { secondary: true, heldMs: 0 })).toBe("inspect");
    expect(resolveVerb("look", { secondary: true, heldMs: 9_000 })).toBe("inspect");
  });
});

describe("layout", () => {
  test("a normalized region becomes design pixels", () => {
    expect(hotspotRect(STAGE, { x: 0.5, y: 0.25, w: 0.25, h: 0.5 })).toEqual({
      x: 640,
      y: 180,
      width: 320,
      height: 360,
    });
  });

  test("a sprite is fitted inside its region, never stretched to it", () => {
    const region = { x: 100, y: 100, width: 200, height: 400 };
    const fitted = containRect(region, { width: 1024, height: 1024 });
    expect(fitted.width).toBe(200);
    expect(fitted.height).toBe(200);
    // Centred in the taller axis.
    expect(fitted.y).toBe(200);
    expect(fitted.x).toBe(100);
  });

  test("a zero-sized texture falls back to the region instead of dividing by zero", () => {
    const region = { x: 0, y: 0, width: 10, height: 10 };
    expect(containRect(region, { width: 0, height: 0 })).toEqual(region);
  });

  test("the HUD sits in its own band under the room, never over it", () => {
    const bar = hudBarRect(STAGE);
    const panel = narrationRect(STAGE);
    const canvas = canvasSize(STAGE);
    // Nothing in the HUD starts before the authored frame ends, so no hotspot
    // region — including one authored low in the frame — can sit under a panel.
    expect(panel.y).toBeGreaterThanOrEqual(STAGE.height);
    expect(panel.y + panel.height).toBeLessThan(bar.y);
    expect(bar.y + bar.height).toBe(canvas.height);
    expect(canvas.height).toBe(STAGE.height + HUD_BAND_HEIGHT);
    expect(canvas.width).toBe(STAGE.width);
    expect(panel.x).toBe(HUD_MARGIN);
    expect(panel.width).toBe(STAGE.width - HUD_MARGIN * 2);
  });

  test("inventory slots run left to right inside the bar", () => {
    const slots = inventorySlotRects(STAGE, 3);
    const bar = hudBarRect(STAGE);
    expect(slots).toHaveLength(3);
    expect(slots[0].x).toBe(HUD_MARGIN);
    expect(slots[1].x).toBe(HUD_MARGIN + INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GAP);
    expect(slots[0].y).toBeGreaterThanOrEqual(bar.y);
    expect(slots[0].y + slots[0].height).toBeLessThanOrEqual(bar.y + bar.height);
    expect(inventorySlotRects(STAGE, 0)).toHaveLength(0);
  });

  test("the verb controls sit right-aligned and clear of the inventory", () => {
    const buttons = verbButtonRects(STAGE);
    expect(buttons.hint.x + buttons.hint.width).toBe(STAGE.width - HUD_MARGIN);
    expect(buttons.look.x).toBeLessThan(buttons.hint.x);
    expect(buttons.act.x).toBeLessThan(buttons.look.x);
    // Every slot the capacity allows ends before the first control begins.
    const slots = inventorySlotRects(STAGE, inventoryCapacity(STAGE));
    const last = slots[slots.length - 1];
    expect(last.x + last.width).toBeLessThanOrEqual(buttons.act.x);
  });

  test("the end card is centred on the room, not on the whole canvas", () => {
    const card = winPanelRect(STAGE);
    expect(card.x + card.width / 2).toBe(STAGE.width / 2);
    expect(card.y + card.height / 2).toBe(STAGE.height / 2);
    expect(card.y + card.height).toBeLessThan(narrationRect(STAGE).y);
  });

  test("layout follows the authored frame rather than assuming 16:9", () => {
    const square = { width: 900, height: 900 };
    const bar = hudBarRect(square);
    const buttons = verbButtonRects(square);
    expect(bar.width).toBe(900);
    expect(bar.y + bar.height).toBe(canvasSize(square).height);
    expect(buttons.hint.x + buttons.hint.width).toBe(900 - HUD_MARGIN);
    expect(inventoryCapacity(square)).toBeGreaterThan(0);
  });
});
