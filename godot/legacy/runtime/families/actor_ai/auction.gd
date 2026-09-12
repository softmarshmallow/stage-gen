class_name FamilyAuction
extends RefCounted

## How one of an actor's several opinions wins the frame.
##
## A port of `web/lib/families/actor-ai/auction.ts`. Every bidder is asked, every
## frame, what it would do and how badly it wants to; the loudest bid wins and the
## rest are discarded. A state machine would need every behaviour to know its
## neighbours in order to name a transition, and adding the seventh state to a
## six-state machine means editing six states — here the seventh behaviour is
## added by writing it.
##
## What is *not* here is the rest of either actor. Which behaviours a genre has,
## what they bid on, and the numbers a profile turns are genre content: an
## aggression archetype and a bot personality are the same kind of thing and
## neither belongs in a shared file.
##
## Determinism is a hard requirement rather than a preference. Nothing here
## consults a clock it was not handed, or a random number generator at all.

## Pick the winning bid, or an empty dictionary when every bidder declined.
##
## Strictly greater wins, so a tie leaves the earlier-declared bidder in place.
## Roster order is therefore a real tiebreak the author controls, and reordering a
## roster is a legitimate way to say "when these two want the frame equally,
## prefer this one". A declined bid is an empty dictionary — a refusal is a value.
static func arbitrate(bids: Array) -> Dictionary:
	var winner: Dictionary = {}
	for entry: Variant in bids:
		var bid: Dictionary = entry
		if bid.is_empty():
			continue
		if winner.is_empty() or float(bid["priority"]) > float(winner["priority"]):
			winner = bid
	return winner


## Poll a roster and arbitrate, in one call.
##
## The shape a stateless ladder takes: each rung is a function of the same context
## that either bids or declines, and declining is the normal outcome. `roster` is
## an array of `Callable(context) -> Dictionary`.
static func run(roster: Array, context: Dictionary) -> Dictionary:
	var bids: Array = []
	for entry: Variant in roster:
		var bidder: Callable = entry
		bids.append(bidder.call(context))
	return arbitrate(bids)
