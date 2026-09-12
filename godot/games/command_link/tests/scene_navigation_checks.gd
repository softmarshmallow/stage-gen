extends SceneTree

## Synthetic lifecycle proof: no artwork, game root or story schema is required.
const NAVIGATION = preload("res://addons/scene_navigation/scene_navigation.gd")
const SCENE = preload("res://tests/fixtures/navigation/scene.gd")
var _errors: Array[String] = []
var _selected := {}
var _routes: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(value: bool, message: String) -> void:
	if not value: _errors.append(message)


func _packed(script: Script = SCENE) -> PackedScene:
	var node := Control.new()
	if script != null: node.set_script(script)
	var packed := PackedScene.new()
	_expect(packed.pack(node) == OK, "The synthetic scene must pack.")
	node.free()
	return packed


func _replace(nav: RefCounted, host: Control, capture: String, target: String, reset: bool = false, packed: PackedScene = null) -> bool:
	return nav.replace_scene(host, _packed() if packed == null else packed, capture, target, reset,
		func(saved: Dictionary) -> void:
			host.set_meta("selected", target)
			_selected = saved,
		func(scene: Control, saved: Dictionary) -> void:
			scene.prepared = true
			if not saved.is_empty(): scene.snapshot = saved.duplicate(true),
		func(route: String) -> void: _routes.append(route))


func _run() -> void:
	var host := Control.new()
	root.add_child(host)
	var nav := NAVIGATION.new()
	_expect(_replace(nav, host, "", "alpha"), "The first scene must install.")
	var first: Control = nav.active_scene
	_expect(first.ready_saw_preparation and first.ready_saw_selection, "Selection and preparation must precede the destination's ready callback.")
	first.snapshot.nested.choice = "kept"
	var focus := Button.new()
	first.add_child(focus)
	focus.grab_focus()
	_expect(root.gui_get_focus_owner() == focus, "The old scene must own focus for this proof.")
	var invalid := _packed(null)
	_expect(not _replace(nav, host, "alpha", "beta", true, invalid), "A scene without navigation must be refused before mutation.")
	_expect(nav.active_scene == first and first.is_inside_tree() and first.saved_calls == 0 and nav.checkpoints.is_empty(), "A rejected destination must retain live scene, checkpoint state and capture count.")
	_expect(root.gui_get_focus_owner() == focus, "A rejected destination must preserve focus.")
	_expect(_replace(nav, host, "alpha", "beta"), "A second owner must install.")
	_expect(not first.is_inside_tree() and first.is_queued_for_deletion(), "The replaced scene must stop receiving input before deferred deletion.")
	_expect(root.gui_get_focus_owner() == null, "Successful navigation releases the old scene's GUI focus.")
	first.snapshot.nested.choice = "changed after capture"
	_expect(nav.checkpoints.alpha.nested.choice == "kept", "Checkpoint capture must deep-copy nested game data.")
	var event := InputEventKey.new()
	event.pressed = true
	event.keycode = KEY_SPACE
	root.push_input(event, false)
	_expect(first.key_count == 0 and nav.active_scene.key_count == 1, "Only the installed scene receives input in the replacement frame.")
	nav.active_scene.snapshot = {"beta_only": [1, 2]}
	_expect(_replace(nav, host, "beta", "alpha"), "Returning to an owner must restore its opaque checkpoint.")
	_expect(nav.active_scene.snapshot.nested.choice == "kept" and nav.checkpoints.beta.beta_only == [1, 2], "Each owner retains its own checkpoint shape.")
	_selected.nested.choice = "mutated by host"
	_expect(nav.checkpoints.alpha.nested.choice == "kept", "Destination preparation receives a copy of retained state.")
	nav.active_scene.navigate.emit("local-route")
	_expect(_routes == ["local-route"], "The host receives the destination's navigation intent unchanged.")
	_expect(_replace(nav, host, "alpha", "alpha", true), "A host-selected reset must still replace its current scene.")
	_expect(not nav.checkpoints.has("alpha") and nav.checkpoints.has("beta") and _selected.is_empty(), "Reset follows capture and clears only the destination owner's checkpoint.")
	host.queue_free()
	await process_frame
	for issue: String in _errors: printerr("FAIL scene navigation: " + issue)
	if _errors.is_empty(): print("PASS scene navigation: preflight, preparation order, focus/input release, opaque checkpoint isolation, reset and intent forwarding")
	quit(0 if _errors.is_empty() else 1)
