"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX,
  DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN,
  mapDialogueSceneFraming,
  normalizeDialogueSceneFramingScale,
} from "@/lib/dialogue-scene/framing";
import { scenarioActionForDocumentKey } from "@/lib/scenario/keys";
import {
  initialScenarioState,
  reduceScenario,
  scenarioIsFinished,
  scenarioProgress,
  scenarioView,
  type ScenarioAction,
  type ScenarioState,
} from "@/lib/scenario/runtime";
import {
  DIALOGUE_SCENE_EXPRESSION_STATES,
  type DialogueSceneDemoExpressionVariant,
  type DialogueSceneDemoFixture,
  type DialogueSceneExpressionState,
} from "@/lib/dialogue-scene/schema";
import { cx } from "@/app/ui";

// "Signal at Blue Hour" — a showcase theme for one demo route. It deliberately
// does not obey the terminal visual language the rest of the shell wears; its
// palette lives in `globals.css` under the `vn-` names.

/** Teal focus ring, everywhere something in this scene takes focus. */
const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-vn-teal " +
  "focus-visible:outline-offset-[3px]";

/** The glass pill every dialogue control wears. */
const CONTROL =
  "min-h-11 cursor-pointer rounded-full border border-vn-edge/24 bg-vn-glass/66 " +
  "px-4 py-[7px] text-vn-paper backdrop-blur-[10px] backdrop-saturate-[1.08] " +
  "enabled:hover:border-vn-rose enabled:hover:bg-vn-rose/12 " +
  "disabled:cursor-not-allowed disabled:border-white/12 disabled:text-[#667792] " +
  "max-[700px]:min-w-0 max-[700px]:flex-1 max-[700px]:px-2 max-[700px]:py-[5px] " +
  "max-[700px]:text-[11px]";

/** The one loud control in the scene: advance, or restart once it has ended. */
const ADVANCE =
  "enabled:border-vn-rose " +
  "enabled:bg-[linear-gradient(100deg,#f29abb,#f7bfd3_56%,#ffd69b)] " +
  "enabled:font-extrabold enabled:text-vn-ink " +
  "enabled:shadow-[0_8px_24px_rgba(203,112,166,0.24)] " +
  // Focused, it keeps its fill and gains a ring that reads on the night sky.
  "enabled:focus-visible:border-[#fff4f8] enabled:focus-visible:outline-[3px] " +
  "enabled:focus-visible:shadow-[0_0_0_2px_var(--color-vn-night),0_9px_28px_rgba(203,112,166,0.32)]";

/** Dim caption text used for status, help, and framing labels. */
const CAPTION = "text-xs text-vn-muted";

export default function DialogueSceneDemo({
  fixture,
}: {
  fixture: DialogueSceneDemoFixture;
}) {
  // A local undo stack, not the save/backlog substrate. This route is a framing
  // and expression preview, so stepping back one statement is a convenience it
  // owns; the real backlog is a cross-genre shell concern and is not this.
  const [history, setHistory] = useState<readonly ScenarioState[]>(() => [
    initialScenarioState(fixture.scenario),
  ]);
  const [dialogueVisible, setDialogueVisible] = useState(true);
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
  const playback = history[history.length - 1]!;
  const view = scenarioView(fixture.scenario, playback);
  const progress = scenarioProgress(fixture.scenario, playback);
  const beatCount = progress.total;
  const complete = scenarioIsFinished(playback);
  const staged = playback.actors[playback.actors.length - 1];
  // The scene has exactly four plates; a scenario that named a fifth was refused
  // when the fixture validated, so an unstaged actor is the only gap left and it
  // falls back to the neutral plate rather than showing an empty frame.
  const expressionState = asExpressionState(staged?.expression ?? null);
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
    (action: ScenarioAction) => {
      setHistory((current) => {
        const from = current[current.length - 1]!;
        const next = reduceScenario(fixture.scenario, from, action);
        if (next === from) return current;
        return action.kind === "restart" ? [next] : [...current, next];
      });
    },
    [fixture.scenario],
  );
  const stepBack = useCallback(() => {
    setHistory((current) => (current.length > 1 ? current.slice(0, -1) : current));
  }, []);

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
      const action = scenarioActionForDocumentKey(event.key, {
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
    : `${progress.seen} of ${beatCount}`;

  return (
    <main
      // The root layout paints the body to match, so an overscroll bounce
      // does not reveal the terminal ground under the night sky.
      data-vn-scene
      className={cx(
        "vn-sky relative grid min-h-dvh w-full place-items-center overflow-hidden",
        "p-[clamp(16px,3vw,38px)] font-vn-body text-vn-paper max-[700px]:p-2",
        // A sparse star field over the sky, behind everything else.
        "before:vn-stars before:pointer-events-none before:absolute before:inset-0",
        "before:opacity-55 before:content-['']",
        "[&>*]:relative [&>*]:z-[1]",
      )}
    >
      <section
        data-vn-game-shell
        className="w-[min(1120px,100%)] overflow-hidden rounded-3xl border border-vn-edge/24 bg-[rgba(4,12,31,0.82)] p-2.5 shadow-[0_30px_90px_rgba(0,2,14,0.58),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-[14px] backdrop-saturate-[1.08] max-[700px]:rounded-[17px] max-[700px]:p-1.5"
        aria-label={fixture.title}
      >
        <header className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-4 px-[5px] pt-[3px] pb-3 max-[700px]:gap-[7px] max-[700px]:px-0.5 max-[700px]:pt-0.5 max-[700px]:pb-[7px]">
          <a
            className={cx(
              "inline-flex min-h-10 items-center rounded-full border border-transparent",
              "px-[11px] py-[7px] text-xs tracking-[0.06em] text-vn-muted no-underline",
              "hover:border-vn-edge/24 hover:bg-white/[0.06] hover:text-vn-teal",
              "focus-visible:border-vn-edge/24 focus-visible:bg-white/[0.06]",
              "focus-visible:text-vn-teal",
              "max-[700px]:min-h-9 max-[700px]:px-[7px] max-[700px]:py-[5px]",
              "max-[700px]:text-[10px]",
              FOCUS,
            )}
            href="/"
            aria-label="Leave dialogue scene"
          >
            ← Exit
          </a>
          <div className="min-w-0 text-center">
            <h1 className="mb-0.5 truncate font-vn-display text-[clamp(20px,3vw,34px)] leading-[1.08] font-semibold tracking-[-0.025em] text-white [text-shadow:0_4px_24px_rgba(0,0,0,0.32),0_0_32px_rgba(242,154,187,0.1)] max-[700px]:text-[clamp(18px,6vw,26px)]">
              {fixture.title}
            </h1>
            <p className="truncate text-[11px] tracking-[0.04em] text-vn-muted max-[700px]:text-[9px]">
              {fixture.sceneLabel}
            </p>
          </div>
          <span
            className="min-w-[58px] text-right text-[11px] tracking-[0.08em] tabular-nums uppercase text-vn-muted max-[700px]:min-w-[44px] max-[700px]:text-[9px]"
            aria-live="polite"
          >
            {complete ? "Complete" : `${progress.seen} / ${beatCount}`}
          </span>
        </header>

        <section
          className="relative isolate aspect-[16/9] w-full overflow-hidden rounded-2xl border border-vn-edge/42 bg-vn-stage shadow-[0_24px_68px_rgba(0,4,18,0.48),0_0_0_1px_rgba(242,154,187,0.05)] max-[700px]:aspect-auto max-[700px]:h-[min(68dvh,128vw)] max-[700px]:min-h-[420px] max-[700px]:rounded-xl max-[400px]:min-h-[400px]"
          aria-label={`Interactive dialogue scene. Current expression: ${expressionVariant.label.toLowerCase()}.`}
          data-expression-state={expressionState}
          data-source-framing-zoom={fixture.presentation.sourceFramingZoom}
        >
          {/* Plain images are intentional here: these are deterministic composition layers. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="absolute inset-0 z-0 h-full w-full select-none object-cover saturate-[1.05] contrast-[1.02]"
            src={fixture.background.src}
            alt={fixture.background.alt}
            draggable={false}
          />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="absolute top-[var(--sg-dialogue-framing-y,6%)] left-[var(--sg-dialogue-framing-x,72%)] z-[1] h-[min(98%,820px)] w-auto max-w-[66%] origin-top -translate-x-1/2 scale-[var(--sg-dialogue-framing-scale,1)] select-none object-contain object-top drop-shadow-[0_18px_20px_rgba(0,8,24,0.35)] max-[700px]:h-[94%] max-[700px]:max-w-[110%]"
            src={expressionVariant.src}
            alt={expressionVariant.alt}
            draggable={false}
            style={spriteStyle}
          />

          <button
            className="absolute inset-0 z-[2] h-full w-full cursor-pointer border-0 bg-transparent p-0 enabled:hover:bg-white/[0.015] disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-vn-teal focus-visible:outline-offset-[-5px]"
            type="button"
            onClick={() => act({ kind: "advance" })}
            disabled={!dialogueVisible || complete || view?.kind === "choice"}
            aria-label={
              complete
                ? "Dialogue scene complete"
                : dialogueVisible
                  ? "Advance to the next dialogue beat"
                  : "Dialogue is hidden; use the Show dialogue control"
            }
          />

          {view?.kind === "choice" && dialogueVisible ? (
            <div
              className="absolute inset-x-[clamp(14px,3vw,36px)] top-1/2 z-[5] flex -translate-y-1/2 flex-col gap-3"
              role="group"
              aria-label="Choose what to say"
            >
              {view.options.map((option, index) => (
                <button
                  key={option.target + option.text}
                  type="button"
                  data-choice-option={index}
                  className="cursor-pointer rounded-2xl border border-vn-edge/70 bg-vn-panel/92 px-6 py-4 text-left text-[clamp(15px,1.7vw,19px)] text-vn-paper shadow-[0_12px_36px_rgba(0,3,18,0.42)] backdrop-blur-[10px] hover:bg-vn-panel focus-visible:outline-2 focus-visible:outline-vn-teal focus-visible:outline-offset-2"
                  onClick={() => act({ kind: "choose", option: index })}
                >
                  {option.text}
                </button>
              ))}
            </div>
          ) : null}

          <div
            id="dialogue-scene-panel"
            className="pointer-events-none absolute right-[clamp(14px,3vw,36px)] bottom-[clamp(14px,3vw,30px)] left-[clamp(14px,3vw,36px)] z-[4] min-h-[clamp(118px,16vw,158px)] rounded-2xl border border-vn-edge/68 bg-vn-panel/92 bg-[linear-gradient(125deg,rgba(13,29,63,0.97),rgba(43,29,68,0.92))] px-[clamp(18px,3vw,30px)] pt-[clamp(24px,3vw,32px)] pb-6 shadow-[0_18px_52px_rgba(0,3,18,0.46),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-[14px] backdrop-saturate-[1.12] after:absolute after:top-3 after:right-4 after:text-[15px] after:text-vn-rose/78 after:content-['✦'] max-[700px]:right-2 max-[700px]:bottom-2 max-[700px]:left-2 max-[700px]:min-h-[146px] max-[700px]:rounded-[13px] max-[700px]:px-3.5 max-[700px]:pt-[25px] max-[700px]:pb-6"
            hidden={!dialogueVisible || view?.kind === "choice"}
            aria-live="polite"
            aria-atomic="true"
          >
            <div className="absolute top-[-16px] left-5 min-w-[114px] rounded-full border border-white/70 bg-[linear-gradient(100deg,#f29abb,#f6bed2_52%,#ffd69b)] px-[15px] py-[5px] text-center font-extrabold text-vn-ink shadow-[0_7px_22px_rgba(203,112,166,0.24)]">
              {complete ? "Scene complete" : (view?.kind === "line" ? view.speakerLabel : null)}
            </div>
            <p className="max-w-[68ch] text-[clamp(16px,1.8vw,21px)] leading-[1.48] text-pretty text-vn-paper max-[700px]:text-[clamp(16px,4.4vw,19px)]">
              {complete
                ? `${view?.kind === "end" ? view.label : "The scene has ended"}. Restart to play again, or go back to revisit the ending.`
                : view?.kind === "line" ? view.text : null}
            </p>
            <span
              className="absolute right-[15px] bottom-2 text-[11px] text-vn-muted max-[700px]:text-[9px]"
              aria-hidden="true"
            >
              {complete ? "Restart to play again" : `${progressLabel} · continue`}
            </span>
          </div>

          {!dialogueVisible ? (
            <div
              className="absolute bottom-2.5 left-2.5 z-[3] rounded-full border border-white/25 bg-[rgba(7,21,46,0.82)] px-2 py-1 text-[11px] text-vn-muted"
              role="status"
            >
              Dialogue hidden
            </div>
          ) : null}
        </section>

        <div
          className="flex items-center gap-2 px-1.5 pt-2.5 pb-0.5 max-[700px]:flex-wrap max-[700px]:items-stretch max-[700px]:gap-[5px] max-[700px]:pt-[7px] max-[700px]:pb-0"
          aria-label="Dialogue navigation"
          role="group"
        >
          <button
            className={cx(CONTROL, FOCUS)}
            type="button"
            onClick={stepBack}
            disabled={history.length === 1}
            aria-label="Previous dialogue beat"
          >
            ← Back
          </button>
          <span
            className={cx(
              CAPTION,
              "min-w-[120px] text-center max-[700px]:order-first max-[700px]:w-full",
            )}
            aria-live="polite"
            aria-atomic="true"
          >
            {progressLabel}
          </span>
          <DialogueSceneAdvanceButton complete={complete} onAction={act} />
          <button
            className={cx(CONTROL, FOCUS, "ml-auto max-[700px]:ml-0 max-[700px]:basis-full")}
            type="button"
            onClick={() => setDialogueVisible((value) => !value)}
            aria-controls="dialogue-scene-panel"
            aria-pressed={!dialogueVisible}
          >
            {dialogueVisible ? "Hide dialogue" : "Show dialogue"}
          </button>
        </div>

        <p className="mt-1 mb-0.5 text-center text-[10px] tracking-[0.04em] text-vn-muted max-[700px]:text-[9px]">
          Enter / Space: advance · ← / →: navigate
        </p>

        <details className="mx-1 mt-1.5 mb-0.5 rounded-xl border border-vn-edge/24 bg-white/[0.035] backdrop-blur-[12px] backdrop-saturate-[1.06]">
          <summary
            className={cx(
              "cursor-pointer px-3 py-[9px] text-[11px] text-vn-muted",
              "open:border-b open:border-white/10 open:text-vn-paper",
              FOCUS,
            )}
          >
            Display options
          </summary>
          <div className="flex items-start justify-between gap-4 px-3 pt-2.5 max-[700px]:gap-2">
            <output
              className={cx(CAPTION, "flex flex-none flex-col items-start text-left")}
              htmlFor="dialogue-scene-framing-range dialogue-scene-framing-number"
              aria-live="polite"
            >
              Character framing: {framing.cameraTerm} · {formatFramingZoom(framingZoom)}
              {sourceLimited ? " · limited by source" : ""}
            </output>
          </div>

          <div className="grid grid-cols-[auto_minmax(180px,1fr)_auto_96px] items-center gap-x-3 gap-y-2 px-3 pt-2.5 pb-3 max-[700px]:grid-cols-[minmax(0,1fr)_112px] max-[700px]:gap-x-2 max-[700px]:gap-y-1.5">
            <label
              htmlFor="dialogue-scene-framing-range"
              className={cx(
                CAPTION,
                "max-[700px]:col-start-1 max-[700px]:row-start-1 max-[700px]:text-[10px]",
              )}
            >
              Character framing
            </label>
            <input
              id="dialogue-scene-framing-range"
              className={cx(
                "min-h-11 w-full accent-vn-rose",
                "max-[700px]:col-start-1 max-[700px]:row-start-2",
                FOCUS,
              )}
              type="range"
              min={DIALOGUE_SCENE_FRAMING_EVIDENCE_MIN}
              max={DIALOGUE_SCENE_FRAMING_EVIDENCE_MAX}
              step={1}
              value={framingZoom}
              onChange={(event) => updateFramingZoom(event.currentTarget.valueAsNumber)}
            />
            <label
              htmlFor="dialogue-scene-framing-number"
              className={cx(
                CAPTION,
                "max-[700px]:col-start-2 max-[700px]:row-start-1 max-[700px]:text-[10px]",
              )}
            >
              Framing value
            </label>
            <input
              id="dialogue-scene-framing-number"
              className={cx(
                "min-h-11 w-full rounded-[9px] border border-white/32 bg-white/[0.07]",
                "px-3 py-2 text-vn-paper caret-vn-paper outline-none",
                "focus:border-vn-teal",
                "max-[700px]:col-start-2 max-[700px]:row-start-2",
                FOCUS,
              )}
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
  readonly onAction: (action: ScenarioAction) => void;
}) {
  const controlState = complete ? "restart" : "advance";
  return (
    <button
      className={cx(CONTROL, ADVANCE, FOCUS)}
      type="button"
      data-primary="true"
      data-control-state={controlState}
      onClick={() => onAction(complete ? { kind: "restart" } : { kind: "advance" })}
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

function asExpressionState(
  value: string | null,
): DialogueSceneExpressionState {
  return DIALOGUE_SCENE_EXPRESSION_STATES.includes(value as DialogueSceneExpressionState)
    ? (value as DialogueSceneExpressionState)
    : "neutral";
}

function formatFramingZoom(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
