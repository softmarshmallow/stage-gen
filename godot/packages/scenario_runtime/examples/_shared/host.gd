extends Control

## A tiny consuming game. Its simulation advances before and during a sequence;
## nothing in the Scenario addon knows about this world or its moving actors.
const HOST = preload("res://addons/scenario_runtime/bindings/host.gd")
const SURFACE = preload("res://addons/scenario_runtime/presentation/dialogue_surface.gd")
const PARTICLES = preload("res://addons/scenario_runtime/presentation/particle_adapter.gd")
var content_directory := "res://examples/combat_dialogue"
var use_world_3d := false
var combat_seconds := 0.0
var errors: Array[String] = []
var host := HOST.new()
var surface := SURFACE.new()
var actor := Node2D.new()
var actor_3d: MeshInstance3D
var camera: Camera3D
var session_id := ""
var _serial := 0
var _started := false
var _paused := false
var _particles := PARTICLES.new()
var _status := Label.new()
var _effect_layer := Control.new()
var _textures: Array[Texture2D] = []
var _checkpoints: Array[Dictionary] = []
var _checkpoint_menu := OptionButton.new()
var _inspection := Label.new()
var _last_visit := ""
var _document: Dictionary = {}
var _catalog: Dictionary = {}


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(actor)
	add_child(_effect_layer)
	_effect_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var pixels := Image.create(12, 12, false, Image.FORMAT_RGBA8)
	pixels.fill(Color(1.0, 0.55, 0.15, 0.8))
	_textures.append(ImageTexture.create_from_image(pixels))
	var registered := host.register_capability("particle", PARTICLES.schema(), _particles)
	if registered.has("error"): errors.append(str(registered.error.message))
	if use_world_3d:
		actor_3d = MeshInstance3D.new()
		var mesh := CapsuleMesh.new()
		mesh.radius = 0.3
		mesh.height = 1.0
		actor_3d.mesh = mesh
		var material := StandardMaterial3D.new()
		material.albedo_color = Color.CORNFLOWER_BLUE
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		actor_3d.material_override = material
		add_child(actor_3d)
		camera = Camera3D.new()
		add_child(camera)
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 6.0
		camera.position = Vector3(0, 0.5, 6)
		camera.current = true
	add_child(surface)
	errors.append_array(surface.configure({"bubble": {"layout": "bubble", "width": 400.0, "height": 150.0}, "portrait": {"portrait": "left"}}))
	surface.speakers = {"pilot": {"name": "Pilot", "anchor": "pilot_actor", "portraits": {"default": "portrait"}}}
	surface.portraits = {"portrait": _textures[0]}
	surface.anchors = {"pilot_actor": {"type": "world_3d", "node": actor_3d, "offset": Vector3(0, 0.7, 0), "offscreen": "clamp"} if use_world_3d else {"type": "world_2d", "node": actor, "offset": Vector2(0, -30), "offscreen": "clamp"}}
	surface.action_requested.connect(_submit)
	var bound := host.bind_surface("dialogue", surface)
	if bound.has("error"): errors.append(str(bound.error.message))
	add_child(_status)
	_status.position = Vector2(20, 18)
	_status.add_theme_font_size_override("font_size", 18)
	_status.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var controls := HBoxContainer.new()
	controls.position = Vector2(20, 55)
	add_child(controls)
	for label: String in ["Continue", "Suspend / resume dialogue", "Invoke again"]:
		var button := Button.new()
		button.text = label
		controls.add_child(button)
		match label:
			"Continue": button.pressed.connect(func() -> void: _submit({"kind": "advance"}))
			"Suspend / resume dialogue": button.pressed.connect(toggle_narrative)
			"Invoke again": button.pressed.connect(invoke)
	var inspection_controls := HBoxContainer.new()
	inspection_controls.position = Vector2(20, 94)
	add_child(inspection_controls)
	var step := Button.new()
	step.text = "Step 0.1s"
	step.pressed.connect(step_narrative)
	inspection_controls.add_child(step)
	_checkpoint_menu.custom_minimum_size.x = 220
	inspection_controls.add_child(_checkpoint_menu)
	var restore := Button.new()
	restore.text = "Restore visited checkpoint"
	restore.pressed.connect(func() -> void:
		if _checkpoint_menu.selected >= 0: restore_checkpoint(_checkpoints[_checkpoint_menu.selected]))
	inspection_controls.add_child(restore)
	_inspection.position = Vector2(20, 134)
	_inspection.add_theme_font_size_override("font_size", 14)
	_inspection.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_inspection)
	_update_world()


func _process(delta: float) -> void:
	combat_seconds += delta
	_update_world()
	if not _started and combat_seconds >= 1.0: invoke()
	if not session_id.is_empty():
		var result := host.tick(session_id, delta)
		if result.has("error"): errors.append(str(result.error.message))
		_refresh()
	_status.text = "Host simulation: %.2fs · Scenario: %s" % [combat_seconds, host.view(session_id).get("status", "not invoked yet")]
	if not errors.is_empty(): _status.text = "; ".join(errors)
	queue_redraw()


func _update_world() -> void:
	actor.position = Vector2(300 + sin(combat_seconds) * 150, 365)
	if is_instance_valid(actor_3d): actor_3d.position = Vector3(sin(combat_seconds) * 1.8, -0.5, 0)


func invoke() -> void:
	if not session_id.is_empty(): host.cancel(session_id, "reinvoked")
	_serial += 1
	session_id = "invocation_%d" % _serial
	_started = true
	_paused = false
	var document = JSON.parse_string(FileAccess.get_file_as_string(content_directory + "/program.json"))
	var catalog = JSON.parse_string(FileAccess.get_file_as_string(content_directory + "/catalog.json"))
	if not document is Dictionary or not catalog is Dictionary:
		errors.append("Example content must be compiled before playing.")
		return
	_document = document
	_catalog = catalog
	_checkpoints.clear()
	_checkpoint_menu.clear()
	_last_visit = ""
	var result := host.invoke(_document, _catalog, _policy(), _bindings())
	if result.has("error"): errors.append(str(result.error.message))
	_refresh()


func _submit(action: Dictionary) -> void:
	if session_id.is_empty(): return
	var result := host.submit(session_id, action)
	if result.has("error"): errors.append(str(result.error.message))
	_refresh()


func toggle_narrative() -> void:
	if session_id.is_empty(): return
	_paused = not _paused
	if _paused: host.suspend(session_id)
	else: host.resume(session_id)
	_refresh()


func _refresh() -> void:
	var view := host.view(session_id)
	if view.get("status", "") in ["ended", "cancelled", "failed"]:
		surface.clear()
	else:
		errors.append_array(surface.present(view))
		surface.update_layout()
	var saved := host.snapshot(session_id)
	if saved.has("state"):
		var state: Dictionary = saved.state
		var visit := str(state.get("visit_id", ""))
		if not visit.is_empty() and visit != _last_visit and state.status == "running":
			_last_visit = visit
			_checkpoints.append(saved.duplicate(true))
			_checkpoint_menu.add_item("%s · %s" % [state.node_id, visit])
			_checkpoint_menu.select(_checkpoints.size() - 1)
		var active: Array[String] = []
		for operation: Dictionary in state.operations.values():
			if operation.status == "running": active.append(str(operation.instance_id))
		_inspection.text = "Node: %s · sequence %.2f · presentation %.2f · reading %.2f\nActive effects: %s · gate: %s" % [state.node_id, state.clocks.sequence, state.clocks.presentation, state.clocks.reading, ", ".join(active) if not active.is_empty() else "none", str(view.get("pending_gate", {}))]
	host.drain_events()


func _policy() -> Dictionary:
	return {"session_id": session_id, "capabilities": {"particle": 1}, "channels": ["dialogue"], "bindings": ["air", "ember_sprite"]}


func _bindings() -> Dictionary:
	return {"air": _effect_layer, "ember_sprite": _textures}


## Preview checkpoints are real validated Session snapshots of visited states.
## No positional seek or second interpreter fabricates prior effects or choices.
func restore_checkpoint(saved: Dictionary) -> Dictionary:
	var candidate := HOST.new()
	candidate.register_capability("particle", PARTICLES.schema(), _particles)
	var prepared := candidate.prepare(_document, _catalog, _policy(), _bindings())
	if prepared.has("error"): return prepared
	var validator := preload("res://addons/scenario_runtime/execution/session.gd").new()
	var validation: Dictionary = validator.restore(prepared.program, prepared.catalog, _policy(), saved)
	if validation.has("error"): return validation
	host.cancel(session_id, "preview_checkpoint")
	candidate.bind_surface("dialogue", surface)
	var result := candidate.restore(_document, _catalog, _policy(), _bindings(), saved)
	if result.has("error"):
		errors.append(str(result.error.message))
		return result
	host = candidate
	_paused = host.view(session_id).get("status") == "suspended"
	_last_visit = str(saved.state.visit_id)
	_refresh()
	return result


func step_narrative() -> void:
	if session_id.is_empty(): return
	if _paused: host.resume(session_id)
	host.tick(session_id, 0.1)
	host.suspend(session_id)
	_paused = true
	_refresh()


func _draw() -> void:
	var extent := get_viewport_rect().size
	if not use_world_3d:
		draw_rect(Rect2(Vector2.ZERO, extent), Color("131f2a"))
		for index in 12:
			var x := fmod(float(index) * 115.0 + combat_seconds * 155.0, maxf(1.0, extent.x))
			draw_line(Vector2(x - 14, 220 + index % 4 * 35), Vector2(x, 220 + index % 4 * 35), Color("e79f57"), 3)
		draw_circle(actor.position, 26, Color.CORNFLOWER_BLUE)
		draw_line(actor.position, actor.position + Vector2(38, 0), Color.WHITE, 5)


func _exit_tree() -> void:
	if not session_id.is_empty(): host.cancel(session_id, "host_exit")
