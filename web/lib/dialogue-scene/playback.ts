import type {
  DialogueSceneDemoBeat,
  DialogueSceneExpressionState,
} from "./schema";

export interface DialogueScenePlaybackState {
  readonly cursor: number;
  readonly dialogueVisible: boolean;
}

export type DialogueScenePlaybackAction = "next" | "back" | "toggle-dialogue";

export function initialDialogueScenePlayback(): DialogueScenePlaybackState {
  return Object.freeze({ cursor: 0, dialogueVisible: true });
}

export function reduceDialogueScenePlayback(
  beatCount: number,
  state: DialogueScenePlaybackState,
  action: DialogueScenePlaybackAction,
): DialogueScenePlaybackState {
  assertBeatCount(beatCount);
  if (!Number.isInteger(state.cursor) || state.cursor < 0 || state.cursor > beatCount) {
    throw new Error("dialogue-scene playback cursor is outside the fixture");
  }
  if (action === "next") {
    if (state.cursor === beatCount) return state;
    return Object.freeze({ ...state, cursor: state.cursor + 1 });
  }
  if (action === "back") {
    if (state.cursor === 0) return state;
    return Object.freeze({ ...state, cursor: state.cursor - 1 });
  }
  return Object.freeze({ ...state, dialogueVisible: !state.dialogueVisible });
}

export function dialogueSceneActionForKey(
  key: string,
): Extract<DialogueScenePlaybackAction, "next" | "back"> | null {
  if (key === "ArrowLeft") return "back";
  if (key === "ArrowRight" || key === "Enter" || key === " " || key === "Spacebar") {
    return "next";
  }
  return null;
}

export function currentDialogueSceneBeat(
  dialogue: readonly DialogueSceneDemoBeat[],
  state: DialogueScenePlaybackState,
): DialogueSceneDemoBeat | null {
  return dialogue[state.cursor] ?? null;
}

export function currentDialogueSceneExpressionState(
  dialogue: readonly DialogueSceneDemoBeat[],
  state: DialogueScenePlaybackState,
): DialogueSceneExpressionState {
  if (dialogue.length < 1) {
    throw new Error("dialogue-scene expression state requires at least one beat");
  }
  const activeBeat = currentDialogueSceneBeat(dialogue, state);
  return (activeBeat ?? dialogue[dialogue.length - 1]).expressionState;
}

export function dialogueSceneIsComplete(
  beatCount: number,
  state: DialogueScenePlaybackState,
): boolean {
  assertBeatCount(beatCount);
  return state.cursor === beatCount;
}

function assertBeatCount(beatCount: number): void {
  if (!Number.isInteger(beatCount) || beatCount < 1) {
    throw new Error("dialogue-scene playback requires at least one beat");
  }
}
