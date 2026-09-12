class_name FamilyTransition
extends RefCounted

## The cover a cut between two runs is made under.
##
## A restart is instantaneous in the simulation — one frame the run has ended,
## the next it is a new run at column two with a new seed — and a cut with
## nothing over it reads as a glitch rather than as a beginning. This is what
## goes over it.
##
## **This is a placeholder, and it is deliberately shaped like the thing that
## will replace it.** A run publishes no transitions today, so nothing here is
## read from a manifest and the published contract is untouched. What a
## `transitions` block would carry when there is one is the same shape the `fx`
## block already carries for moments — a named transition bound to a named
## choreography — so a host would bind it exactly the way it binds a cut-in:
##
##     [[transitions]]
##     transition = "run_restart"
##     choreography = "fade_black_v1"
##
## Until then the binding is a constant in the host and the numbers are below.
## The seam is real: a caller names a choreography rather than assuming one, and
## an unknown name is refused here rather than drawn as a guess.
##
## Every number is a millisecond on the **frame** clock. Nothing about a cut
## reaches the simulation — no output here is read by any system, no system owns
## it, and a host that draws none of it plays the same game.

const FADE_BLACK := "fade_black_v1"


## The one choreography a host may bind today. An unknown name is an empty
## dictionary, which a caller must treat as "draw nothing" rather than as black.
static func choreography(name: String) -> Dictionary:
	if name != FADE_BLACK:
		return {}
	return {
		# Long enough that the swap happens behind a cover that is already
		# fully up, and short enough that a player pressing restart does not
		# feel it as a wait.
		"holdMs": 90.0,
		"fadeMs": 310.0,
	}


## One frame of the cover: how much of the picture it hides, and whether it is
## over. An empty dictionary when the elapsed time is not a time, which is a
## refusal rather than a guess.
static func frame(elapsed_ms: float, ch: Dictionary) -> Dictionary:
	if not is_finite(elapsed_ms) or elapsed_ms < 0.0:
		return {}
	var hold_ms := float(ch["holdMs"])
	var fade_ms := float(ch["fadeMs"])
	# Opaque through the hold, then off quickly and settling — the new run is
	# most of the way visible in the first third of the fade, which is where a
	# player is already looking for it.
	var reveal := FamilyParticles.ease_out_cubic(
		minf(1.0, maxf(0.0, (elapsed_ms - hold_ms) / maxf(1.0, fade_ms)))
	)
	return {
		"cover": 1.0 - reveal,
		"finished": elapsed_ms >= hold_ms + fade_ms,
	}
