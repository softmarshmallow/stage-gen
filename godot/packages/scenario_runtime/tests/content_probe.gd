extends SceneTree

const LOADER = preload("res://addons/scenario_runtime/content/package_loader.gd")
const JSON_DATA = preload("res://addons/scenario_runtime/content/json_data.gd")
const SESSION = preload("res://addons/scenario_runtime/execution/session.gd")
const PARTICLE = preload("res://addons/scenario_runtime/presentation/particle_adapter.gd")
var failures: Array[String] = []
var checks := 0


func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 7:
		push_error("content probe needs first, second, damaged, changed-revision, malformed, incomplete and oversized directories")
		quit(1)
		return
	var loader := LOADER.new()
	_check(not loader.activate(arguments[0], {}).has("error"), "first data-only package activates")
	var pinned := loader.current()
	if pinned.is_empty():
		_finish()
		return
	var session := SESSION.new()
	var policy := {"session_id": "content_player", "channels": ["dialogue"], "capabilities": {}}
	_check(not session.start(pinned.programs.story, pinned.catalog, policy).has("error"), "compiled package runs without Python or a game")
	var first_text := str(session.view().get("text", ""))
	var saved := session.snapshot()
	_check(not loader.activate(arguments[1], {}).has("error"), "same player admits a second independent package")
	var second := loader.current()
	var next := SESSION.new()
	_check(not next.start(second.programs.story, second.catalog, policy).has("error") and next.view().text != first_text, "second package changes content on unchanged runtime")
	_check(session.view().text == first_text, "active session pins its prior content revision")
	var incompatible := SESSION.new()
	_check(incompatible.restore(second.programs.story, second.catalog, policy, saved).has("error"), "old checkpoint cannot silently bind to replacement content")
	var fingerprint: String = second.fingerprint
	_check(loader.activate(arguments[2], {}).has("error"), "damaged package is refused before activation")
	_check(loader.current().fingerprint == fingerprint, "failed activation leaves prior usable selection intact")
	_check(loader.activate(arguments[3], {}).get("error", {}).get("code") == "immutable_revision", "an activated package revision cannot be redefined")
	_check(LOADER.stage(arguments[4], {}).get("error", {}).get("code") == "content_json", "hashed non-object program refuses without a script error")
	_check(LOADER.stage(arguments[5], {"particle": PARTICLE.schema()}).get("error", {}).get("code") == "capability", "manifest must cover inferred effect capabilities")
	_check(LOADER.stage(arguments[6], {}).get("error", {}).get("code") == "content_limit", "manifest size is bounded before reading or parsing it")
	_check(JSON_DATA.parse('{"id":1,"id":2}'.to_utf8_buffer(), "duplicate.json").has("error"), "duplicate JSON fields refused")
	_check(JSON_DATA.parse('{"id":1,"\\u0069d":2}'.to_utf8_buffer(), "escaped.json").has("error"), "escaped duplicate keys refused")
	_check(not JSON_DATA.parse('{"a":{"id":1},"b":{"id":2},"array":[1,"a:b"]}'.to_utf8_buffer(), "nested.json").has("error"), "different objects may use the same field names")
	var result := session.submit({"kind": "advance"})
	_check(result.state.status == "ended", "pinned package continues to its own outcome after replacement")
	_finish()


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)


func _finish() -> void:
	if failures.is_empty():
		print("scenario_content: %d checks passed" % checks)
		quit(0)
	else:
		for failure: String in failures: push_error(failure)
		quit(1)
