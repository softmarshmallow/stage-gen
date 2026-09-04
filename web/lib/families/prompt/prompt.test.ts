import { describe, expect, test } from "bun:test";
import { NO_PROMPT_VIEW, PromptBoard, type Prompt, type PromptView } from "./board";
import { parsePromptBlock } from "./manifest";

function recorder(): { view: PromptView; calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    view: {
      show: (prompt) => calls.push(`show ${prompt.ownerId} ${prompt.text} @${prompt.anchor.x}`),
      hide: (ownerId) => calls.push(`hide ${ownerId}`),
    },
  };
}

const talk = (ownerId: string, x: number): Prompt => ({
  ownerId,
  kind: "talk",
  text: "▲ Talk",
  anchor: { x, y: 0 },
});

// --- E4: the three copies, as two shapes -------------------------------------------------------

describe("E4: the prompt board instantiated into two shapes", () => {
  test("a talk-shaped board: many owners, at most one offering, anchored where they stand", () => {
    const { view, calls } = recorder();
    const board = new PromptBoard(view);
    const villagers = ["baker", "smith", "child"];
    const offerTo = (nearest: string | null) => {
      for (const npcId of villagers) {
        board.set(npcId, npcId === nearest ? talk(npcId, 100) : null);
      }
    };
    offerTo("baker");
    offerTo("baker");
    offerTo("smith");
    offerTo(null);
    // The view is touched only when the answer changes, which is what the three
    // hand-written copies did by accident and this does by construction.
    expect(calls).toEqual([
      "show baker ▲ Talk @100",
      "hide baker",
      "show smith ▲ Talk @100",
      "hide smith",
    ]);
    expect(board.offered()).toEqual([]);
  });

  test("an enter-shaped board: one owner, and moving between doors is a move, not a flicker", () => {
    const { view, calls } = recorder();
    const board = new PromptBoard(view);
    const door = (x: number): Prompt => ({
      ownerId: "portal/enter",
      kind: "enter",
      text: "UP to enter",
      anchor: { x, y: 0 },
    });
    expect(board.set("portal/enter", door(400))).toBe("offered");
    expect(board.set("portal/enter", door(400))).toBe("unchanged");
    // A different door under the same owner repositions rather than hiding and
    // showing, which is what stops the prompt blinking off for a frame as the
    // player steps from one arch into the next.
    expect(board.set("portal/enter", door(900))).toBe("moved");
    expect(board.set("portal/enter", null)).toBe("withdrawn");
    expect(board.set("portal/enter", null)).toBe("unchanged");
    expect(calls).toEqual([
      "show portal/enter UP to enter @400",
      "show portal/enter UP to enter @900",
      "hide portal/enter",
    ]);
  });

  test("two owners can be offering at once, which is a thing the copies could not notice", () => {
    const board = new PromptBoard(NO_PROMPT_VIEW);
    board.set("baker", talk("baker", 100));
    board.set("portal/enter", {
      ownerId: "portal/enter",
      kind: "enter",
      text: "UP to enter",
      anchor: { x: 400, y: 0 },
    });
    expect(board.offered().map((prompt) => prompt.kind)).toEqual(["talk", "enter"]);
    expect(board.offering("baker")).toBe(true);
    expect(board.offering("smith")).toBe(false);
  });
});

describe("the board's own rules", () => {
  test("an offer filed under someone else's name is refused", () => {
    const board = new PromptBoard();
    expect(() => board.set("smith", talk("baker", 100))).toThrow(
      'prompt owner "baker" was offered under the name "smith"',
    );
  });

  test("a torn-down world clears without telling a view whose objects are gone", () => {
    const { view, calls } = recorder();
    const board = new PromptBoard(view);
    board.set("baker", talk("baker", 100));
    board.clear();
    expect(calls).toEqual(["show baker ▲ Talk @100"]);
    // And the next world's villager of the same name is offered again rather
    // than being taken for one that is already showing.
    expect(board.set("baker", talk("baker", 700))).toBe("offered");
  });

  test("E7: a board with nothing drawing it still answers what is on offer", () => {
    const board = new PromptBoard();
    board.set("baker", talk("baker", 100));
    expect(board.offered().map((prompt) => prompt.ownerId)).toEqual(["baker"]);
  });
});

describe("the block the family gates for itself", () => {
  test("whether a prompt can be offered at all is authored, and the gate names it", () => {
    expect(() =>
      parsePromptBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
