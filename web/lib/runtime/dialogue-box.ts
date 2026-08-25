// Screen-fixed dialogue panel for village conversations.
//
// The village's world-space half - the villager, their name label, the "▲ Talk" prompt - lives in
// `npc.ts` and scrolls with the camera. This is the other half: once the player actually speaks
// to somebody, the conversation belongs to the screen, not to a spot in the town, so the panel is
// pinned with `setScrollFactor(0)` and sits at `SCENE_CONTENT_DEPTH.hud` above every world layer.
// A panel that scrolled would slide off the moment the player nudged the camera mid-sentence.
//
// The line-advance rule is deliberately not a method body. A conversation is a small state
// machine - open on the greeting, step to the remark, step to the farewell, then close - and the
// off-by-one that shows the last line twice or drops it entirely is exactly the kind of bug that
// only appears at the end of a conversation, which is the part a screenshot check never reaches.
// `nextDialogueCursor` is therefore an exported pure function, unit-tested without Phaser, and
// the class does nothing with the cursor except render whatever the function returns.

import Phaser from "phaser";
import { SCENE_CONTENT_DEPTH } from "./layers";
import type { DialogueExpressionState } from "./dialogue-sequence";

/** Gap between the panel and the viewport edges, in screen pixels. */
const PANEL_MARGIN_PX = 24;

/** Panel height in screen pixels: enough for a speaker line plus two wrapped lines of dialogue. */
const PANEL_HEIGHT_PX = 132;

/** Character body height. Its lower edge sits behind the dialogue panel. */
const PORTRAIT_HEIGHT_PX = 620;

/** Inner padding between the panel edge and its text, in screen pixels. */
const PANEL_PADDING_PX = 20;

const PANEL_CORNER_RADIUS_PX = 14;
const PANEL_FILL_COLOR = 0x101317;
const PANEL_FILL_ALPHA = 0.92;
const PANEL_STROKE_COLOR = 0xffdf8a;
const PANEL_STROKE_ALPHA = 0.85;
const PANEL_STROKE_WIDTH_PX = 2;

const SPEAKER_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "monospace",
  fontSize: "16px",
  color: "#ffdf8a",
};

const LINE_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "monospace",
  fontSize: "15px",
  color: "#f4f4f4",
};

/** Gap between the speaker name and the line beneath it, in screen pixels. */
const SPEAKER_LINE_GAP_PX = 10;

/**
 * The cursor for a conversation that has not shown a line yet.
 *
 * Exported so `open()` and the tests express "before the first line" with the same value rather
 * than each picking their own sentinel.
 */
export const DIALOGUE_CURSOR_BEFORE_FIRST = -1;

/**
 * Which line a conversation shows next, or null when it is over.
 *
 * Total by construction: every cursor, including the pre-open sentinel and values that could
 * only arrive from a corrupted caller, maps to either a line index inside `lineCount` or to
 * null. That matters because the alternative - clamping - is how a dialogue box ends up stuck on
 * its last line, refusing to close, with the player's movement still gated behind it.
 *
 * Rules:
 *  - A conversation with no lines is over before it starts. A villager whose manifest published
 *    no lines must not open an empty panel that then traps input until the player guesses that
 *    pressing the key again will close it.
 *  - Any cursor before the first line opens on line 0, so `open()` is the same call as
 *    `advance()` and there is only one path into the first line.
 *  - Otherwise step forward, and return null once the last line has already been shown - the
 *    signal for the caller to close rather than to render.
 */
export function nextDialogueCursor(
  cursor: number,
  lineCount: number,
): number | null {
  if (!Number.isSafeInteger(lineCount) || lineCount <= 0) return null;
  if (!Number.isSafeInteger(cursor)) return null;
  if (cursor < 0) return 0;
  const next = cursor + 1;
  return next < lineCount ? next : null;
}

export type DialoguePresentationBeat = Readonly<{
  speaker: string;
  text: string;
  expressionState: DialogueExpressionState | null;
}>;

export type DialoguePortraitTextureKeys = Readonly<
  Record<DialogueExpressionState, string>
>;

/** Convert the original one-speaker string sequence without adding rich presentation state. */
export function legacyDialogueBeats(
  speaker: string,
  lines: readonly string[],
): readonly DialoguePresentationBeat[] {
  return Object.freeze(
    lines.map((text) =>
      Object.freeze({ speaker, text, expressionState: null }),
    ),
  );
}

/** Resolve one presentation frame without Phaser, for cursor/probe tests. */
export function dialogueBeatAt(
  beats: readonly DialoguePresentationBeat[],
  cursor: number,
): DialoguePresentationBeat | null {
  if (!Number.isSafeInteger(cursor) || cursor < 0) return null;
  return beats[cursor] ?? null;
}

/** What a probe needs to assert a conversation without taking a screenshot. */
export type DialogueSnapshot = Readonly<{
  open: boolean;
  /** Name of the villager speaking, or "" while the box is closed. */
  speaker: string;
  /** The line currently on screen, or "" while the box is closed. */
  line: string;
  /** Index of the line on screen, or `DIALOGUE_CURSOR_BEFORE_FIRST` while closed. */
  lineIndex: number;
  /** Total lines in the open conversation, or 0 while closed. */
  lineCount: number;
  /** Rich expression state, or null for closed and legacy conversations. */
  expressionState: DialogueExpressionState | null;
  /** Whether the character overlay itself is visible. */
  portraitVisible: boolean;
}>;

export interface DialogueBoxOpts {
  scene: Phaser.Scene;
  viewW: number;
  viewH: number;
}

export class DialogueBox {
  private readonly scene: Phaser.Scene;
  private readonly viewW: number;
  private readonly viewH: number;
  private readonly container: Phaser.GameObjects.Container;
  private readonly speakerText: Phaser.GameObjects.Text;
  private readonly lineText: Phaser.GameObjects.Text;
  private portrait?: Phaser.GameObjects.Image;
  private portraitTextureKeys: DialoguePortraitTextureKeys | null = null;
  private beats: readonly DialoguePresentationBeat[] = [];
  private cursor = DIALOGUE_CURSOR_BEFORE_FIRST;

  constructor(opts: DialogueBoxOpts) {
    const scene = opts.scene;
    this.scene = scene;
    this.viewW = opts.viewW;
    this.viewH = opts.viewH;
    const panelWidth = Math.max(1, opts.viewW - PANEL_MARGIN_PX * 2);
    const panelX = PANEL_MARGIN_PX;
    const panelY = Math.max(0, opts.viewH - PANEL_HEIGHT_PX - PANEL_MARGIN_PX);

    // One container carries the whole panel so the scroll factor, the depth, and the open/closed
    // visibility are each set once. Setting them per child is how a stray text object ends up
    // scrolling away from the panel it belongs to.
    this.container = scene.add.container(panelX, panelY);
    this.container.setScrollFactor(0);
    this.container.setDepth(SCENE_CONTENT_DEPTH.hud);
    this.container.setVisible(false);

    const panel = scene.add.graphics();
    panel.fillStyle(PANEL_FILL_COLOR, PANEL_FILL_ALPHA);
    panel.fillRoundedRect(
      0,
      0,
      panelWidth,
      PANEL_HEIGHT_PX,
      PANEL_CORNER_RADIUS_PX,
    );
    panel.lineStyle(PANEL_STROKE_WIDTH_PX, PANEL_STROKE_COLOR, PANEL_STROKE_ALPHA);
    panel.strokeRoundedRect(
      0,
      0,
      panelWidth,
      PANEL_HEIGHT_PX,
      PANEL_CORNER_RADIUS_PX,
    );
    this.container.add(panel);

    this.speakerText = scene.add.text(
      PANEL_PADDING_PX,
      PANEL_PADDING_PX,
      "",
      SPEAKER_STYLE,
    );
    this.speakerText.setOrigin(0, 0);
    this.container.add(this.speakerText);

    // Wrapped to the panel's inner width rather than truncated. The recipe caps a villager's
    // line at 160 characters, which overruns one row at this size, and a line clipped mid-word is
    // indistinguishable from a generation fault when reviewing a capture.
    this.lineText = scene.add.text(
      PANEL_PADDING_PX,
      PANEL_PADDING_PX + this.speakerText.height + SPEAKER_LINE_GAP_PX,
      "",
      {
        ...LINE_STYLE,
        wordWrap: { width: Math.max(1, panelWidth - PANEL_PADDING_PX * 2) },
      },
    );
    this.lineText.setOrigin(0, 0);
    this.container.add(this.lineText);
  }

  get isOpen(): boolean {
    return this.cursor >= 0 && this.cursor < this.beats.length;
  }

  /**
   * Start a conversation on its first line.
   *
   * A speaker with no lines leaves the box closed rather than opening it blank, so the caller's
   * input gate - which reads `isOpen` - never latches on a villager who has nothing to say.
   */
  open(speaker: string, lines: readonly string[]): void {
    this.openBeats(legacyDialogueBeats(speaker, lines), null);
  }

  /**
   * Start a rich conversation and bind its complete expression texture set.
   *
   * The caller supplies all four keys as one value only after every corresponding asset has
   * passed its integrity checks. Legacy dialogue passes null, which keeps the portrait absent
   * while using the same cursor and rendering path as rich dialogue.
   */
  openBeats(
    beats: readonly DialoguePresentationBeat[],
    portraitTextureKeys: DialoguePortraitTextureKeys | null,
  ): void {
    const next = nextDialogueCursor(DIALOGUE_CURSOR_BEFORE_FIRST, beats.length);
    if (next === null) {
      this.close();
      return;
    }
    this.beats = beats;
    this.portraitTextureKeys = portraitTextureKeys;
    this.cursor = next;
    this.render();
  }

  /**
   * Step to the next line.
   *
   * Returns false once the last line has already been shown, which is the caller's signal to
   * close - the box does not close itself, because the same key press that ends a conversation
   * must not also be free to start the next one in the same frame.
   */
  advance(): boolean {
    if (!this.isOpen) return false;
    const next = nextDialogueCursor(this.cursor, this.beats.length);
    if (next === null) return false;
    this.cursor = next;
    this.render();
    return true;
  }

  close(): void {
    this.beats = [];
    this.portraitTextureKeys = null;
    this.cursor = DIALOGUE_CURSOR_BEFORE_FIRST;
    this.speakerText.setText("");
    this.lineText.setText("");
    this.container.setVisible(false);
    this.portrait?.setVisible(false);
  }

  /** Release every object this box owns. Called when the scene itself is torn down. */
  destroy(): void {
    this.portrait?.destroy();
    this.portrait = undefined;
    this.container.destroy(true);
  }

  snapshot(): DialogueSnapshot {
    const open = this.isOpen;
    const beat = open ? dialogueBeatAt(this.beats, this.cursor) : null;
    return {
      open,
      speaker: beat?.speaker ?? "",
      line: beat?.text ?? "",
      lineIndex: open ? this.cursor : DIALOGUE_CURSOR_BEFORE_FIRST,
      lineCount: open ? this.beats.length : 0,
      expressionState: beat?.expressionState ?? null,
      portraitVisible: open && (this.portrait?.visible ?? false),
    };
  }

  private render(): void {
    const beat = dialogueBeatAt(this.beats, this.cursor);
    if (!beat) {
      this.close();
      return;
    }
    this.speakerText.setText(beat.speaker);
    this.lineText.setText(beat.text);
    const portraitTextureKey =
      beat.expressionState === null
        ? null
        : (this.portraitTextureKeys?.[beat.expressionState] ?? null);
    if (portraitTextureKey) {
      if (!this.portrait) {
        const portrait = this.scene.add.image(
          this.viewW - PANEL_MARGIN_PX,
          this.viewH - PANEL_MARGIN_PX,
          portraitTextureKey,
        );
        portrait.setOrigin(1, 1);
        portrait.setDisplaySize(
          PORTRAIT_HEIGHT_PX * (2 / 3),
          PORTRAIT_HEIGHT_PX,
        );
        portrait.setScrollFactor(0);
        // The body remains above the world and below the opaque dialogue panel, so its feet can
        // disappear behind the panel without the figure covering the line being spoken.
        portrait.setDepth(SCENE_CONTENT_DEPTH.hud - 1);
        this.portrait = portrait;
      } else {
        this.portrait.setTexture(portraitTextureKey);
        // Phaser refreshes the image's native size when the texture changes. Re-assert the
        // screen contract even though the manifest currently locks every state to 1024x1536.
        this.portrait.setOrigin(1, 1);
        this.portrait.setDisplaySize(
          PORTRAIT_HEIGHT_PX * (2 / 3),
          PORTRAIT_HEIGHT_PX,
        );
      }
      this.portrait.setVisible(true);
    } else {
      this.portrait?.setVisible(false);
    }
    this.container.setVisible(true);
  }
}
