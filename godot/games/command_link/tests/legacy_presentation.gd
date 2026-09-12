extends "res://presentation/stage.gd"

## Historical Command Link fixture checks and captures; never a game presenter.
const CAPTURE_STATES := ["full_body", "blink", "reach_out", "connection", "debug", "dialogue_mira", "dialogue_lena", "dialogue_sera", "manpu_gallery", "manpu_surprise", "manpu_listener", "manpu_both", "manpu_clear", "manpu_gloom", "manpu_sigh", "manpu_heart", "manpu_confusion", "cafe_title", "cafe_settled", "terrace_title", "terrace_settled", "cafe_midfade", "effect_normal", "effect_zero", "hologram_sera", "hologram_sera_later", "hologram_mira", "hologram_lena", "hologram_blink", "hologram_contact"]

func _validate_and_quit() -> void:
	var errors := _validate()
	if errors.is_empty():
		errors.append_array(await _validate_routed_input())
	if not errors.is_empty():
		for issue in errors:
			printerr("FAIL: " + issue)
		get_tree().quit(1)
		return
	print("PASS: fixed 1280x900 logical canvas, native-resolution canvas rendering and letterboxing, scaled-window mouse/touch, images, fingertip mapping, three-actor framing and dialogue progression, manpu references/placement/clearing, gallery, background cover, random locations, location title lifecycle/ownership, per-actor hologram materials/strength/controls, text fit, and restart state")
	get_tree().quit(0)


func _validate() -> Array[String]:
	var errors: Array[String] = _load_errors.duplicate()
	if not errors.is_empty():
		return errors
	if (_images["open"] as Image).get_size() != (_images["closed"] as Image).get_size():
		errors.append("Open and closed eyes must have exactly the same canvas size.")
	var third_image: Image = _images["third"]
	if third_image.get_size() != Vector2i(1024, 1536) or third_image.detect_alpha() == Image.ALPHA_NONE:
		errors.append("Sera's standing image must have a transparent 1024 by 1536 canvas.")
	var speakers := {}
	for beat: Dictionary in stage_profile.dialogue:
		var actor_index := _dialogue_actor_index(String(beat["speaker"]).to_lower())
		if actor_index < 0:
			errors.append("A dialogue line names an unknown speaker.")
		speakers[beat["speaker"]] = true
	for actor: Dictionary in stage_profile.actors:
		if not speakers.has(actor["name"]):
			errors.append("Every visible actor must have a demonstration line: " + String(actor["name"]))
	if not is_finite(_touch_point.x) or not is_finite(_touch_point.y) or _touch_point.x < 0 or _touch_point.x > 1 or _touch_point.y < 0 or _touch_point.y > 1:
		errors.append("The fingertip point must be inside the image canvas.")
	if not is_finite(_touch_radius) or _touch_radius < 0.004 or _touch_radius > 0.12:
		errors.append("The fingertip radius must be between .004 and .12 of image width.")
	if not errors.is_empty():
		return errors
	var touch_image: Image = _images["touch"]
	var pixel := Vector2i(_touch_point * Vector2(touch_image.get_size()))
	pixel.x = clampi(pixel.x, 0, touch_image.get_width() - 1)
	pixel.y = clampi(pixel.y, 0, touch_image.get_height() - 1)
	if touch_image.get_pixelv(pixel).a < 0.10:
		errors.append("The declared fingertip lies on transparent image pixels.")
	for viewport_size in [DESIGN_SIZE]:
		var rect := _image_rect(viewport_size, "reach_out")
		var center := _fingertip_center(viewport_size)
		var image_point := (center - rect.position) / rect.size
		if not image_point.is_equal_approx(_touch_point):
			errors.append("Draw and input disagree after resizing to %s." % viewport_size)
		if not _inside_hotspot(center, viewport_size):
			errors.append("The fingertip center must be interactive at %s." % viewport_size)
		if _inside_hotspot(center + Vector2(_fingertip_radius(viewport_size) * 1.2, 0), viewport_size):
			errors.append("A point outside the fingertip radius must be ignored.")
		if not Rect2(Vector2.ZERO, viewport_size).encloses(rect):
			errors.append("The art leaves the viewport at %s." % viewport_size)
		for actor_index in stage_profile.actors.size():
			var actor_rect := _dialogue_rect(viewport_size, actor_index)
			if not Rect2(Vector2.ZERO, viewport_size).encloses(actor_rect):
				errors.append("A dialogue actor leaves the viewport at %s." % viewport_size)
			if actor_rect.size.y < 200.0:
				errors.append("A standing actor is too small at %s." % viewport_size)
			for other_index in range(actor_index + 1, stage_profile.actors.size()):
				# Transparent source margins may overlap; faces must stay distinct.
				var other_rect := _dialogue_rect(viewport_size, other_index)
				var face := Rect2(actor_rect.position + actor_rect.size * Vector2(0.43, 0.07), actor_rect.size * Vector2(0.22, 0.09))
				var other_face := Rect2(other_rect.position + other_rect.size * Vector2(0.43, 0.07), other_rect.size * Vector2(0.22, 0.09))
				if face.intersects(other_face):
					errors.append("The dialogue actors' faces overlap at %s." % viewport_size)
	_mode = "reach_out"
	_entry = 1.0
	_connected = false
	if _connect_at(Vector2.ZERO) or _connected:
		errors.append("An unrelated background click must not connect.")
	if not _connect_at(_fingertip_center(size)) or not _connected or _reaction <= 0:
		errors.append("Pressing the fingertip must start the acknowledgement and reaction.")
	_mode = "full_body"
	if _connect_at(_fingertip_center(size)):
		errors.append("The full-body view must not accept reach-out interactions.")
	_restart()
	if _connected or _reaction != 0.0 or _mode != "full_body" or _manual_closed:
		errors.append("Restart must restore the opening view and clear the interaction.")
	_toggle_eyes()
	if _texture_key() != "closed":
		errors.append("Closing the eyes must select the matching closed-eye image.")
	_toggle_eyes()
	if _texture_key() != "open":
		errors.append("Opening the eyes must restore the open-eye image.")
	errors.append_array(_validate_manpu())
	errors.append_array(_validate_locations())
	errors.append_array(_validate_character_effects())
	return errors


func _validate_character_effects() -> Array[String]:
	var errors: Array[String] = []
	_restart()
	_set_mode("dialogue")
	_entry = 1.0
	_update_character_layers()
	if not _character_effects["sera"]["enabled"] or _character_effects["mira"]["enabled"] or _character_effects["lena"]["enabled"]:
		errors.append("The opening effect demonstration must apply hologram only to Sera.")
	for actor: Dictionary in stage_profile.actors:
		var id := String(actor["id"])
		var sprite: TextureRect = _actor_nodes[id]
		if sprite.mouse_filter != Control.MOUSE_FILTER_IGNORE or sprite.get_index() >= _actor_overlay.get_index():
			errors.append("Character sprites must ignore input and remain behind the foreground marks.")
		for other: Dictionary in stage_profile.actors:
			if id != other["id"] and _actor_materials[id] == _actor_materials[other["id"]]:
				errors.append("Each actor must have a distinct ShaderMaterial instance.")
		_effect_target = id
		_character_effects[id]["enabled"] = true
		_set_effect_strength(35.0 + _dialogue_actor_index(id) * 20.0)
	for index in stage_profile.actors.size():
		var id := String(stage_profile.actors[index]["id"])
		if not is_equal_approx(float((_actor_materials[id] as ShaderMaterial).get_shader_parameter("strength")), 0.35 + index * 0.2):
			errors.append("Changing one actor's strength must not leak into another material.")
	var saved_effects := _character_effects.duplicate(true)
	_advance_dialogue()
	_change_scene()
	_set_mode("full_body")
	_toggle_eyes()
	_update_character_layers()
	if (_actor_nodes["mira"] as TextureRect).texture != _textures["closed"] or (_actor_nodes["mira"] as TextureRect).material != _actor_materials["mira"]:
		errors.append("Mira's blink frame must retain her character effect.")
	_set_mode("reach_out")
	_update_character_layers()
	if (_actor_nodes["mira"] as TextureRect).texture != _textures["touch"] or (_actor_nodes["mira"] as TextureRect).material != _actor_materials["mira"]:
		errors.append("Mira's contact pose must retain her character effect.")
	_set_mode("manpu_gallery")
	_update_character_layers()
	for sprite: TextureRect in _actor_nodes.values():
		if sprite.visible:
			errors.append("No character effect sprite may remain visible in the manpu gallery.")
	if _character_effects != saved_effects:
		errors.append("Dialogue, location, blink, and mode changes must preserve per-character effect settings.")
	_set_mode("dialogue")
	_effect_target = "sera"
	_set_effect_strength(0.0)
	_update_character_layers()
	if (_actor_nodes["sera"] as TextureRect).material == null or float((_actor_materials["sera"] as ShaderMaterial).get_shader_parameter("strength")) != 0.0:
		errors.append("Zero strength must exercise the shader's exact normal bypass.")
	_toggle_character_effect()
	if (_actor_nodes["sera"] as TextureRect).material != null:
		errors.append("Turning the effect off must remove the actor's material.")
	_entry = 0.0
	_update_character_layers()
	for sprite: TextureRect in _actor_nodes.values():
		if sprite.modulate.a != 0.0:
			errors.append("Character effect sprites must preserve invisible entry opacity.")
	if material != null or _actor_overlay.material != null or _line.material != null:
		errors.append("Character materials must not be applied to the background, foreground overlay, or interface.")
	_restart()
	if _effect_target != "sera" or not _character_effects["sera"]["enabled"] or _character_effects["mira"]["enabled"] or _character_effects["lena"]["enabled"] or _character_effects["sera"]["strength"] != 0.9:
		errors.append("Restart must restore the initial per-character effect demonstration.")
	return errors


func _validate_locations() -> Array[String]:
	var errors: Array[String] = []
	var rng_state := _location_rng.state
	_location_rng.seed = 709
	var seen := {}
	for attempt in 24:
		_restart()
		seen[_location_id] = true
		if not stage_profile.location_ids.has(_location_id) or _location_title_elapsed != 0.0:
			errors.append("Restart must choose a loaded location and announce its entry.")
	if seen.size() != stage_profile.location_ids.size():
		errors.append("Seeded restart selection did not exercise all locations.")
	for viewport_size in [DESIGN_SIZE]:
		for id: String in stage_profile.location_ids:
			var image_size: Vector2 = (_location_textures[id] as Texture2D).get_size()
			var rect := _background_rect(viewport_size, image_size)
			var scale_xy := rect.size / image_size
			if not rect.grow(0.01).encloses(Rect2(Vector2.ZERO, viewport_size)):
				errors.append("A location background leaves an uncovered edge at %s." % viewport_size)
			if not is_equal_approx(scale_xy.x, scale_xy.y) or not rect.get_center().is_equal_approx(viewport_size * 0.5):
				errors.append("A location background must keep its aspect ratio and centered crop.")
	_select_location("forward_command", true)
	_set_mode("dialogue")
	_dialogue_index = 3
	_entry = 0.7
	_manual_closed = true
	_location_title_elapsed = 1.0
	var cues := _active_manpu().duplicate(true)
	_change_scene()
	if _location_id == "forward_command" or _location_title_elapsed != 0.0:
		errors.append("Change scene must choose another location and retrigger its title.")
	if _mode != "dialogue" or _dialogue_index != 3 or _active_manpu() != cues or _entry != 0.7 or not _manual_closed:
		errors.append("Changing scenery must preserve dialogue, manpu, blink, and actor entry state.")
	_location_title_elapsed = 0.1
	_change_scene()
	_change_scene()
	if _location_title.text != String(_locations[_location_id]["name"]) or _location_detail.text != String(_locations[_location_id]["detail"]) or _location_title_elapsed != 0.0:
		errors.append("Rapid location changes must announce only the latest place.")
	var held_location := _location_id
	_location_title_elapsed = 1.2
	_select_location(_location_id)
	if _location_title_elapsed != 1.2:
		errors.append("Selecting an unchanged location must not repeat the title.")
	_advance_dialogue()
	_set_mode("manpu_gallery")
	_set_mode("reach_out")
	if _location_id != held_location or _location_title_elapsed != 1.2:
		errors.append("Dialogue advancement and presentation modes must preserve the location and its title clock.")
	for sample in [[0.0, 0.0], [LOCATION_TITLE_FADE_IN * 0.5, 0.5], [1.0, 1.0],
		[LOCATION_TITLE_FADE_IN + LOCATION_TITLE_HOLD + LOCATION_TITLE_FADE_OUT * 0.5, 0.5], [LOCATION_TITLE_SECONDS, 0.0]]:
		_location_title_elapsed = float(sample[0])
		_update_location_title()
		if not is_equal_approx(_location_title.modulate.a, float(sample[1])) or not is_equal_approx(_location_detail.modulate.a, float(sample[1])):
			errors.append("The location title did not follow its fade-in, hold, and fade-out lifecycle.")
		if _title.modulate.a != 0.0 or _subtitle.modulate.a != 0.0:
			errors.append("The quiet header must stay hidden while the location title appears or fades.")
	for step in 101:
		_location_title_elapsed = LOCATION_HEADER_SETTLE_SECONDS * float(step) / 100.0
		_update_location_title()
		if _location_title.modulate.a * _title.modulate.a > 0.0 or _location_detail.modulate.a * _subtitle.modulate.a > 0.0:
			errors.append("Location and quiet header strings must never be visible in the same rectangle together.")
	if _subtitle.text != String(_locations[held_location]["name"]) or _subtitle.modulate.a != 1.0:
		errors.append("A persistent location name must remain after the title fades.")
	_select_location("forward_command", true)
	var was_frozen := _capture_frozen
	_capture_frozen = false
	_process(LOCATION_HEADER_SETTLE_SECONDS + 1.0)
	if _location_title_elapsed != LOCATION_HEADER_SETTLE_SECONDS or _location_title.modulate.a != 0.0 or _subtitle.text != "Forward Command":
		errors.append("The process clock must settle on the current location's persistent label.")
	_capture_frozen = was_frozen
	_location_rng.state = rng_state
	_restart()
	return errors


func _validate_manpu() -> Array[String]:
	var errors: Array[String] = []
	if _manpu_cue_errors([{"actor": "unknown", "id": "surprise"}]).is_empty():
		errors.append("An unknown actor in a manpu cue was not refused.")
	if _manpu_cue_errors([{"actor": "mira", "id": "unknown"}]).is_empty():
		errors.append("An unknown manpu id was not refused.")
	var covered := {}
	for beat: Dictionary in stage_profile.dialogue:
		for cue: Dictionary in beat["manpu"]:
			covered[cue["id"]] = true
	for id: String in stage_profile.manpu_ids:
		# Sigh Puff is an optional emitted event, covered by this game's
		# one_shot_manpu_integration_checks, rather than a persistent line mark.
		if id != "sigh_puff" and not covered.has(id):
			errors.append("The authored demonstration never uses " + id)
	for viewport_size in [DESIGN_SIZE]:
		var stage := _manpu_stage(viewport_size)
		for actor: String in stage_profile.manpu_head_anchors:
			for id: String in stage_profile.manpu_ids:
				var mark := _manpu_rect(viewport_size, actor, id)
				var owner_rect := _dialogue_rect(viewport_size, _dialogue_actor_index(actor))
				if not stage.encloses(mark) or not is_equal_approx(mark.size.x / owner_rect.size.y, MANPU_ACTOR_HEIGHT_RATIO):
					errors.append("A manpu is clipped or loses its actor-relative size: %s/%s" % [actor, id])
				for other_index in stage_profile.actors.size():
					var actor_rect := _dialogue_rect(viewport_size, other_index)
					# Approximate face bounds measured on the installed standing sprites.
					# A mark must leave both its owner and neighboring faces unobscured.
					var face := Rect2(actor_rect.position + actor_rect.size * Vector2(0.43, 0.07),
						actor_rect.size * Vector2(0.22, 0.09))
					if face.intersects(mark):
						errors.append("A manpu covers a cast member's face at %s: %s/%s" % [viewport_size, actor, id])
		for index in stage_profile.manpu_ids.size():
			if not stage.encloses(_manpu_gallery_cell(viewport_size, index)):
				errors.append("A manpu gallery cell leaves its stage at %s." % viewport_size)
	_set_mode("dialogue")
	if _active_manpu() != [{"actor": "mira", "id": "surprise"}]:
		errors.append("The opening line must carry Mira's surprise.")
	_advance_dialogue()
	if _active_manpu() != [{"actor": "lena", "id": "sweat_drop"}]:
		errors.append("Advancing must replace Mira's surprise with Lena's sweat drop.")
	_dialogue_index = 6
	if stage_profile.dialogue[_dialogue_index]["speaker"] != "Mira" or _active_manpu() != [{"actor": "lena", "id": "sparkle"}]:
		errors.append("The recovered-signal line must mark the listening Lena while Mira speaks.")
	_dialogue_index = 3
	if _active_manpu().size() != 2:
		errors.append("The tactical-map line must show both actors' manpu together.")
	_dialogue_index = 7
	_advance_dialogue()
	if not _active_manpu().is_empty():
		errors.append("The next unmarked line must clear the preceding heart.")
	_advance_dialogue()
	if not _active_manpu().is_empty():
		errors.append("Lena's closing line must remain unmarked.")
	_advance_dialogue()
	if stage_profile.dialogue[_dialogue_index]["speaker"] != "Sera" or _active_manpu() != [{"actor": "sera", "id": "sparkle"}]:
		errors.append("Sera's closing line must show her own sparkle.")
	_advance_dialogue()
	if _dialogue_index != 0 or _active_manpu() != [{"actor": "mira", "id": "surprise"}]:
		errors.append("Reading again must restore Mira's opening line and clear Sera's mark.")
	_set_mode("full_body")
	if not _active_manpu().is_empty():
		errors.append("Leaving dialogue must clear its manpu.")
	_set_mode("dialogue")
	_restart()
	if not _active_manpu().is_empty():
		errors.append("Restart must clear the displayed manpu.")
	return errors


## Exercise native stretch and actual Control routing below and above design size.
## Mouse/touch positions enter in physical window coordinates, so Godot must
## undo both scale and letterboxing. The logical scene must never reflow.
func _validate_routed_input() -> Array[String]:
	var errors: Array[String] = []
	var original_size := get_window().size
	var was_frozen := _capture_frozen
	var initial_layout: Array[Rect2] = []
	_capture_frozen = true
	for viewport_shape: Vector2i in WINDOW_TEST_SIZES:
		get_window().size = viewport_shape
		await get_tree().process_frame
		await get_tree().process_frame
		_restart()
		errors.append_array(_validate_window_scale(viewport_shape))
		var current_layout: Array[Rect2] = [_title.get_rect(), _line.get_rect(), _reach_button.get_rect(),
			_effect_target_button.get_rect(), _background_rect(size, Vector2(2048, 1152))]
		if initial_layout.is_empty():
			initial_layout = current_layout
		elif current_layout != initial_layout:
			errors.append("Resizing the window changed the logical layout or background framing.")
		var opening_location := _location_id
		_entry = 1.0
		var mode_button_center := _reach_button.get_global_rect().get_center()
		_route_mouse(mode_button_center)
		if _mode != "reach_out":
			errors.append("The reach-out button did not receive a viewport mouse press at %s." % viewport_shape)
			continue
		var center := _fingertip_center(size)
		_entry = 0.0
		_route_mouse(center)
		if _connected:
			errors.append("The invisible entry frame accepted a fingertip press.")
		_entry = 1.0
		var output_origin := get_viewport().get_final_transform().origin
		if output_origin.x > 0.0 or output_origin.y > 0.0:
			_route_window_mouse(Vector2.ONE)
			_route_window_touch(Vector2.ONE)
			if _connected:
				errors.append("A press in the letterbox margin reached the character.")
		var miss := Vector2(14, size.y * 0.5)
		_route_mouse(miss)
		if _connected:
			errors.append("An off-target viewport mouse press connected at %s." % viewport_shape)
		_route_mouse(center)
		if not _connected or _reaction <= 0.0:
			errors.append("The fingertip did not receive its viewport mouse press at %s." % viewport_shape)
		_connected = false
		_reaction = 0.0
		_route_touch(miss)
		if _connected:
			errors.append("An off-target viewport touch connected at %s." % viewport_shape)
		_route_touch(center)
		if not _connected or _reaction <= 0.0:
			errors.append("The fingertip did not receive its viewport touch at %s." % viewport_shape)
		_route_mouse(_dialogue_button.get_global_rect().get_center())
		_entry = 1.0
		if _mode != "dialogue" or _dialogue_index != 0 or _speaker.text != "Mira":
			errors.append("The dialogue mode did not open on Mira at %s." % viewport_shape)
		_route_mouse(center)
		_route_touch(center)
		if _connected or _reaction > 0.0 or _dialogue_index != 0:
			errors.append("A dialogue background press leaked into touch interaction or progression.")
		_route_mouse(_next_button.get_global_rect().get_center())
		if _dialogue_index != 1 or _speaker.text != "Lena":
			errors.append("Next did not advance exactly once to Lena at %s." % viewport_shape)
		_route_key(KEY_SPACE)
		if _dialogue_index != 2 or _speaker.text != "Mira":
			errors.append("Space did not advance exactly once to Mira at %s." % viewport_shape)
		_route_key(KEY_ENTER)
		if _dialogue_index != 3 or _speaker.text != "Lena":
			errors.append("Enter did not advance exactly once to Lena at %s." % viewport_shape)
		if _active_manpu().size() != 2:
			errors.append("Viewport progression failed to show both actors' manpu.")
		if _location_id != opening_location:
			errors.append("Ordinary mode and dialogue inputs unexpectedly changed the location.")
		var cues := _active_manpu().duplicate(true)
		_route_mouse(_scene_button.get_global_rect().get_center())
		if _location_id == opening_location or _location_title_elapsed != 0.0 or _dialogue_index != 3 or _active_manpu() != cues:
			errors.append("The scene button must change only the place and its title at %s." % viewport_shape)
		var previous_location := _location_id
		_route_key(KEY_L)
		if _location_id == previous_location or _dialogue_index != 3 or _active_manpu() != cues:
			errors.append("Key L must change scenery once without changing the current exchange.")
		opening_location = _location_id
		# Use real routed mouse/key input; controls must only edit their target.
		_route_mouse(_effect_toggle_button.get_global_rect().get_center())
		if _character_effects["sera"]["enabled"]:
			errors.append("The effect button must turn Sera's hologram off.")
		_route_key(KEY_E)
		_route_key(KEY_T)
		if _effect_target != "mira" or not _character_effects["sera"]["enabled"]:
			errors.append("E must toggle once and T must select Mira without altering Sera.")
		_route_key(KEY_E)
		_route_mouse(_effect_strength_slider.get_global_rect().get_center())
		var mira_strength := float(_character_effects["mira"]["strength"])
		if not _character_effects["mira"]["enabled"] or mira_strength <= 0.0 or mira_strength >= 0.9 or _character_effects["sera"]["strength"] != 0.9:
			errors.append("The strength slider must change only the selected actor.")
		_route_mouse(_effect_target_button.get_global_rect().get_center())
		if _effect_target != "lena" or _character_effects["lena"]["enabled"]:
			errors.append("The target button must select Lena without enabling her effect.")
		if _dialogue_index != 3 or _active_manpu() != cues or _location_id != opening_location:
			errors.append("Effect controls must preserve conversation, manpu, and location.")
		for effect_control: Control in [_effect_target_button, _effect_toggle_button, _effect_strength_slider, _effect_strength_label]:
			if not Rect2(Vector2.ZERO, size).encloses(effect_control.get_rect()) or effect_control.get_rect().intersects(_line.get_rect()) or effect_control.get_rect().intersects(_manpu_stage(size)):
				errors.append("Effect controls must stay inside the window, below the dialogue text and outside the actor stage.")
		for button: Button in [_full_button, _reach_button, _dialogue_button, _manpu_button, _blink_button, _auto_button, _next_button, _scene_button, _restart_button, _effect_target_button, _effect_toggle_button]:
			if not Rect2(Vector2.ZERO, size).encloses(button.get_rect()):
				errors.append("A dialogue control leaves the viewport at %s." % viewport_shape)
		for label: Label in [_title, _subtitle, _location_title, _location_detail]:
			if label.get_rect().intersects(_scene_button.get_rect()) or label.get_rect().intersects(_restart_button.get_rect()) or label.get_rect().end.y > 103:
				errors.append("A location header overlaps a control or leaves the header band.")
		for id: String in stage_profile.location_ids:
			for field in [["name", _location_title], ["detail", _location_detail], ["name", _subtitle]]:
				var label: Label = field[1]
				var measured := label.get_theme_font("font").get_string_size(String(_locations[id][field[0]]),
					HORIZONTAL_ALIGNMENT_LEFT, -1, label.get_theme_font_size("font_size"))
				if measured.x > label.size.x or measured.y > label.size.y:
					errors.append("A location label does not fit at %s: %s." % [viewport_shape, id])
		var font := _line.get_theme_font("font")
		var font_size := _line.get_theme_font_size("font_size")
		for beat: Dictionary in stage_profile.dialogue:
			var text_size := font.get_multiline_string_size(String(beat["line"]), HORIZONTAL_ALIGNMENT_LEFT,
				_line.size.x, font_size, -1, TextServer.BREAK_WORD_BOUND | TextServer.BREAK_MANDATORY)
			var line_count := maxi(1, int(roundf(text_size.y / font.get_height(font_size))))
			var required_height := text_size.y + (line_count - 1) * _line.get_theme_constant("line_spacing")
			if required_height > _line.size.y:
				errors.append("An authored line does not fit at %s: %s" % [viewport_shape, beat["line"]])
		for _line_index in range(3, stage_profile.dialogue.size() - 1):
			_route_key(KEY_SPACE)
		if _dialogue_index != stage_profile.dialogue.size() - 1 or _speaker.text != "Sera" or _next_button.text != "Read again":
			errors.append("Viewport progression must reach Sera's speaker turn at %s." % viewport_shape)
		if _active_manpu() != [{"actor": "sera", "id": "sparkle"}]:
			errors.append("Sera's speaker turn must own its authored manpu.")
		_route_mouse(_next_button.get_global_rect().get_center())
		if _dialogue_index != 0 or _speaker.text != "Mira":
			errors.append("Read again must return from Sera to Mira exactly once.")
		_route_mouse(_manpu_button.get_global_rect().get_center())
		if _mode != "manpu_gallery" or not _active_manpu().is_empty():
			errors.append("The gallery button must leave dialogue and clear its active cues.")
		_route_key(KEY_3)
		_route_key(KEY_4)
		if _mode != "manpu_gallery":
			errors.append("Key 4 must open the manpu gallery.")
		if _location_id != opening_location:
			errors.append("The gallery must keep the current location.")
	get_window().size = original_size
	await get_tree().process_frame
	await get_tree().process_frame
	_capture_frozen = was_frozen
	_restart()
	return errors


func _validate_window_scale(requested_size: Vector2i) -> Array[String]:
	var errors: Array[String] = []
	var window := get_window()
	if window.size != requested_size:
		errors.append("The requested window shape was not applied: %s instead of %s." % [window.size, requested_size])
	if not size.is_equal_approx(DESIGN_SIZE) or not get_viewport_rect().size.is_equal_approx(DESIGN_SIZE):
		errors.append("The logical canvas must stay 1280 by 900 after resizing to %s." % requested_size)
	if window.content_scale_mode != Window.CONTENT_SCALE_MODE_CANVAS_ITEMS or window.content_scale_aspect != Window.CONTENT_SCALE_ASPECT_KEEP:
		errors.append("This spike must render canvas items at output resolution with the aspect ratio kept.")
	var transform := get_viewport().get_final_transform()
	var scale_factor := minf(requested_size.x / DESIGN_SIZE.x, requested_size.y / DESIGN_SIZE.y)
	var expected_extent := DESIGN_SIZE * scale_factor
	var extent := transform.basis_xform(DESIGN_SIZE)
	# Godot rounds the destination rectangle to whole output pixels.
	if absf(extent.x - expected_extent.x) > 1.0 or absf(extent.y - expected_extent.y) > 1.0 or absf(transform.x.y) > 0.0001 or absf(transform.y.x) > 0.0001:
		errors.append("The scene does not scale uniformly into the window at %s." % requested_size)
	if DisplayServer.get_name() != "headless":
		RenderingServer.force_draw(false)
		var rendered_image := get_viewport().get_texture().get_image()
		if rendered_image.get_size() != Vector2i(roundi(extent.x), roundi(extent.y)):
			errors.append("The rendered image must match output content resolution at %s." % requested_size)
	var expected_offset := (Vector2(requested_size) - extent) * 0.5
	if transform.origin.distance_to(expected_offset) > 1.0:
		errors.append("The scene is not centered within its letterbox margins at %s." % requested_size)
	for actor: String in stage_profile.manpu_head_anchors:
		var actor_rect := _dialogue_rect(size, _dialogue_actor_index(actor))
		var mark := _manpu_rect(size, actor, "surprise")
		var drawn_actor_height := transform.basis_xform(Vector2(0, actor_rect.size.y)).length()
		var drawn_mark_height := transform.basis_xform(Vector2(0, mark.size.y)).length()
		if not is_equal_approx(drawn_mark_height / drawn_actor_height, MANPU_ACTOR_HEIGHT_RATIO):
			errors.append("Manpu must retain their actor-relative size at %s: %s." % [requested_size, actor])
	print("Window scaling: window=%s logical=%s output=%s offset=%s manpu_actor_ratio=%.2f" % [window.size, size, extent, transform.origin, MANPU_ACTOR_HEIGHT_RATIO])
	return errors


func _capture_requested() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Screenshots need a real renderer; use --validate for the headless check.")
		get_tree().quit(2)
		return
	var errors := _validate()
	if errors.is_empty():
		errors.append_array(await _validate_routed_input())
	if not errors.is_empty():
		for issue in errors:
			printerr("Capture refused: " + issue)
		get_tree().quit(1)
		return
	var folder := String(_options.get("capture-dir", "res://captures"))
	DirAccess.make_dir_recursive_absolute(folder)
	var states: Array = CAPTURE_STATES if _options.has("capture-all") else [String(_options["capture-state"])]
	for state_name: String in states:
		if not CAPTURE_STATES.has(state_name):
			printerr("Unknown capture state: %s" % state_name)
			get_tree().quit(2)
			return
		_prepare_capture(state_name)
		await get_tree().process_frame
		queue_redraw()
		# A covered macOS window can stop emitting frame_post_draw. Forced draws
		# keep this finite capture independent of window focus, with no live timer.
		for _draw_index in 4:
			RenderingServer.force_draw(false)
		var image := get_viewport().get_texture().get_image()
		var path := folder.path_join(state_name + ".png")
		var error := image.save_png(path)
		if error != OK:
			printerr("Cannot save screenshot: %s" % path)
			get_tree().quit(1)
			return
		print("Captured %s" % ProjectSettings.globalize_path(path))
		var output_transform := get_viewport().get_final_transform()
		var output_extent := output_transform.basis_xform(size)
		var metadata := {"state": state_name, "viewport": [size.x, size.y], "geometry_space": "logical_canvas", "effect_time": _elapsed,
			"capture_space": "render_target", "render_size": [image.get_width(), image.get_height()], "window_size": [get_window().size.x, get_window().size.y],
			"output_rect": [output_transform.origin.x, output_transform.origin.y, output_extent.x, output_extent.y],
			"output_scale": [output_transform.x.x, output_transform.y.y],
			"stretch_mode": "canvas_items", "stretch_aspect": "keep", "manpu_actor_height_ratio": MANPU_ACTOR_HEIGHT_RATIO,
			"dialogue_index": _dialogue_index, "location": _location_id, "effects": _character_effects.duplicate(true),
			"actor_rects": {}, "effect_controls": [], "manpu_rects": []}
		for actor: Dictionary in stage_profile.actors:
			var rect := (_actor_nodes[actor["id"]] as TextureRect).get_rect()
			metadata["actor_rects"][actor["id"]] = [rect.position.x, rect.position.y, rect.size.x, rect.size.y]
		for control: Control in [_effect_target_button, _effect_toggle_button, _effect_strength_slider, _effect_strength_label]:
			var rect := control.get_rect()
			metadata["effect_controls"].append([rect.position.x, rect.position.y, rect.size.x, rect.size.y])
		for cue: Dictionary in _active_manpu():
			var rect := _manpu_rect(size, String(cue["actor"]), String(cue["id"]))
			metadata["manpu_rects"].append({"actor": cue["actor"], "id": cue["id"],
				"rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y]})
		var record := FileAccess.open(folder.path_join(state_name + ".json"), FileAccess.WRITE)
		record.store_string(JSON.stringify(metadata, "\t"))
	print("Capture complete: %d states" % states.size())
	get_tree().quit(0)


func _prepare_capture(state_name: String) -> void:
	_restart()
	var capture_location := String(_options.get("location", "forward_command"))
	if not _locations.has(capture_location):
		capture_location = "forward_command"
	if state_name.begins_with("cafe_"):
		capture_location = "forward_command"
	elif state_name.begins_with("terrace_"):
		capture_location = "perimeter_overlook"
	_select_location(capture_location, true)
	_location_title_elapsed = 1.0 if state_name.ends_with("_title") else LOCATION_HEADER_SETTLE_SECONDS
	if state_name.ends_with("_midfade"):
		_location_title_elapsed = LOCATION_TITLE_FADE_IN * 0.5
	_update_location_title()
	_capture_frozen = true
	_natural_blink = false
	_elapsed = 1.0
	_entry = 1.0
	_manual_closed = state_name == "blink"
	if state_name in ["reach_out", "connection", "debug"]:
		_mode = "reach_out"
	elif state_name in ["dialogue_mira", "dialogue_lena", "dialogue_sera"]:
		_mode = "dialogue"
		_dialogue_index = {"dialogue_mira": 0, "dialogue_lena": 1, "dialogue_sera": 10}[state_name]
	elif state_name in ["cafe_title", "cafe_settled", "terrace_title", "terrace_settled", "cafe_midfade"]:
		_mode = "dialogue"
		_dialogue_index = 3
	elif state_name == "manpu_gallery":
		_mode = "manpu_gallery"
	elif state_name in ["manpu_surprise", "manpu_listener", "manpu_both", "manpu_clear", "manpu_gloom", "manpu_sigh", "manpu_heart", "manpu_confusion"]:
		_mode = "dialogue"
		_dialogue_index = {"manpu_surprise": 0, "manpu_listener": 6, "manpu_both": 3, "manpu_clear": 8,
			"manpu_gloom": 4, "manpu_sigh": 5, "manpu_heart": 7, "manpu_confusion": 2}[state_name]
	if state_name.begins_with("hologram_") or state_name.begins_with("effect_"):
		_mode = "dialogue"
		_dialogue_index = 10
		for id: String in _character_effects:
			_character_effects[id]["enabled"] = false
		_effect_target = "sera"
		if state_name == "effect_zero":
			_character_effects["sera"]["enabled"] = true
			_character_effects["sera"]["strength"] = 0.0
		elif state_name.begins_with("hologram_"):
			if state_name == "hologram_mira":
				_effect_target = "mira"
			elif state_name == "hologram_lena":
				_effect_target = "lena"
			_character_effects[_effect_target]["enabled"] = true
		if state_name == "hologram_sera_later":
			_elapsed = 4.0
		elif state_name == "hologram_blink":
			_effect_target = "mira"
			_character_effects["sera"]["enabled"] = false
			_character_effects["mira"]["enabled"] = true
			_manual_closed = true
		elif state_name == "hologram_contact":
			_mode = "reach_out"
			_effect_target = "mira"
			_character_effects["sera"]["enabled"] = false
			_character_effects["mira"]["enabled"] = true
	if state_name == "connection":
		# Drive the real interaction, then freeze its presentation at a known time.
		_connect_at(_fingertip_center(size))
		_reaction = REACTION_SECONDS - 0.38
	_show_hotspot = state_name == "debug"
	_pointer = Vector2(-1000, -1000)
	_sync_actor_focus(false)
	_sync_manpu_animation(false)
	_update_interface()
	# Validation may leave the last button hovered in window coordinates.
	get_viewport().notify_mouse_exited()
