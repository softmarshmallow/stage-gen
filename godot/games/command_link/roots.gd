extends RefCounted

## Command Link's composition roots. The mission and its own laboratory; no discovery, no game DSL.
const ROOTS := {
	"command_link": preload("res://root.gd"),
	"lab": preload("res://lab/root.gd"),
}


static func create(game_id: String) -> RefCounted:
	if not ROOTS.has(game_id):
		return null
	return ROOTS[game_id].new()
