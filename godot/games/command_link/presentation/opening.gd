extends Control

## Disposable title route. Replace this clip without changing story or demo code.
signal navigate(route_id: String)

const TACTICAL_THEME = preload("res://presentation/ui/tactical_theme.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const LOOP_FADE_OUT_SECONDS := 0.8
const LOOP_FADE_IN_SECONDS := 0.35
@export_file("*.ogv") var video_path := ""
@export var continue_label := "CONTINUE  →"
var content_loader: RefCounted
var content_errors: Array[String] = []
var _player: VideoStreamPlayer
var _leaving := false
var _duration_seconds := 0.0


func _ready() -> void:
	clip_contents = true
	theme = TACTICAL_THEME.build()
	var backing := ColorRect.new()
	backing.color = Color.BLACK
	backing.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(backing)
	backing.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if content_loader == null:
		content_loader = LOCAL_CONTENT.new()
	var loaded: Dictionary = {"resource": null, "errors": content_errors}
	if content_errors.is_empty():
		loaded = content_loader.load_video(video_path.trim_prefix("res://"))
	content_errors.assign(loaded.errors)
	if loaded.resource is VideoStream:
		_player = VideoStreamPlayer.new()
		_player.stream = loaded.resource
		_player.expand = true
		_player.loop = true
		_player.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_player.volume_db = -80.0
		_player.modulate.a = 0.0
		add_child(_player)
		_player.size = size
		_duration_seconds = _player.get_stream_length()
	var begin := Button.new()
	begin.text = continue_label
	# The 16:9 opening occupies y=90..810 on the fixed 1280x900 canvas.
	begin.position = Vector2(1016, 835)
	begin.size = Vector2(220, 40)
	begin.flat = true
	begin.focus_mode = Control.FOCUS_NONE
	begin.add_theme_color_override("font_color", TACTICAL_THEME.MUTED)
	begin.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	begin.pressed.connect(_finish)
	add_child(begin)
	# The explicit continue control remains available even if media is missing.
	if _player != null:
		_player.play()
		resized.connect(_fit_video)


func _process(_delta: float) -> void:
	if _leaving or _player == null:
		return
	_fit_video()
	var position_seconds := _player.stream_position
	var opacity := smoothstep(0.0, LOOP_FADE_IN_SECONDS, position_seconds)
	if _duration_seconds > LOOP_FADE_OUT_SECONDS:
		# Reach black before the last frame, then reveal the new loop from black.
		var fade_start := _duration_seconds - LOOP_FADE_OUT_SECONDS
		var fade_end := _duration_seconds - 0.05
		opacity = minf(opacity, 1.0 - smoothstep(fade_start, fade_end, position_seconds))
	_player.modulate.a = opacity


func _fit_video() -> void:
	var frame := _player.get_video_texture()
	if frame == null or frame.get_width() <= 0 or frame.get_height() <= 0:
		return
	var factor := minf(size.x / frame.get_width(), size.y / frame.get_height())
	_player.size = frame.get_size() * factor
	_player.position = (size - _player.size) * 0.5


func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		get_viewport().set_input_as_handled()
		return
	var continue_requested: bool = event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT
	continue_requested = continue_requested or (event is InputEventScreenTouch and event.pressed)
	if continue_requested:
		get_viewport().set_input_as_handled()
		_finish()


func _finish() -> void:
	if _leaving:
		return
	_leaving = true
	if _player != null:
		_player.stop()
	_leave.call_deferred()


func _leave() -> void:
	navigate.emit("game")
