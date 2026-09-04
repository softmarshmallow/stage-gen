// The `interaction` family, first half: which affordance is offered.
//
// Two models existed and neither shared a line with the other. The platformer
// asks "which villager am I near enough to talk to" — a filter over placed
// actors, a range, and the nearest one wins, sorted inline inside the frame
// step that draws the prompt. The room asks "which authored interaction fires
// for this verb on this hotspot with this item held" — a scan of the authored
// list in order, where the first available one wins, written inline inside the
// reducer.
//
// They are one rule with one parameter. An affordance is *available* when the
// package's own conditions hold — a scenario is bound, a flag is set, the item
// is carried, the hotspot is visible — and the pick between two available ones
// is by proximity where the model has a space and by authored order where it
// does not. "Authored order" is not a degenerate case of proximity: the room's
// list is a priority the author wrote down, and re-sorting it would change
// which line a click produces.

export interface AffordanceQuery<Candidate> {
  /** Everything that could be offered, in the order the package authored it. */
  readonly candidates: Iterable<Candidate>;
  /** Whether this one is available at all: the package's conditions, the consumer's to evaluate. */
  readonly available: (candidate: Candidate) => boolean;
  /**
   * How far away this one is, or omitted for a model with no space.
   *
   * A model that measures distance picks the nearest; one that does not picks
   * the first the author wrote. Ties go to the earlier candidate in both, which
   * is what a stable sort over authored order already gave the platformer.
   */
  readonly distance?: (candidate: Candidate) => number;
}

/** The affordance on offer, or null — which is an ordinary answer and not a failure. */
export function selectAffordance<Candidate>(
  query: AffordanceQuery<Candidate>,
): Candidate | null {
  let best: Candidate | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const candidate of query.candidates) {
    if (!query.available(candidate)) continue;
    if (query.distance === undefined) return candidate;
    const distance = query.distance(candidate);
    if (distance < bestDistance) {
      best = candidate;
      bestDistance = distance;
    }
  }
  return best;
}
