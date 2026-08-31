// The visual novel's spelling of the shared conversation machine.
//
// The cursor arithmetic is `lib/dialogue/conversation` — the same machine the
// platformer's village dialogue box walks. What is the scene's own is how it
// presents the ends (a terminal end card rather than closing a panel), the
// dialogue-visibility toggle, and the rule for which document-level key
// presses should reach a conversation at all.

import {
  advanceConversationCursor,
  conversationActionForKey,
  conversationBeatAt,
  conversationIsFinished,
} from "@/lib/dialogue/conversation";
import type {
  DialogueSceneDemoBeat,
  DialogueSceneExpressionState,
} from "./schema";

export interface DialogueScenePlaybackState {
  readonly cursor: number;
  readonly dialogueVisible: boolean;
}

export type DialogueScenePlaybackAction =
  | "next"
  | "back"
  | "restart"
  | "toggle-dialogue";

export interface DialogueSceneDocumentKeyContext {
  readonly defaultPrevented: boolean;
  readonly modified: boolean;
  readonly editableTarget: boolean;
  readonly activationTarget: boolean;
}

export function initialDialogueScenePlayback(): DialogueScenePlaybackState {
  // A scene opens on its first beat rather than before it: unlike the village
  // panel, which is opened by walking up to somebody, the scene *is* the page.
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
  if (action === "toggle-dialogue") {
    return Object.freeze({ ...state, dialogueVisible: !state.dialogueVisible });
  }
  if (action === "restart") return initialDialogueScenePlayback();
  // The shared core admits a "before the first beat" cursor that a scene has no
  // way to render, so stepping back off the opening beat holds instead.
  const cursor = Math.max(advanceConversationCursor(state.cursor, beatCount, action), 0);
  return cursor === state.cursor ? state : Object.freeze({ ...state, cursor });
}

export function dialogueSceneActionForKey(
  key: string,
): Extract<DialogueScenePlaybackAction, "next" | "back"> | null {
  return conversationActionForKey(key);
}

export function dialogueSceneActionForDocumentKey(
  key: string,
  context: DialogueSceneDocumentKeyContext,
): Extract<DialogueScenePlaybackAction, "next" | "back"> | null {
  if (context.defaultPrevented || context.modified || context.editableTarget) return null;
  const action = dialogueSceneActionForKey(key);
  if (action === null) return null;
  if (
    context.activationTarget &&
    (key === "Enter" || key === " " || key === "Spacebar")
  ) {
    return null;
  }
  return action;
}

export function currentDialogueSceneBeat(
  dialogue: readonly DialogueSceneDemoBeat[],
  state: DialogueScenePlaybackState,
): DialogueSceneDemoBeat | null {
  return conversationBeatAt(dialogue, state.cursor);
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
  return conversationIsFinished(state.cursor, beatCount);
}

function assertBeatCount(beatCount: number): void {
  if (!Number.isInteger(beatCount) || beatCount < 1) {
    throw new Error("dialogue-scene playback requires at least one beat");
  }
}
