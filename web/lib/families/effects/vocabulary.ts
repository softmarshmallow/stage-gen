// The `effects` family: the authored operation vocabulary, and the dispatch.
//
// Three vocabularies exist in the repository and two of them are runtime code:
// the platformer's `set_quest_state` / `grant_item`, tagged by an `operation`
// field, and the room's `set_flag` / `grant_item` / `remove_item` /
// `reveal_hotspot`, which is one object with four optional fields and no tag at
// all. They share `grant_item` by name and not by type — one carries a quantity
// and the other is a unit grant — which is exactly why the family cannot be a
// union of the two shapes and has to be a *lowering* plus a dispatch.
//
// What the family owns:
//
//   - the vocabulary as data: which operations a genre answers for, sealed
//     against the handlers it supplies, so an operation nobody implements is a
//     refusal at boot rather than a silently skipped effect at the one moment
//     it fires;
//   - the dispatch, which is the loop `applyOutcome` had inline;
//   - resolving an authored effect id against the authored table, and saying
//     when one does not resolve.
//
// What it does not own: what any operation *means*. An effect mutates other
// families' slices through their own APIs — `grant_item` goes to the bag, a
// flag goes to the room's flag set — so every handler below is the consumer's,
// and the family never touches a slice.

/** One operation the vocabulary answers for, with the payload it carries. */
export interface LoweredEffect<Payload> {
  readonly operation: string;
  readonly payload: Payload;
}

export type EffectHandler<Payload> = (payload: Payload) => void;

/** A vocabulary that has been checked against the handlers meant to answer it. */
export interface SealedEffectVocabulary<Payload> {
  readonly operations: readonly string[];
  readonly handlers: Readonly<Record<string, EffectHandler<Payload>>>;
}

/**
 * Check a vocabulary against its handlers, once, at boot.
 *
 * Both directions are refused, and both are real. An operation the genre
 * declares and does not implement is an authored name that would do nothing at
 * the moment it fired — the failure mode a dispatch that just skips unknown
 * names has. A handler for an operation the vocabulary does not declare is dead
 * code that reads as coverage.
 */
export function sealEffectVocabulary<Payload>(
  operations: readonly string[],
  handlers: Readonly<Record<string, EffectHandler<Payload>>>,
): SealedEffectVocabulary<Payload> {
  for (const operation of operations) {
    if (!(operation in handlers)) {
      throw new Error(`effect operation "${operation}" is declared with no handler`);
    }
  }
  for (const name of Object.keys(handlers)) {
    if (!operations.includes(name)) {
      throw new Error(`effect handler "${name}" answers an operation nothing declares`);
    }
  }
  return Object.freeze({ operations: Object.freeze([...operations]), handlers });
}

/**
 * Perform lowered operations in order, reporting what was performed.
 *
 * Order is the caller's and it is load-bearing: an authored outcome that grants
 * an item and then completes a quest that counts it is a different outcome from
 * the same two the other way round.
 */
export function applyEffects<Payload>(
  vocabulary: SealedEffectVocabulary<Payload>,
  lowered: Iterable<LoweredEffect<Payload>>,
): readonly string[] {
  const applied: string[] = [];
  for (const entry of lowered) {
    const handler = vocabulary.handlers[entry.operation];
    if (!handler) continue;
    handler(entry.payload);
    applied.push(entry.operation);
  }
  return applied;
}

/** An authored effect, as every genre's table stores one: a name and a body. */
export interface AuthoredEffect {
  readonly effect_id: string;
}

/**
 * Resolve authored effect ids against the table, in the order they were named.
 *
 * An id that does not resolve is skipped rather than refused, which is what
 * both consumers did and is right for the same reason: closure is the package
 * validator's job, and a runtime that threw here would turn a producer's
 * mistake into a crash in the middle of a conversation.
 */
export function resolveEffects<E extends AuthoredEffect>(
  table: readonly E[],
  effectIds: readonly string[],
): readonly E[] {
  const resolved: E[] = [];
  for (const effectId of effectIds) {
    const effect = table.find((entry) => entry.effect_id === effectId);
    if (effect) resolved.push(effect);
  }
  return resolved;
}
