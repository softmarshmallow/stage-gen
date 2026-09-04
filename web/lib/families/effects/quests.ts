// The `effects` family's second slice: quest state.
//
// A quest is not a separate machine. It is two authored effect ids — one that
// starts it, one that completes it — plus a condition the runtime evaluates:
// carry this many of this item while the quest is running. The state itself is
// a name per quest, and the *vocabulary* of names is the genre's, because
// "active" and "completed" are words a package publishes rather than states a
// runtime knows about.

/** What a quest declares: how it starts, and what finishes it. */
export interface QuestSpec {
  readonly quest_id: string;
  readonly completion_item_id: string;
  readonly completion_count: number;
  readonly completion_effect_id: string;
}

/** Which quests are in which state, and nothing else. */
export class QuestLedger {
  private readonly states = new Map<string, string>();

  /** The state of one quest, or null while it has never been started. */
  stateOf(questId: string): string | null {
    return this.states.get(questId) ?? null;
  }

  set(questId: string, state: string): void {
    this.states.set(questId, state);
  }

  /** Every quest with a state, sorted, which is the shape a digest or a readout wants. */
  entries(): readonly (readonly [string, string])[] {
    return [...this.states.entries()].sort(([left], [right]) => (left < right ? -1 : 1));
  }

  clear(): void {
    this.states.clear();
  }
}

/**
 * Which quests the bag has just satisfied.
 *
 * Called with the item that changed and how many of it are now carried, so the
 * check is over the one stack that moved rather than a sweep of the whole bag
 * on every grant. `activeState` is the genre's word for "running": the family
 * compares names and never learns what they mean.
 */
export function questsCompletedBy(
  quests: readonly QuestSpec[],
  ledger: QuestLedger,
  itemId: string,
  carriedCount: number,
  activeState: string,
): readonly QuestSpec[] {
  const completed: QuestSpec[] = [];
  for (const quest of quests) {
    if (quest.completion_item_id !== itemId) continue;
    if (ledger.stateOf(quest.quest_id) !== activeState) continue;
    if (carriedCount < quest.completion_count) continue;
    completed.push(quest);
  }
  return completed;
}

/**
 * Refuse a quest that cannot finish, at boot rather than at the moment it would.
 *
 * A quest completes by changing its own state; that is what a completion *is*.
 * The platformer used to enforce this by filtering at the one call site — it
 * resolved `completion_effect_id` and then performed it only if the operation
 * happened to be the state change — so a package that authored a grant there
 * validated clean, shipped, and silently never completed the quest. Naming it
 * here is what lets the dispatch be uniform: every authored effect id does what
 * it declares, everywhere, because the ones that could not have been reached
 * this way are refused before the first frame.
 */
export function sealQuestCompletions<E extends { readonly effect_id: string; readonly operation: string }>(
  quests: readonly QuestSpec[],
  effects: readonly E[],
  stateOperation: string,
): void {
  for (const quest of quests) {
    const effect = effects.find((entry) => entry.effect_id === quest.completion_effect_id);
    if (effect === undefined) continue;
    if (effect.operation === stateOperation) continue;
    throw new Error(
      `quest "${quest.quest_id}" completes with effect "${effect.effect_id}", whose operation is ` +
        `"${effect.operation}"; a completion must be a "${stateOperation}"`,
    );
  }
}
