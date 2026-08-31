// The agnostic conversation core: an ordered run of beats and a cursor over it.
//
// Two genres in this repository play conversations, and until now each owned a
// copy of the same small state machine with its own sentinels: the platformer's
// village dialogue box stepped a cursor and returned `null` to close, while the
// visual novel reduced `{cursor}` and rendered an end card at the terminal
// value. Same machine, two spellings, two places for the off-by-one at the last
// line to hide. This module is the one machine; each genre keeps only its own
// presentation of the ends.
//
// Nothing here knows about Phaser, a manifest, a bundle, an expression, or a
// portrait. A beat is whatever the caller's beat is - the core only orders them
// and says which one is showing. That is deliberate: when gameplay features
// become node-driven, the node that runs a conversation needs exactly this and
// nothing about how it is drawn.

/** The cursor before a conversation has shown anything. */
export const CONVERSATION_BEFORE_FIRST = -1;

export type ConversationAction = "next" | "back" | "restart";

/**
 * Where the cursor lands after one action, always inside the conversation.
 *
 * Total by construction: every cursor, including the pre-open sentinel and
 * values that could only arrive from a corrupted caller, maps into
 * `[-1, beatCount]`. Totality is the point — the alternative is a conversation
 * stuck on its last line, refusing to close, with the player's input still
 * gated behind it.
 *
 * The range has three regions, and both genres use all of them:
 *   `-1`              nothing shown yet
 *   `0 .. n-1`        that beat is on screen
 *   `n`               the conversation is over
 */
export function advanceConversationCursor(
  cursor: number,
  beatCount: number,
  action: ConversationAction,
): number {
  if (!Number.isSafeInteger(beatCount) || beatCount <= 0) {
    throw new Error("a conversation requires at least one beat");
  }
  if (action === "restart") return CONVERSATION_BEFORE_FIRST;
  const from = Number.isSafeInteger(cursor)
    ? Math.min(Math.max(cursor, CONVERSATION_BEFORE_FIRST), beatCount)
    : CONVERSATION_BEFORE_FIRST;
  if (action === "back") return Math.max(from - 1, CONVERSATION_BEFORE_FIRST);
  return Math.min(from + 1, beatCount);
}

/** The beat on screen at this cursor, or null before the first and after the last. */
export function conversationBeatAt<BeatT>(
  beats: readonly BeatT[],
  cursor: number,
): BeatT | null {
  if (!Number.isSafeInteger(cursor) || cursor < 0) return null;
  return beats[cursor] ?? null;
}

export function conversationIsFinished(cursor: number, beatCount: number): boolean {
  if (!Number.isSafeInteger(beatCount) || beatCount <= 0) return true;
  return Number.isSafeInteger(cursor) && cursor >= beatCount;
}

export function conversationHasStarted(cursor: number): boolean {
  return Number.isSafeInteger(cursor) && cursor > CONVERSATION_BEFORE_FIRST;
}

/**
 * The action a bare key press means, or null for a key this core does not own.
 *
 * Both genres advance on the same keys; whether a given press should reach the
 * conversation at all is the consumer's decision, because only it knows what
 * else is focused.
 */
export function conversationActionForKey(
  key: string,
): Extract<ConversationAction, "next" | "back"> | null {
  if (key === "ArrowLeft") return "back";
  if (key === "ArrowRight" || key === "Enter" || key === " " || key === "Spacebar") {
    return "next";
  }
  return null;
}
