import { describe, expect, test } from "bun:test";
import {
  applyEffects,
  resolveEffects,
  sealEffectVocabulary,
  type LoweredEffect,
} from "./vocabulary";
import { QuestLedger, questsCompletedBy, sealQuestCompletions, type QuestSpec } from "./quests";
import { parseEffectsBlock } from "./manifest";

// --- E4: one dispatch, two vocabularies that share a name and not a type ---------------------

type PlatformerEffect =
  | Readonly<{ effect_id: string; operation: "set_quest_state"; quest_id: string; state: string }>
  | Readonly<{ effect_id: string; operation: "grant_item"; item_id: string; quantity: number }>;

describe("E4: the effects family instantiated into two vocabularies", () => {
  test("a platformer-shaped vocabulary: a tagged operation carrying the whole record", () => {
    const bag: string[] = [];
    const quests = new QuestLedger();
    const vocabulary = sealEffectVocabulary<PlatformerEffect>(["set_quest_state", "grant_item"], {
      grant_item: (effect) => {
        if (effect.operation !== "grant_item") return;
        bag.push(`${effect.item_id}x${effect.quantity}`);
      },
      set_quest_state: (effect) => {
        if (effect.operation !== "set_quest_state") return;
        quests.set(effect.quest_id, effect.state);
      },
    });
    const table: readonly PlatformerEffect[] = [
      { effect_id: "start", operation: "set_quest_state", quest_id: "errand", state: "active" },
      { effect_id: "tart", operation: "grant_item", item_id: "welcome_tart", quantity: 2 },
    ];
    const applied = applyEffects(
      vocabulary,
      resolveEffects(table, ["tart", "start"]).map((effect) => ({
        operation: effect.operation,
        payload: effect,
      })),
    );
    // Order is the caller's, and it is the order the outcome named them in.
    expect(applied).toEqual(["grant_item", "set_quest_state"]);
    expect(bag).toEqual(["welcome_tartx2"]);
    expect(quests.entries()).toEqual([["errand", "active"]]);
  });

  test("a room-shaped vocabulary: four untagged fields lowered in field order", () => {
    const log: string[] = [];
    const vocabulary = sealEffectVocabulary<string>(
      ["set_flag", "grant_item", "remove_item", "reveal_hotspot"],
      {
        set_flag: (name) => log.push(`flag:${name}`),
        // The same name and a different type: here a grant is a unit and
        // carries no quantity at all.
        grant_item: (name) => log.push(`grant:${name}`),
        remove_item: (name) => log.push(`remove:${name}`),
        reveal_hotspot: (name) => log.push(`reveal:${name}`),
      },
    );
    // One authored object carrying three operations at once, which is the shape
    // the platformer's table cannot express and the reason the family is
    // reached through a lowering rather than by renaming a field.
    const lowered: readonly LoweredEffect<string>[] = [
      { operation: "set_flag", payload: "chest_open" },
      { operation: "grant_item", payload: "brass_key" },
      { operation: "reveal_hotspot", payload: "keyhole" },
    ];
    expect(applyEffects(vocabulary, lowered)).toEqual([
      "set_flag",
      "grant_item",
      "reveal_hotspot",
    ]);
    expect(log).toEqual(["flag:chest_open", "grant:brass_key", "reveal:keyhole"]);
  });
});

// --- E3: the refusals the seal buys ------------------------------------------------------------

describe("E3: refusals", () => {
  test("an operation a package may name and nothing implements is refused at boot", () => {
    expect(() =>
      sealEffectVocabulary<string>(["set_flag", "grant_ability"], {
        set_flag: () => undefined,
      }),
    ).toThrow('effect operation "grant_ability" is declared with no handler');
  });

  test("and a handler nothing declares is dead code that reads as coverage", () => {
    expect(() =>
      sealEffectVocabulary<string>(["set_flag"], {
        set_flag: () => undefined,
        reveal_hotspot: () => undefined,
      }),
    ).toThrow('effect handler "reveal_hotspot" answers an operation nothing declares');
  });

  test("a quest that could never finish is refused before the first frame", () => {
    const quests: readonly QuestSpec[] = [
      {
        quest_id: "errand",
        completion_item_id: "gold_coin",
        completion_count: 3,
        completion_effect_id: "pay_up",
      },
    ];
    expect(() =>
      sealQuestCompletions(
        quests,
        [{ effect_id: "pay_up", operation: "grant_item" }],
        "set_quest_state",
      ),
    ).toThrow(
      'quest "errand" completes with effect "pay_up", whose operation is "grant_item"; a completion must be a "set_quest_state"',
    );
    // And the shape every shipped package authors passes.
    expect(() =>
      sealQuestCompletions(
        quests,
        [{ effect_id: "pay_up", operation: "set_quest_state" }],
        "set_quest_state",
      ),
    ).not.toThrow();
  });

  test("an effect id that does not resolve is skipped, because closure is the validator's job", () => {
    expect(resolveEffects([{ effect_id: "a" }], ["a", "missing", "a"])).toEqual([
      { effect_id: "a" },
      { effect_id: "a" },
    ]);
  });
});

// --- the quest ledger ---------------------------------------------------------------------------

describe("quest state", () => {
  const quests: readonly QuestSpec[] = [
    {
      quest_id: "errand",
      completion_item_id: "gold_coin",
      completion_count: 3,
      completion_effect_id: "finish",
    },
    {
      quest_id: "other",
      completion_item_id: "gold_coin",
      completion_count: 1,
      completion_effect_id: "finish_other",
    },
  ];

  test("a quest that has not started cannot be completed by carrying the item", () => {
    const ledger = new QuestLedger();
    expect(questsCompletedBy(quests, ledger, "gold_coin", 99, "active")).toEqual([]);
  });

  test("a running quest completes at its count and not before", () => {
    const ledger = new QuestLedger();
    ledger.set("errand", "active");
    expect(questsCompletedBy(quests, ledger, "gold_coin", 2, "active")).toEqual([]);
    expect(questsCompletedBy(quests, ledger, "gold_coin", 3, "active").map((q) => q.quest_id)).toEqual([
      "errand",
    ]);
    // A different item never satisfies it, however much of it is carried.
    expect(questsCompletedBy(quests, ledger, "welcome_tart", 99, "active")).toEqual([]);
  });

  test("the state vocabulary is the genre's; the family compares names", () => {
    const ledger = new QuestLedger();
    ledger.set("errand", "en_cours");
    expect(questsCompletedBy(quests, ledger, "gold_coin", 3, "en_cours").length).toBe(1);
    expect(questsCompletedBy(quests, ledger, "gold_coin", 3, "active").length).toBe(0);
  });

  test("the ledger reads back sorted, which is what a digest wants", () => {
    const ledger = new QuestLedger();
    ledger.set("zed", "completed");
    ledger.set("errand", "active");
    expect(ledger.entries()).toEqual([
      ["errand", "active"],
      ["zed", "completed"],
    ]);
    expect(ledger.stateOf("nothing")).toBe(null);
    ledger.clear();
    expect(ledger.entries()).toEqual([]);
  });
});

// --- the block, and the refusal ---------------------------------------------------------------

describe("the block the family gates for itself", () => {
  test("a moved vocabulary is refused by name", () => {
    expect(() =>
      parseEffectsBlock(
        { gameplay: "platformer-gameplay-block-v2" },
        { block: "gameplay", version: "platformer-gameplay-block-v1" },
      ),
    ).toThrow('manifest block "gameplay" is published as platformer-gameplay-block-v2');
  });
});
