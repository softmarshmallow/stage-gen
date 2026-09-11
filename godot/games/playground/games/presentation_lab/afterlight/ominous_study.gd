extends "res://games/presentation_lab/afterlight/study_host.gd"

## This laboratory fixture owns its controls, prepared images, layer order and
## clock. The effects consume geometry/textures without knowing the game cast.
const IMPACT = preload("res://addons/game_presentation/camera/impact_shake.gd")
const REFRACTION = preload("res://addons/game_presentation/effects/refraction_field.gd")
const CORRUPTION = preload("res://addons/game_presentation/effects/ominous_corruption.gd")
const MODES: Array[String] = ["barrier", "heat", "corruption", "combined"]
const TARGETS: Array[String] = ["nami", "yuzu", "area", "screen"]
var _mode := "barrier"
var _target := "nami"
var _strength := 0.8
var _noise_enabled := false
var _paused := false
var _clock := 0.0
var _impact = IMPACT.new()
var _world := Transform2D.IDENTITY
var _refraction: Control
var _corruption: Control
var _neutral: ColorRect
var _noise: NoiseTexture2D
var _mode_buttons: Dictionary = {}
var _target_buttons: Dictionary = {}
var _noise_button: Button
var _pause_button: Button
var _strength_slider: HSlider
var _effect_status: Label
var _strength_label: Label


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	for profile: Dictionary in content.get("guests", []):
		if profile["id"] in ["nami", "yuzu"]:
			_guest_textures[profile["id"]] = _load_texture(profile["path"])
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(background["path"]))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		var extent := _backgrounds[0].get_size()
		extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
		_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	_actor = TextureRect.new()
	_actor.name = "PreparedTargetSprite"
	_actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_actor)
	_neutral = ColorRect.new()
	_neutral.name = "NeutralArea"
	_neutral.color = Color("d2b5ad")
	_neutral.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_neutral)
	var noise_source := FastNoiseLite.new()
	noise_source.seed = 73
	noise_source.frequency = 0.035
	_noise = NoiseTexture2D.new()
	_noise.width = 256
	_noise.height = 256
	_noise.noise = noise_source
	_noise.seamless = true
	_build_effect_layers()
	_build_ominous_ui()
	_reset_effects()


func _build_effect_layers() -> void:
	_refraction = REFRACTION.new()
	_refraction.name = "WorldRefraction"
	add_child(_refraction)
	_corruption = CORRUPTION.new()
	_corruption.name = "TargetCorruption"
	add_child(_corruption)


func _apply_effects() -> void:
	var noise_texture: Texture2D = _noise if _noise_enabled else null
	_load_errors.append_array(_refraction.configure({"mode": "heat" if _mode == "heat" else "barrier", "amplitude_px": 10.0, "tint_strength": 0.0 if _mode == "heat" else 0.055, "noise_texture": noise_texture}))
	_load_errors.append_array(_refraction.set_strength(_strength if _mode in ["barrier", "heat", "combined"] else 0.0))
	_load_errors.append_array(_corruption.configure({"screen": _target == "screen", "noise_texture": noise_texture}))
	_corruption.set_source(_guest_textures.get(_target) if _target in ["nami", "yuzu"] else null)
	_load_errors.append_array(_corruption.set_strength(_strength if _mode in ["corruption", "combined"] else 0.0))


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	_clock += delta
	_impact.advance(delta)
	_advance_effects(delta)
	_present()


func _advance_effects(_delta: float) -> void:
	_load_errors.append_array(_refraction.set_time(_clock))
	_load_errors.append_array(_corruption.set_time(_clock))


func _select_mode(mode: String) -> void:
	if mode not in MODES: return
	_mode = mode
	_apply_effects()
	_present()


func _select_target(target: String) -> void:
	if target not in TARGETS: return
	_target = target
	_apply_effects()
	_present()


func _set_strength(value: float) -> void:
	_strength = clampf(value, 0.0, 1.0)
	_apply_effects()
	_present()


func _toggle_noise() -> void:
	_noise_enabled = not _noise_enabled
	_apply_effects()
	_present()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_ominous_ui()


func _play_impact() -> void:
	_load_errors.append_array(_impact.start())
	_present()


func _reset_effects() -> void:
	_paused = false
	_clock = 0.0
	_impact.clear()
	_clear_effects()
	_apply_effects()
	_present()


func _clear_effects() -> void:
	_refraction.clear()
	_corruption.clear()


func _target_rect() -> Rect2:
	if _target == "screen": return Rect2(Vector2.ZERO, DESIGN_SIZE)
	if _target == "area": return Rect2(440, 200, 400, 390)
	var texture: Texture2D = _guest_textures.get(_target)
	if texture == null: return Rect2(440, 100, 400, 850)
	var height := 860.0
	var width := height * texture.get_width() / texture.get_height()
	return Rect2(640.0 - width * 0.5, 92.0, width, height)


func _present() -> void:
	if _effect_status == null: return
	_world = _impact.compose(Transform2D.IDENTITY, _base_background, DESIGN_SIZE)
	_actor.visible = _target != "area"
	_neutral.visible = _target == "area"
	_actor.texture = _guest_textures.get("nami" if _target == "screen" else _target)
	var actor_rect := _target_rect()
	if _target == "screen":
		var dimensions := _actor.texture.get_size()
		actor_rect = Rect2(640 - 430.0 * dimensions.x / dimensions.y, 92, 860.0 * dimensions.x / dimensions.y, 860)
	var posed := _world * actor_rect
	_actor.position = posed.position
	_actor.size = posed.size
	_neutral.position = posed.position
	_neutral.size = posed.size
	_present_effects()
	_update_ominous_ui()
	queue_redraw()


func _present_effects() -> void:
	# Full-screen contamination is screen-space; other targets follow the world.
	var bounds := _target_rect() if _target == "screen" else _world * _target_rect()
	_load_errors.append_array(_refraction.set_rect(bounds))
	_load_errors.append_array(_corruption.set_rect(bounds))


func effect_state() -> Dictionary:
	return {"mode": _mode, "target": _target, "strength": _strength, "noise": _noise_enabled,
		"paused": _paused, "clock": _clock, "impact": _impact.get_state(), "world": _world}


func _build_ominous_ui() -> void:
	_ui = Control.new()
	_ui.name = "OminousStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 99), Color("211b28"))
	_label("Ominous effects", Rect2(46, 34, 940, 45), 34, INK)
	_label("Screen refraction, target corruption, and a heavier camera impact.", Rect2(48, 83, 968, 27), 18, MUTED)
	_button("Effects menu", Rect2(1040, 48, 192, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(24, 640, 1232, 240), Color("211b28"))
	var labels := ["Barrier distortion", "Heat haze", "Corruption", "Combined"]
	for index in MODES.size():
		var button := _button(labels[index], Rect2(42 + index * 303, 660, 290, 42), _select_mode.bind(MODES[index]))
		button.toggle_mode = true
		_mode_buttons[MODES[index]] = button
	var targets := ["Nami sprite", "Yuzu sprite", "Neutral area", "Full screen"]
	for index in TARGETS.size():
		var button := _button(targets[index], Rect2(42 + index * 224, 716, 212, 40), _select_target.bind(TARGETS[index]))
		button.toggle_mode = true
		_target_buttons[TARGETS[index]] = button
	_noise_button = _button("", Rect2(938, 716, 294, 40), _toggle_noise)
	_strength_label = _label("", Rect2(46, 779, 175, 34), 18, INK)
	_strength_slider = HSlider.new()
	_strength_slider.position = Vector2(222, 781)
	_strength_slider.size = Vector2(365, 32)
	_strength_slider.min_value = 0.0
	_strength_slider.max_value = 1.0
	_strength_slider.step = 0.01
	_strength_slider.value = _strength
	_strength_slider.value_changed.connect(_set_strength)
	_ui.add_child(_strength_slider)
	_button("Impact / retrigger", Rect2(615, 775, 225, 44), _play_impact)
	_pause_button = _button("Pause", Rect2(854, 775, 177, 44), _toggle_pause)
	_button("Reset", Rect2(1045, 775, 187, 44), _reset_effects)
	_effect_status = _label("", Rect2(46, 836, 1186, 29), 17, MUTED)


func _update_ominous_ui() -> void:
	for mode: String in _mode_buttons: _mode_buttons[mode].set_pressed_no_signal(mode == _mode)
	for target: String in _target_buttons: _target_buttons[target].set_pressed_no_signal(target == _target)
	_strength_slider.set_value_no_signal(_strength)
	_strength_label.text = "Strength: %.2f" % _strength
	_noise_button.text = "Noise texture" if _noise_enabled else "Procedural noise"
	_pause_button.text = "Resume" if _paused else "Pause"
	_effect_status.text = "%s  •  %.2f s  •  Sprite alpha or a soft area supplies coverage; no generated art." % ["Paused" if _paused else "Running", _clock]
	if not _load_errors.is_empty(): _effect_status.text = "; ".join(_load_errors)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if _backgrounds.is_empty() or _backgrounds[0] == null: return
	draw_texture_rect(_backgrounds[0], _world * _base_background, false)


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE: navigate.emit("effects_menu")
		elif event.keycode == KEY_SPACE: _toggle_pause()
		else: return
		get_viewport().set_input_as_handled()
