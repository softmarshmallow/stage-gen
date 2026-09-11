extends SceneTree

## The playable ensemble episode is exercised through the actual application
## shell. Native capture mode also checks both authored and doubled resolution.
const DESIGN_SIZE := Vector2(1280, 900)
const EPISODE_BEAT_COUNT := 57
const HEROINE_IDS := ["nami", "yuzu", "sena", "riko"]
const TRANSMISSION_BEATS := ["eira_on_the_relay", "a_voice_in_the_glass", "the_return_channel", "one_private_question", "follow_the_pulse", "eira_signs_off"]
const KEEPER_REALM_BEATS := ["the_unlit_house", "the_keeper", "the_price_of_return", "a_name_is_not_consent", "the_room_refuses", "nami_beyond_the_wall", "follow_the_warmth"]
const CAPTURE_DIRECTORY := "res://tests/afterlight-ensemble"
const IMPACT_SHAKE := preload("res://addons/game_presentation/camera/impact_shake.gd")
const CHECKPOINT_KINDS := ["walk", "eye", "handoff", "detail", "projection", "monologue", "exit", "establish", "rift", "contact"]
const CAPTURE_BEATS := ["undeliverable", "eyes_on_nami", "no_ordinary_post", "a_glass_record", "caught_in_the_light", "the_unlit_house", "the_keeper", "the_price_of_return", "the_room_refuses", "only_a_second", "sena_takes_over", "reading_room", "riko_on_the_glass", "eira_on_the_relay", "the_return_channel", "eira_signs_off", "follow_the_diagram", "riko_signs_off", "everyone_accounted_for", "the_next_arrival"]
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _capture_count := 0


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-ensemble")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Afterlight ensemble captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "afterlight", "Run with --game afterlight.")
	if _app.selected_game_id != "afterlight":
		await _dispose_app()
		_finish()
		return
	_expect(_active()._load_errors.is_empty(), "The authored episode must initialize: " + str(_active()._load_errors))
	if _errors.is_empty():
		for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
			await _episode_at_size(window_size)
	await _dispose_app()
	_finish()


func _dispose_app() -> void:
	# Let stopped typing playback release its audio-server references before
	# quitting; headless checks can otherwise exit in the final sound's buffer.
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame


func _episode_at_size(window_size: Vector2i) -> void:
	root.size = window_size
	_expect(_app.open_route("new_game"), "A new episode must be reachable.")
	await _settle()
	var game := _active()
	_expect(game.set_language("ko").is_empty(), "Korean must be available.")
	var visited: Array[String] = []
	var cast_seen: Array[String] = []
	var checkpoints := {}
	var effects_seen := {}
	var completed := false
	_expect(game.beats.size() == EPISODE_BEAT_COUNT, "The complete episode must include the private relay call before ward repair and the later excursion.")
	_expect(game.content.get("guests", []).size() == 4 and game.content.get("supporting_cast", []).size() == 2, "The remote operator and antagonist must be supporting characters, separate from the four heroine profiles.")
	var backgrounds: Array = game.content.get("backgrounds", [])
	_expect(backgrounds.size() >= 4, "The otherworld encounter and private relay call must each have a prepared location.")
	if backgrounds.size() >= 3:
		_expect(backgrounds[2].get("id") == "keeper_hall", "The third background must bind the Hall of Unclaimed Names.")
		for warm_index in 2:
			_expect(backgrounds[2].get("path") != backgrounds[warm_index].get("path"), "The otherworld hall must use distinct artwork from either warm lounge.")
	if backgrounds.size() >= 4:
		_expect(backgrounds[3].get("id") == "relay_alcove", "The fourth background must bind the dedicated relay alcove.")
		for other_index in 3:
			_expect(backgrounds[3].get("path") != backgrounds[other_index].get("path"), "The relay alcove must use distinct artwork from the lounges and infernal hall.")
	for iteration in game.beats.size() + 4:
		game = _active()
		var beat: Dictionary = game.current_beat()
		var id := str(beat["id"])
		var kind := str(beat["type"])
		visited.append(id)
		_expect(game._load_errors.is_empty(), "Beat must initialize without errors: " + id + " " + str(game._load_errors))
		if not game._load_errors.is_empty(): break
		_expect(game._text(game._resolved_text_key(beat)) != "[" + game._resolved_text_key(beat) + "]", "Every beat needs translated text: " + id)
		_expect(not game.has_method("_select_guest"), "Play must follow the ensemble episode without a cast selector.")
		game._process(0.1 if id == "only_a_second" else (0.23 if kind in ["handoff", "exit", "rift"] else 0.63))
		await _settle()
		_expect(str(game.current_beat()["id"]) == id, "Every beat must hold for explicit continuation: " + id)
		_check_coverage(game, id)
		_check_ominous_effects(game, id, effects_seen)
		_check_transmission(game, id)
		if id == "between_addresses":
			_expect(game._background_index == 2 and game._black.visible, "The dedicated hall must bind behind the black monologue before its reveal.")
		if KEEPER_REALM_BEATS.has(id):
			_expect(game._background_index == 2, "The encounter must retain its dedicated hall throughout the otherworld sequence: " + id)
		if id == "the_unlit_house":
			_expect(game._cast.visible_ids().is_empty() and not game._portrait.visible, "The hall must first appear without a character obscuring the location.")
		if id in ["the_return", "a_hand_to_hold", "a_touch_that_stays", "only_a_second"]:
			_expect(game._background_index == 1, "The return must restore the warm reading lounge: " + id)
		for actor_id: String in game._cast.visible_ids():
			if not cast_seen.has(actor_id): cast_seen.append(actor_id)
		if id == "the_seal_answers":
			_expect(visited.size() >= 2 and visited[-2] == "the_reroute", "The realm-shift setup must follow the ward repair, rather than the first portrait encounter.")
			for actor_id: String in HEROINE_IDS:
				_expect(cast_seen.has(actor_id), "Every heroine must be introduced before the realm excursion: " + actor_id)
			for introduction: String in ["eyes_on_nami", "a_glass_record", "sena_takes_over", "riko_on_the_glass", "the_signal", "the_reroute"]:
				_expect(visited.has(introduction), "The familiar ensemble and ward repair must precede the shift: " + introduction)
			for call_beat: String in TRANSMISSION_BEATS:
				_expect(visited.has(call_beat), "The complete private relay conversation must precede ward repair and the realm shift: " + call_beat)
			_expect(not cast_seen.has("keeper"), "The distinct antagonist must remain unseen before the excursion.")
		if id == "scarlet_pressure":
			_expect(visited.size() >= 2 and visited[-2] == "the_seal_answers", "The first rift must follow its later story setup.")
		if (CHECKPOINT_KINDS.has(kind) and not checkpoints.has(kind)) or TRANSMISSION_BEATS.has(id):
			await _language_and_detour(game, id)
			if CHECKPOINT_KINDS.has(kind): checkpoints[kind] = true
			game = _active()
			_check_transmission(game, id)
		if id == "the_keeper":
			_expect(game._cast.visible_ids() == ["keeper"] and beat.get("speaker") == "keeper", "The villain must appear as the distinct Keeper, not a heroine's borrowed appearance.")
			_expect(game._profile("keeper").get("path", "").length() > 0, "The Keeper must bind her own prepared image.")
			for actor_id: String in HEROINE_IDS:
				_expect(game._profile("keeper").get("path") != game._profile(actor_id).get("path"), "The Keeper must not reuse a heroine image: " + actor_id)
			_expect(game._local_corruption.visible and game._barrier.visible, "The Keeper must hold live aura and refraction during the laboratory detour.")
			await _language_and_detour(game, id)
			game = _active()
		if kind == "rift":
			_expect(game._shake.is_active(), "Rift coverage must be tested while the shake is still active: " + id)
			for frame in 16:
				game._process(0.0125)
				var pose: Dictionary = game._camera.sample()
				var zoom := float(pose["zoom"])
				var base := Transform2D(Vector2(zoom, 0), Vector2(0, zoom), Vector2(float(pose["offset_x"]), float(pose["offset_y"])))
				_expect(IMPACT_SHAKE.can_compose(base, game._base_background, DESIGN_SIZE), "The actual interpolating camera base must permit shake overscan: " + id)
				_check_coverage(game, id + " during impact")
		if kind == "monologue":
			var frozen := _world_snapshot(game)
			game._process(0.2)
			_expect(_same(frozen, _world_snapshot(game)), "Monologue must freeze every world controller and actor: " + id)
		if id == "only_a_second":
			var already_revealed: bool = game._reveal.sample()["phase"] == "holding"
			_expect(not game._cast._manpu.one_shots().is_empty() if already_revealed else game._cast._manpu.one_shots().is_empty(), "Nami's relief puff must follow the actual text reveal, including immediate full text for a ready voice.")
			var expected_age: float = (game._elapsed - game._manpu_event_time if already_revealed else 0.0) + 0.1
			var reveal_state: Dictionary = game._reveal.get_state()
			var remaining := maxf(0.0, float(str(reveal_state["text"]).length()) / float(reveal_state["chars_per_second"]) - float(reveal_state["elapsed"]))
			game._process(remaining + 0.1)
			var puffs: Array = game._cast._manpu.one_shots()
			_expect(puffs.size() == 1 and puffs[0]["actor"] == "nami" and puffs[0]["id"] == "sigh_puff", "Nami must visibly sigh in relief after the return line settles.")
			_expect(is_equal_approx(game._elapsed - game._manpu_event_time, expected_age), "The return puff must retain its actual after-reveal age.")
		if _capture_enabled and CAPTURE_BEATS.has(id):
			if kind not in ["handoff", "exit", "eye", "establish", "rift"] and id != "only_a_second":
				game._advance_clocks(1.0)
				game._reveal.request_advance()
				game._render()
			_check_transmission(game, id)
			await _capture(id + "-" + str(window_size.x), game)
		if id == "everyone_accounted_for":
			_expect(game._cast.visible_ids() == HEROINE_IDS, "The physical finale must reunite the four heroines without either supporting character.")
		if kind == "ending":
			game._reveal.request_advance()
			game._next()
			_expect(game._paused and str(game.current_beat()["id"]) == id, "Finishing must open the game menu without losing the final beat.")
			completed = true
			break
		if game._cinematic() and not game._cinematic_complete():
			game._next()
			_expect(str(game.current_beat()["id"]) == id and game._cinematic_complete(), "A cinematic skip must finish motion before advancing the story: " + id)
			_expect(game._dialogue.visible, "Cinematic text must become readable after motion: " + id)
			if kind == "handoff":
				_expect(game._cast.visible_ids() == ["yuzu", "sena"], "Handoff must settle to its survivor/arrival pair before continuing.")
			if kind == "exit":
				_expect(not game._cast.visible_ids().has("riko"), "Sign-off must finish before the next dialogue.")
			if kind == "rift":
				_expect(not game._shake.is_active() and float(game._shake.sample()["envelope"]) == 0.0, "Settling a rift must finish its shake without residual displacement: " + id)
				_check_coverage(game, id + " after settlement")
				if id == "the_return":
					for field: Control in [game._heat_haze, game._world_corruption, game._local_corruption, game._barrier]:
						_expect(field.get_strength() == 0.0 and not field.visible, "The return must finish fading all ominous fields before continuation.")
		for click_index in 4:
			if str(game.current_beat()["id"]) != id: break
			if _fulfill_contact_gate(game):
				pass
			elif game._choice_pending() and game._reveal.sample()["phase"] == "holding":
				game._choose("help_first")
			else:
				game._next()
		_expect(str(game.current_beat()["id"]) != id, "At most reveal/continue actions must advance a settled beat: " + id)
		await _settle()
	_expect(completed and visited.size() == EPISODE_BEAT_COUNT, "All authored beats must play through the private call and explicit choice to the ending at " + str(window_size))
	_expect(cast_seen.size() == 6 and cast_seen.has("keeper") and cast_seen.has("eira"), "The plot must introduce all four heroines, the remote operator, and the distinct antagonist.")
	_expect(checkpoints.size() == CHECKPOINT_KINDS.size(), "Every cinematic/monologue checkpoint family must be exercised.")
	_expect(effects_seen.size() == 5, "The main episode must demonstrate barrier, heat, scene corruption, actor corruption, and environmental corruption.")


func _fulfill_contact_gate(game: Control) -> bool:
	if game.current_beat().get("type") != "contact": return false
	var id := str(game.current_beat()["id"])
	if not bool(game.contact_target()["ready"]): game._next()
	var target: Dictionary = game.contact_target()
	_expect(bool(target["ready"]), "The required contact must become ready after text reveal.")
	_expect(game._try_contact(target["center"]), "Story traversal must explicitly fulfill the authored contact target.")
	game._process(1.0)
	_expect(str(game.current_beat()["id"]) != id, "The confirmed contact must finish its feedback before continuing.")
	return true


func _check_transmission(game: Control, id: String) -> void:
	var in_call := TRANSMISSION_BEATS.has(id)
	var display: Dictionary = game._transmission_display.snapshot()
	var projected: Array[String] = []
	for actor_id: String in game._cast._projection:
		if bool(game._cast._projection[actor_id]): projected.append(actor_id)
	_expect(not bool(game._cast._projection["riko"]), "Riko must remain physically present whenever staged in the main episode: " + id)
	if in_call:
		_expect(game._cast.visible_ids() == ["eira"] and not game._cast.visible and not game._portrait.visible, "The private call must replace the standing cast with Eira's display, including the courier's replies: " + id)
		_expect(projected == ["eira"], "Only Eira may use transmission treatment during the private call: " + id)
		_expect(bool(display["visible"]) and display["actor_id"] == "eira", "The floating display must carry Eira's portrait throughout the private conversation: " + id)
		_expect(bool(display["feed_clipped"]) and float(display["hologram_strength"]) > 0.0, "The TV treatment must use the clipped portrait feed and a live material: " + id)
		_expect(is_equal_approx(float(display["effect_time"]), game._effect_time), "The TV treatment and floating frame must use the host world clock: " + id)
		var frame: Rect2 = display["frame_rect"]
		var feed: Rect2 = display["feed_rect"]
		var portrait: Rect2 = display["portrait_rect"]
		_expect(Rect2(Vector2.ZERO, DESIGN_SIZE).encloses(frame), "The complete floating display must remain inside the viewport: " + id)
		_expect(frame.encloses(feed) and feed.has_area() and portrait.grow(0.01).encloses(feed), "The framed screen must contain a fully covered portrait feed: " + id)
		_expect(feed.encloses(display["face_rect"]) and feed.has_point(display["eye_point"]), "Eira's face and eyes must remain inside the TV frame at wide and close camera positions: " + id)
		_expect(frame.position.y >= 112.0 and not frame.intersects(game._speaker.get_rect()) and not frame.intersects(game._line.get_rect()), "The floating display must leave the header and dialogue text unobscured: " + id)
		_expect(game._background_index == 3, "Every private call turn must retain the relay alcove: " + id)
		_expect(game._profile("eira").get("path", "").length() > 0, "Eira must bind her own prepared character image.")
		for other_id: String in HEROINE_IDS + ["keeper"]:
			_expect(game._profile("eira").get("path") != game._profile(other_id).get("path"), "The remote operator must not reuse another cast member's image: " + other_id)
	else:
		_expect(projected.is_empty() and not game._cast.visible_ids().has("eira"), "Leaving the private call must clear Eira and all transmission state: " + id)
		_expect(not bool(display["visible"]) and str(display["actor_id"]).is_empty(), "The framed portrait display must disappear completely outside the call: " + id)
		_expect(display["frame_rect"] == Rect2() and float(display["hologram_strength"]) == 0.0 and float(display["effect_time"]) == 0.0, "Clearing the call must reset its frame and live shader state: " + id)
		for actor_id: String in game._cast.visible_ids():
			_expect(game._cast._sprites[actor_id].material == null, "Visible physical actors must not inherit the transmission material: " + id + " / " + actor_id)
	if id == "hold_the_message":
		_expect(game._background_index == 3 and game._black.visible and game._cast.visible_ids().is_empty(), "The dedicated relay scene must bind beneath its black entrance monologue.")
	elif id == "relay_return":
		_expect(game._background_index == 1 and game._black.visible and game._cast.visible_ids().is_empty(), "The return monologue must clear the call and restore the reading lounge beneath black.")
	elif not in_call:
		_expect(game._background_index != 3, "The dedicated relay location must not leak into the physical ensemble or infernal encounter: " + id)
	if id == "follow_the_diagram":
		_expect(game._background_index == 1 and game._cast.visible_ids() == ["yuzu", "sena", "riko"], "After the call, ward repair must resume with the physical ensemble in the reading lounge.")


func _language_and_detour(game: Control, id: String) -> void:
	var before := _world_snapshot(game)
	var saved: Dictionary = game.save_game()
	var fraction := float(saved["reveal_fraction"])
	var elapsed: float = game._elapsed
	_expect(game.set_language("en").is_empty(), "English switch must succeed during " + id)
	_expect(_same(before, _world_snapshot(game)) and is_equal_approx(game._elapsed, elapsed), "Language change must preserve world time and framing: " + id)
	_expect(is_equal_approx(float(game.save_game()["reveal_fraction"]), fraction), "Language change must preserve normalized typewriter progress: " + id)
	_expect(game.set_language("ko").is_empty(), "Korean switch must succeed during " + id)
	var before_detour := _world_snapshot(game)
	var words: Dictionary = game._reveal.sample()
	game._toggle_pause()
	var paused_state := _world_snapshot(game)
	game._process(2.0)
	_expect(_same(paused_state, _world_snapshot(game)), "The game menu must pause world clocks: " + id)
	_expect(_app.open_route("game:lab"), "The dedicated laboratory must be reachable from the episode.")
	await _settle()
	_expect(_app.selected_game_id == "lab", "Technical demonstrations must live in the laboratory game.")
	_expect(_app.open_route("game:afterlight"), "The episode must resume after the laboratory detour.")
	await _settle()
	var restored := _active()
	_expect(restored._load_errors.is_empty(), "Restored episode must validate: " + id + " " + str(restored._load_errors))
	_expect(str(restored.current_beat()["id"]) == id and not restored._paused, "Detour must resume the exact playable beat: " + id)
	_expect(_same(before_detour, _world_snapshot(restored)), "Replay restore must preserve composed transforms and actor effects: " + id)
	_expect(restored._reveal.sample() == words and restored.get_language() == "ko", "Detour must preserve Korean text and reveal progress: " + id)


func _world_snapshot(game: Control) -> Dictionary:
	var actors := {}
	for id: String in game._textures:
		actors[id] = {"appearance": game._cast._appearance(id), "posed": game._cast._posed_rect(id), "projection": game._cast._projection[id]}
	return {
		"contact": game.contact_target(), "contact_time": game._contact_time,
		"world": game._world_transform(), "background": game.presented_background_rect(),
		"background_id": game.content["backgrounds"][game._background_index]["id"],
		"camera": game._camera.get_state(), "walking": game._walking.get_state(),
		"eye": game._eye.get_state(), "establish": game._establish.get_state(), "drift": game._drift.get_state(),
		"actors": actors, "manpu": game._cast._manpu.get_state(), "projection_time": game._cast._elapsed,
		"transmission_display": game._transmission_display.snapshot(),
		"shake": game._shake.get_state(), "effect_time": game._effect_time,
		"heat": _field_snapshot(game._heat_haze), "barrier": _field_snapshot(game._barrier),
		"world_corruption": _field_snapshot(game._world_corruption), "local_corruption": _field_snapshot(game._local_corruption),
	}


func _field_snapshot(field: Control) -> Dictionary:
	# Hidden retained geometry is not visible state and need not be reconstructed
	# by replaying intermediate renders; strength and shader clocks still must match.
	return {"strength": field.get_strength(), "time": field.get_time(), "rect": field.get_source_rect() if field.visible else Rect2(),
		"visible": field.visible, "settings": field.get_settings(),
		"pattern_transform": field.get_pattern_transform() if field.has_method("get_pattern_transform") else Transform2D.IDENTITY,
		"uniform_strength": field._field_material.get_shader_parameter("strength"),
		"uniform_time": field._field_material.get_shader_parameter("field_time"),
		"has_source": field.get_source() != null if field.visible and field.has_method("get_source") else false}


func _check_ominous_effects(game: Control, id: String, effects_seen: Dictionary) -> void:
	var beat: Dictionary = game.current_beat()
	var fields := {"heat": game._heat_haze, "barrier": game._barrier, "scene_corruption": game._world_corruption}
	for key: String in fields:
		var field: Control = fields[key]
		_expect(is_equal_approx(field.get_time(), game._effect_time), "Every procedural field must use the persistent world clock: " + id + " / " + key)
		if float(beat.get(key, 0.0)) > 0.0:
			_expect(field.visible and field.get_strength() > 0.0, "An authored field must appear in main play: " + id + " / " + key)
			effects_seen[key] = true
		else:
			_expect(not field.visible and field.get_strength() == 0.0, "An unauthored field must not leak into the next beat: " + id + " / " + key)
	var target: Dictionary = beat.get("corruption", {})
	if target.has("actor"):
		var actor_id := str(target["actor"])
		_expect(game._local_corruption.get_source() == game._textures[actor_id], "Actor corruption must reuse the current cast texture: " + id)
		_expect(game._local_corruption.get_source_rect().is_equal_approx(game._cast.get_presented_actor_rect(actor_id)), "Actor aura must follow final camera and actor motion: " + id)
		_expect(game._local_corruption.visible and game._local_corruption.get_strength() > 0.0, "Actor corruption must be visible in the encounter: " + id)
		effects_seen["actor_corruption"] = true
	elif target.has("area"):
		_expect(game._local_corruption.get_source() == null and game._local_corruption.visible, "Environmental corruption must work without a sprite or bespoke mask: " + id)
		_expect(game._local_corruption.get_source_rect().is_equal_approx(game._world_transform() * (target["area"] as Rect2)), "Environmental corruption must follow the world camera: " + id)
		effects_seen["area_corruption"] = true
	else:
		_expect(game._local_corruption.get_strength() == 0.0 and not game._local_corruption.visible, "Local corruption must be disabled without a current target: " + id)
	if beat.has("speaker_name"):
		_expect(game._speaker.text == game._text(str(beat["speaker_name"])), "The antagonist and distant speakers need their authored localized name: " + id)
	if not beat.has("shake"):
		_expect(not game._shake.is_active(), "Leaving a shaken beat must cancel its camera cue: " + id)
	if id == "only_a_second":
		_expect(game._background_index == 1 and game._cast.visible_ids() == HEROINE_IDS, "The return must restore the reading room and familiar ensemble without the antagonist.")
		_expect(not game._shake.is_active(), "The safe room must have no remaining impact shake.")


func _check_coverage(game: Control, context: String) -> void:
	var rect: Rect2 = game.presented_background_rect()
	_expect(rect.position.x <= 0.01 and rect.position.y <= 0.01 and rect.end.x >= DESIGN_SIZE.x - 0.01 and rect.end.y >= DESIGN_SIZE.y - 0.01, "The composed camera must keep the background covered: " + context)
	if game.current_beat()["type"] == "detail":
		var portrait := Rect2(game._portrait.position, game._portrait.size)
		_expect(portrait.position.x < -20 and portrait.position.y < -100 and portrait.end.x > DESIGN_SIZE.x + 20 and portrait.end.y > DESIGN_SIZE.y + 20, "Detail framing must retain overscan for drift and halo.")
		_expect(game._halo.visible and game._halo.get_source_rect().is_equal_approx(portrait), "Halo must follow the unchanged detail sprite geometry.")


func _same(a: Variant, b: Variant) -> bool:
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size(): return false
		for key: Variant in a:
			if not b.has(key) or not _same(a[key], b[key]): return false
		return true
	if a is Array and b is Array:
		if a.size() != b.size(): return false
		for index in a.size():
			if not _same(a[index], b[index]): return false
		return true
	if (a is float or a is int) and (b is float or b is int): return is_equal_approx(float(a), float(b))
	if a is Transform2D and b is Transform2D: return a.is_equal_approx(b)
	if a is Rect2 and b is Rect2: return a.is_equal_approx(b)
	return a == b


func _capture(label: String, game: Control) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(CAPTURE_DIRECTORY) == OK, "The ensemble capture directory must be writable.")
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Capture must use native window resolution.")
	_expect(picture.save_png(CAPTURE_DIRECTORY.path_join(label + ".png")) == OK, "The ensemble capture must save: " + label)
	var metadata := FileAccess.open(CAPTURE_DIRECTORY.path_join(label + ".json"), FileAccess.WRITE)
	metadata.store_string(JSON.stringify({"beat": game.current_beat()["id"], "language": game.get_language(), "window": [picture.get_width(), picture.get_height()], "cast": game._cast.visible_ids(), "checkpoint": game.save_game()}, "\t"))
	_capture_count += 1


func _freeze_route(node: Node) -> void:
	if node.has_method("current_beat"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _active() -> Control:
	return _app.active_scene


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _active() != null: _active().set_process(false)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)


func _finish() -> void:
	for issue: String in _errors: printerr("FAIL Afterlight ensemble: " + issue)
	if _errors.is_empty():
		print("PASS Afterlight ensemble: " + str(EPISODE_BEAT_COUNT) + " authored beats and one explicit convergent choice, four physical heroines, six-turn solo Eira portrait inside a floating TV in the relay laboratory, confined transmission treatment and readable UI, clean ensemble return, later distinct Keeper and infernal hall, live transmission/shake/corruption laboratory detours, Korean/English reveal continuity, world coverage, monologue/pause clocks and 1x/2x framing")
		if _capture_count > 0: print("Afterlight ensemble captures: " + str(_capture_count))
	quit(0 if _errors.is_empty() else 1)
