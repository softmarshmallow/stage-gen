extends SceneTree

## One-use native-render evidence for real UI states. This helper routes input
## through the live viewport; it does not replace controls or their styles.
const FOLDER := "res://qa/tactical-ui/controls"
const DESIGN_SIZE := Vector2(1280, 900)
var _router: Control
var _errors: Array[String] = []
var _captures := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Control-state captures require the native renderer; use --check-only for headless parsing.")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(FOLDER) != OK:
		printerr("Could not create control-state capture directory.")
		quit(2)
		return
	root.size = Vector2i(1280, 900)
	var main: PackedScene = load("res://main.tscn")
	_router = main.instantiate()
	root.add_child(_router)
	_router.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_freeze(_router.get("active_scene") as Control)
	var scene: Control = await _open("menu")
	var primary: Button = scene.get("_play_button") as Button
	_move_mouse(Vector2(2, 898))
	primary.grab_focus()
	_expect(primary.has_focus(), "Menu primary must have actual keyboard focus.")
	await _capture("menu_primary_focus", primary)
	root.gui_release_focus()
	var card: Button = (scene.get("_demo_buttons") as Dictionary)["dialogue_camera"] as Button
	_move_mouse(card.get_global_rect().get_center())
	await process_frame
	_expect(card.is_hovered() and card.get_draw_mode() == BaseButton.DRAW_HOVER, "Demo card must be in its actual hover state.")
	await _capture("menu_card_hover", card)
	_mouse_button(card.get_global_rect().get_center(), true)
	await process_frame
	_expect(card.get_draw_mode() in [BaseButton.DRAW_PRESSED, BaseButton.DRAW_HOVER_PRESSED], "Demo card must be held in its actual pressed state.")
	await _capture("menu_card_pressed", card)
	# Releasing outside the card cancels the pending click without navigation.
	_move_mouse(Vector2(2, 898), MOUSE_BUTTON_MASK_LEFT)
	_mouse_button(Vector2(2, 898), false)
	scene = await _open("new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	for index in 4:
		var next: Button = scene.get("_next_button") as Button
		_expect(next.visible and not next.disabled, "Authored briefing must expose an enabled Next button.")
		_click(next)
		if String(scene.get("_story_id")) != "orders":
			_tick(scene, 1.0)
	_expect(String(scene.get("_story_id")) == "orders", "The real briefing route must reach the orders beat.")
	_tick(scene, 0.3)
	var choices: Array = scene.get("_choice_buttons")
	for choice: Button in choices:
		_expect(choice.visible and choice.disabled, "Orders must be visibly disabled while returning wide.")
	_move_mouse(Vector2(2, 898))
	root.gui_release_focus()
	await _capture("game_orders_disabled", choices[0] as Button)
	_tick(scene, 0.5)
	var first_choice: Button = choices[0] as Button
	_expect(not first_choice.disabled, "Settled wide framing must enable the real choices.")
	first_choice.grab_focus()
	_expect(first_choice.has_focus(), "Enabled choice must have actual keyboard focus.")
	await _capture("game_choice_focus", first_choice)
	scene = await _open("demos/dialogue_camera")
	scene.set("_location_title_elapsed", 3.7)
	scene.call("_update_location_title")
	_move_mouse(Vector2(2, 898))
	var slider: HSlider = scene.get("_zoom_slider") as HSlider
	slider.grab_focus()
	_expect(slider.has_focus(), "Zoom slider must have actual keyboard focus.")
	await _capture("demo_slider_focus", slider)
	for issue: String in _errors:
		printerr("FAIL Control capture: " + issue)
	if _errors.is_empty():
		print("PASS: %d native control-state PNG and metadata pairs" % _captures)
	quit(0 if _errors.is_empty() else 1)


func _open(route: String) -> Control:
	_expect(bool(_router.call("open_route", route)), "Could not open " + route)
	var scene: Control = _router.get("active_scene") as Control
	_freeze(scene)
	await process_frame
	await process_frame
	if scene.has_method("_update_character_layers"):
		scene.set("_entry", 1.0)
		scene.set("_location_title_elapsed", 3.7)
		scene.call("_update_location_title")
		scene.call("_update_interface")
	return scene


func _freeze(scene: Control) -> void:
	if scene.has_method("_update_character_layers"):
		scene.set("_capture_frozen", true)
		scene.set("_capturing", true)
		scene.set("_natural_blink", false)
		scene.set("_blink_remaining", 0.0)
		scene.set("_elapsed", 1.0)
		scene.set("_pointer", Vector2(-1000, -1000))


func _tick(scene: Control, duration: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", duration)
	scene.set("_capture_frozen", true)


func _move_mouse(point: Vector2, buttons: int = 0) -> void:
	var event := InputEventMouseMotion.new()
	event.position = point
	event.global_position = point
	event.button_mask = buttons
	root.push_input(event, true)


func _mouse_button(point: Vector2, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = point
	event.global_position = point
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	event.pressed = pressed
	root.push_input(event, true)


func _click(button: Button) -> void:
	var point := button.get_global_rect().get_center()
	_move_mouse(point)
	_mouse_button(point, true)
	_mouse_button(point, false)


func _capture(name: String, control: Control) -> void:
	var scene: Control = _router.get("active_scene") as Control
	scene.queue_redraw()
	await process_frame
	for index in 4:
		RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900), "Control captures must use the fixed logical viewport.")
	_expect(picture.save_png(FOLDER.path_join(name + ".png")) == OK, "Could not save " + name)
	var rect := control.get_global_rect()
	var transform := root.get_final_transform()
	var extent := transform.basis_xform(DESIGN_SIZE)
	var metadata := {"state": name, "route": String(_router.get("current_route")),
		"capture_space": "logical_viewport", "renderer": DisplayServer.get_name(),
		"viewport": [picture.get_width(), picture.get_height()], "window_size": [root.size.x, root.size.y],
		"output_rect": [transform.origin.x, transform.origin.y, extent.x, extent.y],
		"control_class": control.get_class(), "control_rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
		"has_focus": control.has_focus(), "visible": control.is_visible_in_tree()}
	if control is BaseButton:
		metadata["disabled"] = control.disabled
		metadata["hovered"] = control.is_hovered()
		metadata["draw_mode"] = control.get_draw_mode()
	if control is Slider:
		metadata["value"] = control.value
	if scene.has_method("save_dialogue_camera"):
		metadata["dialogue_camera"] = scene.call("save_dialogue_camera")
	if scene.has_method("save_game"):
		metadata["story_id"] = String(scene.get("_story_id"))
	var output := FileAccess.open(FOLDER.path_join(name + ".json"), FileAccess.WRITE)
	_expect(output != null, "Could not write metadata for " + name)
	if output != null:
		output.store_string(JSON.stringify(metadata, "\t"))
	_captures += 1
	print("Control capture: " + ProjectSettings.globalize_path(FOLDER.path_join(name + ".png")))


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)
