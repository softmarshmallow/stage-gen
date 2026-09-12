extends RefCounted

## Private scene lifecycle shared by the presentation games. Owners resolve routes
## and validate options before calling replace_scene. Checkpoints are opaque;
## this helper knows no story, route names, content bindings or save schema.
var active_scene: Control
var checkpoints: Dictionary = {}


## Preflight the destination before capturing state or removing old input listeners.
## select_scene runs before prepare_scene and _ready so the host's public route
## fields already describe the scene being installed. Neither callback owns time.
func replace_scene(
	host: Control,
	packed: PackedScene,
	capture_owner: String,
	target_owner: String,
	reset_target: bool,
	select_scene: Callable,
	prepare_scene: Callable,
	navigate: Callable
) -> bool:
	if packed == null or not packed.can_instantiate():
		return false
	var candidate := packed.instantiate()
	if not (candidate is Control) or not candidate.has_signal("navigate"):
		candidate.free()
		return false
	if not select_scene.is_valid() or not prepare_scene.is_valid() or not navigate.is_valid():
		candidate.free()
		return false
	if not capture_owner.is_empty() and active_scene != null and active_scene.has_method("save_game"):
		checkpoints[capture_owner] = active_scene.save_game().duplicate(true)
	if reset_target:
		checkpoints.erase(target_owner)
	var saved: Dictionary = checkpoints.get(target_owner, {}).duplicate(true)
	host.get_viewport().gui_release_focus()
	if active_scene != null:
		# A queued deletion alone leaves the old scene listening to this frame.
		host.remove_child(active_scene)
		active_scene.queue_free()
	active_scene = candidate
	select_scene.call(saved)
	prepare_scene.call(active_scene, saved)
	active_scene.connect("navigate", navigate)
	host.add_child(active_scene)
	active_scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return true
