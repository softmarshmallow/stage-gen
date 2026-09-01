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
// The engine is only the view. Every transition goes through the pure reducer in
// `lib/scenario/runtime.ts` — which is where the branching lives, and which the
// platformer is meant to share — and the character's placement still comes from
// `framing.ts`. Putting an engine underneath gave the scene no second opinion
// about which statement is showing, who is on stage, or which flags are set.

import Phaser from "phaser";
import {
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
} from "./framing";
import { ScenarioAudio, htmlAudioTransport } from "./scene-audio";
import {
  bodyTextPoint,
  bodyTextWrapWidth,
  choiceAt,
  choiceRects,
  completeCardRect,
  DIALOGUE_STAGE,
  dialoguePanelRect,
  progressPoint,
  slotFrame,
  speakerChipRect,
} from "./scene-hud";
import type { Rect } from "@/lib/shell/hud-geometry";
import {
  dialogueSceneExpression,
  dialogueSceneStage,
  type DialogueSceneFixture,
} from "./schema";
import { scenarioActionForKey, scenarioOptionForKey } from "@/lib/scenario/keys";
import {
  initialScenarioState,
  reduceScenario,
  scenarioIsFinished,
  scenarioProgress,
  scenarioView,
  type ScenarioState,
} from "@/lib/scenario/runtime";

function stageKey(stageId: string): string {
  return `vn:stage:${stageId}`;
}

function plateKey(actorId: string, state: string): string {
  return `vn:actor:${actorId}:${state}`;
}

/** How much an actor who is not speaking is dimmed and pushed back. */
const LISTENER_TINT = 0x7f8496;
const LISTENER_ALPHA = 0.82;

const PANEL_FILL = 0x111a33;
const PANEL_ALPHA = 0.93;
const PANEL_STROKE = 0x6f7bb0;
const CHIP_FILL = 0xf3a7c4;
const CHOICE_FILL = 0x16203f;
const CHOICE_HOVER = 0x243358;
const INK = "#141726";
const PAPER = "#f4f1ee";
const DIM = "#a9b0c8";
const CORNER = 18;

/** Depth rungs: world, then character, then the panel, then choices, then the end card. */
const DEPTH = { backdrop: 0, sprite: 10, panel: 100, choice: 150, complete: 200 } as const;

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

const CHOICE_STYLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: "Georgia, 'Times New Roman', serif",
  fontSize: "28px",
  color: PAPER,
};

export interface DialogueSceneGameHandle {
  destroy(removeCanvas: boolean): void;
}

class DialogueScene extends Phaser.Scene {
  private playback: ScenarioState;
  private readonly audio: ScenarioAudio;

  private backdrop!: Phaser.GameObjects.Image;
  /** One sprite per drawable actor, shown or hidden as the scenario stages them. */
  private readonly cast = new Map<string, Phaser.GameObjects.Image>();
  private panel!: Phaser.GameObjects.Graphics;
  private chip!: Phaser.GameObjects.Graphics;
  private speaker!: Phaser.GameObjects.Text;
  private body!: Phaser.GameObjects.Text;
  private progress!: Phaser.GameObjects.Text;
  private choiceLayer!: Phaser.GameObjects.Container;
  private completeLayer!: Phaser.GameObjects.Container;
  private completeTitle!: Phaser.GameObjects.Text;

  constructor(private readonly fixture: DialogueSceneFixture) {
    super("dialogue-scene");
    this.playback = initialScenarioState(fixture.scenario);
    this.audio = new ScenarioAudio(fixture, htmlAudioTransport());
  }

  preload(): void {
    for (const stage of this.fixture.stages) {
      this.load.image(stageKey(stage.stageId), stage.src);
    }
    for (const actor of this.fixture.actors) {
      for (const variant of actor.expressions) {
        this.load.image(plateKey(actor.actorId, variant.state), variant.src);
      }
    }
  }

  create(): void {
    const opening = this.fixture.stages[0]!;
    this.backdrop = this.add
      .image(0, 0, stageKey(opening.stageId))
      .setOrigin(0, 0)
      .setDisplaySize(DIALOGUE_STAGE.width, DIALOGUE_STAGE.height)
      .setDepth(DEPTH.backdrop);

    for (const actor of this.fixture.actors) {
      const first = actor.expressions[0]!;
      this.cast.set(
        actor.actorId,
        this.add
          .image(0, 0, plateKey(actor.actorId, first.state))
          .setOrigin(0, 0)
          .setDepth(DEPTH.sprite)
          .setVisible(false),
      );
    }

    this.createPanel();
    this.createChoiceLayer();
    this.createCompleteCard();

    // A tap on the frame advances, because a visual novel with one thing to do
    // needs no button to find. When a choice is up, the tap has to land on an
    // option instead: the whole frame no longer means one thing.
    this.input.on(Phaser.Input.Events.POINTER_UP, (pointer: Phaser.Input.Pointer) => {
      const view = scenarioView(this.fixture.scenario, this.playback);
      if (view?.kind === "choice") {
        const option = choiceAt(DIALOGUE_STAGE, view.options.length, {
          x: pointer.worldX,
          y: pointer.worldY,
        });
        if (option !== null) this.act({ kind: "choose", option });
        return;
      }
      this.act({ kind: "advance" });
    });
    this.input.keyboard?.on("keydown", (event: KeyboardEvent) => {
      const view = scenarioView(this.fixture.scenario, this.playback);
      if (view?.kind === "choice") {
        const option = scenarioOptionForKey(event.key);
        if (option === null || option >= view.options.length) return;
        event.preventDefault();
        this.act({ kind: "choose", option });
        return;
      }
      const action = scenarioActionForKey(event.key);
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

  private createChoiceLayer(): void {
    this.choiceLayer = this.add.container(0, 0).setDepth(DEPTH.choice).setVisible(false);
  }

  private createCompleteCard(): void {
    const card = completeCardRect(DIALOGUE_STAGE);
    const frame = this.add.graphics();
    frame.fillStyle(0x0b1024, 0.95);
    frame.fillRoundedRect(card.x, card.y, card.width, card.height, CORNER);
    frame.lineStyle(2, CHIP_FILL, 0.85);
    frame.strokeRoundedRect(card.x, card.y, card.width, card.height, CORNER);
    this.completeTitle = this.add
      .text(card.x + card.width / 2, card.y + card.height / 2 - 26, "", {
        ...BODY_STYLE,
        fontSize: "38px",
      })
      .setOrigin(0.5, 0.5);
    const hint = this.add
      .text(
        card.x + card.width / 2,
        card.y + card.height / 2 + 34,
        "tap to play again",
        META_STYLE,
      )
      .setOrigin(0.5, 0.5);
    this.completeLayer = this.add
      .container(0, 0, [frame, this.completeTitle, hint])
      .setDepth(DEPTH.complete)
      .setVisible(false);
  }

  private act(action: Parameters<typeof reduceScenario>[2]): void {
    // Advancing off the end plays again rather than doing nothing. The reducer
    // is right to hold at the ending - that is what "finished" means - but a tap
    // that visibly does nothing reads as a broken scene, so the view decides
    // what the end card's one gesture is for.
    const intent =
      action.kind === "advance" && scenarioIsFinished(this.playback)
        ? ({ kind: "restart" } as const)
        : action;
    // Every advance is a user gesture, which is exactly what a browser wants
    // before it will start audio: the opening `play` lands on the first tap.
    this.audio.unlock();
    const next = reduceScenario(this.fixture.scenario, this.playback, intent);
    if (next === this.playback) return;
    this.playback = next;
    this.render();
  }

  /** Stop everything on teardown; the script has no say once the scene is gone. */
  stopAudio(): void {
    this.audio.stopAll();
  }

  private render(): void {
    const view = scenarioView(this.fixture.scenario, this.playback);
    this.audio.apply(this.playback.tracks);
    this.renderStage();
    this.renderCast(view?.kind === "line" ? view.speaker : null);

    const showingLine = view?.kind === "line";
    const showingChoice = view?.kind === "choice";
    // Exactly one of the three surfaces is on screen at a time; a panel repeating
    // the end card underneath it would say the same thing twice.
    this.panel.setVisible(showingLine);
    this.chip.setVisible(showingLine);
    this.speaker.setVisible(showingLine);
    this.body.setVisible(showingLine);
    this.progress.setVisible(showingLine);
    this.choiceLayer.setVisible(showingChoice);
    this.completeLayer.setVisible(view?.kind === "end");

    if (view?.kind === "end") {
      this.completeTitle.setText(view.label);
      this.choiceLayer.removeAll(true);
      return;
    }
    if (showingChoice) {
      this.renderChoices(view.options.map((option) => option.text));
      return;
    }
    this.choiceLayer.removeAll(true);
    if (!showingLine) return;
    this.body.setText(view.text);
    const progress = scenarioProgress(this.fixture.scenario, this.playback);
    this.progress.setText(`${progress.seen} / ${progress.total} · tap to continue`);
    this.renderSpeaker(view.speakerLabel ?? "");
  }

  private renderChoices(labels: readonly string[]): void {
    this.choiceLayer.removeAll(true);
    const rects = choiceRects(DIALOGUE_STAGE, labels.length);
    rects.forEach((rect, index) => {
      const box = this.add.graphics();
      box.fillStyle(index === 0 ? CHOICE_HOVER : CHOICE_FILL, 0.94);
      box.fillRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
      box.lineStyle(2, PANEL_STROKE, 0.8);
      box.strokeRoundedRect(rect.x, rect.y, rect.width, rect.height, CORNER);
      const label = this.add
        .text(rect.x + rect.width / 2, rect.y + rect.height / 2, labels[index] ?? "", {
          ...CHOICE_STYLE,
          wordWrap: { width: rect.width - 48 },
          align: "center",
        })
        .setOrigin(0.5, 0.5);
      this.choiceLayer.add([box, label]);
    });
  }

  private renderStage(): void {
    const stageId = this.playback.stage;
    if (stageId === null) return;
    const stage = dialogueSceneStage(this.fixture, stageId);
    // The fixture validator already refused a scenario that stages something it
    // has no backdrop for, so a miss here would be a contract violation rather
    // than a scene to paper over.
    if (stage === null) return;
    this.backdrop.setTexture(stageKey(stage.stageId));
  }

  private renderCast(speaker: string | null): void {
    // Everybody the scenario has on stage, each in the slot it put them in and
    // at the expression it last named. Whoever is speaking is drawn at full
    // colour in front; the rest are dimmed and pushed back, which is how a
    // player knows who is talking without reading the name chip.
    const framing = mapDialogueSceneFraming(this.fixture.presentation.framingZoom);
    const baseline = mapDialogueSceneFraming(this.fixture.presentation.sourceFramingZoom);
    const placement = {
      scale: normalizeDialogueSceneFramingScale(
        framing.presentation.scale,
        baseline.presentation.scale,
      ),
      xPercent: framing.presentation.position.xPercent,
      yPercent: framing.presentation.position.yPercent,
    };
    const staged = new Map(this.playback.actors.map((actor) => [actor.actorId, actor]));
    for (const [actorId, sprite] of this.cast) {
      const onStage = staged.get(actorId);
      if (onStage === undefined) {
        sprite.setVisible(false);
        continue;
      }
      const variant = dialogueSceneExpression(this.fixture, actorId, onStage.expression);
      if (variant === null) {
        sprite.setVisible(false);
        continue;
      }
      const key = plateKey(actorId, variant.state);
      const source = this.textures.get(key).getSourceImage();
      const frame = slotFrame(
        DIALOGUE_STAGE,
        { width: source.width || 1, height: source.height || 1 },
        placement,
        onStage.slot,
      );
      const speaking = speaker === actorId;
      sprite
        .setVisible(true)
        .setTexture(key)
        .setPosition(frame.x, frame.y)
        .setDisplaySize(frame.width, frame.height)
        .setDepth(DEPTH.sprite + (speaking ? 1 : 0))
        .setAlpha(speaking ? 1 : LISTENER_ALPHA);
      if (speaking) sprite.clearTint();
      else sprite.setTint(LISTENER_TINT);
    }
  }

  private renderSpeaker(label: string): void {
    this.speaker.setText(label);
    const chip: Rect = speakerChipRect(
      dialoguePanelRect(DIALOGUE_STAGE),
      this.speaker.width,
    );
    this.chip.clear();
    if (label === "") return;
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
  fixture: DialogueSceneFixture,
): DialogueSceneGameHandle {
  const scene = new DialogueScene(fixture);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    width: DIALOGUE_STAGE.width,
    height: DIALOGUE_STAGE.height,
    parent,
    backgroundColor: "#05070a",
    scene: [scene],
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  });
  return {
    destroy: (removeCanvas: boolean) => {
      // Phaser tears down its own canvas; the audio elements are ours, and a
      // track still playing after the player navigated away is the one bug
      // every web soundtrack has shipped at least once.
      scene.stopAudio();
      game.destroy(removeCanvas);
    },
  };
}
