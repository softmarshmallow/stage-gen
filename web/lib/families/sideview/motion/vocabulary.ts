// Which semantic states a genre's actors can be in, and which of them a
// package owes.
//
// The vocabulary is a **parameter**, which is the whole ruling. The runner's
// avatar has six states and the platformer's player has ten; the jumper's
// closed set in the plan's own table is three (`rise`, `fall`, `death`). None
// of those is more correct than the others and none of them belongs in a shared
// file as a union — what belongs here is the *shape*: a closed ordered set,
// some of whose members are owed by every package and the rest of which are
// answers a package may decline to give.
//
// The refusal this buys is the one the plan names. A package whose motion set
// lacks a state the genre requires is refused **at parse**, by name, rather
// than reaching a controller that quietly draws something else — because a
// controller that decides what to do from what artwork arrived has let
// availability write a rule, and availability may only ever choose a
// presentation.

export interface MotionVocabularyInput {
  /** The closed set, in the order the genre publishes it. */
  readonly states: readonly string[];
  /** The subset every package owes. */
  readonly required: readonly string[];
  /** The subset drawn as a sustained cycle rather than a one-shot. */
  readonly looping?: readonly string[];
}

export interface MotionVocabulary {
  readonly states: readonly string[];
  readonly required: readonly string[];
  readonly looping: readonly string[];
  has(state: string): boolean;
  isRequired(state: string): boolean;
  isLooping(state: string): boolean;
}

/**
 * Close a vocabulary, refusing one that contradicts itself.
 *
 * A duplicated state, a required state that is not in the set, and a looping
 * state that is not in the set are all the same defect — a vocabulary that
 * names something it does not contain — and all three are refused here rather
 * than discovered as a missing strip at draw time.
 */
export function sealMotionVocabulary(input: MotionVocabularyInput): MotionVocabulary {
  const states = Object.freeze([...input.states]);
  const set = new Set(states);
  if (states.length === 0) throw new Error("a motion vocabulary must name at least one state");
  if (set.size !== states.length) {
    throw new Error("a motion vocabulary must not name a state twice");
  }
  for (const state of input.required) {
    if (!set.has(state)) {
      throw new Error(`motion vocabulary requires ${state}, which it does not contain`);
    }
  }
  for (const state of input.looping ?? []) {
    if (!set.has(state)) {
      throw new Error(`motion vocabulary loops ${state}, which it does not contain`);
    }
  }
  const required = Object.freeze([...input.required]);
  const looping = Object.freeze([...(input.looping ?? [])]);
  const requiredSet = new Set(required);
  const loopingSet = new Set(looping);
  return Object.freeze({
    states,
    required,
    looping,
    has: (state: string) => set.has(state),
    isRequired: (state: string) => requiredSet.has(state),
    isLooping: (state: string) => loopingSet.has(state),
  });
}

/**
 * Resolve what a package published against what the genre requires.
 *
 * `extraRequired` is how a genre states a requirement that is *conditional on
 * something else it authored* — the runner owes a `slide` exactly when it
 * declares a duck profile and a `fly` exactly when it declares an encounter —
 * without the family having to know what a duck profile is.
 *
 * The returned set is the declared states in the vocabulary's own order, so a
 * consumer iterating it gets the canonical order rather than the publication
 * order, which is what makes two packages' motion tables comparable.
 */
export function resolveMotionSet(
  declared: readonly string[],
  vocabulary: MotionVocabulary,
  options: Readonly<{ label: string; extraRequired?: readonly string[] }>,
): readonly string[] {
  const seen = new Set<string>();
  for (const state of declared) {
    if (!vocabulary.has(state)) {
      throw new Error(`${options.label} declares unknown motion state ${state}`);
    }
    if (seen.has(state)) {
      throw new Error(`${options.label} declares the ${state} motion twice`);
    }
    seen.add(state);
  }
  for (const state of [...vocabulary.required, ...(options.extraRequired ?? [])]) {
    if (!seen.has(state)) {
      throw new Error(`${options.label} is missing the ${state} state`);
    }
  }
  return Object.freeze(vocabulary.states.filter((state) => seen.has(state)));
}
