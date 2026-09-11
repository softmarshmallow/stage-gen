extends RefCounted

## Explicit composition roots for this experiment. No discovery or game DSL.
const ROOTS := {
	"command_link": preload("res://games/command_link/root.gd"),
	"bishoujo_afterlight": preload("res://games/bishoujo_afterlight/root.gd"),
	"presentation_lab": preload("res://games/presentation_lab/root.gd"),
}


static func create(game_id: String) -> RefCounted:
	# Keep the earlier reserved-root launch command usable.
	if game_id == "dating_sim":
		game_id = "bishoujo_afterlight"
	if not ROOTS.has(game_id):
		return null
	return ROOTS[game_id].new()
