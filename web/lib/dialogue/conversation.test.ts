import { describe, expect, test } from "bun:test";
import {
  advanceConversationCursor,
  CONVERSATION_BEFORE_FIRST,
  conversationActionForKey,
  conversationBeatAt,
  conversationHasStarted,
  conversationIsFinished,
} from "./conversation";

const BEATS = ["greeting", "remark", "farewell"] as const;

describe("advanceConversationCursor", () => {
  test("walks every beat exactly once and then finishes", () => {
    let cursor: number = CONVERSATION_BEFORE_FIRST;
    const seen: string[] = [];
    for (let step = 0; step < 10; step += 1) {
      cursor = advanceConversationCursor(cursor, BEATS.length, "next");
      const beat = conversationBeatAt(BEATS, cursor);
      if (beat === null) break;
      seen.push(beat);
    }
    expect(seen).toEqual(["greeting", "remark", "farewell"]);
    expect(conversationIsFinished(cursor, BEATS.length)).toBe(true);
  });

  test("stays inside the conversation at both ends", () => {
    expect(advanceConversationCursor(3, 3, "next")).toBe(3);
    expect(advanceConversationCursor(CONVERSATION_BEFORE_FIRST, 3, "back")).toBe(-1);
    expect(advanceConversationCursor(0, 3, "back")).toBe(CONVERSATION_BEFORE_FIRST);
  });

  test("back from the end returns to the last beat rather than past it", () => {
    const cursor = advanceConversationCursor(3, 3, "back");
    expect(cursor).toBe(2);
    expect(conversationBeatAt(BEATS, cursor)).toBe("farewell");
  });

  test("a corrupted cursor is pulled back inside rather than trusted", () => {
    for (const cursor of [Number.NaN, Number.POSITIVE_INFINITY, 1.5, -99, 999]) {
      const next = advanceConversationCursor(cursor, 3, "next");
      expect(next).toBeGreaterThanOrEqual(CONVERSATION_BEFORE_FIRST);
      expect(next).toBeLessThanOrEqual(3);
    }
  });

  test("restart returns to before the first beat from anywhere", () => {
    for (const cursor of [CONVERSATION_BEFORE_FIRST, 0, 2, 3]) {
      expect(advanceConversationCursor(cursor, 3, "restart")).toBe(
        CONVERSATION_BEFORE_FIRST,
      );
    }
  });

  test("an empty conversation is refused rather than silently opening", () => {
    for (const beatCount of [0, -3, 1.5, Number.NaN]) {
      expect(() => advanceConversationCursor(0, beatCount, "next")).toThrow(
        "at least one beat",
      );
    }
  });
});

describe("readings", () => {
  test("no beat is on screen before the first or after the last", () => {
    expect(conversationBeatAt(BEATS, CONVERSATION_BEFORE_FIRST)).toBeNull();
    expect(conversationBeatAt(BEATS, 3)).toBeNull();
    expect(conversationBeatAt(BEATS, 1)).toBe("remark");
    expect(conversationBeatAt(BEATS, Number.NaN)).toBeNull();
  });

  test("an empty conversation is over before it starts", () => {
    expect(conversationIsFinished(CONVERSATION_BEFORE_FIRST, 0)).toBe(true);
  });

  test("started is distinct from finished", () => {
    expect(conversationHasStarted(CONVERSATION_BEFORE_FIRST)).toBe(false);
    expect(conversationHasStarted(0)).toBe(true);
    expect(conversationIsFinished(0, 3)).toBe(false);
    expect(conversationIsFinished(3, 3)).toBe(true);
  });
});

describe("conversationActionForKey", () => {
  test("both genres advance and step back on the same keys", () => {
    expect(conversationActionForKey("ArrowRight")).toBe("next");
    expect(conversationActionForKey("Enter")).toBe("next");
    expect(conversationActionForKey(" ")).toBe("next");
    expect(conversationActionForKey("Spacebar")).toBe("next");
    expect(conversationActionForKey("ArrowLeft")).toBe("back");
    expect(conversationActionForKey("Escape")).toBeNull();
    expect(conversationActionForKey("a")).toBeNull();
  });
});
