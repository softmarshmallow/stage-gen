extends SceneTree

## Focused real-host lifecycle and native shader proof. --capture-ominous writes
## 1x/2x screenshots; force_draw avoids waiting for an idle frame_post_draw.
const DESIGN_SIZE := Vector2(1280, 900)
const DIRECTORY := "res://tests/ominous-vfx"
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _captures := 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-ominous")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Ominous VFX capture requires a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await process_frame
	_expect(_app.open_route("game:lab/ominous_study"), "The dedicated ominous study must be routable.")
	await process_frame
	var study: Control = _app.active_scene
	study.set_process(false)
	study._reset_effects()
	_expect(study._load_errors.is_empty(), "Prepared fixture and shared presenters must initialize.")
	if not study._load_errors.is_empty():
		_finish()
		return
	_check_layers(study)
	_check_targets_and_lifecycle(study)
	_check_impact(study)
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		await process_frame
		_check_layout(study)
		if _capture_enabled: await _check_pixels(study, window_size)
	study._clear_effects()
	_expect(not study._refraction.visible and not study._corruption.visible, "Clear must hide both fields.")
	_expect(study._corruption.get_source() == null and study._refraction.get_time() == 0.0 and study._corruption.get_time() == 0.0, "Clear must release the sprite mask and reset both shader clocks.")
	_expect(study._load_errors.is_empty(), "All host operations must remain valid.")
	var old_effect: WeakRef = weakref(study._corruption)
	_expect(_app.open_route("game:lab/effects_menu"), "The study must return to its laboratory menu.")
	await process_frame
	await process_frame
	_expect(old_effect.get_ref() == null, "Leaving the route must free its effect nodes and copies.")
	_finish()


func _check_layers(study: Control) -> void:
	_expect(study._actor.get_index() < study._refraction.get_index() and study._refraction.get_index() < study._corruption.get_index() and study._corruption.get_index() < study._ui.get_index(), "Each screen-reading field must follow affected world content and precede UI.")
	for field: Control in [study._refraction, study._corruption]:
		_expect(field._copy.get_index() < field._quad.get_index(), "Each refraction pass must refresh its own screen copy before drawing.")
		_expect(field.mouse_filter == Control.MOUSE_FILTER_IGNORE and field._quad.mouse_filter == Control.MOUSE_FILTER_IGNORE, "Shader coverage must never intercept controls.")


func _check_targets_and_lifecycle(study: Control) -> void:
	for target: String in study.TARGETS:
		study._select_target(target)
		for mode: String in study.MODES:
			study._select_mode(mode)
			study._reset_effects()
			study._set_strength(0.65)
			study._process(0.37)
			_expect(is_equal_approx(study._refraction.get_time(), 0.37) and is_equal_approx(study._corruption.get_time(), 0.37), "Both field presenters must sample the one host clock.")
			_expect(study._corruption.get_source() == (study._guest_textures[target] if target in ["nami", "yuzu"] else null), "Corruption must accept either existing sprite alpha or a source-free area.")
			_expect(study._corruption.get_settings()["screen"] == (target == "screen"), "Only explicit screen targeting may ignore the sprite/area mask.")
			var before: Dictionary = study.effect_state()
			for index in 3: study._present()
			_expect(study.effect_state() == before, "Rendering must not advance or restart effects.")
			study._toggle_pause()
			var frozen: Dictionary = study.effect_state()
			study._process(2.0)
			_expect(study.effect_state() == frozen, "Pause must freeze both shaders and the impact clock.")
			study._toggle_pause()
			study._set_strength(0.0)
			_expect(not study._refraction.visible and not study._corruption.visible, "Zero strength must disable both visible treatments.")
			_expect(study._refraction._copy.copy_mode == BackBufferCopy.COPY_MODE_DISABLED and study._corruption._copy.copy_mode == BackBufferCopy.COPY_MODE_DISABLED, "Zero strength must disable redundant screen copies.")
			study._set_strength(0.8)
			study._toggle_noise()
			_expect(study._refraction.get_settings()["noise_texture"] == study._noise and study._corruption.get_settings()["noise_texture"] == study._noise, "One optional reusable noise texture must feed both presenters.")
			_expect(is_equal_approx(study._clock, 0.37), "Changing the texture input must preserve the current field time.")
			study._toggle_noise()
			study._reset_effects()
			_expect(study._clock == 0.0 and study._world == Transform2D.IDENTITY, "Reset must restore time and the exact base camera without changing targets.")


func _check_impact(study: Control) -> void:
	study._select_mode("combined")
	study._select_target("yuzu")
	study._play_impact()
	var moved := false
	for step in 110:
		study._process(1.0 / 60.0)
		var bounds: Rect2 = study._world * study._base_background
		_expect(bounds.position.x <= 0.001 and bounds.position.y <= 0.001 and bounds.end.x >= DESIGN_SIZE.x - 0.001 and bounds.end.y >= DESIGN_SIZE.y - 0.001, "Heavy impact must maintain full background coverage.")
		if study._world != Transform2D.IDENTITY: moved = true
		_expect(Rect2(study._actor.position, study._actor.size).is_equal_approx(study._world * study._target_rect()), "The sprite must receive the composed camera transform exactly once.")
		_expect(study._corruption.get_source_rect().is_equal_approx(study._world * study._target_rect()), "The actor corruption mask must follow the same final camera frame.")
	_expect(moved and study._world == Transform2D.IDENTITY, "Impact must visibly displace the frame then return exactly to base.")
	study._play_impact()
	study._process(0.2)
	study._toggle_pause()
	var frozen: Dictionary = study.effect_state()
	study._process(1.0)
	_expect(study.effect_state() == frozen, "An active heavy impact must pause with the shader clocks.")
	study._toggle_pause()
	study._play_impact()
	_expect(study._impact.sample()["active"] and study._impact.get_state()["elapsed"] == 0.0, "Retrigger must replace the impact clock at its authored start.")
	study._reset_effects()


func _check_layout(study: Control) -> void:
	for button: Button in study._mode_buttons.values() + study._target_buttons.values():
		_expect(Rect2(Vector2.ZERO, DESIGN_SIZE).encloses(button.get_rect()), "Study controls must stay inside the fixed logical canvas at both native sizes.")
	var final := root.get_final_transform()
	var window := Vector2(root.size)
	var transformed := final * Rect2(Vector2.ZERO, DESIGN_SIZE)
	_expect(transformed.size.is_equal_approx(window), "The 1x/2x window must render the entire logical canvas at its native scale.")


func _check_pixels(study: Control, window_size: Vector2i) -> void:
	var scale_factor := float(window_size.x) / DESIGN_SIZE.x
	var preview := Rect2(70, 145, 1140, 475)
	for target: String in study.TARGETS:
		study._select_target(target)
		study._select_mode("corruption")
		study._reset_effects()
		study._process(0.62)
		study._set_strength(0.0)
		var clean := await _frame_image()
		study._set_strength(0.8)
		var affected := await _frame_image()
		_expect(_different_pixels(clean, affected, preview, scale_factor) > 80, "Corruption must visibly affect every source type at native " + str(window_size.x) + ": " + target)
		_expect(_different_pixels(clean, affected, Rect2(28, 26, 1220, 90), scale_factor) == 0, "Screen corruption must leave the later-drawn header UI unchanged.")
		await _capture(affected, "corruption-" + target + "-" + str(window_size.x))
	study._select_target("screen")
	study._set_strength(0.8)
	for mode: String in ["barrier", "heat"]:
		study._select_mode(mode)
		study._reset_effects()
		study._process(0.71)
		var affected := await _frame_image()
		study._set_strength(0.0)
		var clean := await _frame_image()
		_expect(_different_pixels(clean, affected, preview, scale_factor) > 100, "Screen refraction must alter actual background/actor pixels for " + mode)
		study._refraction.hide()
		study._corruption.hide()
		var disabled := await _frame_image()
		_expect(_different_pixels(clean, disabled, preview, scale_factor) == 0, "Strength zero must render exactly as disabled effect layers.")
		study._set_strength(0.8)
		await _capture(affected, mode + "-" + str(window_size.x))
	study._select_mode("combined")
	study._select_target("nami")
	study._toggle_noise()
	if study._noise.get_image() == null: await study._noise.changed
	study._reset_effects()
	study._process(0.34)
	study._play_impact()
	study._process(0.13)
	await _capture(await _frame_image(), "noise-combined-impact-" + str(window_size.x))
	study._toggle_noise()
	study._reset_effects()


func _frame_image() -> Image:
	await process_frame
	RenderingServer.force_draw(false)
	return root.get_texture().get_image()


func _capture(picture: Image, name: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(DIRECTORY))
	_expect(picture.save_png(DIRECTORY + "/" + name + ".png") == OK, "Native capture must save: " + name)
	_captures += 1


func _different_pixels(left: Image, right: Image, logical: Rect2, factor: float) -> int:
	var bounds := Rect2i(logical.position * factor, logical.size * factor)
	var count := 0
	for y in range(bounds.position.y, bounds.end.y, maxi(1, roundi(6 * factor))):
		for x in range(bounds.position.x, bounds.end.x, maxi(1, roundi(6 * factor))):
			var delta := left.get_pixel(x, y) - right.get_pixel(x, y)
			if absf(delta.r) + absf(delta.g) + absf(delta.b) > 0.012: count += 1
	return count


func _expect(condition: bool, message: String) -> void:
	if not condition and message not in _errors: _errors.append(message)


func _finish() -> void:
	for message: String in _errors: printerr("FAIL Ominous VFX: " + message)
	if _errors.is_empty():
		print("PASS Ominous VFX: arbitrary sprite/area/screen targets, procedural/texture inputs, host clocks, pause/reset/cleanup, refraction order, zero strength, impact coverage and fixed native 1x/2x layout")
		if _captures > 0: print("Ominous VFX captures: " + str(_captures))
	quit(0 if _errors.is_empty() else 1)
