extends SceneTree

const GAME = preload("res://story.gd")
const COMPOSITION = preload("res://root.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var composition := COMPOSITION.new()
	var game := GAME.new()
	composition.prepare_scene(game, "game", {}, {})
	root.add_child(game)
	game.set_process(false)
	_expect(game._load_errors.is_empty(), "Admitted program and bound resources initialize.")
	_expect(game._program.get("scenario_id") == "afterlight_episode" and game.beats.size() == 57, "The real game executes v3 while reviewing every original beat.")
	game._process(0.25)
	var original: Dictionary = game.save_game()
	var rejected := original.duplicate(true)
	rejected["session"]["program_fingerprint"] = "different_program"
	game.saved_state = rejected.duplicate(true)
	game._restore_game()
	game._render()
	_expect(not game._load_errors.is_empty() and game._checkpoint_refused and game._recovery_button.visible, "Incompatible Session identities expose a visible fresh-start action.")
	_expect(game.saved_state == rejected, "Refusal preserves the source checkpoint.")
	game._restart()
	_expect(game._load_errors.is_empty() and game.current_beat()["id"] == "undeliverable", "Explicit fresh start executes the current program.")
	game.saved_state = {"story_version": 4, "beat_id": "undeliverable"}
	var old := game.saved_state.duplicate(true)
	game._restore_game()
	game._render()
	_expect(game._checkpoint_refused and game._recovery_button.visible and "story_version 5" in " ".join(game._load_errors), "Version four is visibly refused with its supported envelope version.")
	_expect(game.saved_state == old, "Old checkpoints are not rewritten during refusal.")
	game._restart()
	game.saved_state = original.duplicate(true)
	game._restore_game()
	_expect(game._load_errors.is_empty() and is_equal_approx(game._elapsed, 0.25), "Version five resumes the exact admitted invocation and visual clock.")
	var tampered := game.save_game()
	for record: Dictionary in tampered["presentation_journal"]:
		if record.get("type") == "front_background": record["parameters"]["index"] = 1; break
	game.saved_state = tampered
	var before := game._session.snapshot()
	game._restore_game()
	_expect(not game._load_errors.is_empty() and game._session.snapshot() == before, "Visual replay refuses commands that differ from the admitted Session operation registry, without replacing the session.")
	game._restart()
	var review: Dictionary = game.current_beat()
	review["next"] = "the_next_arrival"
	game._next()
	game._next()
	_expect(game.current_beat()["id"] == "across_the_threshold", "Inspection metadata cannot replace graph progression.")
	var admitted_program: Dictionary = game._program.duplicate(true)
	_expect(not game._admit_documents(game._types, null, {}), "Malformed external records are refused structurally.")
	game._render()
	_expect(game._line.visible_characters == -1 and not game._load_errors.is_empty() and game._program == admitted_program, "Admission failure is visible and preserves the admitted program.")
	var exiting_session: RefCounted = game._session
	game.queue_free()
	await process_frame
	_expect(exiting_session.view()["status"] == "cancelled", "Removing the game explicitly cancels its invocation.")
	for issue: String in _errors: printerr("FAIL Afterlight Scenario Binding: " + issue)
	if _errors.is_empty(): print("PASS Afterlight Scenario Binding: genuine v3 execution, immutable progression, versioned resume, operation-bound visual replay and visible preserved-checkpoint refusal")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
