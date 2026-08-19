"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN,
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
  type DialogueSceneFramingPromptContext,
} from "@/lib/dialogue-scene/framing";
import {
  currentDialogueSceneBeat,
  currentDialogueSceneExpressionState,
  dialogueSceneActionForKey,
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
  const promptContext = useMemo<DialogueSceneFramingPromptContext>(
    () => ({
      identity: [
        `one original adult heroine, explicitly age ${fixture.appearance.age}`,
        fixture.appearance.visualIdentity,
        "same facial structure, adult age, body proportions, costume construction, and identity-defining accessories as the supplied reference",
      ],
      style: [
        fixture.appearance.artDirection,
        "same line treatment, palette, lighting direction, and material rendering as the supplied reference",
        "no photorealism or 3D-render styling",
      ],
      expression: expressionVariant.description,
      tierOverrides: {
        "full-body": {
          cropDirective:
            "the bottom edge of the final canvas must sit below both shoe soles while retaining a floor margin of 2%-6% of canvas height; the top of the hair, both hands, complete cardigan hem, both legs, and both shoes must remain inside the canvas",
          visibleAnatomy:
            "entire hair and head, neck, shoulders, torso, both arms and hands, cardigan hem, both legs, and both shoes",
        },
        "waist-up": {
          cropDirective:
            "the bottom edge of the final canvas must cross at the natural waist directly below the cardigan button line; hips, thighs, knees, lower legs, and shoes must remain outside the canvas",
          visibleAnatomy:
            "entire hair and head, neck, both shoulders, torso through the natural waist, and both upper arms",
        },
      },
    }),
    [fixture.appearance, expressionVariant.description],
  );
  const framing = useMemo(
    () => mapDialogueSceneFraming(framingZoom, promptContext),
    [framingZoom, promptContext],
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
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      const action = dialogueSceneActionForKey(event.key);
      if (action === null) return;

      const formControlTarget =
        event.target instanceof HTMLElement &&
        event.target.closest("input, textarea, select") !== null;
      if (formControlTarget) return;

      const activationTarget =
        event.target instanceof HTMLElement &&
        event.target.closest("button, a, summary") !== null;
      if (
        activationTarget &&
        (event.key === "Enter" || event.key === " " || event.key === "Spacebar")
      ) {
        return;
      }

      event.preventDefault();
      act(action);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [act]);

  const progressLabel = complete
    ? `Scene complete · ${beatCount} of ${beatCount}`
    : `Beat ${playback.cursor + 1} of ${beatCount}`;

  return (
    <main className="sg-dialogue-demo-page">
      <header className="sg-dialogue-demo-header">
        <div>
          <a className="sg-dialogue-demo-back" href="/">
            ← stage-gen / dialogue-scene
          </a>
          <p className="sg-dialogue-demo-eyebrow">
            Visual Novel Scene Kit · playable romance vignette
          </p>
          <h1>{fixture.title}</h1>
          <p className="sg-dialogue-demo-scene-label">{fixture.sceneLabel}</p>
        </div>
        <div
          className="sg-dialogue-demo-status"
          role="status"
          aria-label={`Tasteful 15 plus slow-burn romance; heroine ${fixture.appearance.label} is age ${fixture.appearance.age}`}
        >
          <strong>15+ slow-burn romance</strong>
          <span>heroine age {fixture.appearance.age} · adult cast</span>
          <small>deterministic fixture · no generation</small>
        </div>
      </header>

      <div className="sg-dialogue-hero-layout">
        <section
          className="sg-dialogue-stage"
          aria-label={`Visual Novel Scene Kit demo: ${fixture.sceneLabel}. ${fixture.appearance.label} is ${expressionVariant.label.toLowerCase()}.`}
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

          <div className="sg-dialogue-episode-mark" aria-hidden="true">
            <span>BLUE HOUR</span>
            <strong>01</strong>
          </div>
          <div className="sg-dialogue-expression-badge" aria-live="polite">
            <span>expression variant</span>
            <strong>{expressionVariant.label}</strong>
          </div>

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
                ? "The blue-hour signal is steady—for the array, and perhaps for the two of you. Use Back to revisit the final beat."
                : beat?.text}
            </p>
            <span className="sg-dialogue-line-count" aria-hidden="true">
              {progressLabel} · tap to continue
            </span>
          </div>

          {!playback.dialogueVisible ? (
            <div className="sg-dialogue-asset-only" role="status">
              dialogue hidden · asset-only composition
            </div>
          ) : null}
        </section>

        <aside className="sg-dialogue-profile" aria-labelledby="mio-profile-heading">
          <a
            className="sg-dialogue-profile-art"
            href={fixture.appearance.conceptSrc}
            aria-label={`Open ${fixture.appearance.label} concept key art`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={fixture.appearance.conceptSrc}
              alt={`${fixture.appearance.label} concept key art`}
              draggable={false}
            />
            <span>concept key art ↗</span>
          </a>
          <div className="sg-dialogue-profile-copy">
            <p className="sg-dialogue-profile-kicker">Heroine profile</p>
            <h2 id="mio-profile-heading">{fixture.appearance.label}</h2>
            <p className="sg-dialogue-profile-role">
              {fixture.appearance.age} · {fixture.appearance.role}
            </p>
            <p className="sg-dialogue-profile-tagline">“{fixture.appearance.tagline}”</p>
            <p className="sg-dialogue-profile-description">
              {fixture.appearance.description}
            </p>
          </div>
          <div className="sg-dialogue-expression-set">
            <div>
              <strong>Expression set</strong>
              <span>{fixture.expressionVariants.length.toString().padStart(2, "0")} states</span>
            </div>
            <ul aria-label="Mio expression variants">
              {fixture.expressionVariants.map((variant) => (
                <li
                  key={variant.state}
                  className={variant.state === expressionState ? "is-active" : undefined}
                  aria-current={variant.state === expressionState ? "true" : undefined}
                >
                  <span aria-hidden="true">{variant.state === expressionState ? "✦" : "·"}</span>
                  {variant.label}
                </li>
              ))}
            </ul>
            <p>Each dialogue beat selects one static variant—no rig or frame animation.</p>
          </div>
        </aside>
      </div>

      <div className="sg-dialogue-controls" aria-label="Dialogue controls" role="group">
        <button
          className="sg-btn"
          type="button"
          onClick={() => act("back")}
          disabled={playback.cursor === 0}
          aria-label="Previous dialogue beat"
        >
          ← Back
        </button>
        <span className="sg-dialogue-control-status" aria-live="polite" aria-atomic="true">
          {progressLabel}
        </span>
        <button
          className="sg-btn sg-dialogue-next"
          type="button"
          onClick={() => act("next")}
          disabled={complete}
          aria-label={complete ? "Dialogue scene complete" : "Next dialogue beat"}
        >
          Continue →
        </button>
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
        Click or tap the scene to continue. Keyboard: Enter, Space, or → advances; ←
        goes back.
      </p>

      <section
        className="sg-dialogue-framing"
        aria-labelledby="dialogue-scene-framing-heading"
      >
        <div className="sg-dialogue-framing-heading">
          <div>
            <p className="sg-dialogue-framing-kicker">Presentation control</p>
            <h2 id="dialogue-scene-framing-heading">Camera framing lab</h2>
            <p id="dialogue-scene-framing-guidance">
              Tested range 25–85. This upper-body source is authored at{" "}
              {fixture.presentation.sourceFramingZoom}; lower values make it smaller but
              cannot reveal unauthored anatomy.
            </p>
          </div>
          <output
            className="sg-dialogue-framing-output"
            htmlFor="dialogue-scene-framing-range dialogue-scene-framing-number"
            aria-live="polite"
          >
            <strong>{framing.cameraTerm}</strong>
            <span>
              framingZoom {formatFramingZoom(framingZoom)}/100
              {sourceLimited ? " · source-limited" : ""}
            </span>
          </output>
        </div>

        <div className="sg-dialogue-framing-inputs">
          <label htmlFor="dialogue-scene-framing-range">framingZoom slider</label>
          <input
            id="dialogue-scene-framing-range"
            type="range"
            min={DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN}
            max={DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX}
            step={1}
            value={framingZoom}
            aria-describedby="dialogue-scene-framing-guidance"
            onChange={(event) => updateFramingZoom(event.currentTarget.valueAsNumber)}
          />
          <label htmlFor="dialogue-scene-framing-number">framingZoom value</label>
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
            aria-describedby="dialogue-scene-framing-guidance"
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

        <details className="sg-dialogue-framing-prompt">
          <summary>Coarse-generation prompt for this state</summary>
          <p>
            The crop template is tested; Mio’s identity and active expression are supplied
            by the fixture. Deterministic presentation crop remains required.
          </p>
          <pre>{framing.prompt.text}</pre>
        </details>
      </section>

      <details className="sg-dialogue-assets">
        <summary>Deterministic fixture assets and roles</summary>
        <dl>
          <div>
            <dt>background</dt>
            <dd>
              <a href={fixture.background.src}>{fixture.background.id}</a>
            </dd>
          </div>
          <div>
            <dt>appearance identity</dt>
            <dd>
              <a href={fixture.appearance.conceptSrc}>{fixture.appearance.label}</a>
              <span>{fixture.appearance.visualIdentity}</span>
            </dd>
          </div>
          <div>
            <dt>expression variants</dt>
            <dd>
              {fixture.expressionVariants.map((variant) => (
                <a key={variant.id} href={variant.src}>
                  {variant.state} · {variant.id}
                </a>
              ))}
            </dd>
          </div>
        </dl>
      </details>
    </main>
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
