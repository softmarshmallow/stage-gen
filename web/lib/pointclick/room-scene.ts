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
import { bootGame, type GameHandle } from "@/lib/hosts/phaser/host";
import { hostScene } from "@/lib/hosts/phaser/scene-base";
import { registerPresentationFallback } from "@/lib/families/ui/fallback";
import type { UiIconGlyph } from "@/lib/manifest/ui-icon-layout";
import { AtlasButton } from "@/lib/families/ui/button";
import { UI_ATLAS_SHEETS, uiAtlasSheetKey } from "@/lib/families/ui/sheets";
import { mostReadable } from "@/lib/families/ui/contrast";
import { NineSliceWidget } from "@/lib/families/ui/widget";
import { roomUiSheetAsset } from "./contract";
import type { RoomHotspot, RoomManifest } from "./contract";
import {
  hotspotRect,
  hudBarRect,
  canvasSize,
  inventoryCapacity,
  inventorySlotRects,
  narrationRect,
  roomTextLayout,
  resolveVerb,
  verbButtonRects,
  winPanelRect,
  type VerbMode,
} from "./room-hud";
import { bagItemIds } from "@/lib/families/inventory";
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
/** The dark end of the range, for when the drawn plate is light. */
const INK_TEXT = "#141726";
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

export type RoomGameHandle = GameHandle<RoomPlayState>;

/**
 * How a host drives one room.
 *
 * The room is still the whole game inside its canvas; these are the two seams a
 * case needs. `resume` is a saved state to open on, `carriedFlags` are the facts
 * an earlier beat set, and `onChange` fires after every click so the shell can
 * autosave and notice the win without polling.
 */
export interface RoomGameOptions {
  readonly resume?: RoomPlayState | null;
  readonly carriedFlags?: readonly string[];
  readonly onChange?: (state: RoomPlayState) => void;
}

class RoomScene extends hostScene<RoomPlayState>(Phaser.Scene) {
  private state: RoomPlayState;
  private mode: VerbMode = "act";
  private hintsVisible = false;
  private pressStartedAt = 0;

  private readonly hotspotObjects = new Map<string, Phaser.GameObjects.GameObject>();
  private markers!: Phaser.GameObjects.Graphics;
  private narration!: Phaser.GameObjects.Text;
  /** The drawn plate's own interior height, so long narration can be fitted to it. */
  private narrationHeight = 0;
  private hoverLabel!: Phaser.GameObjects.Text;
  private slotFrames!: Phaser.GameObjects.Graphics;
  private readonly slotIcons: Phaser.GameObjects.Image[] = [];
  private readonly slotRects: Rect[] = [];
  private holdingLabel!: Phaser.GameObjects.Text;
  private modeButtons = new Map<VerbMode, AtlasButton>();
  private hintButton!: AtlasButton;
  private winLayer!: Phaser.GameObjects.Container;

  constructor(
    private readonly tag: string,
    private readonly manifest: RoomManifest,
    private readonly options: RoomGameOptions = {},
  ) {
    super({
      key: "pointclick-room",
      designSpace: canvasSize(manifest.scene),
      background: "#05070a",
    });
    this.state = options.resume ?? initialState(manifest, options.carriedFlags ?? []);
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
    // The interface is generated art like everything else here. The sheets are published with
    // a canonical alpha boundary already, so the plain loader is enough; a sheet that does not
    // arrive is replaced in `create` by the loud stand-in under the same key.
    for (const [role, key] of UI_ATLAS_SHEETS) {
      this.load.image(key, preparedAssetUrl(this.tag, roomUiSheetAsset(this.manifest.ui, role)));
    }
  }

  create(): void {
    const stage = this.stage;
    this.zoomToDesignSpace();
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

    for (const [, key, kind] of UI_ATLAS_SHEETS) {
      if (!this.textures.exists(key)) registerPresentationFallback(this.textures, key, kind);
    }

    this.createHud();
    this.createWinCard();
    // Phaser's own loader ran in `preload`; reaching `create` is what "ready"
    // means for a scene whose assets are all declared images. The failure card
    // the base owns is why a backdrop that will not decode now says so instead
    // of leaving a room the player can click around in the dark.
    if (this.textures.exists(BACKDROP_KEY)) this.finishLoading();
    else this.failLoading("Unable to load room", new Error(this.manifest.scene.backdrop));
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

    const barPanel = this.panel(bar, DEPTH.hud);
    const narrationPanel = this.panel(panel, DEPTH.hud);

    // No room-name line here: the reducer opens on the room's name and the page
    // chrome carries it too, so a header would say it a third time and steal the
    // height that long narration lines need.
    // Where the words go is measured on the drawn frame, not guessed: the producer publishes
    // the ornament-free interior and the layout turns it into an origin and a wrap width, so
    // a heavier border in a future run moves the text instead of running under it.
    const narrationSafe = narrationPanel.safeRect();
    const text = roomTextLayout(narrationSafe);
    // The plate is a fixed height and the narration is authored prose, so a long
    // line — or two narrations joining, which is what the window room's exit
    // does — can run past the border and render on the backdrop. The interior is
    // measured on the drawn frame, so the text is fitted to it rather than
    // trusted to be short.
    this.narrationHeight = Math.max(1, narrationSafe.height - (text.y - narrationSafe.y) * 2);
    // Measured on the drawn plate, not fixed: the narration colour was authored for a dark
    // fallback fill, and a package that ships a cream panel made the narration invisible while
    // the hotspot labels, which are accent gold, survived. See lib/families/ui/contrast.
    const narrationBg = narrationPanel.interiorColor();
    const narrationInk =
      narrationBg === null ? BODY_TEXT : (mostReadable(narrationBg, [BODY_TEXT, INK_TEXT]) ?? BODY_TEXT);
    this.narration = this.add
      .text(text.x, text.y, "", {
        ...NARRATION_STYLE,
        color: narrationInk,
        wordWrap: { width: text.wrapWidth },
      })
      .setDepth(DEPTH.hud + 1);

    // The control hint used to start six pixels below the bar's top edge, which was empty
    // canvas when the bar was a rectangle and is the drawn frame's border now. It starts at
    // the bar's own measured interior instead, so the words never run under the art.
    const label = roomTextLayout(barPanel.safeRect());
    const barBg = barPanel.interiorColor();
    // The hint is deliberately quiet, so its dim grey is offered first and only replaced when
    // the drawn bar makes it unreadable rather than merely subtle.
    const hintInk =
      barBg === null ? DIM_TEXT : (mostReadable(barBg, [DIM_TEXT, INK_TEXT, BODY_TEXT], 3) ?? DIM_TEXT);
    this.holdingLabel = this.add
      .text(label.x, label.y, "", { ...CONTROL_STYLE, fontSize: "18px", color: hintInk })
      .setDepth(DEPTH.hud + 1);

    this.createInventorySlots();

    const buttons = verbButtonRects(stage);
    // The verbs carry the two glyphs the preview icon set holds for them: a hand for acting
    // and a magnifying glass for looking. The hotspot toggle has no glyph in the set and says
    // its word alone, rather than borrowing a symbol that means something else.
    this.modeButtons.set(
      "act",
      this.controlButton(buttons.act, "Act", () => this.setMode("act"), "hand"),
    );
    this.modeButtons.set(
      "look",
      this.controlButton(buttons.look, "Look", () => this.setMode("look"), "search"),
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
        const itemId = bagItemIds(this.state.inventory)[index];
        if (itemId === undefined) return;
        this.state = selectItem(this.state, itemId);
        this.render();
      });
      this.slotIcons.push(icon);
      this.slotRects.push(slot);
    });
  }

  /**
   * One drawn panel at any size, from the single generated frame.
   *
   * The bar, the narration plate and the win card were three rounded rectangles with three
   * sets of colours; they are one sheet stretched to three sizes now, so the room's panels
   * agree with its art by construction rather than by someone picking matching hex values.
   */
  private panel(rect: Rect, depth: number): NineSliceWidget {
    return new NineSliceWidget({
      scene: this,
      sheetKey: uiAtlasSheetKey("panel_frame"),
      layout: this.manifest.ui.panelFrame.layout,
      width: rect.width,
      height: rect.height,
      x: rect.x + rect.width / 2,
      y: rect.y + rect.height / 2,
      depth,
    });
  }

  /**
   * A verb control, drawn from the generated button sheet.
   *
   * The bar is a toggle, and the sheet publishes `normal, hover, pressed, disabled` rather
   * than a selected cell, so the chosen verb is shown with the pressed art. That is the
   * honest reading of a four-state sheet: a selected cell is a separate role promotion.
   */
  private controlButton(
    rect: Rect,
    label: string,
    onPress: () => void,
    glyph?: UiIconGlyph,
  ): AtlasButton {
    const button = new AtlasButton({
      scene: this,
      sheetKey: uiAtlasSheetKey("button_rect"),
      layout: this.manifest.ui.buttonRect.layout,
      rect,
      depth: DEPTH.hud + 1,
      label,
      style: CONTROL_STYLE,
      icon: glyph
        ? {
            sheetKey: uiAtlasSheetKey("preview_icons"),
            layout: this.manifest.ui.previewIcons.layout,
            glyph,
          }
        : undefined,
      onPress,
    });
    // The verb reads on the button's own art, which is a different sheet from the panels.
    const face = button.widget.interiorColor();
    if (face !== null) {
      const ink = mostReadable(face, [BODY_TEXT, INK_TEXT]);
      if (ink !== null) button.text.setColor(ink);
    }
    return button;
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
    this.options.onChange?.(this.state);
    this.publish(this.state);
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

    this.setNarration(this.state.narration);
    this.renderInventory();

    for (const [mode, button] of this.modeButtons) button.setSelected(this.mode === mode);
    this.hintButton.setSelected(this.hintsVisible);

    this.winLayer.setVisible(this.state.solved);
  }

  /**
   * Put the words on the plate, and keep them on it.
   *
   * Phaser wraps to a width and grows downward without limit, so the only way a
   * fixed plate holds authored prose is to step the size down until it fits.
   * Three steps and a floor: below that the words would be smaller than the
   * control hints and unreadable, and losing a line is better than losing the
   * paragraph, so the last step clamps rather than continuing.
   */
  private setNarration(value: string): void {
    const sizes = [26, 23, 20, 18];
    for (const size of sizes) {
      this.narration.setFontSize(size);
      this.narration.setText(value);
      if (this.narration.height <= this.narrationHeight) return;
    }
  }

  private renderInventory(): void {
    this.slotFrames.clear();
    this.slotIcons.forEach((icon, index) => {
      const itemId = bagItemIds(this.state.inventory)[index];
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
  options: RoomGameOptions = {},
): RoomGameHandle {
  return bootGame(parent, new RoomScene(tag, manifest, options));
}
