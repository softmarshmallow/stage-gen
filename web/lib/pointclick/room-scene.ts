// The point-and-click room as a Phaser scene: one canvas, nothing around it.
//
// The room used to be DOM — an <img> with absolutely positioned buttons over it
// and the inventory in page chrome below. That reads as a web page with a
// picture on it. A room is a game, and it now runs on the same engine the
// platformer does: one fixed design space (the authored scene frame), scaled to
// whatever viewport it lands in, with the backdrop, the hotspots, the narration,
// the inventory and the verb controls all drawn inside the canvas. Embedded on a
// phone it fills the screen and plays; embedded in a page it letterboxes.
//
// The engine is only the view. Every transition still goes through the pure
// reducer in `state.ts` — the same state machine the Python solvability proof
// searched — so putting a game engine underneath did not give the room a second
// source of truth about whether it can be finished.

import Phaser from "phaser";
import { preparedAssetUrl } from "@/lib/shell/asset-url";
import { containRect, type Rect } from "@/lib/shell/hud-geometry";
import { applyDeviceZoom, currentDevicePixelScale, deviceGameSize } from "@/lib/device-pixels/device-camera";
import type { RoomHotspot, RoomManifest } from "./contract";
import {
  hotspotRect,
  hudBarRect,
  canvasSize,
  hudLabelPoint,
  inventoryCapacity,
  inventorySlotRects,
  narrationRect,
  resolveVerb,
  verbButtonRects,
  winPanelRect,
  type VerbMode,
} from "./room-hud";
import {
  clickHotspot,
  hotspotVisible,
  initialState,
  inspectHotspot,
  selectItem,
  type RoomPlayState,
} from "./state";

const BACKDROP_KEY = "room:backdrop";
const PANEL_FILL = 0x0d1014;
const PANEL_ALPHA = 0.9;
const PANEL_STROKE = 0x6d757f;
const ACCENT = 0xffdf8a;
const ACCENT_TEXT = "#ffdf8a";
const BODY_TEXT = "#f2f3f5";
const DIM_TEXT = "#98a0ab";
const CORNER = 10;

/** Depth rungs: world, then hotspot furniture, then screen furniture, then the end card. */
const DEPTH = { backdrop: 0, hotspot: 10, marker: 20, hud: 100, win: 200 } as const;

const NARRATION_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "Georgia, 'Times New Roman', serif",
  fontSize: "26px",
  color: BODY_TEXT,
  lineSpacing: 8,
};

const CONTROL_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "24px",
  color: BODY_TEXT,
};

const LABEL_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "22px",
  color: ACCENT_TEXT,
};

function spriteKey(ref: string): string {
  return `room:${ref}`;
}

export interface RoomGameHandle {
  destroy(removeCanvas: boolean): void;
}

class RoomScene extends Phaser.Scene {
  private state: RoomPlayState;
  private mode: VerbMode = "act";
  private hintsVisible = false;
  private pressStartedAt = 0;

  private readonly hotspotObjects = new Map<string, Phaser.GameObjects.GameObject>();
  private markers!: Phaser.GameObjects.Graphics;
  private narration!: Phaser.GameObjects.Text;
  private hoverLabel!: Phaser.GameObjects.Text;
  private slotFrames!: Phaser.GameObjects.Graphics;
  private readonly slotIcons: Phaser.GameObjects.Image[] = [];
  private readonly slotRects: Rect[] = [];
  private holdingLabel!: Phaser.GameObjects.Text;
  private modeButtons = new Map<VerbMode, Phaser.GameObjects.Graphics>();
  private hintButton!: Phaser.GameObjects.Graphics;
  private winLayer!: Phaser.GameObjects.Container;

  constructor(
    private readonly tag: string,
    private readonly manifest: RoomManifest,
  ) {
    super("pointclick-room");
    this.state = initialState(manifest);
  }

  private get stage(): { width: number; height: number } {
    return { width: this.manifest.scene.width, height: this.manifest.scene.height };
  }

  preload(): void {
    this.load.image(BACKDROP_KEY, preparedAssetUrl(this.tag, this.manifest.scene.backdrop));
    for (const hotspot of this.manifest.hotspots) {
      if (hotspot.sprite) {
        this.load.image(spriteKey(hotspot.sprite), preparedAssetUrl(this.tag, hotspot.sprite));
      }
    }
    for (const item of this.manifest.items) {
      this.load.image(spriteKey(item.icon), preparedAssetUrl(this.tag, item.icon));
    }
  }

  create(): void {
    const stage = this.stage;
    // The canvas is device-pixel sized; zoom the camera back to the authored frame plus HUD band.
    applyDeviceZoom(this.cameras.main, canvasSize(this.manifest.scene));
    this.input.mouse?.disableContextMenu();

    // The backdrop covers the authored frame exactly; the HUD band below it is
    // canvas the room never draws into, so no hotspot can end up under a panel.
    this.add
      .image(0, 0, BACKDROP_KEY)
      .setOrigin(0, 0)
      .setDisplaySize(stage.width, stage.height)
      .setDepth(DEPTH.backdrop);

    this.markers = this.add.graphics().setDepth(DEPTH.marker);

    for (const hotspot of this.manifest.hotspots) {
      this.hotspotObjects.set(hotspot.id, this.createHotspot(hotspot));
    }

    this.hoverLabel = this.add
      .text(0, 0, "", LABEL_STYLE)
      .setOrigin(0.5, 1)
      .setDepth(DEPTH.marker + 1)
      .setVisible(false);

    this.createHud();
    this.createWinCard();
    this.render();
  }

  // ------------------------------------------------------------------ world

  private createHotspot(hotspot: RoomHotspot): Phaser.GameObjects.GameObject {
    const region = hotspotRect(this.stage, hotspot.region);
    const object = hotspot.sprite
      ? this.spriteHotspot(hotspot.sprite, region)
      : this.add
          .zone(region.x, region.y, region.width, region.height)
          .setOrigin(0, 0)
          .setDepth(DEPTH.hotspot);
    object.setInteractive({ useHandCursor: true });
    object.on(Phaser.Input.Events.GAMEOBJECT_POINTER_DOWN, () => {
      this.pressStartedAt = this.time.now;
    });
    object.on(
      Phaser.Input.Events.GAMEOBJECT_POINTER_UP,
      (pointer: Phaser.Input.Pointer) => this.pressed(hotspot.id, pointer),
    );
    object.on(Phaser.Input.Events.GAMEOBJECT_POINTER_OVER, () => this.hover(hotspot, true));
    object.on(Phaser.Input.Events.GAMEOBJECT_POINTER_OUT, () => this.hover(hotspot, false));
    return object;
  }

  private spriteHotspot(ref: string, region: Rect): Phaser.GameObjects.Image {
    const texture = this.textures.get(spriteKey(ref)).getSourceImage();
    const frame = containRect(region, {
      width: texture.width || region.width,
      height: texture.height || region.height,
    });
    return this.add
      .image(frame.x, frame.y, spriteKey(ref))
      .setOrigin(0, 0)
      .setDisplaySize(frame.width, frame.height)
      .setDepth(DEPTH.hotspot);
  }

  private hover(hotspot: RoomHotspot, entering: boolean): void {
    if (!entering) {
      this.hoverLabel.setVisible(false);
      return;
    }
    const region = hotspotRect(this.stage, hotspot.region);
    this.hoverLabel
      .setText(hotspot.label)
      .setPosition(region.x + region.width / 2, Math.max(28, region.y - 8))
      .setVisible(true);
  }

  private pressed(hotspotId: string, pointer: Phaser.Input.Pointer): void {
    if (this.state.solved) return;
    const verb = resolveVerb(this.mode, {
      secondary: pointer.rightButtonReleased(),
      heldMs: this.time.now - this.pressStartedAt,
    });
    this.state =
      verb === "inspect"
        ? inspectHotspot(this.manifest, this.state, hotspotId)
        : clickHotspot(this.manifest, this.state, hotspotId);
    this.render();
  }

  // -------------------------------------------------------------------- hud

  private createHud(): void {
    const stage = this.stage;
    const bar = hudBarRect(stage);
    const panel = narrationRect(stage);

    this.panel(bar, { fill: 0x05070a, alpha: 0.92, stroke: false }).setDepth(DEPTH.hud);
    this.panel(panel).setDepth(DEPTH.hud);

    // No room-name line here: the reducer opens on the room's name and the page
    // chrome carries it too, so a header would say it a third time and steal the
    // height that long narration lines need.
    this.narration = this.add
      .text(panel.x + 28, panel.y + 18, "", {
        ...NARRATION_STYLE,
        wordWrap: { width: panel.width - 56 },
      })
      .setDepth(DEPTH.hud + 1);

    const label = hudLabelPoint(stage);
    this.holdingLabel = this.add
      .text(label.x, label.y, "", { ...CONTROL_STYLE, fontSize: "18px", color: DIM_TEXT })
      .setDepth(DEPTH.hud + 1);

    this.createInventorySlots();

    const buttons = verbButtonRects(stage);
    this.modeButtons.set("act", this.controlButton(buttons.act, "Act", () => this.setMode("act")));
    this.modeButtons.set(
      "look",
      this.controlButton(buttons.look, "Look", () => this.setMode("look")),
    );
    this.hintButton = this.controlButton(buttons.hint, "Hotspots", () => {
      this.hintsVisible = !this.hintsVisible;
      this.render();
    });
  }

  /**
   * The inventory is a fixed pool of slots, built once and then shown or hidden.
   *
   * Rebuilding it per state change meant destroying the very zone that was
   * dispatching the press that caused the change, which is how an inventory
   * ends up unclickable. Slots are permanent furniture; only what they hold
   * changes.
   */
  private createInventorySlots(): void {
    const slots = inventorySlotRects(this.stage, inventoryCapacity(this.stage));
    this.slotFrames = this.add.graphics().setDepth(DEPTH.hud + 1);
    slots.forEach((slot, index) => {
      const icon = this.add
        .image(slot.x + slot.width / 2, slot.y + slot.height / 2, BACKDROP_KEY)
        .setOrigin(0.5)
        .setDepth(DEPTH.hud + 2)
        .setVisible(false);
      const zone = this.add
        .zone(slot.x, slot.y, slot.width, slot.height)
        .setOrigin(0, 0)
        .setDepth(DEPTH.hud + 3)
        .setInteractive({ useHandCursor: true });
      zone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, () => {
        const itemId = this.state.inventory[index];
        if (itemId === undefined) return;
        this.state = selectItem(this.state, itemId);
        this.render();
      });
      this.slotIcons.push(icon);
      this.slotRects.push(slot);
    });
  }

  private panel(
    rect: Rect,
    options: { fill?: number; alpha?: number; stroke?: boolean } = {},
  ): Phaser.GameObjects.Graphics {
    const graphics = this.add.graphics();
    graphics.fillStyle(options.fill ?? PANEL_FILL, options.alpha ?? PANEL_ALPHA);
    graphics.fillRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
    if (options.stroke !== false) {
      graphics.lineStyle(2, PANEL_STROKE, 0.5);
      graphics.strokeRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
    }
    return graphics;
  }

  /** A button is a graphic plus its label, and the graphic is redrawn to show state. */
  private controlButton(rect: Rect, label: string, onPress: () => void): Phaser.GameObjects.Graphics {
    const graphics = this.add.graphics().setDepth(DEPTH.hud + 1);
    this.add
      .text(rect.x + rect.width / 2, rect.y + rect.height / 2, label, CONTROL_STYLE)
      .setOrigin(0.5)
      .setDepth(DEPTH.hud + 2);
    const zone = this.add
      .zone(rect.x, rect.y, rect.width, rect.height)
      .setOrigin(0, 0)
      .setDepth(DEPTH.hud + 3)
      .setInteractive({ useHandCursor: true });
    zone.on(Phaser.Input.Events.GAMEOBJECT_POINTER_UP, onPress);
    graphics.setData("rect", rect);
    return graphics;
  }

  private paintButton(graphics: Phaser.GameObjects.Graphics, active: boolean): void {
    const rect = graphics.getData("rect") as Rect;
    graphics.clear();
    graphics.fillStyle(active ? ACCENT : 0x1a1f26, active ? 0.9 : 0.85);
    graphics.fillRoundedRect(rect.x, rect.y, rect.width, rect.height, 8);
    graphics.lineStyle(2, active ? ACCENT : PANEL_STROKE, active ? 1 : 0.6);
    graphics.strokeRoundedRect(rect.x, rect.y, rect.width, rect.height, 8);
  }

  private setMode(mode: VerbMode): void {
    this.mode = mode;
    this.render();
  }

  private createWinCard(): void {
    const stage = this.stage;
    const rect = winPanelRect(stage);
    const dim = this.add.graphics();
    dim.fillStyle(0x05070a, 0.72);
    dim.fillRect(0, 0, stage.width, stage.height);

    const card = this.add.graphics();
    card.fillStyle(PANEL_FILL, 0.97);
    card.fillRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
    card.lineStyle(2, ACCENT, 0.9);
    card.strokeRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
    const title = this.add
      .text(rect.x + rect.width / 2, rect.y + 44, "✦ Room complete", {
        ...LABEL_STYLE,
        fontSize: "28px",
      })
      .setOrigin(0.5, 0);
    const line = this.add
      .text(rect.x + rect.width / 2, rect.y + 100, this.manifest.win.narration, {
        ...NARRATION_STYLE,
        fontSize: "26px",
        align: "center",
        wordWrap: { width: rect.width - 72 },
      })
      .setOrigin(0.5, 0);
    this.winLayer = this.add
      .container(0, 0, [dim, card, title, line])
      .setDepth(DEPTH.win)
      .setVisible(false);
  }

  // ----------------------------------------------------------------- render

  /** One pass over the whole view from the reducer's state: no partial updates. */
  private render(): void {
    for (const hotspot of this.manifest.hotspots) {
      const object = this.hotspotObjects.get(hotspot.id);
      if (object === undefined) continue;
      const visible = hotspotVisible(this.manifest, this.state, hotspot.id);
      if (object instanceof Phaser.GameObjects.Image) object.setVisible(visible);
      if (visible) object.setInteractive({ useHandCursor: true });
      else object.disableInteractive();
    }

    this.markers.clear();
    if (this.hintsVisible) {
      this.markers.lineStyle(3, ACCENT, 0.85);
      for (const hotspot of this.manifest.hotspots) {
        if (!hotspotVisible(this.manifest, this.state, hotspot.id)) continue;
        const region = hotspotRect(this.stage, hotspot.region);
        this.markers.strokeRoundedRect(region.x, region.y, region.width, region.height, 8);
      }
    }

    this.narration.setText(this.state.narration);
    this.renderInventory();

    for (const [mode, graphics] of this.modeButtons) this.paintButton(graphics, this.mode === mode);
    this.paintButton(this.hintButton, this.hintsVisible);

    this.winLayer.setVisible(this.state.solved);
  }

  private renderInventory(): void {
    this.slotFrames.clear();
    this.slotIcons.forEach((icon, index) => {
      const itemId = this.state.inventory[index];
      const item =
        itemId === undefined
          ? undefined
          : this.manifest.items.find((entry) => entry.id === itemId);
      const slot = this.slotRects[index];
      if (item === undefined || slot === undefined) {
        icon.setVisible(false);
        return;
      }
      const key = spriteKey(item.icon);
      const holding = this.state.selectedItem === itemId;
      this.slotFrames.fillStyle(holding ? 0x2a2416 : 0x11151b, 0.95);
      this.slotFrames.fillRoundedRect(slot.x, slot.y, slot.width, slot.height, 8);
      this.slotFrames.lineStyle(holding ? 3 : 2, holding ? ACCENT : PANEL_STROKE, holding ? 1 : 0.6);
      this.slotFrames.strokeRoundedRect(slot.x, slot.y, slot.width, slot.height, 8);
      const source = this.textures.get(key).getSourceImage();
      const fitted = containRect(
        { x: 0, y: 0, width: slot.width - 16, height: slot.height - 16 },
        { width: source.width || 1, height: source.height || 1 },
      );
      icon.setTexture(key).setDisplaySize(fitted.width, fitted.height).setVisible(true);
    });
    const held = this.state.selectedItem;
    const label = held ? this.manifest.items.find((entry) => entry.id === held)?.label : undefined;
    this.holdingLabel.setText(
      label ? `holding ${label} — tap what to use it on` : "tap to act · hold to look",
    );
  }
}

/**
 * Boot one room into `parent`, scaled to fit whatever that element is.
 *
 * The design space is the authored scene frame, so a room laid out at 1280×720
 * plays identically on a phone and in a page column; the engine letterboxes,
 * and nothing in the room is measured in CSS pixels.
 */
export function bootRoomGame(
  parent: HTMLElement,
  tag: string,
  manifest: RoomManifest,
): RoomGameHandle {
  const canvas = canvasSize(manifest.scene);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    ...deviceGameSize(canvas, currentDevicePixelScale()),
    parent,
    backgroundColor: "#05070a",
    scene: [new RoomScene(tag, manifest)],
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  });
  return { destroy: (removeCanvas: boolean) => game.destroy(removeCanvas) };
}
