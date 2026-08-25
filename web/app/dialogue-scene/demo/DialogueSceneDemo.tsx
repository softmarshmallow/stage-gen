"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN,
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
} from "@/lib/dialogue-scene/framing";
import {
  currentDialogueSceneBeat,
  currentDialogueSceneExpressionState,
  dialogueSceneActionForDocumentKey,
  dialogueSceneIsComplete,
  initialDialogueScenePlayback,
  reduceDialogueScenePlayback,
  type DialogueScenePlaybackAction,
} from "@/lib/dialogue-scene/playback";
import type {
  DialogueSceneDemoExpressionVariant,
  DialogueSceneDemoFixture,
  DialogueSceneExpressionState,
} from "@/lib/dialogue-scene/schema";

export default function DialogueSceneDemo({
  fixture,
}: {
  fixture: DialogueSceneDemoFixture;
}) {
  const [playback, setPlayback] = useState(initialDialogueScenePlayback);
  const [framingZoom, setFramingZoom] = useState(() =>
    Math.min(
      DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
      Math.max(DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN, fixture.presentation.framingZoom),
    ),
  );
  const [framingZoomDraft, setFramingZoomDraft] = useState(() =>
    formatFramingZoom(
      Math.min(
        DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
        Math.max(DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN, fixture.presentation.framingZoom),
      ),
    ),
  );
  const beatCount = fixture.dialogue.length;
  const beat = currentDialogueSceneBeat(fixture.dialogue, playback);
  const complete = dialogueSceneIsComplete(beatCount, playback);
  const expressionState = currentDialogueSceneExpressionState(
    fixture.dialogue,
    playback,
  );
  const expressionVariant = requireExpressionVariant(
    fixture.expressionVariants,
    expressionState,
  );
  const framing = useMemo(
    () => mapDialogueSceneFraming(framingZoom),
    [framingZoom],
  );
  const sourceBaselineFraming = useMemo(
    () => mapDialogueSceneFraming(fixture.presentation.sourceFramingZoom),
    [fixture.presentation.sourceFramingZoom],
  );
  const normalizedPresentationScale = normalizeDialogueSceneFramingScale(
    framing.presentation.scale,
    sourceBaselineFraming.presentation.scale,
  );
  const sourceLimited = framingZoom < fixture.presentation.sourceFramingZoom;
  const spriteStyle = {
    "--sg-dialogue-framing-scale": String(normalizedPresentationScale),
    "--sg-dialogue-framing-x": `${framing.presentation.position.xPercent}%`,
    "--sg-dialogue-framing-y": `${framing.presentation.position.yPercent}%`,
  } as CSSProperties;

  const act = useCallback(
    (action: DialogueScenePlaybackAction) => {
      setPlayback((current) => reduceDialogueScenePlayback(beatCount, current, action));
    },
    [beatCount],
  );

  const updateFramingZoom = useCallback((value: number) => {
    if (!Number.isFinite(value)) return;
    const bounded = Math.min(
      DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
      Math.max(DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN, value),
    );
    setFramingZoom(bounded);
    setFramingZoomDraft(formatFramingZoom(bounded));
  }, []);

  const framingZoomDraftValue = Number(framingZoomDraft);
  const framingZoomDraftValid =
    framingZoomDraft.trim() !== "" &&
    Number.isFinite(framingZoomDraftValue) &&
    framingZoomDraftValue >= DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN &&
    framingZoomDraftValue <= DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target =
        event.target instanceof Element ? event.target : document.activeElement;
      const action = dialogueSceneActionForDocumentKey(event.key, {
        defaultPrevented: event.defaultPrevented,
        modified: event.altKey || event.ctrlKey || event.metaKey,
        editableTarget:
          target !== null &&
          target.closest(
            'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
          ) !== null,
        activationTarget:
          target !== null && target.closest("button, a, summary") !== null,
      });
      if (action === null) return;

      event.preventDefault();
      act(action);
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [act]);

  const progressLabel = complete
    ? `Scene complete · ${beatCount} of ${beatCount}`
    : `${playback.cursor + 1} of ${beatCount}`;

  return (
    <main className="sg-dialogue-demo-page">
      <section className="sg-dialogue-game-shell" aria-label={fixture.title}>
        <header className="sg-dialogue-demo-header">
          <a className="sg-dialogue-demo-back" href="/" aria-label="Leave dialogue scene">
            ← Exit
          </a>
          <div className="sg-dialogue-game-title">
            <h1>{fixture.title}</h1>
            <p className="sg-dialogue-demo-scene-label">{fixture.sceneLabel}</p>
          </div>
          <span className="sg-dialogue-game-progress" aria-live="polite">
            {complete ? "Complete" : `${playback.cursor + 1} / ${beatCount}`}
          </span>
        </header>

        <section
          className="sg-dialogue-stage"
          aria-label={`Interactive dialogue scene. Current expression: ${expressionVariant.label.toLowerCase()}.`}
          data-expression-state={expressionState}
          data-source-framing-zoom={fixture.presentation.sourceFramingZoom}
        >
          {/* Plain images are intentional here: these are deterministic composition layers. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="sg-dialogue-background"
            src={fixture.background.src}
            alt={fixture.background.alt}
            draggable={false}
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="sg-dialogue-standing-sprite"
            src={expressionVariant.src}
            alt={expressionVariant.alt}
            draggable={false}
            style={spriteStyle}
          />

          <button
            className="sg-dialogue-stage-advance"
            type="button"
            onClick={() => act("next")}
            disabled={!playback.dialogueVisible || complete}
            aria-label={
              complete
                ? "Dialogue scene complete"
                : playback.dialogueVisible
                  ? "Advance to the next dialogue beat"
                  : "Dialogue is hidden; use the Show dialogue control"
            }
          />

          <div
            id="dialogue-scene-panel"
            className="sg-dialogue-panel"
            hidden={!playback.dialogueVisible}
            aria-live="polite"
            aria-atomic="true"
          >
            <div className="sg-dialogue-namebox">
              {complete ? "Scene complete" : beat?.speaker}
            </div>
            <p>
              {complete
                ? "The scene has ended. Restart to play again, or go back to revisit the ending."
                : beat?.text}
            </p>
            <span className="sg-dialogue-line-count" aria-hidden="true">
              {complete ? "Restart to play again" : `${progressLabel} · continue`}
            </span>
          </div>

          {!playback.dialogueVisible ? (
            <div className="sg-dialogue-asset-only" role="status">
              Dialogue hidden
            </div>
          ) : null}
        </section>

        <div className="sg-dialogue-controls" aria-label="Dialogue navigation" role="group">
          <button
            className="sg-btn"
            type="button"
            onClick={() => act("back")}
            disabled={playback.cursor === 0}
            aria-label="Previous dialogue beat"
          >
            ← Back
          </button>
          <span
            className="sg-dialogue-control-status"
            aria-live="polite"
            aria-atomic="true"
          >
            {progressLabel}
          </span>
          <DialogueSceneAdvanceButton complete={complete} onAction={act} />
          <button
            className="sg-btn sg-dialogue-visibility"
            type="button"
            onClick={() => act("toggle-dialogue")}
            aria-controls="dialogue-scene-panel"
            aria-pressed={!playback.dialogueVisible}
          >
            {playback.dialogueVisible ? "Hide dialogue" : "Show dialogue"}
          </button>
        </div>

        <p className="sg-dialogue-key-help">
          Enter / Space: advance · ← / →: navigate
        </p>

        <details className="sg-dialogue-framing">
          <summary>Display options</summary>
          <div className="sg-dialogue-framing-heading">
            <output
              className="sg-dialogue-framing-output"
              htmlFor="dialogue-scene-framing-range dialogue-scene-framing-number"
              aria-live="polite"
            >
              Character framing: {framing.cameraTerm} · {formatFramingZoom(framingZoom)}
              {sourceLimited ? " · limited by source" : ""}
            </output>
          </div>

          <div className="sg-dialogue-framing-inputs">
            <label htmlFor="dialogue-scene-framing-range">Character framing</label>
            <input
              id="dialogue-scene-framing-range"
              type="range"
              min={DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN}
              max={DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX}
              step={1}
              value={framingZoom}
              onChange={(event) => updateFramingZoom(event.currentTarget.valueAsNumber)}
            />
            <label htmlFor="dialogue-scene-framing-number">Framing value</label>
            <input
              id="dialogue-scene-framing-number"
              className="sg-input sg-dialogue-framing-number"
              type="number"
              inputMode="numeric"
              min={DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN}
              max={DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX}
              step={1}
              value={framingZoomDraft}
              aria-invalid={!framingZoomDraftValid}
              onChange={(event) => {
                const nextDraft = event.currentTarget.value;
                const nextValue = event.currentTarget.valueAsNumber;
                setFramingZoomDraft(nextDraft);
                if (
                  Number.isFinite(nextValue) &&
                  nextValue >= DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN &&
                  nextValue <= DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX
                ) {
                  setFramingZoom(nextValue);
                }
              }}
              onBlur={(event) => {
                const nextValue = event.currentTarget.valueAsNumber;
                updateFramingZoom(Number.isFinite(nextValue) ? nextValue : framingZoom);
              }}
            />
          </div>
        </details>
      </section>
    </main>
  );
}

export function DialogueSceneAdvanceButton({
  complete,
  onAction,
}: {
  readonly complete: boolean;
  readonly onAction: (
    action: Extract<DialogueScenePlaybackAction, "next" | "restart">,
  ) => void;
}) {
  const controlState = complete ? "restart" : "advance";
  return (
    <button
      className="sg-btn sg-dialogue-advance"
      type="button"
      data-control-state={controlState}
      onClick={() => onAction(complete ? "restart" : "next")}
      aria-label={complete ? "Restart dialogue from first beat" : "Next dialogue beat"}
    >
      {complete ? "↻ Restart" : "Next →"}
    </button>
  );
}

function requireExpressionVariant(
  variants: readonly DialogueSceneDemoExpressionVariant[],
  state: DialogueSceneExpressionState,
): DialogueSceneDemoExpressionVariant {
  const variant = variants.find((candidate) => candidate.state === state);
  if (variant === undefined) {
    throw new Error(`dialogue-scene fixture is missing expression state: ${state}`);
  }
  return variant;
}

function formatFramingZoom(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
