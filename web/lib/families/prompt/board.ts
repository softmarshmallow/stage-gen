// The `prompt` family: what the game is offering the player right now.
//
// Three copies existed, plus a fourth in a class nothing constructed. The
// platformer's scene decided which villager could be talked to and then set a
// `Text`'s visibility itself; the portal system decided which door could be
// entered and then positioned and showed a `Text` of its own; the dead `Npc`
// class carried a third `talkPrompt` with the same show-and-hide written again.
// None of the three could say *what* was on offer without being asked to draw
// it, and the two live ones had no way of noticing that they were both offering
// at once.
//
// A prompt is not part of `interaction`, and the portal is the reason. "UP to
// enter" has nothing to do with a conversation: it is an affordance the space
// offers, answered by a map entry. What the two have in common is the shape —
// an owner, a kind, a line of text and a place in the world to float it — and
// that shape is what this family owns. Whether the prompt is a `Text`, a sheet
// widget or nothing at all is the view's.

export interface PromptAnchor {
  readonly x: number;
  readonly y: number;
}

export interface Prompt {
  /** Who is offering. One owner offers at most one prompt at a time. */
  readonly ownerId: string;
  /** What kind of affordance this is — `talk`, `enter`. The genre's vocabulary. */
  readonly kind: string;
  readonly text: string;
  /** Where in the world it floats. Screen-fixed prompts anchor at a screen point. */
  readonly anchor: PromptAnchor;
}

/** What changed for one owner this frame. */
export type PromptEdge = "offered" | "moved" | "withdrawn" | "unchanged";

export interface PromptView {
  /** Draw, or redraw, one owner's prompt. Called on `offered` and on `moved`. */
  show(prompt: Prompt): void;
  /** Stop drawing one owner's prompt. */
  hide(ownerId: string): void;
}

/** A board with nothing drawing it: a headless boot, and every test that is not about the view. */
export const NO_PROMPT_VIEW: PromptView = Object.freeze({
  show: () => undefined,
  hide: () => undefined,
});

function sameOffer(left: Prompt, right: Prompt): boolean {
  return (
    left.kind === right.kind &&
    left.text === right.text &&
    left.anchor.x === right.anchor.x &&
    left.anchor.y === right.anchor.y
  );
}

/**
 * What is on offer, and the edges as it changes.
 *
 * A registry rather than a frame step, deliberately. The two systems that offer
 * prompts are already ordered by the roster for other reasons — one draws after
 * the player has moved, the other inside the controller's own update — and
 * inserting a settle step between them would buy an ordering constraint for
 * nothing. Writing through to the view on the edge gives the same result: the
 * view is only touched when the answer changes, which is what the three copies
 * did by hand and got right by accident.
 */
export class PromptBoard {
  private readonly showing = new Map<string, Prompt>();

  constructor(private readonly view: PromptView = NO_PROMPT_VIEW) {}

  /** Offer `prompt` for its owner, or withdraw that owner's prompt with null. */
  set(ownerId: string, prompt: Prompt | null): PromptEdge {
    const current = this.showing.get(ownerId);
    if (prompt === null) {
      if (current === undefined) return "unchanged";
      this.showing.delete(ownerId);
      this.view.hide(ownerId);
      return "withdrawn";
    }
    if (prompt.ownerId !== ownerId) {
      throw new Error(
        `prompt owner "${prompt.ownerId}" was offered under the name "${ownerId}"`,
      );
    }
    if (current === undefined) {
      this.showing.set(ownerId, prompt);
      this.view.show(prompt);
      return "offered";
    }
    if (sameOffer(current, prompt)) return "unchanged";
    this.showing.set(ownerId, prompt);
    this.view.show(prompt);
    return "moved";
  }

  /** Whether this owner is offering anything. */
  offering(ownerId: string): boolean {
    return this.showing.has(ownerId);
  }

  /** Everything on offer, in the order it was first offered. */
  offered(): readonly Prompt[] {
    return [...this.showing.values()];
  }

  /**
   * Withdraw everything, without telling the view.
   *
   * For a world being torn down, where the objects the view was drawing into
   * are about to be destroyed. A board that kept its answers across a rebuild
   * would decline to re-offer a prompt whose owner id happened to appear on the
   * next map too, and the new prompt would never be drawn.
   */
  clear(): void {
    this.showing.clear();
  }
}
