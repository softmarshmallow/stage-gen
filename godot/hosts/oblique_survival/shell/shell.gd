class_name SurvivalShell
extends CanvasLayer

## The screens around the game: the opening cinematic, the title screen, the
## loading screen. Everything a player meets before the world exists.
##
## This is host layer in the strict sense of the host contract: it extends a
## scene node, it reads the filesystem through the run directory, it runs tweens
## and it reads the wall clock. None of that is allowed inward, and none of it is
## needed there — no simulation is running while these screens are up, so nothing
## here can make a frame unreplayable. The world is not built until Play is
## pressed, which is what makes the loading screen honest rather than a bar drawn
## over a game that is already standing.
##
## What it draws comes from the manifest's `shell` block and nothing else: the
## plates by role, the layout's canvas and reserved rectangles in canvas pixels,
## the authored strings, and the typeface the run publishes. Geometry is scaled
## by one factor — the window's height over the canvas's — so a rectangle the
## pipeline measured is the rectangle a string lands in.
##
## Every string is composited here. No plate carries lettering, by contract, so
## the game's name is set from the manifest's `strings.display_name` in the run's
## own face; swapping the face changes no art.

## Play was pressed. The frame owner takes it from here: it shows the loading
## screen, builds the world, and closes this.
signal play_pressed
## The opening finished or was skipped, and the title is up.
signal title_reached

const CANVAS_REFERENCE := Vector2(2560.0, 1440.0)
## How far a backdrop layer drifts from centre, as a fraction of the canvas. The
## published `drift` is in canvas pixels and is what the gate measured against;
## this is the host's own slower motion inside that budget.
const DRIFT_SECONDS := 24.0
## A shot's card fades in over this, and the whole shot cross-fades out over it.
const CARD_FADE := 0.6
const DISSOLVE := 0.8
## The loading screen never flashes: it holds at least this long even if the
## world stands up instantly.
const MIN_DWELL := 0.7

var package: HostRunDir = null
var kit: SurvivalUiKit = null

var _block: Dictionary = {}
var _canvas := CANVAS_REFERENCE
var _scale := 1.0
var _font: FontFile = null
var _root: Control = null
var _phase := "idle"

# --- the opening
var _shots: Array = []
var _shot_index := -1
var _shot_elapsed := 0.0
var _shot_node: Control = null
var _card_node: Label = null

# --- the title
var _title_node: Control = null
var _backdrop_layers: Array[TextureRect] = []
var _drift_phase := 0.0

# --- the loading
var _loading_node: Control = null
var _progress: ProgressBar = null
var _loading_elapsed := 0.0
var _preload_refs: Array[String] = []
var _preload_cursor := 0
var _preload_done := false


## Open the shell over a run. Returns false when the run has no shell to show,
## in which case the frame owner boots straight into the world — which is what
## every run before this family existed did.
func open(run: HostRunDir, ui_kit: SurvivalUiKit) -> bool:
	package = run
	kit = ui_kit
	var manifest: Dictionary = run.manifest
	var block: Variant = manifest.get("shell")
	if typeof(block) != TYPE_DICTIONARY or (block as Dictionary).is_empty():
		# A package that authors no shell is not a failure; one that authored a
		# shell the run never drew is, and the host contract says a degrade
		# reports the role it could not find rather than going quiet.
		var status: Dictionary = manifest.get("status", {})
		if String(status.get("shell", "none")) == "missing":
			push_warning(
				"shell: the run authors a shell block and did not publish it; "
				+ "booting straight into the world without a title screen"
			)
		return false

	_block = block
	_font = _load_typeface()
	_root = Control.new()
	_root.name = "ShellRoot"
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(_root)

	_shots = _shot_list()
	if _shots.is_empty():
		_enter_title()
	else:
		_enter_opening()
	return true


func _process(delta: float) -> void:
	match _phase:
		"opening":
			_tick_opening(delta)
		"title":
			_tick_title(delta)
		"loading":
			_tick_loading(delta)


func _unhandled_input(event: InputEvent) -> void:
	if _phase != "opening" or not _skippable():
		return
	var pressed := (
		(event is InputEventKey and event.is_pressed() and not event.is_echo())
		or (event is InputEventMouseButton and event.is_pressed())
	)
	if pressed:
		get_viewport().set_input_as_handled()
		_enter_title()


# ===========================================================================
# The opening
# ===========================================================================


func _enter_opening() -> void:
	_phase = "opening"
	_shot_index = -1
	_advance_shot()


func _advance_shot() -> void:
	_shot_index += 1
	if _shot_index >= _shots.size():
		_enter_title()
		return
	var shot: Dictionary = _shots[_shot_index]
	var previous := _shot_node

	_shot_elapsed = 0.0
	_shot_node = Control.new()
	_shot_node.set_anchors_preset(Control.PRESET_FULL_RECT)
	_shot_node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_shot_node)

	var plate := _plate_texture(shot.get("plate", {}))
	if plate != null:
		var picture := _cover_rect(plate)
		_shot_node.add_child(picture)
		_apply_move(picture, String(shot.get("move", "hold")), float(shot.get("seconds", 4.0)))

	var card := String(shot.get("card", ""))
	if card != "":
		_card_node = _card_label(card)
		_shot_node.add_child(_card_node)
		var fade := create_tween()
		fade.tween_property(_card_node, "modulate:a", 1.0, CARD_FADE).from(0.0)

	# A dissolve cross-fades the outgoing shot; a cut drops it. The previous
	# shot's own transition decides, not this one's.
	if previous != null:
		var out := "cut"
		if _shot_index > 0:
			out = String((_shots[_shot_index - 1] as Dictionary).get("out_transition", "cut"))
		if out == "cut":
			previous.queue_free()
		else:
			var wipe := create_tween()
			wipe.tween_property(previous, "modulate:a", 0.0, DISSOLVE)
			wipe.tween_callback(previous.queue_free)


func _tick_opening(delta: float) -> void:
	_shot_elapsed += delta
	var shot: Dictionary = _shots[_shot_index] if _shot_index < _shots.size() else {}
	if _shot_elapsed >= float(shot.get("seconds", 4.0)):
		_advance_shot()


## The move a shot is played with. Presentation only, and a pure function of the
## shot's own seconds: the contract owns which move, the host owns how it feels.
func _apply_move(picture: Control, move: String, seconds: float) -> void:
	var travel := 0.06
	var tween := create_tween()
	tween.set_ease(Tween.EASE_IN_OUT).set_trans(Tween.TRANS_SINE)
	match move:
		"push_in":
			picture.scale = Vector2.ONE
			tween.tween_property(picture, "scale", Vector2.ONE * (1.0 + travel), seconds)
		"pull_out":
			picture.scale = Vector2.ONE * (1.0 + travel)
			tween.tween_property(picture, "scale", Vector2.ONE, seconds)
		"pan_left":
			tween.tween_property(picture, "position:x", -travel * _window().x, seconds)
		"pan_right":
			tween.tween_property(picture, "position:x", travel * _window().x, seconds)
		_:
			tween.kill()


# ===========================================================================
# The title
# ===========================================================================


func _enter_title() -> void:
	if _phase == "title":
		return
	_phase = "title"
	for child in _root.get_children():
		(child as Node).queue_free()
	_shot_node = null
	_card_node = null

	var title: Dictionary = _block.get("title", {})
	_title_node = Control.new()
	_title_node.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(_title_node)
	_backdrop_layers.clear()

	for entry: Variant in title.get("backdrop", []):
		var layer: Dictionary = entry
		var texture := _plate_texture(layer.get("plate", {}))
		if texture == null:
			continue
		var rect := _cover_rect(texture)
		_title_node.add_child(rect)
		_backdrop_layers.append(rect)

	# The mark: an emblem over the game's own name, both inside the band the
	# pipeline measured for legibility. The name is a string, never a plate.
	var band := _region("title", "mark_band")
	var mark := VBoxContainer.new()
	mark.alignment = BoxContainer.ALIGNMENT_CENTER
	mark.add_theme_constant_override("separation", int(24.0 * _scale))
	mark.position = band.position
	mark.size = band.size
	_title_node.add_child(mark)

	var emblem := _plate_texture(title.get("emblem", {}))
	if emblem != null:
		var badge := TextureRect.new()
		badge.texture = emblem
		badge.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		badge.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		badge.custom_minimum_size = Vector2(0.0, band.size.y * 0.52)
		badge.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		mark.add_child(badge)

	var wordmark := Label.new()
	wordmark.text = _display_name()
	wordmark.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	wordmark.add_theme_color_override("font_color", SurvivalUiKit.TEXT)
	wordmark.add_theme_color_override("font_outline_color", SurvivalUiKit.OUTLINE)
	wordmark.add_theme_constant_override("outline_size", int(10.0 * _scale))
	if _font != null:
		wordmark.add_theme_font_override("font", _font)
	wordmark.add_theme_font_size_override("font_size", int(band.size.y * 0.34))
	mark.add_child(wordmark)

	# The controls. They are `button_rect` bodies from the run's own interface
	# sheets, which is why the backdrop under them is not gated for legibility:
	# a label reads because the button is behind it.
	var stack := VBoxContainer.new()
	var column := _region("title", "control_stack")
	stack.position = column.position
	stack.size = column.size
	stack.alignment = BoxContainer.ALIGNMENT_BEGIN
	stack.add_theme_constant_override("separation", int(16.0 * _scale))
	_title_node.add_child(stack)

	var play := SurvivalUiKit.button("Play", int(22.0 * _scale))
	play.custom_minimum_size = Vector2(column.size.x, 0.0)
	if kit != null and kit.has_frames():
		for state: String in ["normal", "hover", "pressed", "disabled"]:
			play.add_theme_stylebox_override(state, kit.button_style(state))
	if _font != null:
		play.add_theme_font_override("font", _font)
	play.pressed.connect(_on_play)
	stack.add_child(play)

	title_reached.emit()


func _tick_title(delta: float) -> void:
	# Parallax: the layers drift on a slow sine, each nearer one further. No
	# frames were generated for this; it is the same pixels, moved.
	_drift_phase += delta / DRIFT_SECONDS
	var published := float(_block.get("title", {}).get("drift", 0))
	var budget: float = published * _scale
	for index in _backdrop_layers.size():
		var layer := _backdrop_layers[index]
		var depth := float(index + 1) / float(_backdrop_layers.size())
		var offset := sin(_drift_phase * TAU) * budget * depth * 0.5
		layer.position.x = offset


func _on_play() -> void:
	play_pressed.emit()


# ===========================================================================
# The loading screen
# ===========================================================================


## Show the loading screen and start warming the run's media. The frame owner
## calls this on `play_pressed`; when `loading_finished` fires it may boot.
func begin_loading() -> void:
	_phase = "loading"
	_loading_elapsed = 0.0
	_preload_cursor = 0
	_preload_done = false
	_preload_refs = _closure_refs()
	for child in _root.get_children():
		(child as Node).queue_free()
	_backdrop_layers.clear()

	var loading: Dictionary = _block.get("loading", {})
	_loading_node = Control.new()
	_loading_node.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(_loading_node)

	var backdrop := _loading_backdrop(loading)
	if backdrop != null:
		_loading_node.add_child(_cover_rect(backdrop))

	var strip := _region("loading", "status_strip")
	var column := VBoxContainer.new()
	column.position = strip.position
	column.size = strip.size
	column.alignment = BoxContainer.ALIGNMENT_END
	column.add_theme_constant_override("separation", int(14.0 * _scale))
	_loading_node.add_child(column)

	var tip := _pick_tip(loading)
	if tip != "":
		var label := Label.new()
		label.text = tip
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.add_theme_color_override("font_color", SurvivalUiKit.TEXT)
		label.add_theme_color_override("font_outline_color", SurvivalUiKit.OUTLINE)
		label.add_theme_constant_override("outline_size", SurvivalUiKit.OUTLINE_SIZE)
		if _font != null:
			label.add_theme_font_override("font", _font)
		label.add_theme_font_size_override("font_size", int(20.0 * _scale))
		column.add_child(label)

	_progress = ProgressBar.new()
	_progress.min_value = 0.0
	_progress.max_value = 1.0
	_progress.value = 0.0
	_progress.show_percentage = false
	_progress.custom_minimum_size = Vector2(0.0, 10.0 * _scale)
	column.add_child(_progress)


func _tick_loading(delta: float) -> void:
	_loading_elapsed += delta
	# Decode a slice of the closure per frame rather than all of it at once, so
	# the bar moves and the window keeps answering.
	var budget := 4
	while budget > 0 and _preload_cursor < _preload_refs.size():
		var ref := _preload_refs[_preload_cursor]
		if ref.ends_with(".mp3"):
			package.audio(ref)
		else:
			package.texture(ref)
		_preload_cursor += 1
		budget -= 1
	if _progress != null:
		var total := maxi(1, _preload_refs.size())
		_progress.value = float(_preload_cursor) / float(total)
	if _preload_cursor >= _preload_refs.size() and _loading_elapsed >= MIN_DWELL:
		_preload_done = true


## True once the media is warm and the minimum dwell has passed.
func loading_finished() -> bool:
	return _preload_done


## Take the shell down. The frame owner calls this once the world is standing.
func close() -> void:
	_phase = "idle"
	if _root != null:
		_root.queue_free()
		_root = null
	_backdrop_layers.clear()
	hide()


# ===========================================================================
# Reading the block
# ===========================================================================


func _shot_list() -> Array:
	var opening: Dictionary = _block.get("opening", {})
	var shots: Variant = opening.get("shots", [])
	return shots if typeof(shots) == TYPE_ARRAY else []


func _skippable() -> bool:
	return bool(_block.get("opening", {}).get("skippable", true))


func _display_name() -> String:
	return String(_block.get("strings", {}).get("display_name", ""))


func _pick_tip(loading: Dictionary) -> String:
	var tips: Variant = loading.get("tips", [])
	if typeof(tips) != TYPE_ARRAY or (tips as Array).is_empty():
		return ""
	# The seeded generator, never the wall clock: a replay of one seed shows one
	# tip (the host contract's rule 3).
	var layout: Dictionary = package.layout if not package.layout.is_empty() else {}
	var seed_value := int(layout.get("seed", 1))
	return String((tips as Array)[seed_value % (tips as Array).size()])


## Every rectangle is published in canvas pixels; the host scales the canvas to
## the window and scales the rectangles by the same factor. Nothing is inferred.
func _region(screen: String, name: String) -> Rect2:
	var block: Dictionary = _block.get(screen, {})
	var canvas: Dictionary = block.get("canvas", {})
	_canvas = Vector2(
		float(canvas.get("width", CANVAS_REFERENCE.x)),
		float(canvas.get("height", CANVAS_REFERENCE.y)),
	)
	var window := _window()
	_scale = window.y / _canvas.y
	var fallback := Rect2(Vector2.ZERO, window)
	for entry: Variant in block.get("reserved", []):
		var reserved: Dictionary = entry
		if String(reserved.get("region", "")) != name:
			continue
		var rect: Dictionary = reserved.get("rect", {})
		var offset := (window.x - _canvas.x * _scale) * 0.5
		return Rect2(
			Vector2(float(rect.get("x", 0)) * _scale + offset, float(rect.get("y", 0)) * _scale),
			Vector2(float(rect.get("width", 0)) * _scale, float(rect.get("height", 0)) * _scale),
		)
	return fallback


func _plate_texture(plate: Variant) -> Texture2D:
	if typeof(plate) != TYPE_DICTIONARY:
		return null
	var ref := String((plate as Dictionary).get("asset", ""))
	return package.texture(ref) if ref != "" else null


func _loading_backdrop(loading: Dictionary) -> Texture2D:
	var backdrop: Dictionary = loading.get("backdrop", {})
	if String(backdrop.get("source", "")) == "generated":
		return _plate_texture(backdrop.get("plate", {}))
	# Bound to art the run already publishes, which costs no generation. The
	# role is resolved against the manifest by the recipe that published it; a
	# role this host cannot resolve simply leaves the screen dark rather than
	# inventing a picture.
	var role := String(backdrop.get("artifact_role", ""))
	var looks: Dictionary = package.manifest.get("seasons", {})
	for key: Variant in looks.keys():
		if role.ends_with(String(key)):
			var look: Dictionary = looks[key]
			var ref := String(look.get("asset", ""))
			if ref != "":
				return package.texture(ref)
	return null


## The face the run publishes, or null for the machine's own font.
func _load_typeface() -> FontFile:
	var face: Dictionary = _block.get("typeface", {})
	var ref := String(face.get("asset", ""))
	if ref == "":
		return null
	var absolute := package.path(ref)
	if absolute == "" or not FileAccess.file_exists(absolute):
		push_warning("shell: the manifest binds a typeface the run does not carry: %s" % ref)
		return null
	var file := FontFile.new()
	var error := file.load_dynamic_font(absolute)
	if error != OK:
		push_warning("shell: the published typeface did not load (%d): %s" % [error, ref])
		return null
	return file


## Every artifact the manifest binds, which is what the loading screen is
## actually waiting for. Derived from the document rather than from a directory
## walk: a consumer never classifies by filename, and this warms exactly what the
## run says it is made of.
func _closure_refs() -> Array[String]:
	var found: Array[String] = []
	_collect_refs(package.manifest, found)
	return found


func _collect_refs(value: Variant, into: Array[String]) -> void:
	match typeof(value):
		TYPE_DICTIONARY:
			for key: Variant in (value as Dictionary).keys():
				_collect_refs((value as Dictionary)[key], into)
		TYPE_ARRAY:
			for entry: Variant in value as Array:
				_collect_refs(entry, into)
		TYPE_STRING:
			var text := String(value)
			var drawable := (
				text.ends_with(".png") or text.ends_with(".webp") or text.ends_with(".mp3")
			)
			if drawable and not text.ends_with(".raw.png") and not into.has(text):
				into.append(text)


func _window() -> Vector2:
	return Vector2(get_viewport().get_visible_rect().size)


## A plate fills the screen: the canvas is 16:9 and so is almost every window,
## and a letterbox on a title screen reads as a bug rather than as respect for
## the aspect ratio.
func _cover_rect(texture: Texture2D) -> TextureRect:
	var rect := TextureRect.new()
	rect.texture = texture
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rect.pivot_offset = _window() * 0.5
	return rect


func _card_label(text: String) -> Label:
	var band := _region("opening", "card_band")
	var label := Label.new()
	label.text = text
	label.position = band.position
	label.size = band.size
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", SurvivalUiKit.TEXT)
	label.add_theme_color_override("font_outline_color", SurvivalUiKit.OUTLINE)
	label.add_theme_constant_override("outline_size", int(6.0 * _scale))
	if _font != null:
		label.add_theme_font_override("font", _font)
	label.add_theme_font_size_override("font_size", int(band.size.y * 0.26))
	return label
