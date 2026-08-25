import { describe, expect, test } from "bun:test";
import { dialogueSceneDemoFixture } from "./demo-fixture";
import {
  currentDialogueSceneBeat,
  currentDialogueSceneExpressionState,
  dialogueSceneActionForDocumentKey,
  dialogueSceneActionForKey,
  dialogueSceneIsComplete,
  initialDialogueScenePlayback,
  reduceDialogueScenePlayback,
} from "./playback";

describe("dialogue-scene deterministic playback", () => {
  test("moves forward and back while retaining a stable completed state", () => {
    const count = dialogueSceneDemoFixture.dialogue.length;
    let state = initialDialogueScenePlayback();
    expect(currentDialogueSceneBeat(dialogueSceneDemoFixture.dialogue, state)?.id).toBe(
      "late-arrival",
    );
    expect(
      currentDialogueSceneExpressionState(dialogueSceneDemoFixture.dialogue, state),
    ).toBe("neutral");

    state = reduceDialogueScenePlayback(count, state, "next");
    state = reduceDialogueScenePlayback(count, state, "next");
    expect(
      currentDialogueSceneExpressionState(dialogueSceneDemoFixture.dialogue, state),
    ).toBe("delighted");

    for (let index = state.cursor; index < count; index += 1) {
      state = reduceDialogueScenePlayback(count, state, "next");
    }
    expect(dialogueSceneIsComplete(count, state)).toBeTrue();
    expect(currentDialogueSceneBeat(dialogueSceneDemoFixture.dialogue, state)).toBeNull();

    const completed = state;
    state = reduceDialogueScenePlayback(count, state, "next");
    expect(state).toBe(completed);

    state = reduceDialogueScenePlayback(count, state, "back");
    expect(state.cursor).toBe(count - 1);
    expect(currentDialogueSceneBeat(dialogueSceneDemoFixture.dialogue, state)?.id).toBe(
      "beside-me",
    );
    expect(
      currentDialogueSceneExpressionState(dialogueSceneDemoFixture.dialogue, completed),
    ).toBe("delighted");

    state = reduceDialogueScenePlayback(count, completed, "restart");
    expect(state).toEqual(initialDialogueScenePlayback());
    expect(currentDialogueSceneBeat(dialogueSceneDemoFixture.dialogue, state)?.id).toBe(
      "late-arrival",
    );
  });

  test("toggles the asset-only composition without changing the current line", () => {
    const count = dialogueSceneDemoFixture.dialogue.length;
    const lineTwo = reduceDialogueScenePlayback(count, initialDialogueScenePlayback(), "next");
    const hidden = reduceDialogueScenePlayback(count, lineTwo, "toggle-dialogue");
    expect(hidden).toEqual({ cursor: 1, dialogueVisible: false });
    expect(reduceDialogueScenePlayback(count, hidden, "toggle-dialogue")).toEqual(lineTwo);
  });

  test("resolves every dialogue beat to its declared static expression variant", () => {
    const expectedStates = [
      "neutral",
      "neutral",
      "delighted",
      "flustered",
      "flustered",
      "concerned",
      "concerned",
      "delighted",
    ] as const;
    let state = initialDialogueScenePlayback();

    for (const expected of expectedStates) {
      expect(
        currentDialogueSceneExpressionState(dialogueSceneDemoFixture.dialogue, state),
      ).toBe(expected);
      state = reduceDialogueScenePlayback(
        dialogueSceneDemoFixture.dialogue.length,
        state,
        "next",
      );
    }

    expect(
      currentDialogueSceneExpressionState(dialogueSceneDemoFixture.dialogue, state),
    ).toBe("delighted");
  });

  test("binds playback states to the expected static sprite URL", () => {
    const expectedSpriteByState = {
      neutral: "/dialogue-scene/demo/anime/heroine-neutral.png",
      delighted: "/dialogue-scene/demo/anime/heroine-delighted.png",
      flustered: "/dialogue-scene/demo/anime/heroine-flustered.png",
      concerned: "/dialogue-scene/demo/anime/heroine-concerned.png",
    } as const;
    let state = initialDialogueScenePlayback();

    for (const beat of dialogueSceneDemoFixture.dialogue) {
      const expressionState = currentDialogueSceneExpressionState(
        dialogueSceneDemoFixture.dialogue,
        state,
      );
      const variant = dialogueSceneDemoFixture.expressionVariants.find(
        (candidate) => candidate.state === expressionState,
      );

      expect(variant?.src).toBe(expectedSpriteByState[beat.expressionState]);
      state = reduceDialogueScenePlayback(
        dialogueSceneDemoFixture.dialogue.length,
        state,
        "next",
      );
    }
  });

  test("maps the documented keyboard controls to the same linear actions", () => {
    expect(dialogueSceneActionForKey("Enter")).toBe("next");
    expect(dialogueSceneActionForKey(" ")).toBe("next");
    expect(dialogueSceneActionForKey("Spacebar")).toBe("next");
    expect(dialogueSceneActionForKey("ArrowRight")).toBe("next");
    expect(dialogueSceneActionForKey("ArrowLeft")).toBe("back");
    expect(dialogueSceneActionForKey("Escape")).toBeNull();
  });

  test("advances from neutral document focus without duplicating native controls", () => {
    const neutralFocus = {
      defaultPrevented: false,
      modified: false,
      editableTarget: false,
      activationTarget: false,
    } as const;
    expect(dialogueSceneActionForDocumentKey("Enter", neutralFocus)).toBe("next");
    expect(dialogueSceneActionForDocumentKey(" ", neutralFocus)).toBe("next");

    const focusedButton = { ...neutralFocus, activationTarget: true };
    expect(dialogueSceneActionForDocumentKey("Enter", focusedButton)).toBeNull();
    expect(dialogueSceneActionForDocumentKey(" ", focusedButton)).toBeNull();
    expect(dialogueSceneActionForDocumentKey("ArrowRight", focusedButton)).toBe("next");

    expect(
      dialogueSceneActionForDocumentKey("Enter", {
        ...neutralFocus,
        editableTarget: true,
      }),
    ).toBeNull();
  });
});
