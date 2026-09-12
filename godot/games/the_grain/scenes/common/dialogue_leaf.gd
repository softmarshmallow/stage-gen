class_name HostDialogueLeaf
extends Control

const ScenarioRefusal = preload("res://addons/scenario_runtime/refusal.gd")
const ScenarioProgram = preload("res://addons/scenario_runtime/program.gd")
const ScenarioRuntime = preload("res://addons/scenario_runtime/runtime.gd")

## A dialogue scene, drawn and played.
##
## A port of `web/lib/dialogue-scene/scene-game.ts`. The stage, the cast, the
## conversation panel, the choice row and the end card, in one 1672x941 design
## frame the host scales to whatever window it lands in.
##
## **It lives in `hosts/common/` for the same reason the room's leaf does**:
## three hosts draw it. The scene host plays one scenario, and the case host
## plays six of them in order with a room between.
##
## There is no loop and no `update`. Everything redraws inside `_render`, which
## runs once when the leaf opens and once per accepted action — the browser's
## scene has no tween, no typewriter and no fade either, and inventing one here
## would be a second opinion about a moment the reducer already decided.

## What was just drawn, for a shell that autosaves every line.
## `line` is empty when the moment is not one.
signal moment(state: Dictionary, statement_id: Variant, line: Dictionary, outcome: Variant)
## An `advance` at an ending, when a shell is listening. Without one the same
## gesture restarts the scene.
signal finished(outcome: String, flags: PackedStringArray)

const PAPER := Color(0.9569, 0.9451, 0.9333)
const INK := Color(0.0784, 0.0902, 0.149)
const DIM := Color(0.6627, 0.6902, 0.7843)
const GROUND := Color(0.0196, 0.0275, 0.0392)

## The body's step-down ladder. A line is authored prose in a fixed box, so the
## size comes down until it fits and the label clips below the floor — the same
## rule the room's narration plate keeps, for the same reason.
const BODY_SIZES := [30, 26, 22]
const BODY_LINE_SPACING := 12
const SPEAKER_SIZE := 24
const META_SIZE := 20
const CHOICE_SIZE := 28
## The end card's own ladder. An outcome label is authored prose in a fixed card:
## `first_bell` is "The first person who thinks this dinner is about them", which
## is two rows at 38 in a box that holds one, and the second row was simply not
## drawn.
const TITLE_SIZES := [38, 32, 26]

## Depth rungs: the world, the cast above it by its own stacking, then the
## furniture, then whatever ends the scene.
const DEPTH_BACKDROP := 0
const DEPTH_SPRITE := 10
const DEPTH_PANEL := 100
const DEPTH_TEXT := 101
const DEPTH_CHOICE := 150
const DEPTH_COMPLETE := 200

## What a track is played at. The browser's HTML audio volume, in decibels.
const TRACK_VOLUME := 0.55

var bundle: Dictionary = {}
var program: Dictionary = {}

var _package: HostRunDir = null
var _sheets: HostUiSheets = null
var _state: Dictionary = {}
var _placement: Dictionary = {}
var _turn_events: Array = []

var _backdrop: TextureRect = null
var _cast: Dictionary = {}
var _panel: HostPanelFrame = null
var _name: Label = null
var _body: Label = null
var _progress: Label = null
var _choice_layer: Control = null
var _choices: Array = []
var _complete: Control = null
var _complete_title: Label = null
var _complete_control: HostAtlasButton = null
var _players: Dictionary = {}
var _playing: PackedStringArray = PackedStringArray()


## What a dialogue-scene run's document is called. Not `manifest.json`: a scene
## run has no manifest at all.
const DOCUMENT_REF := "bundle.json"


## Open a scene run, choose one of its scenarios, and build the leaf, or refuse.
##
## The parse is behind this door for the same reason the room's is: a case host
## may not name `DialogueBundle`, and what it may name is a leaf player that
## knows its own genre.
static func open(
	run_dir: String,
	scenario_id: String = "",
	carried: PackedStringArray = PackedStringArray(),
	resume: Variant = null
) -> Variant:
	var package := HostRunDir.open(run_dir, Callable(), "", DOCUMENT_REF)
	if package == null:
		return KernelRefusal.of(
			"dialogue/run", "%s has no readable %s" % [run_dir, DOCUMENT_REF], run_dir
		)
	var parsed: Variant = DialogueBundle.parse(package.manifest, scenario_id)
	if KernelRefusal.is_refusal(parsed):
		return parsed
	return of(package, parsed as Dictionary, carried, resume)


## Build one scene over an opened run. `document` is the parsed bundle,
## `carried` the facts an earlier beat set, `resume` a saved playback or null.
static func of(
	package: HostRunDir,
	document: Dictionary,
	carried: PackedStringArray = PackedStringArray(),
	resume: Variant = null
) -> Variant:
	var parsed: Variant = ScenarioProgram.parse(document["scenario"])
	if ScenarioRefusal.is_refusal(parsed):
		return _scenario_refusal(parsed)
	var sheets := HostUiSheets.of(package, document.get("ui"))
	if not sheets.has("panel_frame") or not sheets.has("button_rect"):
		return KernelRefusal.of(
			"dialogue/ui",
			(
				"this scene publishes no panel or button art; regenerate it with a current "
				+ "stage-gen (stage-gen dialogue-scene generate)"
			),
			"scene_data.ui"
		)
	var placement: Variant = DialogueFraming.placement(
		float((document["placement"] as Dictionary)["framingZoom"]),
		float((document["placement"] as Dictionary)["sourceFramingZoom"])
	)
	if KernelRefusal.is_refusal(placement):
		return placement

	var made := HostDialogueLeaf.new()
	made._package = package
	made._sheets = sheets
	made.bundle = document
	made.program = parsed
	made._placement = placement
	made.mouse_filter = Control.MOUSE_FILTER_STOP
	made.size = Vector2(DialogueLayout.STAGE_WIDTH, DialogueLayout.STAGE_HEIGHT)

	# A save that no longer fits its program is not a save. The player is opened
	# fresh rather than resumed onto an actor nobody declares.
	var restored: Variant = (
		null if resume == null else ScenarioRuntime.restore(parsed, resume)
	)
	if restored is Dictionary:
		made._state = restored
	else:
		var opening := ScenarioRuntime.initial_state(parsed, carried)
		if ScenarioRefusal.is_refusal(opening):
			made.free()
			return _scenario_refusal(opening)
		made._state = opening

	var built: Variant = made._build()
	if KernelRefusal.is_refusal(built):
		return built
	made._render()
	return made


## The opening moment's tracks, started once there is a tree to play them in.
##
## The first render happens while the leaf is still being built — that is what
## makes "what is drawn" a pure function of the state — and an audio player
## outside the tree refuses to play. So the intent is recorded then and the
## sound starts here, which is also how the browser's own audio waits for the
## first gesture.
func _ready() -> void:
	_start_tracks()


func canvas() -> Dictionary:
	return DialogueLayout.stage_size()


func state() -> Dictionary:
	return _state


## Say the moment that is already on screen. A shell that connects after the
## leaf was built asks for it once, so its first save is its first line.
func report() -> void:
	_report(view())


func view() -> Dictionary:
	return ScenarioRuntime.view(program, _state)


## One transition. `advance` at an ending hands over to a listening shell
## instead of restarting, which is the whole of the seam a case needs.
func act(action: Dictionary) -> void:
	var current := view()
	if String(current.get("kind", "")) == "end" and String(action.get("kind", "")) == "advance":
		if finished.get_connections().size() > 0:
			_silence()
			var flags := PackedStringArray()
			for flag: Variant in (_state["flags"] as Array):
				flags.append(String(flag))
			finished.emit(String(current["outcome"]), flags)
			return
		action = {"kind": ScenarioRuntime.ACTION_RESTART}
	var turn := ScenarioRuntime.reduce_turn(program, _state, action)
	if ScenarioRefusal.is_refusal(turn):
		push_warning("dialogue scene: %s" % ScenarioRefusal.line(turn))
		return
	# A turn that moved nothing raises nothing, which is how "nothing happened"
	# is a checkable answer rather than an object a caller compares by identity.
	if (turn["events"] as Array).is_empty():
		return
	_state = turn["state"]
	_turn_events = turn["events"]
	_render()


func advance() -> void:
	act({"kind": ScenarioRuntime.ACTION_ADVANCE})


func choose(option: int) -> void:
	act({"kind": ScenarioRuntime.ACTION_CHOOSE, "option": option})


## Stop every track. A shell leaving this beat owes the next one silence.
func silence() -> void:
	_silence()


# --------------------------------------------------------------------- build


func _build() -> Variant:
	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = GROUND
	ground.size = size
	add_child(ground)

	_backdrop = TextureRect.new()
	_backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_backdrop.stretch_mode = TextureRect.STRETCH_SCALE
	_backdrop.size = size
	_backdrop.z_index = DEPTH_BACKDROP
	add_child(_backdrop)
	var opening: Array = bundle["stages"]
	if opening.is_empty():
		return KernelRefusal.of("dialogue/stages", "this scene publishes no backdrop", "stages")
	_backdrop.texture = _package.texture(String((opening[0] as Dictionary)["path"]))
	if _backdrop.texture == null:
		return KernelRefusal.of(
			"dialogue/stages",
			"this scene's opening backdrop (%s) will not decode"
			% String((opening[0] as Dictionary)["path"]),
			"stages"
		)

	for entry: Variant in (bundle["actors"] as Array):
		var member: Dictionary = entry
		var plate := TextureRect.new()
		plate.mouse_filter = Control.MOUSE_FILTER_IGNORE
		plate.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		plate.stretch_mode = TextureRect.STRETCH_SCALE
		plate.visible = false
		add_child(plate)
		_cast[String(member["actorId"])] = plate

	var built: Variant = _build_panel()
	if KernelRefusal.is_refusal(built):
		return built
	_build_choices()
	_build_complete()
	return true


func _build_panel() -> Variant:
	_panel = HostPanelFrame.of(_sheets, "panel_frame", DialogueLayout.panel_rect(_insets()))
	if _panel == null:
		return KernelRefusal.of(
			"dialogue/ui", "this scene publishes no conversation panel", "ui.panel_frame"
		)
	_panel.z_index = DEPTH_PANEL
	add_child(_panel)
	var box: Variant = DialogueLayout.box_layout(_panel.safe_rect())
	if KernelRefusal.is_refusal(box):
		return box
	var laid: Dictionary = box

	_name = _label(SPEAKER_SIZE, _readable(_panel, [INK, PAPER], 4.5, INK))
	_name.position = Vector2(
		float((laid["name"] as Dictionary)["x"]), float((laid["name"] as Dictionary)["y"])
	)
	_name.z_index = DEPTH_TEXT + 1
	add_child(_name)

	_body = _label(int(BODY_SIZES[0]), _readable(_panel, [PAPER, INK], 4.5, PAPER))
	_body.add_theme_constant_override("line_spacing", BODY_LINE_SPACING)
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.clip_text = true
	_body.position = Vector2(
		float((laid["body"] as Dictionary)["x"]), float((laid["body"] as Dictionary)["y"])
	)
	_body.size = Vector2(float(laid["bodyWrapWidth"]), float(laid["bodyHeight"]))
	_body.z_index = DEPTH_TEXT
	add_child(_body)

	# Dim grey first, then ink, then paper — the browser's candidate order, at the
	# browser's own threshold. A first draft asked for 3.0 here, which is the
	# *room's* number for its control hint; the scene's readout was always
	# measured at the body-text ratio like everything else on this panel.
	_progress = _label(
		META_SIZE, _readable(_panel, [DIM, INK, PAPER], FamilyContrast.BODY_TEXT_RATIO, DIM)
	)
	_progress.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_progress.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	_progress.z_index = DEPTH_TEXT
	var corner: Dictionary = laid["progress"]
	_progress.size = Vector2(360.0, float(META_SIZE) * 1.6)
	_progress.position = Vector2(
		float(corner["x"]) - _progress.size.x, float(corner["y"]) - _progress.size.y
	)
	add_child(_progress)
	return true


func _build_choices() -> void:
	_choice_layer = Control.new()
	_choice_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_choice_layer.z_index = DEPTH_CHOICE
	_choice_layer.visible = false
	add_child(_choice_layer)


func _build_complete() -> void:
	_complete = Control.new()
	_complete.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_complete.z_index = DEPTH_COMPLETE
	_complete.visible = false
	add_child(_complete)

	var card := DialogueLayout.complete_card_rect()
	var frame := HostPanelFrame.of(_sheets, "panel_frame", card)
	_complete.add_child(frame)
	var safe := frame.safe_rect()
	var control_rect := DialogueLayout.complete_control_rect(card)
	_complete_title = _label(int(TITLE_SIZES[0]), _readable(frame, [PAPER, INK], 4.5, PAPER))
	_complete_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_complete_title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_complete_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	# The words get exactly the room above the control and no more, and they are
	# clipped to it. An outcome label is authored prose and the card is a fixed
	# rectangle, so the two meet somewhere; an ending that ran over the button
	# that answers it would be the worst place for them to meet.
	_complete_title.clip_text = true
	_complete_title.position = Vector2(float(safe["x"]), float(safe["y"]))
	_complete_title.size = Vector2(
		float(safe["width"]),
		maxf(float(TITLE_SIZES[0]), float(control_rect["y"]) - float(safe["y"]) - 10.0)
	)
	# Explicitly above the frame it sits on. The browser left this label at the
	# default depth while its siblings were at 200, so whether the words drew over
	# the card or under it was the engine's business rather than the author's.
	_complete_title.z_index = 1
	_complete.add_child(_complete_title)

	# This genre's own paper and ink, rather than the button's defaults, which are
	# the room's. What the measurement chooses between is the palette the scene
	# was drawn in.
	_complete_control = HostAtlasButton.of(_sheets, control_rect, "", "retry", PAPER, INK)
	if _complete_control != null:
		_complete_control.z_index = 1
		_complete_control.pressed.connect(advance)
		_complete.add_child(_complete_control)


func _label(size: int, colour: Color) -> Label:
	var made := Label.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made.add_theme_font_size_override("font_size", size)
	made.add_theme_color_override("font_color", colour)
	return made


# --------------------------------------------------------------------- input


func _gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var click: InputEventMouseButton = event
	if click.button_index != MOUSE_BUTTON_LEFT or click.pressed:
		return
	# A choice belongs to its buttons; a tap anywhere else is a step forward.
	if String(view().get("kind", "")) == "choice":
		return
	advance()


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey):
		return
	var key: InputEventKey = event
	if not key.pressed or key.echo:
		return
	var current := view()
	if String(current.get("kind", "")) == "choice":
		var options: Array = current.get("options", [])
		var digit := key.keycode - KEY_1
		if digit >= 0 and digit < 9 and digit < options.size():
			accept_event()
			choose(digit)
		return
	if key.keycode == KEY_ENTER or key.keycode == KEY_SPACE or key.keycode == KEY_RIGHT:
		accept_event()
		advance()


# -------------------------------------------------------------------- render


func _render() -> void:
	var current := view()
	_report(current)
	_apply_tracks()
	_render_stage()
	_render_cast(current)

	var showing_line := String(current.get("kind", "")) == "line"
	var showing_choice := String(current.get("kind", "")) == "choice"
	var showing_end := String(current.get("kind", "")) == "end"
	_panel.visible = showing_line
	_name.visible = showing_line
	_body.visible = showing_line
	_progress.visible = showing_line
	_choice_layer.visible = showing_choice
	_complete.visible = showing_end

	if showing_end:
		_set_title(String(current.get("label", "")))
		_hide_choices()
		return
	if showing_choice:
		_render_choices(current.get("options", []))
		return
	_hide_choices()
	if not showing_line:
		return
	_set_body(String(current.get("text", "")))
	var seen := ScenarioRuntime.progress(program, _state)
	_progress.text = "%d / %d · tap to continue" % [int(seen["seen"]), int(seen["total"])]
	var label: Variant = current.get("speakerLabel")
	_name.text = "" if label == null else String(label)
	_name.visible = _name.text != ""


func _report(current: Dictionary) -> void:
	var kind := String(current.get("kind", ""))
	var statement: Variant = (
		null
		if kind == "end" or kind == ""
		else ScenarioRuntime.statement_id(String(_state["label"]), int(_state["index"]))
	)
	var line: Dictionary = {}
	if kind == "line":
		line = {"speaker": current.get("speakerLabel"), "text": String(current.get("text", ""))}
	moment.emit(_state, statement, line, current.get("outcome"))
	_turn_events = []


func _render_stage() -> void:
	var stage_id: Variant = _state["stage"]
	if stage_id == null:
		return
	var found := DialogueBundle.stage(bundle, String(stage_id))
	if found.is_empty():
		return
	var texture := _package.texture(String(found["path"]))
	if texture != null:
		_backdrop.texture = texture


func _render_cast(current: Dictionary) -> void:
	var speaking: Variant = (
		current.get("speaker") if String(current.get("kind", "")) == "line" else null
	)
	var staged := {}
	for entry: Variant in (_state["actors"] as Array):
		var member: Dictionary = entry
		staged[String(member["actorId"])] = member
	for actor_id: Variant in _cast.keys():
		var plate: TextureRect = _cast[actor_id]
		if not staged.has(actor_id):
			plate.visible = false
			continue
		var member: Dictionary = staged[actor_id]
		var variant := DialogueBundle.expression(bundle, String(actor_id), member["expression"])
		if variant.is_empty():
			plate.visible = false
			continue
		var texture := _package.texture(String(variant["path"]))
		if texture == null:
			plate.visible = false
			continue
		var slot := String(member["slot"])
		var emphasis := (
			DialogueLayout.narration_emphasis(slot)
			if speaking == null
			else DialogueLayout.actor_emphasis(slot, String(speaking) == String(actor_id))
		)
		var frame := DialogueLayout.emphasized_frame(
			DialogueLayout.slot_frame(
				{"width": texture.get_width(), "height": texture.get_height()}, _placement, slot
			),
			float(emphasis["scale"])
		)
		plate.texture = texture
		plate.position = Vector2(float(frame["x"]), float(frame["y"]))
		plate.size = Vector2(float(frame["width"]), float(frame["height"]))
		plate.z_index = DEPTH_SPRITE + int(emphasis["stackOrder"])
		var tint: Array = emphasis["tint"]
		plate.modulate = (
			Color(1.0, 1.0, 1.0, float(emphasis["alpha"]))
			if tint.is_empty()
			else Color(
				float(tint[0]) / 255.0,
				float(tint[1]) / 255.0,
				float(tint[2]) / 255.0,
				float(emphasis["alpha"])
			)
		)
		plate.visible = true


## The choice row, grown but never destroyed: taking a button apart while it is
## dispatching the press that caused this render is how a menu stops answering.
func _render_choices(options: Array) -> void:
	var rects := DialogueLayout.choice_rects(options.size(), _insets())
	while _choices.size() < rects.size():
		var index := _choices.size()
		var button := HostAtlasButton.of(_sheets, rects[index], "", "", PAPER, INK)
		if button == null:
			break
		button.pressed.connect(func() -> void: choose(index))
		_choice_layer.add_child(button)
		_choices.append(button)
	for index in _choices.size():
		var button: HostAtlasButton = _choices[index]
		var shown := index < rects.size()
		button.visible = shown
		button.set_enabled(shown)
		if not shown:
			continue
		button.set_rect(rects[index])
		# Wrapped to the button's own interior. An option is authored prose in a
		# fixed rectangle, and the browser broke a long one onto a second line
		# rather than letting its ends hang off the art on both sides.
		button.set_wrapped_label(String((options[index] as Dictionary).get("text", "")))


func _hide_choices() -> void:
	for entry: Variant in _choices:
		var button: HostAtlasButton = entry
		button.visible = false
		button.set_enabled(false)


# --------------------------------------------------------------------- audio


## The tracks the reducer says are playing, as a set difference: one that was
## playing before and after is never restarted.
func _apply_tracks() -> void:
	var wanted := PackedStringArray()
	for entry: Variant in (_state["tracks"] as Array):
		wanted.append(String(entry))
	for playing in _playing:
		# A track whose mp3 is missing caches a null player, and calling `stop` on
		# that aborts this function — which would leave `_playing` holding the
		# dead track and silence every track after it for the rest of the scene.
		# The browser skipped a missing source and kept the rest of the
		# soundtrack; so does this.
		if not wanted.has(playing) and _players.get(playing) != null:
			(_players[playing] as AudioStreamPlayer).stop()
	_playing = wanted
	_start_tracks()


## Play whatever the state says should be sounding and is not.
func _start_tracks() -> void:
	if not is_inside_tree():
		return
	for track_id in _playing:
		var player := _player(track_id)
		if player != null and not player.playing:
			player.play()


func _player(track_id: String) -> AudioStreamPlayer:
	if _players.has(track_id):
		return _players[track_id]
	var found := DialogueBundle.track(bundle, track_id)
	var made: AudioStreamPlayer = null
	if not found.is_empty():
		var stream := _package.audio(String(found["path"]))
		if stream != null:
			stream.loop = true
			made = AudioStreamPlayer.new()
			made.stream = stream
			made.volume_db = linear_to_db(TRACK_VOLUME)
			add_child(made)
	_players[track_id] = made
	return made


func _silence() -> void:
	for entry: Variant in _players.values():
		if entry != null:
			(entry as AudioStreamPlayer).stop()
	_playing = PackedStringArray()


## The panel sheet's insets in screen pixels: its own, divided by the density it
## was authored at.
func _insets() -> Dictionary:
	var block := _sheets.block("panel_frame")
	var insets: Dictionary = block.get("insets", {})
	var factor := maxf(1.0, float(block.get("draw_scale", 1)))
	return {
		"left": float(insets.get("left", 0)) / factor,
		"top": float(insets.get("top", 0)) / factor,
		"right": float(insets.get("right", 0)) / factor,
		"bottom": float(insets.get("bottom", 0)) / factor,
	}


## Put the ending's own words on the card, whole.
func _set_title(value: String) -> void:
	var size := HostTextFit.fitted_size(
		_complete_title.get_theme_font("font"),
		value,
		_complete_title.size.x,
		_complete_title.size.y,
		TITLE_SIZES,
		0
	)
	_complete_title.add_theme_font_size_override("font_size", size)
	_complete_title.text = value


## Put the line in the box, and keep it in it.
func _set_body(value: String) -> void:
	var size := HostTextFit.fitted_size(
		_body.get_theme_font("font"),
		value,
		_body.size.x,
		_body.size.y,
		BODY_SIZES,
		BODY_LINE_SPACING
	)
	_body.add_theme_font_size_override("font_size", size)
	_body.text = value


func _readable(panel: HostPanelFrame, candidates: Array, ratio: float, fallback: Color) -> Color:
	var face := panel.interior_color()
	if face.is_empty():
		return fallback
	var channels: Array = []
	for entry: Variant in candidates:
		var colour: Color = entry
		channels.append([colour.r * 255.0, colour.g * 255.0, colour.b * 255.0])
	var choice := FamilyContrast.most_readable(face, channels, ratio)
	return fallback if choice < 0 else candidates[choice]


## Adapt package failures to this game's existing load-error boundary.
static func _scenario_refusal(value: Dictionary) -> KernelRefusal:
	var error: Dictionary = value["error"]
	return KernelRefusal.of(error["code"], error["message"], error["path"])
