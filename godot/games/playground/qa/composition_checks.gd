extends SceneTree

## Checks the game-composition seam using existing local raster fixtures.
## Run with -s res://qa/composition_checks.gd, with or without --headless.
const DESIGN_SIZE := Vector2(1280, 900)
const PROFILE_PATH := "res://presentation/stage_profile.gd"
const STAGE_PATH := "res://presentation/stage.gd"
const MANPU_IDS: Array[String] = ["surprise", "confusion", "sweat_drop", "anger_vein", "sparkle", "heart", "gloom_lines", "sigh", "sigh_puff"]
const LOCATION_IDS: Array[String] = ["forward_command", "perimeter_overlook", "coastal_staging"]
var _errors: Array[String] = []
var _observations: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	await _game_roots()
	await _alternate_cast()
	await _contact_binding()
	await _empty_and_missing_profiles()
	await _malformed_landmarks()
	if _errors.is_empty():
		for observation: String in _observations:
			print("PASS composition: " + observation)
	else:
		for issue: String in _errors:
			printerr("FAIL composition: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _settle() -> void:
	await process_frame
	await process_frame
	if DisplayServer.get_name() != "headless":
		RenderingServer.force_draw()


func _dispose(node: Node) -> void:
	root.remove_child(node)
	node.queue_free()
	await process_frame


func _game_roots() -> void:
	var registry: Script = load("res://main_games.gd")
	var command_link: RefCounted = registry.call("create", "command_link")
	var other_command_link: RefCounted = registry.call("create", "command_link")
	var dating_sim: RefCounted = registry.call("create", "bishoujo_afterlight")
	var legacy_dating: RefCounted = registry.call("create", "dating_sim")
	_expect(command_link != null and dating_sim != null, "Both explicit game roots must resolve.")
	if command_link == null or dating_sim == null:
		return
	_expect(command_link != other_command_link, "Root factories must not return shared mutable singletons.")
	_expect(command_link.call("id") == "command_link" and dating_sim.call("id") == "bishoujo_afterlight", "Game roots must retain distinct identities.")
	_expect(command_link.call("entry_route") == "opening" and dating_sim.call("entry_route") == "game", "Afterlight must begin with its authored approach instead of Command Link's opening.")
	_expect(String(dating_sim.call("scene_path", "opening")).is_empty(), "Afterlight must not expose the tactical opening route.")
	_expect(command_link.call("scene_path", "game") != dating_sim.call("scene_path", "game"), "The games must have different story entry scenes.")
	_expect((command_link.call("validate_options", {"opening-variant": "b"}) as Array).is_empty(), "Command Link must retain its authored opening variants.")
	_expect(not (dating_sim.call("validate_options", {"opening-variant": "b"}) as Array).is_empty(), "Tactical opening options must not silently configure Afterlight.")
	_expect(legacy_dating != null and legacy_dating.call("id") == dating_sim.call("id"), "The former dating_sim selector must resolve the explicitly named Afterlight root.")
	_expect(dating_sim.call("title") == "Bishōjo: Afterlight", "The second game must expose its own discoverable title.")
	_expect(String(dating_sim.call("scene_path", "approach_study")).is_empty(), "Afterlight must expose story routes only.")
	var laboratory: RefCounted = registry.call("create", "presentation_lab")
	_expect(laboratory != null and not String(laboratory.call("scene_path", "approach_study")).is_empty(), "Presentation Lab must own the focused approach study.")
	var command_scene: Control = _root_scene(command_link, "game")
	var companion: Control = _root_scene(other_command_link, "game")
	var dating_scene: Control = _root_scene(dating_sim, "game")
	if command_scene == null or dating_scene == null:
		return
	var first_profile: RefCounted = command_scene.get("stage_profile")
	var second_profile: RefCounted = companion.get("stage_profile")
	_expect(first_profile != second_profile, "Preparing game scenes must allocate independent profile objects.")
	var first_actors: Array = first_profile.get("actors")
	var second_actors: Array = second_profile.get("actors")
	var original_name := String(first_actors[0]["name"])
	first_actors[0]["name"] = "Changed only in this instance"
	_expect(String(second_actors[0]["name"]) == original_name, "Nested cast records must not be shared between game profiles.")
	first_actors[0]["name"] = original_name
	companion.free()
	root.add_child(command_scene)
	command_scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(dating_scene)
	dating_scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect((command_scene.get("_load_errors") as Array).is_empty(), "Command Link's root must inject its assets before the shared stage becomes ready.")
	_expect(command_scene.get("_story_id") == "arrival", "Command Link must retain its existing first story beat.")
	_expect((dating_scene.get("_load_errors") as Array).is_empty(), "Afterlight must load its independently owned placeholder assets.")
	_expect(str(dating_scene.call("current_beat").get("id", "")) == "undeliverable", "Afterlight must begin its original linear episode.")
	_expect((dating_scene.get("_textures") as Dictionary).has("nami") and dating_scene.get("_cast") != null, "Afterlight must prepare its own ensemble cast before the story begins.")
	_expect(not _contains_video(dating_scene), "Afterlight must not instantiate the tactical opening video.")
	var host_script: Script = dating_scene.get_script()
	while host_script != null:
		_expect(host_script.resource_path != STAGE_PATH and not host_script.resource_path.begins_with("res://games/command_link/"), "Afterlight's host inheritance must not depend on the tactical stage or Command Link.")
		host_script = host_script.get_base_script()
	await _dispose(command_scene)
	await _dispose(dating_scene)
	_observations.append("distinct roots, unchanged Command Link entry, Afterlight-owned ensemble UI, and separate laboratory study ownership")


func _root_scene(game_root: RefCounted, route_id: String) -> Control:
	var path := String(game_root.call("scene_path", route_id))
	_expect(not path.is_empty(), "A game root must resolve its entry route.")
	if path.is_empty():
		return null
	var packed: PackedScene = load(path)
	var scene: Control = packed.instantiate()
	game_root.call("prepare_scene", scene, route_id, {}, {})
	return scene


func _contains_video(node: Node) -> bool:
	if node is VideoStreamPlayer:
		return true
	for child: Node in node.get_children():
		if _contains_video(child):
			return true
	return false


func _profile(actor_ids: Array[String]) -> RefCounted:
	var profile: RefCounted = load(PROFILE_PATH).new()
	var assets := {}
	var actors: Array[Dictionary] = []
	var head_anchors := {}
	var eye_anchors := {}
	var head_tops := {}
	for index in actor_ids.size():
		var actor_id: String = actor_ids[index]
		var texture_id := "portrait_" + actor_id
		assets[texture_id] = "res://assets/character_second_standing.png" if index % 2 == 0 else "res://assets/character_third_standing.png"
		actors.append({"id": actor_id, "name": actor_id.capitalize(), "texture": texture_id})
		head_anchors[actor_id] = Vector2(0.80, 0.10)
		eye_anchors[actor_id] = Vector2(0.51, 0.11)
		head_tops[actor_id] = 0.0
	profile.set("display_title", "Composition fixture")
	profile.set("asset_paths", assets)
	profile.set("actors", actors)
	profile.set("manpu_head_anchors", head_anchors)
	profile.set("dialogue_eye_anchors", eye_anchors)
	profile.set("dialogue_head_top", head_tops)
	if not actor_ids.is_empty():
		var dialogue: Array[Dictionary] = [{"speaker": actor_ids[0].capitalize(), "line": "A different cast uses the same presentation.", "manpu": [{"actor": actor_ids[0], "id": "sparkle"}]}]
		profile.set("dialogue", dialogue)
		profile.set("manpu_catalog_path", "res://assets/manpu/catalog.json")
		profile.set("manpu_ids", MANPU_IDS.duplicate())
		profile.set("location_catalog_path", "res://assets/locations/catalog.json")
		profile.set("location_ids", LOCATION_IDS.duplicate())
		profile.set("default_hologram_actor_id", actor_ids.back())
	return profile


func _stage(profile: RefCounted) -> Control:
	var stage: Control = load(STAGE_PATH).new()
	stage.set("stage_profile", profile)
	root.add_child(stage)
	stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return stage


func _alternate_cast() -> void:
	var actor_ids: Array[String] = ["vale", "jun", "ember", "rin"]
	var first := _stage(_profile(actor_ids))
	var second := _stage(_profile(actor_ids))
	await _settle()
	for stage: Control in [first, second]:
		var load_errors: Array = stage.get("_load_errors")
		_expect(load_errors.is_empty(), "A four-actor renamed profile must load: " + str(load_errors))
		if not load_errors.is_empty():
			await _dispose(first)
			await _dispose(second)
			return
		stage.call("_set_mode", "dialogue")
		stage.set("_capture_frozen", true)
		stage.set("_entry", 1.0)
		stage.call("_update_character_layers")
	await _settle()
	var nodes: Dictionary = first.get("_actor_nodes")
	_expect(nodes.keys() == actor_ids, "The stage must construct only the supplied cast, in its authored order.")
	_expect(int(first.call("_dialogue_actor_index", "mira")) == -1 and int(first.call("_dialogue_actor_index", "sera")) == -1, "The reusable stage must not require original actor IDs.")
	var previous_center := -INF
	var centers: Array[float] = []
	for actor_id: String in actor_ids:
		var sprite: TextureRect = nodes[actor_id]
		_expect(sprite.visible and sprite.texture != null, "Every alternate actor must have a visible sprite: " + actor_id)
		var center := sprite.get_rect().get_center().x
		_expect(center > previous_center, "Actor placement must follow the supplied roster order.")
		centers.append(center)
		previous_center = center
	_expect(is_equal_approx((centers.front() + centers.back()) * 0.5, DESIGN_SIZE.x * 0.5), "A different actor count must remain centered on the fixed canvas.")
	_expect(not bool(first.get("_layout_loaded")), "An omitted contact interaction must not load the Command Link fingertip layout.")
	var reach_button: Button = first.get("_reach_button")
	_expect(reach_button == null or reach_button.disabled or not reach_button.visible, "The shared controls must not offer an unconfigured contact interaction.")
	_expect((first.call("_presented_manpu_cues") as Array).size() == 1, "Manpu cues must resolve renamed actor IDs.")
	_expect((first.call("focus_dialogue_camera", "jun", 2.0, 0.0) as Array).is_empty(), "Dialogue camera targeting must accept a renamed actor.")
	_expect(String((first.call("save_dialogue_camera") as Dictionary).get("focus_id", "")) == "jun", "The camera must retain the alternate actor as its actual target.")
	_expect((first.call("exit_actor", "ember") as Array).is_empty(), "Actor exits must accept a renamed actor.")
	var second_exit: RefCounted = second.get("_character_exit")
	_expect(not bool(second_exit.call("is_exiting", "ember")), "Exiting an actor in one stage must not change another stage's transition state.")
	var second_camera: Dictionary = second.call("save_dialogue_camera")
	_expect(String(second_camera.get("focus_id", "")).is_empty(), "Focusing one stage must not move another stage's camera.")
	var first_effects: Dictionary = first.get("_character_effects")
	var second_effects: Dictionary = second.get("_character_effects")
	first_effects["vale"]["enabled"] = true
	first_effects["vale"]["strength"] = 0.25
	_expect(not bool(second_effects["vale"]["enabled"]), "Character effect records must not be shared between stage instances.")
	var first_materials: Dictionary = first.get("_actor_materials")
	var second_materials: Dictionary = second.get("_actor_materials")
	_expect(first_materials["vale"] != second_materials["vale"], "Shader material state must belong to one stage instance.")
	await _dispose(first)
	await _dispose(second)
	_observations.append("four renamed actors, camera and manpu targeting, optional contact, and isolated transition/material state")


func _contact_binding() -> void:
	var actor_ids: Array[String] = ["quinn", "riley"]
	var profile := _profile(actor_ids)
	var assets: Dictionary = profile.get("asset_paths")
	assets["reaching_quinn"] = "res://assets/character_touch.png"
	profile.set("contact_actor_id", "quinn")
	profile.set("contact_texture", "reaching_quinn")
	profile.set("contact_layout_path", "res://assets/layout.json")
	profile.set("portrait_actor_id", "riley")
	profile.set("portrait_open_texture", "portrait_riley")
	var stage := _stage(profile)
	await _settle()
	_expect((stage.get("_load_errors") as Array).is_empty(), "Contact ownership must accept a renamed actor and texture binding.")
	var nodes: Dictionary = stage.get("_actor_nodes")
	var textures: Dictionary = stage.get("_textures")
	var sprite: TextureRect = nodes["quinn"]
	var portrait: TextureRect = nodes["riley"]
	_expect(portrait.visible and not sprite.visible and portrait.texture == textures["portrait_riley"], "Portrait mode must select its own actor and texture independently of the contact role.")
	stage.call("_set_mode", "reach_out")
	stage.set("_capture_frozen", true)
	stage.set("_entry", 1.0)
	stage.call("_update_character_layers")
	await _settle()
	_expect(sprite.visible and not portrait.visible and sprite.texture == textures["reaching_quinn"], "Reach-out mode must draw only the contact owner with its bound texture.")
	stage.call("_set_mode", "dialogue")
	stage.call("_update_character_layers")
	_expect(sprite.visible and portrait.visible and sprite.texture == textures["portrait_quinn"] and portrait.texture == textures["portrait_riley"], "Returning to dialogue must restore each actor's own standing texture.")
	stage.call("_set_mode", "reach_out")
	stage.set("_entry", 1.0)
	var point: Vector2 = stage.call("_fingertip_center", DESIGN_SIZE)
	_expect(bool(stage.call("_connect_at", point)), "The configured contact actor must accept its source-image hotspot.")
	stage.call("exit_actor", "quinn")
	_expect(not bool(stage.get("_connected")) and not bool(stage.call("_connect_at", point)), "Exiting the configured contact actor must clear and gate contact.")
	stage.call("_set_mode", "full_body")
	stage.call("_update_character_layers")
	_expect(portrait.visible and not sprite.visible, "Exiting the contact actor must not hide the separately configured portrait actor.")
	await _dispose(stage)
	_observations.append("distinct portrait and contact actors, independent texture selection, and contact exit gating")


func _empty_and_missing_profiles() -> void:
	var empty := _stage(_profile([]))
	await _settle()
	_expect((empty.get("_load_errors") as Array).is_empty(), "An explicitly actor-free profile must be valid.")
	_expect((empty.get("_actor_nodes") as Dictionary).is_empty() and (empty.get("_textures") as Dictionary).is_empty(), "An actor-free stage must not import Command Link's cast or portraits.")
	_expect((empty.get("_locations") as Dictionary).is_empty(), "An omitted location catalog must not import tactical backgrounds.")
	await _dispose(empty)
	var unconfigured := _stage(null)
	await _settle()
	_expect(not (unconfigured.get("_load_errors") as Array).is_empty(), "An unconfigured stage must report the missing profile.")
	_expect(not unconfigured.can_process(), "An unconfigured stage must stop processing cleanly.")
	_expect((unconfigured.get("_actor_nodes") as Dictionary).is_empty(), "A missing profile must not fall back to the tactical game.")
	await _dispose(unconfigured)
	_observations.append("explicitly empty presentation and a clean missing-profile failure without tactical fallbacks")


func _malformed_landmarks() -> void:
	for invalid_case: Array in [
		["dialogue_eye_anchors", Vector2(INF, 0.1), "nonfinite eye position"],
		["manpu_head_anchors", Vector2(0.8, NAN), "nonfinite manpu position"],
		["dialogue_head_top", "zero", "string head landmark"],
		["dialogue_head_top", NAN, "nonfinite head landmark"],
		["dialogue_eye_anchors", null, "missing eye landmark"],
	]:
		var actor_ids: Array[String] = ["quinn"]
		var profile := _profile(actor_ids)
		var landmarks: Dictionary = profile.get(String(invalid_case[0]))
		if invalid_case[1] == null:
			landmarks.erase("quinn")
		else:
			landmarks["quinn"] = invalid_case[1]
		var stage := _stage(profile)
		await _settle()
		var description := String(invalid_case[2])
		_expect(not (stage.get("_load_errors") as Array).is_empty(), "Malformed profile must report " + description + ".")
		_expect(not stage.can_process(), "Malformed profile must stop processing: " + description + ".")
		_expect((stage.get("_actor_nodes") as Dictionary).is_empty() and (stage.get("_textures") as Dictionary).is_empty(), "Malformed landmarks must fail before loading assets or creating actor nodes: " + description + ".")
		await _dispose(stage)
	_observations.append("missing, nonfinite, and nonnumeric landmarks rejected before rendering or asset loading")
