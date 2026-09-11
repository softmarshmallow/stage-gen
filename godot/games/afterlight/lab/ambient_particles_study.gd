extends "res://lab/study_host.gd"

## Ambient Particles is this study's use of independent Sprite Particle Emitters.
## Prepared atmosphere profiles supply art/direction; all layers share one camera.
const EMITTER = preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
const ATMOSPHERE = preload("res://atmosphere_profile.gd")
const IMPACT = preload("res://addons/game_presentation/camera/impact_shake.gd")
const PROFILES := ["quiet_interior", "infernal_hall"]
var _profile_id := "quiet_interior"
var _emitters: Array[Control] = []
var _emitter_root: Control
var _density := 1.0
var _elapsed := 0.0
var _paused := false
var _draining := false
var _world := Transform2D.IDENTITY
var _impact = IMPACT.new()
var _profile_buttons: Dictionary = {}
var _pause_button: Button
var _density_slider: HSlider
var _density_label: Label
var _drain_button: Button


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(background["path"]))
	_emitter_root = Control.new()
	_emitter_root.name = "WorldParticleLayers"
	_emitter_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_emitter_root)
	_build_particles_ui()
	_restart_particles()


func _restart_particles() -> void:
	for emitter: Control in _emitters:
		emitter.clear()
		emitter.queue_free()
	_emitters.clear()
	_elapsed = 0.0
	_draining = false
	_impact.clear()
	_background_index = 2 if _profile_id == "infernal_hall" else 0
	if _backgrounds.size() <= _background_index or _backgrounds[_background_index] == null: return
	var extent := _backgrounds[_background_index].get_size()
	extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
	_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	for fixture: Dictionary in ATMOSPHERE.profile(_profile_id):
		var emitter := EMITTER.new()
		emitter.name = "Ambient_" + str(fixture["id"])
		_emitter_root.add_child(emitter)
		var settings: Dictionary = fixture["options"].duplicate(true)
		settings["rate"] = float(settings.get("rate", 18.0)) * _density
		# Raising density reserves enough capacity for the complete birth window.
		var capacity := ceili(float(settings["rate"]) * float(settings.get("lifetime_max", 5.0)))
		settings["max_particles"] = maxi(int(settings.get("max_particles", 256)), capacity)
		_load_errors.append_array(emitter.start(fixture["region"], fixture["textures"], settings))
		_emitters.append(emitter)
	_present_particles()


func _select_profile(profile_id: String) -> void:
	if profile_id not in PROFILES or profile_id == _profile_id: return
	_profile_id = profile_id
	_restart_particles()


func _set_density(value: float) -> void:
	_density = value
	_restart_particles()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_particles_ui()


func _drain_particles() -> void:
	_draining = true
	for emitter: Control in _emitters: emitter.stop()
	_present_particles()


func _play_shake() -> void:
	_load_errors.append_array(_impact.start({"amplitude_x": 24.0, "amplitude_y": 20.0, "duration": 1.4, "seed": 98}))
	_present_particles()


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	_elapsed += delta
	_impact.advance(delta)
	for emitter: Control in _emitters: _load_errors.append_array(emitter.advance(delta))
	_present_particles()


func _present_particles() -> void:
	_world = _impact.compose(Transform2D.IDENTITY, _base_background, DESIGN_SIZE)
	for emitter: Control in _emitters: _load_errors.append_array(emitter.present(_world))
	_update_particles_ui()
	queue_redraw()


func particles_study_state() -> Dictionary:
	var states: Array[Dictionary] = []
	for emitter: Control in _emitters: states.append(emitter.get_state())
	return {"profile_id": _profile_id, "density": _density, "elapsed": _elapsed,
		"paused": _paused, "draining": _draining, "world": _world,
		"impact": _impact.get_state(), "emitters": states}


func _build_particles_ui() -> void:
	_ui = Control.new()
	_ui.name = "AmbientParticlesStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 103), Color("211b28"))
	_label_text("study.ambient.title", Rect2(46, 31, 700, 47), 31, INK)
	var description := _label_text("study.ambient.description", Rect2(48, 82, 940, 30), 17, MUTED)
	description.size = Vector2(940, 30)
	_build_language_picker(Rect2(800, 39, 192, 38))
	_return_button = _button_text("ui.effects_menu", Rect2(1021, 48, 211, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(24, 686, 1232, 194), Color("211b28"))
	for index in PROFILES.size():
		var profile_id: String = PROFILES[index]
		var button := _button_text("study.ambient." + profile_id, Rect2(46 + index * 224, 705, 210, 42), _select_profile.bind(profile_id))
		button.name = "QuietInterior" if index == 0 else "InfernalHall"
		button.toggle_mode = true
		_profile_buttons[profile_id] = button
	_density_label = _label("", Rect2(522, 698, 304, 27), 18, INK)
	_density_slider = HSlider.new()
	_density_slider.name = "ParticleDensitySlider"
	_density_slider.position = Vector2(522, 733)
	_density_slider.size = Vector2(304, 24)
	_density_slider.min_value = 0.25
	_density_slider.max_value = 2.0
	_density_slider.step = 0.25
	_density_slider.value = _density
	_density_slider.value_changed.connect(_set_density)
	_ui.add_child(_density_slider)
	_status = _label("", Rect2(864, 704, 355, 48), 16, ACCENT)
	_status.name = "ParticleStudyStatus"
	_pause_button = _button_text("ui.pause", Rect2(46, 778, 186, 42), _toggle_pause)
	_pause_button.name = "PauseParticles"
	_button_text("ui.replay", Rect2(246, 778, 186, 42), _restart_particles).name = "RestartParticles"
	_drain_button = _button_text("study.ambient.drain", Rect2(446, 778, 230, 42), _drain_particles)
	_drain_button.name = "DrainParticles"
	_button_text("study.burst.shake", Rect2(690, 778, 215, 42), _play_shake).name = "ShakeAmbientCamera"
	var hint := _label_text("study.ambient.hint", Rect2(46, 839, 1170, 27), 15, MUTED)
	hint.size = Vector2(1170, 27)


func _update_particles_ui() -> void:
	if _status == null: return
	for profile_id: String in _profile_buttons:
		_profile_buttons[profile_id].set_pressed_no_signal(profile_id == _profile_id)
	_density_label.text = _text("study.ambient.density", {"value": "%.2f" % _density})
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_drain_button.disabled = _draining
	var count := 0
	for emitter: Control in _emitters: count += int(emitter.get_state()["particle_count"])
	var phase := "draining" if _draining else "emitting"
	_status.text = _text("study.ambient.status", {"count": count, "seconds": "%.1f" % _elapsed, "phase": _text("study.ambient." + phase)})
	if not _load_errors.is_empty(): _status.text = "\n".join(_load_errors)


func _refresh_language() -> void:
	_update_particles_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if _backgrounds.size() > _background_index and _backgrounds[_background_index] != null:
		draw_texture_rect(_backgrounds[_background_index], _world * _base_background, false)


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else: return
	get_viewport().set_input_as_handled()


func _exit_tree() -> void:
	for emitter: Control in _emitters: emitter.clear()
