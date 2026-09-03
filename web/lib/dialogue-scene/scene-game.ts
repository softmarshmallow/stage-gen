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
  choiceRects,
  completeCardControlRect,
  completeCardRect,
  DIALOGUE_STAGE,
  dialoguePanelRect,
  emphasizedFrame,
  slotFrame,
  visualNovelBoxLayout,
  type VisualNovelBoxLayout,
} from "./scene-hud";
import { actorEmphasis, narrationEmphasis } from "./emphasis";
import { AtlasButton } from "@/lib/ui-atlas/button";
import { UI_ATLAS_SHEETS, uiAtlasSheetKey } from "@/lib/ui-atlas/sheets";
import { NineSliceWidget } from "@/lib/ui-atlas/widget";
import { mostReadable } from "@/lib/ui-atlas/contrast";
import { registerPresentationFallback } from "@/lib/ui-atlas/fallback";
import type { Rect } from "@/lib/shell/hud-geometry";
import { applyDeviceZoom, currentDevicePixelScale, deviceGameSize } from "@/lib/device-pixels/device-camera";
import {
  dialogueSceneExpression,
  dialogueSceneStage,
  type DialogueSceneFixture,
} from "./schema";
import { scenarioActionForKey, scenarioOptionForKey } from "@/lib/scenario/keys";
import {
  initialScenarioState,
  reduceScenario,
  restoreScenarioState,
  scenarioIsFinished,
  scenarioProgress,
  scenarioStatementId,
  scenarioView,
  type ScenarioState,
} from "@/lib/scenario/runtime";

function stageKey(stageId: string): string {
  return `vn:stage:${stageId}`;
}

function plateKey(actorId: string, state: string): string {
  return `vn:actor:${actorId}:${state}`;
}

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

/**
 * The first of `candidates` that is readable on the widget's drawn interior.
 *
 * Null when the sheet cannot be sampled, which is the caller's signal to keep the authored
 * colour: a stand-in texture or an unloaded sheet is not a reason to repaint the HUD.
 */
function readableOnPanel(widget: NineSliceWidget, candidates: readonly string[]): string | null {
  const background = widget.interiorColor();
  return background === null ? null : mostReadable(background, candidates);
}

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

/** What the scene reports to whatever is hosting it, once per drawn moment. */
export interface DialogueSceneMoment {
  readonly state: ScenarioState;
  /** `<label>#<index>` of what is on screen, or null at the ending card. */
  readonly statementId: string | null;
  /** The line being spoken, for a backlog; null for a choice or an ending. */
  readonly line: { readonly speaker: string | null; readonly text: string } | null;
  readonly outcome: string | null;
}

/**
 * How a host drives one scene.
 *
 * The scene stays the whole game inside its canvas. These are the two seams a
 * shell around it genuinely needs: where to start, and what just happened. A
 * host that supplies `onFinish` also takes over what the ending card's one
 * gesture means - in a case it is "on to the next beat", not "play it again".
 */
export interface DialogueSceneOptions {
  readonly resume?: ScenarioState | null;
  /** Facts an earlier beat set, seeded into the flags this scenario declares. */
  readonly carriedFlags?: readonly string[];
  readonly onMoment?: (moment: DialogueSceneMoment) => void;
  readonly onFinish?: (outcome: string, flags: readonly string[]) => void;
}

class DialogueScene extends Phaser.Scene {
  private playback: ScenarioState;
  private readonly audio: ScenarioAudio;

  private backdrop!: Phaser.GameObjects.Image;
  /** One sprite per drawable actor, shown or hidden as the scenario stages them. */
  private readonly cast = new Map<string, Phaser.GameObjects.Image>();
  private panel!: NineSliceWidget;
  private box!: VisualNovelBoxLayout;
  private speaker!: Phaser.GameObjects.Text;
  private body!: Phaser.GameObjects.Text;
  private progress!: Phaser.GameObjects.Text;
  /** Body colour measured on the drawn panel; see `readableOnPanel`. */
  private inkOnPanel: string = PAPER;
  private choiceLayer!: Phaser.GameObjects.Container;
  private completeLayer!: Phaser.GameObjects.Container;
  private completeTitle!: Phaser.GameObjects.Text;
  private completeControl!: AtlasButton;

  constructor(
    private readonly fixture: DialogueSceneFixture,
    private readonly options: DialogueSceneOptions = {},
  ) {
    super("dialogue-scene");
    const resumed =
      options.resume == null ? null : restoreScenarioState(fixture.scenario, options.resume);
    this.playback =
      resumed ?? initialScenarioState(fixture.scenario, options.carriedFlags ?? []);
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
    // The interface is generated art like the cast and the rooms. The sheets are published
    // with a canonical alpha boundary, so the plain loader is enough; one that does not
    // arrive is replaced in `create` by the loud stand-in under the same key.
    this.load.image(uiAtlasSheetKey("panel_frame"), this.fixture.ui.panelFrame.src);
    this.load.image(uiAtlasSheetKey("button_rect"), this.fixture.ui.buttonRect.src);
    this.load.image(uiAtlasSheetKey("preview_icons"), this.fixture.ui.previewIcons.src);
  }

  create(): void {
    // The comment in `preload` promised a stand-in for an interface sheet that
    // does not arrive, and the room scene has always registered one; the scene
    // did not, so a run published without one of the three sheets drew Phaser's
    // own missing-texture green instead of saying what was wrong. A missing
    // image must not remove the mechanic that would have used it.
    for (const [, key, kind] of UI_ATLAS_SHEETS) {
      if (!this.textures.exists(key)) registerPresentationFallback(this.textures, key, kind);
    }
    // The canvas is device-pixel sized; zoom the camera back to the stage it is written in.
    applyDeviceZoom(this.cameras.main, DIALOGUE_STAGE);
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
      // A choice is up: the buttons own the pointer now, so a tap that missed them all
      // must not advance the scene past the decision it was asking for.
      if (view?.kind === "choice") return;
      void pointer;
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
    this.panel = new NineSliceWidget({
      scene: this,
      sheetKey: uiAtlasSheetKey("panel_frame"),
      layout: this.fixture.ui.panelFrame.layout,
      width: panel.width,
      height: panel.height,
      x: panel.x + panel.width / 2,
      y: panel.y + panel.height / 2,
      depth: DEPTH.panel,
    });

    // Where the words go is measured on the drawn frame, not guessed: the producer publishes
    // the ornament-free interior and the layout turns it into a name row, a wrapped body, and
    // a bottom-right progress anchor.
    this.box = visualNovelBoxLayout(this.panel.safeRect());
    // The panel is generated art, so the text colour is measured on it rather than fixed. The
    // authored pairing is paper on a dark plate; on a light one it inverts, which is the whole
    // reason this exists — a cream plate swallowed the body text entirely while the speaker
    // name, which happened to be ink, stayed readable.
    this.inkOnPanel = readableOnPanel(this.panel, [PAPER, INK]) ?? PAPER;
    const meta = readableOnPanel(this.panel, [DIM, INK, PAPER]) ?? DIM;

    this.speaker = this.add
      .text(this.box.name.x, this.box.name.y, "", {
        ...SPEAKER_STYLE,
        color: readableOnPanel(this.panel, [INK, PAPER]) ?? INK,
      })
      .setOrigin(0, 0)
      .setDepth(DEPTH.panel + 2);

    this.body = this.add
      .text(this.box.body.x, this.box.body.y, "", {
        ...BODY_STYLE,
        color: this.inkOnPanel,
        wordWrap: { width: this.box.bodyWrapWidth },
      })
      .setDepth(DEPTH.panel + 1);

    this.progress = this.add
      .text(this.box.progress.x, this.box.progress.y, "", { ...META_STYLE, color: meta })
      .setOrigin(1, 1)
      .setDepth(DEPTH.panel + 1);
  }

  private createChoiceLayer(): void {
    this.choiceLayer = this.add.container(0, 0).setDepth(DEPTH.choice).setVisible(false);
  }

  private readonly choiceButtons: AtlasButton[] = [];

  /** Park the pool: hidden and not answering a pointer, but never destroyed. */
  private hideChoices(): void {
    for (const button of this.choiceButtons) {
      button.setVisible(false);
      button.setLive(false);
    }
  }

  private createCompleteCard(): void {
    const card = completeCardRect(DIALOGUE_STAGE);
    const frame = new NineSliceWidget({
      scene: this,
      sheetKey: uiAtlasSheetKey("panel_frame"),
      layout: this.fixture.ui.panelFrame.layout,
      width: card.width,
      height: card.height,
      x: card.x + card.width / 2,
      y: card.y + card.height / 2,
      depth: DEPTH.complete,
    });
    this.completeTitle = this.add
      .text(card.x + card.width / 2, card.y + card.height / 2 - 26, "", {
        ...BODY_STYLE,
        color: readableOnPanel(frame, [PAPER, INK]) ?? BODY_STYLE.color,
        fontSize: "38px",
      })
      .setOrigin(0.5, 0.5);
    // The way back is a control rather than a hint: an icon-only button carrying the
    // `retry` glyph from the preview icon set, on the same sheet the choices are cut from.
    // A tap anywhere still plays again, exactly as before; the button says so visibly.
    this.completeControl = new AtlasButton({
      scene: this,
      sheetKey: uiAtlasSheetKey("button_rect"),
      layout: this.fixture.ui.buttonRect.layout,
      rect: completeCardControlRect(card),
      depth: DEPTH.complete,
      label: "",
      icon: {
        sheetKey: uiAtlasSheetKey("preview_icons"),
        layout: this.fixture.ui.previewIcons.layout,
        glyph: "retry",
      },
      onPress: () => this.act({ kind: "advance" }),
    });
    this.completeControl.setLive(false);
    this.completeLayer = this.add
      .container(0, 0, [frame.image, this.completeTitle, ...this.completeControl.parts])
      .setDepth(DEPTH.complete)
      .setVisible(false);
  }

  private act(action: Parameters<typeof reduceScenario>[2]): void {
    // Advancing off the end plays again rather than doing nothing. The reducer
    // is right to hold at the ending - that is what "finished" means - but a tap
    // that visibly does nothing reads as a broken scene, so the view decides
    // what the end card's one gesture is for. Inside a case that gesture belongs
    // to the host: the next beat, not this one over again.
    if (action.kind === "advance" && scenarioIsFinished(this.playback)) {
      const outcome = this.playback.outcome;
      if (this.options.onFinish !== undefined && outcome !== null) {
        this.audio.stopAll();
        this.options.onFinish(outcome, this.playback.flags);
        return;
      }
    }
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
    this.report(view);
    this.audio.apply(this.playback.tracks);
    this.renderStage();
    this.renderCast(view?.kind === "line" ? view.speaker : null);

    const showingLine = view?.kind === "line";
    const showingChoice = view?.kind === "choice";
    // Exactly one of the three surfaces is on screen at a time; a panel repeating
    // the end card underneath it would say the same thing twice.
    this.panel.image.setVisible(showingLine);
    this.speaker.setVisible(showingLine);
    this.body.setVisible(showingLine);
    this.progress.setVisible(showingLine);
    this.choiceLayer.setVisible(showingChoice);
    this.completeLayer.setVisible(view?.kind === "end");
    this.completeControl.setLive(view?.kind === "end");

    if (view?.kind === "end") {
      this.completeTitle.setText(view.label);
      this.hideChoices();
      return;
    }
    if (showingChoice) {
      this.renderChoices(view.options.map((option) => option.text));
      return;
    }
    this.hideChoices();
    if (!showingLine) return;
    this.body.setText(view.text);
    const progress = scenarioProgress(this.fixture.scenario, this.playback);
    this.progress.setText(`${progress.seen} / ${progress.total} · tap to continue`);
    this.renderSpeaker(view.speakerLabel ?? "");
  }

  /**
   * Draw the current choice as a pool of generated buttons.
   *
   * The options used to be rebuilt from scratch on every render, with the first one painted
   * in a highlight colour that never moved: a hover look that no pointer could reach. They
   * are buttons now, so hovering and pressing show the producer's own art for those states,
   * and the pool is reused rather than destroyed, because destroying the object that is
   * dispatching the press that caused the render is how a menu becomes unclickable.
   */
  private renderChoices(labels: readonly string[]): void {
    const rects = choiceRects(DIALOGUE_STAGE, labels.length);
    while (this.choiceButtons.length < rects.length) {
      const index = this.choiceButtons.length;
      const button = new AtlasButton({
        scene: this,
        sheetKey: uiAtlasSheetKey("button_rect"),
        layout: this.fixture.ui.buttonRect.layout,
        rect: rects[index]!,
        depth: DEPTH.choice,
        label: "",
        style: { ...CHOICE_STYLE, align: "center" },
        onPress: () => this.act({ kind: "choose", option: index }),
      });
      // A choice sits on the button sheet, not the panel, so it is measured on its own art.
      const choiceInk = readableOnPanel(button.widget, [PAPER, INK]);
      if (choiceInk !== null) button.text.setColor(choiceInk);
      this.choiceButtons.push(button);
      this.choiceLayer.add([...button.parts]);
    }
    this.choiceButtons.forEach((button, index) => {
      const rect = rects[index];
      const shown = rect !== undefined;
      button.setVisible(shown);
      button.setLive(shown);
      if (!shown || rect === undefined) return;
      button.setRect(rect);
      button.setLabel(labels[index] ?? "");
      button.text.setStyle({ wordWrap: { width: Math.max(1, rect.width - 48) } });
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
    // colour, a little larger, and in front; the rest recede without leaving,
    // which is how a player knows who is talking without reading the name plate.
    // The numbers are `emphasis.ts`, so the rule is unit-tested rather than
    // buried in a draw call.
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
      const emphasis =
        speaker === null
          ? narrationEmphasis(onStage.slot)
          : actorEmphasis(onStage.slot, speaker === actorId);
      const drawn = emphasizedFrame(frame, emphasis.scale);
      sprite
        .setVisible(true)
        .setTexture(key)
        .setPosition(drawn.x, drawn.y)
        .setDisplaySize(drawn.width, drawn.height)
        .setDepth(DEPTH.sprite + emphasis.stackOrder)
        .setAlpha(emphasis.alpha);
      if (emphasis.tint === null) sprite.clearTint();
      else sprite.setTint(emphasis.tint);
    }
  }

  /**
   * Tell the host what is on screen, exactly once per drawn moment.
   *
   * Reported from `render` rather than from `act` so a resumed scene announces
   * its first moment too: a host that only heard about transitions would have
   * nothing to autosave until the player pressed something.
   */
  private report(view: ReturnType<typeof scenarioView>): void {
    if (this.options.onMoment === undefined) return;
    this.options.onMoment({
      state: this.playback,
      statementId:
        this.playback.outcome === null
          ? scenarioStatementId(this.playback.label, this.playback.index)
          : null,
      line:
        view?.kind === "line"
          ? { speaker: view.speakerLabel, text: view.text }
          : null,
      outcome: this.playback.outcome,
    });
  }

  private renderSpeaker(label: string): void {
    // The name sits on the panel's own safe interior rather than on a pill straddling its
    // top edge: the frame is drawn art now, and a plate laid across its border would cover
    // the ornament the producer was asked to keep in the corners.
    this.speaker.setText(label).setVisible(label !== "");
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
  options: DialogueSceneOptions = {},
): DialogueSceneGameHandle {
  const scene = new DialogueScene(fixture, options);
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    ...deviceGameSize(DIALOGUE_STAGE, currentDevicePixelScale()),
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
