extends SceneTree

const GAME = preload("res://game.gd")
const COMPOSITION = preload("res://root.gd")
var failures: Array[String] = []
var checks := 0


func _initialize() -> void:
	_run.call_deferred()


func _new(saved: Dictionary = {}) -> Control:
	var game = GAME.new()
	COMPOSITION.new().prepare_scene(game, "game", {}, saved)
	root.add_child(game)
	game.set_process(false)
	return game


func _run() -> void:
	var game := _new()
	for step in 25:
		if game._story_id == "link": break
		game._process(10.0)
		if game._current_beat().has("choices"): game._choose(0)
		else: game._advance_dialogue()
	_check(game._story_id == "link" and not game._connected, "real mission reaches unconfirmed contact through Scenario")
	var saved: Dictionary = game.save_game()
	var unbound: Dictionary = game._program.duplicate(true)
	unbound.nodes.overlook.cues[0].effect.parameters.location = "unbound_location"
	_check(not game._mission_binding_errors(unbound).is_empty(), "future location references are admitted before starting a mission")
	unbound = game._program.duplicate(true)
	unbound.nodes.briefing.cues[0].effect.parameters.camera.target = "unbound_actor"
	_check(not game._mission_binding_errors(unbound).is_empty(), "future camera targets are admitted before their cue")
	var original := saved.duplicate(true)
	var restored := _new(saved)
	_check(restored._scenario_ready and restored._load_errors.is_empty(), "valid mission checkpoint restores")
	restored._process(10.0)
	_check(restored._connect_at(restored._fingertip_center(restored.size)) and restored._facts.connected, "restored contact can still complete its required gate")
	var confirmed := _new(restored.save_game())
	_check(confirmed._scenario_ready and confirmed._connected and confirmed._facts.connected, "confirmed contact agrees with restored narrative facts")
	confirmed.free()
	restored.free()
	for mutation: Dictionary in [
		{"schema_version": 999}, {"connected": true}, {"location": "perimeter_overlook"},
		{"briefing_handoff_elapsed": 1.5}, {"briefing_handoff_started": false},
		{"location_title_elapsed": INF}, {"dialogue_camera": []}, {"story_id": "arrival"},
	]:
		var changed := saved.duplicate(true)
		changed.merge(mutation, true)
		var candidate := _new(changed)
		_check(not candidate._scenario_ready and not candidate._load_errors.is_empty(), "inconsistent checkpoint refused before route activation: " + str(mutation.keys()[0]))
		_check(candidate.saved_state == changed and candidate.save_game() == changed and candidate._line.text.contains("new mission"), "refusal preserves the checkpoint through Menu and shows recovery")
		candidate.free()
	_check(saved == original, "admission never rewrites caller-owned checkpoint")
	game.free()
	if failures.is_empty():
		print("PASS scenario_binding_checks: %d checks passed" % checks)
		quit(0)
	else:
		for failure: String in failures: push_error(failure)
		quit(1)


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)
