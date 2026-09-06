class_name SysPlayerAnim
extends RefCounted

## Reads `player_vitals`, `player_action`; writes `player_frame`.
## viewer/index.html 1469-1481.
##
## `hurt` and `gather` play to completion before idle/walk can take over.


static func update(world: World, dt: float) -> void:
	var player: PlayerState = world.player
	player.elapsed += dt
	if player.busy != null:
		# A busy player owns its own elapsed.
		return
	var states := Targeting.player_states(world)
	if (player.state == "hurt" or player.state == "gather") \
			and player.elapsed < Targeting.state_duration(states.get(player.state, null)):
		return
	var moving := sqrt(player.vx * player.vx + player.vz * player.vz) > 0.1
	var next := "walk" if (moving and states.has("walk")) else "idle"
	if next != player.state:
		player.state = next
		player.elapsed = 0.0
