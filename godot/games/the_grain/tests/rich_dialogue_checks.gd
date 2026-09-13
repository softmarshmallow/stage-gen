extends SceneTree

## Runs the actual installed sequence against a caller-selected prepared run.
## Optional captures use the same deterministic traversal as the assertions.
const RichLeaf = preload("res://scenes/common/rich_dialogue_leaf.gd")
var _checks := 0
var _failures: Array[String] = []
var _run_dir := ""
var _capture_dir := ""
var _viewport: SubViewport


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size() - 1):
		if args[index] == "--run": _run_dir = args[index + 1]
		if args[index] == "--capture-dir": _capture_dir = args[index + 1]
	if _run_dir.is_empty():
		printerr("rich_dialogue_checks requires --run <prepared dialogue run>")
		quit(2)
		return
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(1672, 941)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(_viewport)
	var leaf: Variant = _open(null)
	if leaf == null:
		_finish()
		return
	await process_frame
	var first := str(leaf.view().node_id)
	leaf.advance()
	_check(str(leaf.view().node_id) == first, "first press reveals without skipping the line")
	_check(leaf._body.visible_ratio >= 1.0 or leaf._body.visible_characters < 0, "first press reveals the complete text")
	leaf.advance()
	_check(str(leaf.view().node_id) != first, "second press advances")
	_reach(leaf, "the_service_door_09")
	var entrance: Dictionary = leaf.frame_sample()
	leaf.step(0.225)
	_check(not _same(leaf.frame_sample(), entrance), "cast entrance has an observable midpoint")
	var cast_midpoint: Dictionary = leaf.frame_sample().cast
	_check(cast_midpoint.edwin.alpha > 0.0 and cast_midpoint.edwin.alpha < 1.0, "Edwin enters with partial opacity")
	await _capture("01-cast-midpoint")
	var frozen: Dictionary = leaf.snapshot()
	var midpoint: Dictionary = leaf.frame_sample()
	leaf.set_suspended(true)
	var suspended: Dictionary = leaf.snapshot()
	leaf.step(3.0)
	leaf.advance()
	_check(_same(leaf.snapshot(), suspended), "backlog suspension freezes clocks and refuses advance")
	_check(not paused, "presentation suspension does not pause the SceneTree")
	leaf.set_suspended(false)
	_check(_same(leaf.frame_sample(), midpoint), "resume retains the transition midpoint")
	var clone: Variant = _open(JSON.parse_string(JSON.stringify(frozen)))
	if clone != null:
		_check(_same(clone.frame_sample(), midpoint), "JSON checkpoint reconstructs the active transition exactly")
		_check(clone.state().flags.has("rang_the_bell"), "rich save retains carried case facts outside its declared facts")
		_dispose(clone)
	clone = _open(JSON.parse_string(JSON.stringify(suspended)))
	if clone != null:
		clone.set_suspended(false)
		clone.step(0.1)
		_check(not _same(clone.frame_sample(), midpoint), "restored suspended invocation can be resumed by the game")
		_dispose(clone)
	var at_entrance := str(leaf.view().node_id)
	leaf.advance()
	_check(str(leaf.view().node_id) == at_entrance, "advance finishes transition without advancing story")
	var settled: Dictionary = leaf.frame_sample()
	_check(not _same(settled, midpoint), "finish reaches the visual endpoint")
	clone = _open(JSON.parse_string(JSON.stringify(leaf.snapshot())))
	if clone != null:
		_check(_same(clone.frame_sample(), settled), "completed operation checkpoint reconstructs the settled frame")
		_dispose(clone)
	await _capture("02-cast-settled")
	_reach(leaf, "the_dark_floor_03")
	var dissolve_start: Dictionary = leaf.frame_sample()
	await _capture("03-dissolve-start")
	leaf.step(0.3)
	_check(not _same(leaf.frame_sample(), dissolve_start), "location dissolve progresses at its midpoint")
	await _capture("04-dissolve-midpoint")
	leaf.step(0.3)
	await _capture("05-dissolve-complete")
	_check(leaf.state().stage == "tollands_cosmetics_floor", "the cosmetics floor is the settled stage")
	_reach(leaf, "the_winter_room_03")
	leaf.step(0.4)
	await _capture("06-winter-room-midpoint")
	leaf.step(0.4)
	await _capture("07-winter-room-settled")
	_reach(leaf, "the_winter_room_10")
	leaf.step(1.0)
	var focus: Dictionary = leaf.frame_sample()
	await _capture("08-lydia-focus")
	_reach(leaf, "the_winter_room_11")
	leaf.step(1.0)
	_check(not _same(leaf.frame_sample(), focus), "Ruth's reply returns to the wider frame")
	await _capture("09-ruth-reply")
	var frame_settings: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://narrative/catalog.json")).definitions.values()[0].parameters.duplicate(true)
	frame_settings.to_frame.stage = "missing_location"
	_check(not leaf.admit_frame(frame_settings).is_empty(), "unknown future location is refused")
	frame_settings.to_frame = frame_settings.from_frame.duplicate(true)
	frame_settings.to_frame.cast[0].expression = "missing_expression"
	_check(not leaf.admit_frame(frame_settings).is_empty(), "unknown expression is refused instead of taking a fallback")
	frame_settings.to_frame = frame_settings.from_frame.duplicate(true)
	frame_settings.to_frame.focus = "missing_actor"
	_check(not leaf.admit_frame(frame_settings).is_empty(), "unbound focus actor is refused")
	var bad_catalog: Dictionary = leaf._catalog_document.duplicate(true)
	var future_preset: String = bad_catalog.definitions.keys().back()
	bad_catalog.definitions[future_preset].parameters.to_frame.stage = "unavailable_future_location"
	var refused: Variant = RichLeaf.of_rich(leaf._package, leaf.bundle, leaf._rich_document, bad_catalog, PackedStringArray(["rang_the_bell"]))
	_check(KernelRefusal.is_refusal(refused), "future resource failure refuses the entire invocation before its first line")
	if refused is HostDialogueLeaf: refused.free()
	var old_leaf: Variant = HostDialogueLeaf.open(_run_dir, "e1_way_in")
	_check(not KernelRefusal.is_refusal(old_leaf), "the original prepared reader still opens independently")
	if old_leaf is HostDialogueLeaf:
		refused = GrainDialoguePlayer.open(_run_dir, "e1_way_in", PackedStringArray(["rang_the_bell"]), old_leaf.snapshot())
		_check(KernelRefusal.is_refusal(refused), "an old v2 checkpoint is explicitly refused by the migrated scene")
		if refused is HostDialogueLeaf: refused.free()
		old_leaf.free()
	var foreign_facts: Dictionary = leaf.snapshot().duplicate(true)
	foreign_facts.carried_facts = ["a_different_case"]
	refused = GrainDialoguePlayer.open(_run_dir, "e1_way_in", PackedStringArray(["rang_the_bell"]), foreign_facts)
	_check(KernelRefusal.is_refusal(refused), "a checkpoint from different carried case facts is refused")
	if refused is HostDialogueLeaf: refused.free()
	for index in 80:
		if leaf.view().get("kind") == "end": break
		leaf.step(30.0)
		leaf.advance()
	_check(leaf.view().get("kind") == "end", "the complete real sequence reaches its end card")
	_check(leaf.view().get("outcome") == "first_bell", "the original case outcome is preserved")
	for fact in ["rang_the_bell", "place_card_moved_twice", "suitcase_unopened"]:
		_check(leaf.state().flags.has(fact), "the case receives " + fact)
	var saved := CaseSave.of_scenario("rich_check", "b_way_in", PackedStringArray(["rang_the_bell"]), leaf.state(), [], "2026-09-13T00:00:00Z", leaf.snapshot())
	_check(saved.scenario == leaf.snapshot(), "the existing case save stores the complete rich snapshot")
	clone = _open(JSON.parse_string(JSON.stringify(leaf.snapshot())))
	if clone != null:
		_check(clone.view().get("kind") == "end", "restored terminal snapshot shows its end card")
		_check(_same(clone.frame_sample(), leaf.frame_sample()), "restored terminal snapshot retains the final world frame")
		clone.advance()
		_check(clone.view().get("kind") == "line" and clone.view().get("node_id") == first, "standalone retry starts a fresh rich invocation")
		_dispose(clone)
	var emitted: Array = []
	leaf.finished.connect(func(outcome: String, flags: PackedStringArray) -> void: emitted.append({"outcome": outcome, "flags": flags}))
	leaf.advance()
	_check(emitted.size() == 1 and emitted[0].outcome == "first_bell", "the case receives the completed leaf outcome")
	if emitted.size() == 1:
		var case_document: Dictionary = CaseDocument.parse({
			"kind": "case-runtime-v1", "schema_version": 1, "case_id": "rich_handoff", "entry": "b_way_in",
			"facts": [{"fact_id": "rang_the_bell"}, {"fact_id": "place_card_moved_twice"}, {"fact_id": "suitcase_unopened"}],
			"beats": [
				{"beat_id": "b_way_in", "kind": "scenario", "run_tag": "scene", "edges": [{"outcome": "first_bell", "to": "b_table"}]},
				{"beat_id": "b_table", "kind": "scenario", "run_tag": "scene", "edges": []},
			],
		})
		var case_state := CaseRuntime.initial(case_document)
		case_state.phase = CaseRuntime.PHASE_PLAYING
		case_state.progress.facts = PackedStringArray(["rang_the_bell"])
		var turn := CaseRuntime.reduce(case_document, "rich_check", case_state, {"kind": "finish", "beatId": "b_way_in", "outcome": emitted[0].outcome, "flags": emitted[0].flags}, "2026-09-13T00:00:00Z")
		_check(turn.state.progress.beatId == "b_table", "the case takes its next scene edge from the rich outcome")
		_check(turn.state.progress.facts == PackedStringArray(["place_card_moved_twice", "rang_the_bell", "suitcase_unopened"]), "the case carries prior and newly established facts together")
	_dispose(leaf)
	_finish()


func _open(saved: Variant) -> Variant:
	var opened: Variant = GrainDialoguePlayer.open(_run_dir, "e1_way_in", PackedStringArray(["rang_the_bell"]), saved)
	_check(not KernelRefusal.is_refusal(opened), "installed rich sequence opens with prepared art")
	if KernelRefusal.is_refusal(opened):
		_failures.append(opened.line())
		return null
	var leaf: HostDialogueLeaf = opened
	_check(leaf.get_script() == RichLeaf, "the real game's selection uses the rich Session leaf")
	_viewport.add_child(leaf)
	leaf.set_process(false)
	return leaf


func _reach(leaf: HostDialogueLeaf, node_id: String) -> void:
	for index in 100:
		if str(leaf.view().get("node_id", "")) == node_id: return
		if leaf.view().get("kind") == "end": break
		leaf.call("step", 30.0)
		leaf.advance()
	_check(false, "real traversal reaches " + node_id)


func _dispose(leaf: HostDialogueLeaf) -> void:
	leaf.silence()
	_viewport.remove_child(leaf)
	leaf.free()


func _same(left: Variant, right: Variant) -> bool:
	if (left is float or left is int) and (right is float or right is int):
		return absf(float(left) - float(right)) < 0.00001
	if left is Dictionary and right is Dictionary:
		if left.size() != right.size(): return false
		for key: Variant in left:
			if not right.has(key) or not _same(left[key], right[key]): return false
		return true
	if left is Array and right is Array:
		if left.size() != right.size(): return false
		for index in left.size():
			if not _same(left[index], right[index]): return false
		return true
	return left == right


func _capture(name: String) -> void:
	if _capture_dir.is_empty(): return
	DirAccess.make_dir_recursive_absolute(_capture_dir)
	await process_frame
	# A background or occluded desktop window may skip its automatic draw.
	# The owned offscreen viewport must still render this exact sampled frame.
	RenderingServer.force_draw(false)
	var image := _viewport.get_texture().get_image()
	_check(image != null and not image.is_empty(), "native renderer produces " + name)
	if image != null:
		_check(image.save_png(_capture_dir.path_join(name + ".png")) == OK, "capture saved: " + name)


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition: _failures.append(message)


func _finish() -> void:
	for failure in _failures: printerr("FAIL " + failure)
	if _failures.is_empty(): print("PASS rich_dialogue_checks: %d checks passed" % _checks)
	quit(0 if _failures.is_empty() else 1)
