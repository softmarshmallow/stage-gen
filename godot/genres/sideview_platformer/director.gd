class_name PlatformerDirector
extends RefCounted

## This genre's instantiation of the `director` family: an authored gate.
##
## `[[boss_encounters]]` publishes four facts about a set-piece — where it stands
## (`anchor`), what stands there (`mob_id`), what plays while it does
## (`track_id`), and whether it comes back (`respawn_policy`). What each becomes:
##
##   - `anchor` is a spatial trigger, resolved against the map's own portal
##     endpoints — the same table `[[spawns]]` and `[[transitions]]` resolve
##     their anchors against — so a gate is a *place in the map* rather than a
##     fraction somebody typed into a consumer.
##   - `mob_id` is what the gate places when it fires. A boss is `director` plus a
##     profile: the rank scale, the vitals gauge and the actor-ai archetype are
##     already somebody else's.
##   - `track_id` is a swap, applied when the gate fires and put back when it
##     ends.
##   - `respawn_policy = "quest_reset_only"` is `once`. A gate is a place in a
##     story, and the story does not un-happen because the player walked back
##     through the map.
##
## **Why the swap is not the family's ledger.** `FamilySwapLedger` holds
## Callables and therefore lives *beside* the world rather than in it. This
## genre's one swap is a value — the track pool to put back — and a value can
## live in the slice a digest hashes. Two runtimes cannot disagree about a list
## of strings the way they can about two closures written twice.

## The phase vocabulary, and it is deliberately short. The runner's has six
## because a streamed track has an arena to wait for and a cut-in to play over;
## an authored map has neither. `armed` is before the body has reached the gate,
## `engaged` is the fight, and with `once` recurrence `ended` is where it stays.
const PHASE_ARMED := "armed"
const PHASE_ENGAGED := "engaged"
const PHASE_ENDED := "ended"

## What a gate ended as. One member: the fight ends when the thing standing in it
## is defeated. A gate the player walks away from is still `engaged` — the world
## it stood in is torn down and the gate re-armed — which is why "left" is not an
## outcome here.
const OUTCOME_WON := "won"

const RECURRENCE_ONCE := "once"
const RECURRENCE_RECURRING := "recurring"


## The state one gate opens in.
static func armed() -> Dictionary:
	return {"phase": PHASE_ARMED, "phaseStartedAt": null, "outcome": null, "trackPool": []}


## How this genre's authored policy reads as the family's recurrence.
static func recurrence(respawn_policy: String) -> String:
	return RECURRENCE_ONCE if respawn_policy == "quest_reset_only" else RECURRENCE_RECURRING


## Whether this gate is done with, for good.
static func spent(state: Dictionary, respawn_policy: String) -> bool:
	return (
		String(state["phase"]) == PHASE_ENDED
		and recurrence(respawn_policy) == RECURRENCE_ONCE
	)


## Resolve an authored anchor to a place on the map, in world pixels.
##
## The map's portal endpoints are the anchor table. A set-piece's anchor was
## never checked by the runtime that came before, because nothing read it — so an
## unresolved one is answered with a refusal here and reported by whoever asked,
## which is the same call `drop_loot` makes about an item id that does not
## resolve.
static func anchor_x(map: Dictionary, anchor: String) -> float:
	for entry: Variant in (map["endpoints"] as Array):
		var endpoint: Dictionary = entry
		if String(endpoint["anchor"]) == anchor:
			return float(endpoint["normalizedX"]) * float(map["worldWidthPx"])
	return -1.0


## Fire the gate, holding on to the pool the swap has to put back.
static func engage(state: Dictionary, now_ms: float, restore_pool: PackedStringArray) -> void:
	FamilyDirector.enter_phase(state, PHASE_ENGAGED, now_ms)
	var pool: Array = []
	for track in restore_pool:
		pool.append(track)
	state["trackPool"] = pool


## End the gate. The pool it put aside is the caller's to restore, because only
## the caller owns the bag.
static func end(state: Dictionary, now_ms: float, outcome: String) -> void:
	FamilyDirector.enter_phase(state, PHASE_ENDED, now_ms)
	state["outcome"] = outcome
