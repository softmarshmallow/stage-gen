// The visual novel as a Phaser scene: one canvas, nothing around it.
//
// The scene used to be DOM — an <img> backdrop with another <img> absolutely
// positioned over it and the dialogue box built from divs and Tailwind. That
// reads as a web page with a picture on it. A scene is a game, and it now runs
// on the same engine the platformer and the point-and-click room do: one fixed
// design space (the producer's own background frame), scaled to whatever
// viewport it lands in, with the backdrop, the character, the dialogue panel
// and the end card all drawn inside the canvas. Embedded on a phone it fills
// the screen and plays; embedded in a page it letterboxes.
//
// The engine is only the view. Every transition still goes through the pure
// reducer in `playback.ts`, and the character's placement still comes from
// `framing.ts` — putting an engine underneath gave the scene no second opinion
// about which beat is showing or how the character is framed.

import Phaser from "phaser";
import {
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
} from "./framing";
import {
  currentDialogueSceneBeat,
  currentDialogueSceneExpressionState,
  dialogueSceneActionForKey,
  dialogueSceneIsComplete,
  initialDialogueScenePlayback,
  reduceDialogueScenePlayback,
  type DialogueScenePlaybackAction,
  type DialogueScenePlaybackState,
} from "./playback";
import {
  bodyTextPoint,
  bodyTextWrapWidth,
  completeCardRect,
  DIALOGUE_STAGE,
  dialoguePanelRect,
  progressPoint,
  speakerChipRect,
  spriteFrame,
  type Rect,
} from "./scene-hud";
import type {
  DialogueSceneDemoFixture,
  DialogueSceneExpressionState,
} from "./schema";

const BACKDROP_KEY = "vn:backdrop";

const PANEL_FILL = 0x111a33;
const PANEL_ALPHA = 0.93;
const PANEL_STROKE = 0x6f7bb0;
const CHIP_FILL = 0xf3a7c4;
const INK = "#141726";
const PAPER = "#f4f1ee";
const DIM = "#a9b0c8";
const CORNER = 18;

/** Depth rungs: world, then character, then the panel, then the end card. */
const DEPTH = { backdrop: 0, sprite: 10, panel: 100, complete: 200 } as const;

const BODY_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "Georgia, 'Times New Roman', serif",
  fontSize: "30px",
  color: PAPER,
  lineSpacing: 12,
};

const SPEAKER_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "24px",
  fontStyle: "bold",
  color: INK,
};

const META_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "system-ui, sans-serif",
  fontSize: "20px",
  color: DIM,
};

function expressionKey(state: DialogueSceneExpressionState): string {
  return `vn:expression:${state}`;
}

export interface DialogueSceneGameHandle {
  destroy(removeCanvas: boolean): void;
}

class DialogueScene extends Phaser.Scene {
  private playback: DialogueScenePlaybackState = initialDialogueScenePlayback();

  private character!: Phaser.GameObjects.Image;
  private panel!: Phaser.GameObjects.Graphics;
  private chip!: Phaser.GameObjects.Graphics;
  private speaker!: Phaser.GameObjects.Text;
  private body!: Phaser.GameObjects.Text;
  private progress!: Phaser.GameObjects.Text;
  private completeLayer!: Phaser.GameObjects.Container;

  constructor(private readonly fixture: DialogueSceneDemoFixture) {
    super("dialogue-scene");
  }

  private get beatCount(): number {
    return this.fixture.dialogue.length;
  }

  preload(): void {
    this.load.image(BACKDROP_KEY, this.fixture.background.src);
    for (const variant of this.fixture.expressionVariants) {
      this.load.image(expressionKey(variant.state), variant.src);
    }
  }

  create(): void {
    this.add
      .image(0, 0, BACKDROP_KEY)
      .setOrigin(0, 0)
      .setDisplaySize(DIALOGUE_STAGE.width, DIALOGUE_STAGE.height)
      .setDepth(DEPTH.backdrop);

    this.character = this.add.image(0, 0, expressionKey("neutral")).setOrigin(0, 0);
    this.character.setDepth(DEPTH.sprite);

    this.createPanel();
    this.createCompleteCard();

    // The whole frame advances, the way a visual novel does: there is exactly
    // one thing to do, so there is no button to find.
    this.input.on(Phaser.Input.Events.POINTER_UP, () => this.act("next"));
    this.input.keyboard?.on("keydown", (event: KeyboardEvent) => {
      const action = dialogueSceneActionForKey(event.key);
      if (action === null) return;
      event.preventDefault();
      this.act(action);
    });

    this.render();
  }

  private createPanel(): void {
    const panel = dialoguePanelRect(DIALOGUE_STAGE);
    this.panel = this.add.graphics().setDepth(DEPTH.panel);
    this.panel.fillStyle(PANEL_FILL, PANEL_ALPHA);
    this.panel.fillRoundedRect(panel.x, panel.y, panel.width, panel.height, CORNER);
    this.panel.lineStyle(2, PANEL_STROKE, 0.7);
    this.panel.strokeRoundedRect(panel.x, panel.y, panel.width, panel.height, CORNER);

    this.chip = this.add.graphics().setDepth(DEPTH.panel + 1);
    this.speaker = this.add.text(0, 0, "", SPEAKER_STYLE).setDepth(DEPTH.panel + 2);

    const body = bodyTextPoint(panel);
    this.body = this.add
      .text(body.x, body.y, "", {
        ...BODY_STYLE,
        wordWrap: { width: bodyTextWrapWidth(panel) },
      })
      .setDepth(DEPTH.panel + 1);

    const progress = progressPoint(panel);
    this.progress = this.add
      .text(progress.x, progress.y, "", META_STYLE)
      .setOrigin(1, 1)
      .setDepth(DEPTH.panel + 1);
  }

  private createCompleteCard(): void {
    const card = completeCardRect(DIALOGUE_STAGE);
    const frame = this.add.graphics();
    frame.fillStyle(0x0b1024, 0.95);
    frame.fillRoundedRect(card.x, card.y, card.width, card.height, CORNER);
    frame.lineStyle(2, CHIP_FILL, 0.85);
    frame.strokeRoundedRect(card.x, card.y, card.width, card.height, CORNER);
    const title = this.add
      .text(card.x + card.width / 2, card.y + card.height / 2 - 26, "Scene complete", {
        ...BODY_STYLE,
        fontSize: "38px",
      })
      .setOrigin(0.5, 0.5);
    const hint = this.add
      .text(
        card.x + card.width / 2,
        card.y + card.height / 2 + 34,
        "tap to play again · ← to step back",
        META_STYLE,
      )
      .setOrigin(0.5, 0.5);
    this.completeLayer = this.add
      .container(0, 0, [frame, title, hint])
      .setDepth(DEPTH.complete)
      .setVisible(false);
  }

  private act(action: DialogueScenePlaybackAction): void {
    // Advancing off the end plays again rather than doing nothing. The reducer
    // is right to hold at the terminal cursor - that is what "finished" means -
    // but a tap that visibly does nothing reads as a broken scene, so the view
    // decides what the end card's one gesture is for.
    const intent =
      action === "next" && dialogueSceneIsComplete(this.beatCount, this.playback)
        ? "restart"
        : action;
    const next = reduceDialogueScenePlayback(this.beatCount, this.playback, intent);
    if (next === this.playback) return;
    this.playback = next;
    this.render();
  }

  private render(): void {
    const complete = dialogueSceneIsComplete(this.beatCount, this.playback);
    const state = currentDialogueSceneExpressionState(this.fixture.dialogue, this.playback);
    this.renderCharacter(state);

    // The end card says the scene is over; a panel repeating it underneath says
    // it twice. Only one of the two is on screen at a time.
    const beat = currentDialogueSceneBeat(this.fixture.dialogue, this.playback);
    this.panel.setVisible(!complete);
    this.chip.setVisible(!complete);
    this.speaker.setVisible(!complete);
    this.body.setVisible(!complete);
    this.progress.setVisible(!complete);
    this.completeLayer.setVisible(complete);
    if (complete) return;
    this.body.setText(beat?.text ?? "");
    this.progress.setText(
      `${this.playback.cursor + 1} / ${this.beatCount} · tap to continue`,
    );
    this.renderSpeaker(beat?.speaker ?? "");
  }

  private renderCharacter(state: DialogueSceneExpressionState): void {
    const key = expressionKey(state);
    const source = this.textures.get(key).getSourceImage();
    const framing = mapDialogueSceneFraming(this.fixture.presentation.framingZoom);
    const baseline = mapDialogueSceneFraming(this.fixture.presentation.sourceFramingZoom);
    const frame = spriteFrame(
      DIALOGUE_STAGE,
      { width: source.width || 1, height: source.height || 1 },
      {
        scale: normalizeDialogueSceneFramingScale(
          framing.presentation.scale,
          baseline.presentation.scale,
        ),
        xPercent: framing.presentation.position.xPercent,
        yPercent: framing.presentation.position.yPercent,
      },
    );
    this.character
      .setTexture(key)
      .setPosition(frame.x, frame.y)
      .setDisplaySize(frame.width, frame.height);
  }

  private renderSpeaker(label: string): void {
    this.speaker.setText(label);
    const chip: Rect = speakerChipRect(
      dialoguePanelRect(DIALOGUE_STAGE),
      this.speaker.width,
    );
    this.chip.clear();
    this.chip.fillStyle(CHIP_FILL, 1);
    this.chip.fillRoundedRect(chip.x, chip.y, chip.width, chip.height, chip.height / 2);
    this.speaker.setPosition(chip.x + chip.width / 2, chip.y + chip.height / 2).setOrigin(0.5, 0.5);
  }
}

/**
 * Boot one scene into `parent`, scaled to fit whatever that element is.
 *
 * The design space is the producer's background frame, so a scene plays
 * identically on a phone and in a page column; the engine letterboxes, and
 * nothing in the scene is measured in CSS pixels.
 */
export function bootDialogueSceneGame(
  parent: HTMLElement,
  fixture: DialogueSceneDemoFixture,
): DialogueSceneGameHandle {
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    width: DIALOGUE_STAGE.width,
    height: DIALOGUE_STAGE.height,
    parent,
    backgroundColor: "#05070a",
    scene: [new DialogueScene(fixture)],
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  });
  return { destroy: (removeCanvas: boolean) => game.destroy(removeCanvas) };
}
