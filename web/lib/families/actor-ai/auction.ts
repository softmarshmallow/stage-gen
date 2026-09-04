// How one of an actor's several opinions wins the frame.
//
// Two arbitration engines existed for one job: the bot's priority auction and
// the creature's node chain. The composition table's claim is that the auction
// *subsumes* the chain, and the claim is exactly right — but not for the reason
// it is usually argued. The creature's chain is not a state machine at all. It
// is `mobIntent`, five conditions in a fixed order, and a fixed order is a
// priority ladder written with `if`. Restating it as five bidders at descending
// priorities is not an approximation of it; it is the same function, and that
// is measured exhaustively rather than argued.
//
// What is *not* here is the rest of either actor. Which behaviours a genre has,
// what they bid on, and the numbers a profile turns are genre content — an
// aggression archetype and a bot personality are the same kind of thing and
// neither belongs in a shared file. This is the contract those opinions are
// written against, the rule that picks between them, and nothing else.
//
// Determinism is a hard requirement rather than a preference: both genres verify
// themselves by replaying a fixed-step transcript and comparing frame hashes.
// Nothing here consults a clock it was not handed, or a random number generator
// at all. Ties break on roster order, which is stable.

/** One opinion, at the strength it is held. */
export interface Bid<Action> {
  readonly priority: number;
  readonly action: Action;
}

/**
 * Pick the winning bid.
 *
 * Strictly greater wins, so a tie leaves the earlier-declared bidder in place.
 * Roster order is therefore a real tiebreak the author controls, and reordering
 * a roster is a legitimate way to say "when these two want the frame equally,
 * prefer this one".
 */
export function arbitrate<B extends { readonly priority: number }>(
  bids: readonly (B | null)[],
): B | null {
  let winner: B | null = null;
  for (const bid of bids) {
    if (!bid) continue;
    if (!winner || bid.priority > winner.priority) winner = bid;
  }
  return winner;
}

/**
 * Poll a roster and arbitrate, in one call.
 *
 * The shape a stateless ladder takes: each rung is a function of the same
 * context that either bids or declines, and declining is the normal outcome.
 */
export function runAuction<Context, B extends { readonly priority: number }>(
  roster: readonly ((context: Context) => B | null)[],
  context: Context,
): B | null {
  return arbitrate(roster.map((bidder) => bidder(context)));
}

/**
 * A ladder of conditions, in priority order, as an auction.
 *
 * The adapter for the shape a genre already has as an `if` chain: the first
 * entry whose predicate holds wins, which is what a descending auction with one
 * bidder per rung computes. Written here so the restatement is a call rather
 * than a hand translation each genre gets subtly wrong.
 */
export function ladder<Context, Action>(
  rungs: readonly (readonly [(context: Context) => boolean, Action])[],
  context: Context,
): Action | null {
  const won = arbitrate(
    rungs.map(([holds, action], index) =>
      holds(context) ? { priority: rungs.length - index, action } : null,
    ),
  );
  return won === null ? null : won.action;
}
