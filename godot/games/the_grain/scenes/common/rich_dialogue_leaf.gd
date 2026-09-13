class_name GrainRichDialogueLeaf
extends HostDialogueLeaf

## The case's existing framed UI, driven by one rich Scenario invocation.
## The game owns textures, layout, input routing and saved-file policy.
const INVOCATION_HOST = preload("res://addons/scenario_runtime/bindings/host.gd")
const JSON_DATA = preload("res://addons/scenario_runtime/content/json_data.gd")
const FRAME_BINDING = preload("res://presentation/grain_frame.gd")
const CAPABILITIES_PATH := "res://presentation/scenario_capabilities.json"
const SESSION_ID := "grain_dialogue"

var _host = INVOCATION_HOST.new()
var _frame_binding = FRAME_BINDING.new()
var _rich_document: Dictionary = {}
var _catalog_document: Dictionary = {}
var _capabilities: Dictionary = {}
var _started := false
var _last_visit := ""
var _last_statement := ""
var _reading_start := 0.0
var _reported_reveal := false
var _current_frame: Dictionary = {}
var _frame_elapsed := 0.0
var _world: Control = null
var _old_background: TextureRect = null
var _new_background: TextureRect = null
var _old_cast: Dictionary = {}
var _new_cast: Dictionary = {}
var _stage_textures: Dictionary = {}
var _actor_textures: Dictionary = {}
var _frame_geometry: Dictionary = {}
var _carried_facts: Array[String] = []


static func open_rich(run_dir: String, scenario_id: String, carried: PackedStringArray = PackedStringArray(), resume: Variant = null) -> Variant:
	if scenario_id.is_empty() or scenario_id != scenario_id.to_lower() or not scenario_id.is_valid_identifier():
		return KernelRefusal.of("dialogue/scenario", "The authored scenario identity is invalid.")
	var package := HostRunDir.open(run_dir, Callable(), "", DOCUMENT_REF)
	if package == null:
		return KernelRefusal.of("dialogue/run", "%s has no readable %s" % [run_dir, DOCUMENT_REF], run_dir)
	var document: Variant = DialogueBundle.parse(package.manifest, scenario_id)
	if KernelRefusal.is_refusal(document):
		return document
	var source := _read_json("res://narrative/%s.json" % scenario_id)
	if source.has("error"):
		return _rich_refusal(source)
	var catalog := _read_json("res://narrative/catalog.json")
	if catalog.has("error"):
		return _rich_refusal(catalog)
	return of_rich(package, document, source.value, catalog.value, carried, resume)


static func of_rich(package: HostRunDir, document: Dictionary, source: Dictionary, catalog: Dictionary, carried: PackedStringArray = PackedStringArray(), resume: Variant = null) -> Variant:
	var capabilities := _read_json(CAPABILITIES_PATH)
	if capabilities.has("error"):
		return _rich_refusal(capabilities)
	if not capabilities.value.get("grain_frame") is Dictionary or capabilities.value.size() != 1:
		return KernelRefusal.of("dialogue/capabilities", "The game requires its installed grain_frame capability schema.")
	if source.get("scenario_id") != document.get("scenarioId"):
		return KernelRefusal.of("dialogue/scenario", "The authored sequence does not match this prepared scene binding.")
	var sheets := HostUiSheets.of(package, document.get("ui"))
	if not sheets.has("panel_frame") or not sheets.has("button_rect"):
		return KernelRefusal.of("dialogue/ui", "This prepared scene has no panel or button art.")
	var placement: Variant = DialogueFraming.placement(float(document.placement.framingZoom), float(document.placement.sourceFramingZoom))
	if KernelRefusal.is_refusal(placement):
		return placement
	var made := GrainRichDialogueLeaf.new()
	made._package = package
	made._sheets = sheets
	made.bundle = document
	made._placement = placement
	made._rich_document = source.duplicate(true)
	made._catalog_document = catalog.duplicate(true)
	made._capabilities = capabilities.value
	for fact: String in carried:
		if fact.is_empty() or fact != fact.to_lower() or not fact.is_valid_identifier():
			made.free()
			return KernelRefusal.of("dialogue/facts", "The case supplied an invalid fact identity.")
		if not made._carried_facts.has(fact):
			made._carried_facts.append(fact)
	made._carried_facts.sort()
	made.mouse_filter = Control.MOUSE_FILTER_STOP
	made.clip_contents = true
	made.size = Vector2(DialogueLayout.STAGE_WIDTH, DialogueLayout.STAGE_HEIGHT)
	var registered: Dictionary = made._host.register_capability("grain_frame", made._capabilities.grain_frame, made._frame_binding)
	if registered.has("error"):
		made.free()
		return _rich_refusal(registered)
	var admitted: Dictionary = made._host.prepare(source, catalog, made._policy(), {"stage": made})
	if admitted.has("error"):
		made.free()
		return _rich_refusal(admitted)
	made.program = admitted.program
	var presentation_errors := made._admit_presentation()
	if not presentation_errors.is_empty():
		made.free()
		return KernelRefusal.of("dialogue/presentation", "; ".join(presentation_errors))
	var built: Variant = made._build()
	if KernelRefusal.is_refusal(built):
		made.free()
		return built
	made._build_rich_world()
	var initial_facts := {}
	for fact: String in made.program.facts:
		if bool(made.program.facts[fact].get("external", false)):
			initial_facts[fact] = carried.has(fact)
	var result: Dictionary
	if resume == null:
		result = made._host.invoke(source, catalog, made._policy(), {"stage": made}, initial_facts)
	elif resume is Dictionary and resume.get("kind") == "grain-scenario-snapshot" and resume.get("schema_version") == 1 and resume.get("carried_facts") is Array and resume.carried_facts == made._carried_facts and resume.get("session") is Dictionary and resume.size() == 4:
		result = made._host.restore(source, catalog, made._policy(), {"stage": made}, resume.session)
	else:
		result = {"error": {"message": "The saved conversation is not a Scenario checkpoint."}}
	if result.has("error"):
		made.free()
		return KernelRefusal.of("dialogue/save-incompatible" if resume != null else "dialogue/scenario", "%s%s" % [str(result.error.get("message", "Scenario could not start.")), " Start the case again to use the updated episode; the saved file has been preserved." if resume != null else ""])
	made._started = true
	# A saved backlog pause is transient game UI state. The live case reapplies
	# its current cover policy after mounting the leaf.
	if made._host.view(SESSION_ID).get("status") == "suspended":
		made._host.resume(SESSION_ID)
	made._sync_invocation()
	return made


func _ready() -> void:
	_start_tracks()


func _process(delta: float) -> void:
	step(delta)


func _exit_tree() -> void:
	if _started:
		_host.cancel(SESSION_ID, "game_scene_exit")
	_silence()


func step(delta: float) -> void:
	if not _started or _suspended or _state.get("outcome") != null or not is_finite(delta) or delta <= 0.0:
		return
	var result: Dictionary = _host.tick(SESSION_ID, delta)
	if result.has("error"):
		push_warning("The Grain presentation: " + str(result.error.message))
		return
	_sync_invocation()


func state() -> Dictionary:
	return _state.duplicate(true)


func snapshot() -> Dictionary:
	return {"kind": "grain-scenario-snapshot", "schema_version": 1, "carried_facts": _carried_facts.duplicate(), "session": _core_snapshot()} if _started else {}


func _core_snapshot() -> Dictionary:
	return _host.snapshot(SESSION_ID)


func view() -> Dictionary:
	if not _started:
		return {}
	var shown: Dictionary = _host.view(SESSION_ID)
	var speaker: Variant = shown.get("speaker")
	shown["speakerLabel"] = null if speaker == null else program.speakers.get(str(speaker), {}).get("display_name", str(speaker))
	if shown.get("status") == "ended":
		shown["kind"] = "end"
		shown["label"] = _ending_label(str(shown.outcome))
	return shown


func act(action: Dictionary) -> void:
	if not _started or _suspended:
		return
	var current := view()
	if current.get("kind") == "end" and action.get("kind") == "advance":
		if not finished.get_connections().is_empty():
			_silence()
			finished.emit(str(current.outcome), PackedStringArray(_state.flags))
		else:
			_restart_invocation()
		return
	var translated := action.duplicate(true)
	if translated.get("kind") == "choose" and translated.has("option"):
		var index := int(translated.option)
		var options: Array = current.get("options", [])
		if index < 0 or index >= options.size():
			return
		translated = {"kind": "choose", "choice_id": str(options[index].id)}
	var result: Dictionary = _host.submit(SESSION_ID, translated)
	if result.has("error"):
		push_warning("The Grain presentation: " + str(result.error.message))
		return
	_sync_invocation()
	if str(view().get("visit_id", "")) == str(current.get("visit_id", "")) and bool(result.get("consumed", false)):
		_report(view())


func set_suspended(value: bool) -> void:
	if _suspended == value:
		return
	_suspended = value
	if _started:
		if value:
			_host.suspend(SESSION_ID)
		else:
			_host.resume(SESSION_ID)
	for player: Variant in _players.values():
		if player is AudioStreamPlayer:
			player.stream_paused = value
	if _started:
		_sync_invocation()


func _restart_invocation() -> void:
	_silence()
	_host = INVOCATION_HOST.new()
	_frame_binding = FRAME_BINDING.new()
	_host.register_capability("grain_frame", _capabilities.grain_frame, _frame_binding)
	var initial_facts := {}
	for fact: String in program.facts:
		if bool(program.facts[fact].get("external", false)):
			initial_facts[fact] = _carried_facts.has(fact)
	var result: Dictionary = _host.invoke(_rich_document, _catalog_document, _policy(), {"stage": self}, initial_facts)
	if result.has("error"):
		push_warning("The Grain cannot restart this conversation: " + str(result.error.message))
		return
	_last_visit = ""
	_last_statement = ""
	_reported_reveal = false
	_sync_invocation()


func report() -> void:
	if _started:
		_report(view())


func _policy() -> Dictionary:
	return {"session_id": SESSION_ID, "capabilities": {"grain_frame": 1}, "channels": ["dialogue"], "bindings": ["stage"]}


func _admit_presentation() -> Array[String]:
	var errors: Array[String] = []
	for node: Dictionary in program.nodes.values():
		if node.kind not in ["line", "choice"]:
			continue
		var profile: Dictionary = node.presentation
		for key: String in profile:
			if key not in ["channel", "profile", "chars_per_second", "legacy_statement_id"]:
				errors.append("Unsupported dialogue presentation field: " + key)
		if profile.get("channel") != "dialogue" or profile.get("profile") != "bottom":
			errors.append("The Grain binds its framed bottom dialogue channel only.")
		if node.advance_mode != "manual":
			errors.append("The Grain's framed dialogue advances through the player's input.")
		var speed: Variant = profile.get("chars_per_second")
		if not (speed is float or speed is int) or not is_finite(float(speed)) or float(speed) <= 0.0 or float(speed) > 240.0:
			errors.append("Dialogue reveal speed must be between 0 and 240 characters per second.")
		var identity: Variant = profile.get("legacy_statement_id")
		if not identity is String or not _valid_statement_id(identity):
			errors.append("Dialogue must retain its explicit original statement identity.")
		if not node.get("text") is String:
			errors.append("This game's current episode requires literal authored dialogue.")
		var cues: Array = node.get("cues", [])
		if cues.size() != 1 or cues[0].effect.type != "grain_frame" or cues[0].instance_id != "frame" or cues[0].target != "stage" or cues[0].scope != "node" or cues[0].clock != "presentation" or cues[0].get("at", -1.0) != 0.0 or cues[0].duration != null:
			errors.append("Each presentation requires one immediate node-owned grain frame.")
		if node.get("gates") != [{"event": "operation_completed:frame", "finish_on_advance": true}, {"event": "text_revealed", "finish_on_advance": true}]:
			errors.append("Dialogue requires ordered frame and text reveal gates.")
	return errors


func _sync_invocation() -> void:
	var events: Array[Dictionary] = _host.drain_events()
	var force_reveal := false
	var current := view()
	for event: Dictionary in events:
		if event.get("visit_id") == current.get("visit_id") and event.get("type") in ["scenario/reveal_requested", "scenario/finish_requested"]:
			force_reveal = true
	var saved := _core_snapshot()
	var core: Dictionary = saved.state
	var new_visit := str(current.get("visit_id", "")) != _last_visit
	if new_visit:
		_last_visit = str(current.get("visit_id", ""))
		_reported_reveal = core.gate_events.has("text_revealed")
		_reading_start = float(core.clocks.reading)
		var operation := _current_operation(core)
		if not operation.is_empty():
			_reading_start = float(operation.start_time)
	if force_reveal:
		_reveal(current)
		core = _core_snapshot().state
	var operation := _current_operation(core)
	if not operation.is_empty() and (new_visit or not _current_frame.is_empty()):
		var elapsed := maxf(0.0, float(core.clocks.presentation) - float(operation.start_time))
		if operation.status == "finished":
			elapsed = float(operation.effect.parameters.seconds)
		present_frame(operation.effect.parameters, elapsed)
	var flags: Array = _carried_facts.duplicate()
	for flag: String in core.facts:
		if core.facts[flag] == true and not flags.has(flag):
			flags.append(flag)
	flags.sort()
	var source_statement := _last_statement
	if current.get("kind") == "end" and not operation.is_empty():
		source_statement = str(program.nodes[operation.node_id].presentation.legacy_statement_id)
	var identity := str(current.get("presentation", {}).get("legacy_statement_id", source_statement))
	if not identity.is_empty():
		_last_statement = identity
	var split := identity.rsplit("#", true, 1)
	var target: Dictionary = _current_frame.get("to_frame", {"stage": null, "cast": []})
	var cast: Array = []
	for actor: Dictionary in target.cast:
		cast.append({"actorId": actor.actor_id, "expression": actor.expression, "slot": actor.slot})
	if current.get("kind") == "end":
		cast.clear()
		for plate: TextureRect in _old_cast.values():
			plate.hide()
		for plate: TextureRect in _new_cast.values():
			plate.hide()
	_state = {"label": split[0] if split.size() == 2 else "", "index": int(split[1]) if split.size() == 2 else 0, "flags": flags, "seen": core.seen.duplicate(), "stage": target.stage, "actors": cast, "tracks": [], "outcome": core.outcome}
	_render()
	if new_visit:
		_report(current)
	if current.get("kind") == "line" and not _reported_reveal and _reveal_fraction(core, current) >= 1.0:
		_reveal(current)
		_render()


func _current_operation(core: Dictionary) -> Dictionary:
	for operation: Dictionary in core.operations.values():
		if operation.visit_id == core.visit_id and operation.instance_id == "frame":
			return operation
	if core.status == "ended":
		return core.operations.get(str(core.instances.get("frame", "")), {})
	return {}


func _reveal(current: Dictionary) -> void:
	if _reported_reveal or current.get("kind") not in ["line", "choice"]:
		return
	_host.submit(SESSION_ID, {"kind": "host_event", "session_id": SESSION_ID, "node_id": str(current.node_id), "visit_id": str(current.visit_id), "name": "text_revealed"})
	_reported_reveal = true
	_host.drain_events()


func _reveal_fraction(core: Dictionary, current: Dictionary) -> float:
	if _reported_reveal or core.gate_events.has("text_revealed"):
		return 1.0
	var length := str(current.get("text", "")).length()
	if length == 0:
		return 1.0
	return clampf((float(core.clocks.reading) - _reading_start) * float(current.presentation.chars_per_second) / float(length), 0.0, 1.0)


func _render() -> void:
	var current := view()
	var line: bool = current.get("kind") == "line"
	var choice: bool = current.get("kind") == "choice"
	var ending: bool = current.get("kind") == "end"
	_panel.visible = line
	_body.visible = line
	_name.visible = line and current.get("speaker") != null
	_progress.visible = line
	_choice_layer.visible = choice
	_complete.visible = ending
	_layout_dialogue_portrait(current)
	if ending:
		_set_title(str(current.get("label", "Complete")))
		_hide_choices()
	elif choice:
		_render_choices(current.get("options", []))
	else:
		_hide_choices()
		if line:
			_set_body(str(current.text))
			_name.text = str(current.get("speakerLabel", "")) if current.get("speakerLabel") != null else ""
			_body.visible_ratio = _reveal_fraction(_core_snapshot().state, current)
			_progress.text = "tap to reveal / continue" if _body.visible_ratio < 1.0 or not current.get("pending_gate", {}).is_empty() else "tap to continue"


func _report(current: Dictionary) -> void:
	var line := {}
	if current.get("kind") == "line":
		line = {"speaker": current.get("speakerLabel"), "text": str(current.text)}
	var statement: Variant = null if current.get("kind") == "end" else current.get("presentation", {}).get("legacy_statement_id")
	moment.emit(state(), statement, line, current.get("outcome"))


func _ending_label(outcome: String) -> String:
	for ending: Dictionary in bundle.scenario.get("endings", []):
		if ending.get("outcome_id") == outcome:
			return str(ending.get("label", outcome))
	return outcome.replace("_", " ").capitalize()


func admit_frame(parameters: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: String in ["from_frame", "to_frame"]:
		var frame: Dictionary = parameters[key]
		var stage := DialogueBundle.stage(bundle, str(frame.stage))
		if stage.is_empty() or _package.texture(str(stage.get("path", ""))) == null:
			errors.append("Unknown or unavailable stage: " + str(frame.stage))
		else:
			_stage_textures[str(frame.stage)] = _package.texture(str(stage.path))
		var actors := {}
		for actor: Dictionary in frame.cast:
			var id := str(actor.actor_id)
			if actors.has(id):
				errors.append("A frame cannot stage an actor twice: " + id)
			actors[id] = true
			var member := DialogueBundle.actor(bundle, id)
			var found := false
			for expression: Dictionary in member.get("expressions", []):
				if expression.state == actor.expression:
					var texture := _package.texture(str(expression.path))
					if texture != null:
						_actor_textures[id + ":" + str(actor.expression)] = texture
						found = true
			if not found:
				errors.append("Unknown or unavailable actor expression: %s/%s" % [id, actor.expression])
		if not str(frame.focus).is_empty() and not actors.has(str(frame.focus)):
			errors.append("Camera focus requires a staged actor: " + str(frame.focus))
	return errors


func _build_rich_world() -> void:
	_world = Control.new()
	_old_background = TextureRect.new()
	_new_background = TextureRect.new()
	_backdrop.hide()
	for actor: TextureRect in _cast.values():
		actor.hide()
	_world.name = "ScenarioWorld"
	_world.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_world.size = size
	_world.z_index = DEPTH_BACKDROP
	add_child(_world)
	for background: TextureRect in [_old_background, _new_background]:
		_setup_texture(background)
		background.size = size
		_world.add_child(background)
	for actor: String in _cast:
		var old := TextureRect.new()
		var next := TextureRect.new()
		for plate: TextureRect in [old, next]:
			_setup_texture(plate)
			plate.hide()
			_world.add_child(plate)
		_old_cast[actor] = old
		_new_cast[actor] = next


func present_frame(parameters: Dictionary, elapsed: float) -> void:
	_current_frame = parameters.duplicate(true)
	_frame_elapsed = minf(maxf(elapsed, 0.0), float(parameters.seconds))
	var ratio := 1.0 if float(parameters.seconds) == 0.0 else _frame_elapsed / float(parameters.seconds)
	var weight := smoothstep(0.0, 1.0, ratio)
	var before: Dictionary = parameters.from_frame
	var after: Dictionary = parameters.to_frame
	_old_background.texture = _stage_textures[str(before.stage)]
	_new_background.texture = _stage_textures[str(after.stage)]
	_new_background.modulate.a = weight
	var from_poses := _poses(before)
	var to_poses := _poses(after)
	var camera_from := _camera_pose(before, from_poses)
	var camera_to := _camera_pose(after, to_poses)
	var zoom := lerpf(float(before.zoom), float(after.zoom), weight)
	var offset: Vector2 = camera_from.offset.lerp(camera_to.offset, weight)
	_world.scale = Vector2(zoom, zoom)
	_world.position = offset
	var visible_cast := {}
	for id: String in _cast:
		var old: TextureRect = _old_cast[id]
		var next: TextureRect = _new_cast[id]
		old.hide()
		next.hide()
		if not from_poses.has(id) and not to_poses.has(id):
			continue
		var from: Dictionary = from_poses.get(id, {}).duplicate()
		var to: Dictionary = to_poses.get(id, {}).duplicate()
		if from.is_empty():
			from = to.duplicate()
			from.rect = Rect2(to.rect.position + _entry_offset(to.slot), to.rect.size)
			from.color = Color(to.color, 0.0)
		if to.is_empty():
			to = from.duplicate()
			to.rect = Rect2(from.rect.position + _entry_offset(from.slot), from.rect.size)
			to.color = Color(from.color, 0.0)
		var rect := Rect2(from.rect.position.lerp(to.rect.position, weight), from.rect.size.lerp(to.rect.size, weight))
		var color: Color = from.color.lerp(to.color, weight)
		var order := int(to.order)
		if from.texture == to.texture:
			_draw_plate(next, to.texture, rect, color, order)
		else:
			_draw_plate(old, from.texture, rect, Color(color, color.a * (1.0 - weight)), order)
			_draw_plate(next, to.texture, rect, Color(color, color.a * weight), order + 1)
		visible_cast[id] = {"position": [rect.position.x, rect.position.y], "size": [rect.size.x, rect.size.y], "alpha": color.a}
	_frame_geometry = {"elapsed": _frame_elapsed, "seconds": float(parameters.seconds), "progress": ratio, "weight": weight, "from_stage": str(before.stage), "to_stage": str(after.stage), "zoom": zoom, "offset": [offset.x, offset.y], "cast": visible_cast}


func frame_sample() -> Dictionary:
	return _frame_geometry.duplicate(true)


func _poses(frame: Dictionary) -> Dictionary:
	var result := {}
	for actor: Dictionary in frame.cast:
		var texture: Texture2D = _actor_textures[str(actor.actor_id) + ":" + str(actor.expression)]
		var emphasis := DialogueLayout.narration_emphasis(str(actor.slot)) if str(frame.focus).is_empty() else DialogueLayout.actor_emphasis(str(actor.slot), actor.actor_id == frame.focus)
		var placed := DialogueLayout.emphasized_frame(DialogueLayout.slot_frame({"width": texture.get_width(), "height": texture.get_height()}, _placement, str(actor.slot)), float(emphasis.scale))
		var tint: Array = emphasis.tint
		var color := Color(1.0, 1.0, 1.0, float(emphasis.alpha)) if tint.is_empty() else Color(float(tint[0]) / 255.0, float(tint[1]) / 255.0, float(tint[2]) / 255.0, float(emphasis.alpha))
		result[str(actor.actor_id)] = {"texture": texture, "rect": Rect2(placed.x, placed.y, placed.width, placed.height), "color": color, "order": DEPTH_SPRITE + int(emphasis.stackOrder) * 2, "slot": str(actor.slot)}
	return result


func _camera_pose(frame: Dictionary, poses: Dictionary) -> Dictionary:
	var zoom := float(frame.zoom)
	var focal := size * Vector2(0.5, 0.35)
	if poses.has(str(frame.focus)):
		var rect: Rect2 = poses[str(frame.focus)].rect
		focal = rect.position + rect.size * Vector2(0.5, 0.2)
	var offset := focal * (1.0 - zoom)
	offset.x = clampf(offset.x, size.x * (1.0 - zoom), 0.0)
	offset.y = clampf(offset.y, size.y * (1.0 - zoom), 0.0)
	return {"offset": offset}


static func _entry_offset(slot: String) -> Vector2:
	return Vector2(-70.0 if slot in ["far_left", "left"] else 70.0, 12.0)


static func _setup_texture(texture: TextureRect) -> void:
	texture.mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	texture.stretch_mode = TextureRect.STRETCH_SCALE


static func _draw_plate(plate: TextureRect, texture: Texture2D, rect: Rect2, tint: Color, order: int) -> void:
	plate.texture = texture
	plate.position = rect.position
	plate.size = rect.size
	plate.modulate = tint
	plate.z_index = order
	plate.visible = tint.a > 0.0


static func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {"error": {"message": "The game has no authored content at " + path}}
	return JSON_DATA.parse(FileAccess.get_file_as_bytes(path), path)


static func _valid_statement_id(value: String) -> bool:
	var parts := value.rsplit("#", true, 1)
	return parts.size() == 2 and not parts[0].is_empty() and parts[1].is_valid_int() and int(parts[1]) >= 0


static func _rich_refusal(value: Dictionary) -> KernelRefusal:
	return KernelRefusal.of("dialogue/scenario", str(value.error.get("message", "The authored Scenario content is invalid.")))
