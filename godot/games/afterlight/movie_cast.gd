extends Node

## Afterlight's presentation adapter keeps the existing actor/effect surface.
## Movie Sprite Actor owns compositing; the story owns speech and blink timing.
const MOVIE_ACTOR = preload("res://addons/movie_sprite_actor/movie_sprite_actor.gd")
const MOUTH_CYCLE := ["rest", "mouth_a", "mouth_o", "mouth_a", "rest", "mouth_o"]
signal failed(errors: Array[String])

var textures: Dictionary = {}
var _players: Dictionary = {}
var _viewports: Dictionary = {}
var _eye_clocks: Dictionary = {}
var _speech_clock := 0.0
var _speaker := ""
var _paused := false
var _errors: Array[String] = []


func configure(content_loader: RefCounted, bindings: Dictionary) -> Array[String]:
	shutdown()
	var errors: Array[String] = []
	if bindings.is_empty(): return errors
	if content_loader == null or not content_loader.has_method("resolve") or not content_loader.has_method("get_settings"):
		_errors = ["Movie cast requires the local content loader."]
		return _errors.duplicate()
	for actor_id: String in bindings:
		var reference := str(bindings[actor_id])
		var resolved: Dictionary = content_loader.resolve(reference, false)
		if not resolved.errors.is_empty():
			errors.append_array(resolved.errors)
			continue
		# Optional local diagnostic media is not required by distributable content.
		if not FileAccess.file_exists(resolved.path): continue
		var player := MOVIE_ACTOR.new()
		var actor_errors: Array[String] = player.configure(content_loader, reference)
		if not actor_errors.is_empty():
			errors.append_array(actor_errors)
			player.free()
			continue
		if str(player.snapshot().character_id) != actor_id:
			errors.append("Movie cast character binding does not match its manifest: " + actor_id)
			player.shutdown()
			player.free()
			continue
		player.failed.connect(_on_player_failed.bind(actor_id))
		var viewport := SubViewport.new()
		viewport.name = actor_id.to_pascal_case() + "MovieCanvas"
		viewport.size = player.snapshot().frame_size
		viewport.transparent_bg = true
		viewport.disable_3d = true
		viewport.gui_disable_input = true
		viewport.handle_input_locally = false
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
		viewport.add_child(player)
		add_child(viewport)
		_players[actor_id] = player
		_viewports[actor_id] = viewport
		textures[actor_id] = viewport.get_texture()
		_eye_clocks[actor_id] = 1.4 if actor_id == "riko" else 0.0
	_errors.append_array(errors)
	return errors


func advance(delta: float, speaker: String, speaking: bool) -> void:
	var elapsed := 0.0 if _paused or not is_finite(delta) else maxf(delta, 0.0)
	if _paused:
		for player: Node2D in _players.values(): player.advance(0.0)
		return
	if speaker != _speaker:
		_speaker = speaker
		_speech_clock = 0.0
	if speaking: _speech_clock += elapsed
	else: _speech_clock = 0.0
	for actor_id: String in _players:
		var player: Node2D = _players[actor_id]
		# Zero-time advances still finish asynchronous body-page preparation.
		player.advance(elapsed)
		_eye_clocks[actor_id] = float(_eye_clocks[actor_id]) + elapsed
		var time := fmod(float(_eye_clocks[actor_id]), 5.1 if actor_id == "riko" else 4.3)
		var eye := "rest"
		if time >= 3.75 and time < 4.0:
			eye = "eyes_closed"
			if actor_id == "yuzu" and (time < 3.81 or time >= 3.93): eye = "eyes_half"
		player.set_eye_state(eye)
		var mouth := "rest"
		if speaking and speaker == actor_id:
			mouth = MOUTH_CYCLE[int(_speech_clock / 0.115) % MOUTH_CYCLE.size()]
		player.set_mouth_state(mouth)


func set_paused(value: bool) -> void:
	_paused = value
	for player: Node2D in _players.values(): player.set_paused(value)


func get_texture(actor_id: String) -> Texture2D:
	return textures.get(actor_id)


func snapshot() -> Dictionary:
	var actors: Dictionary = {}
	for actor_id: String in _players: actors[actor_id] = _players[actor_id].snapshot()
	return {"actors": actors, "paused": _paused, "speaker": _speaker, "errors": _errors.duplicate()}


func _on_player_failed(errors: Array[String], actor_id: String) -> void:
	var contextual: Array[String] = []
	for error: String in errors: contextual.append(actor_id + ": " + error)
	_errors.append_array(contextual)
	failed.emit(contextual)


func shutdown() -> void:
	for player: Node2D in _players.values(): player.shutdown()
	for viewport: SubViewport in _viewports.values():
		remove_child(viewport)
		viewport.free()
	_players.clear()
	_viewports.clear()
	textures.clear()
	_eye_clocks.clear()
	_speech_clock = 0.0
	_speaker = ""
	_paused = false
	_errors.clear()


func _exit_tree() -> void:
	shutdown()
