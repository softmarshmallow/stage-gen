class_name CaseChrome
extends Control

## Everything a case draws that is not the beat it is playing.
##
## A port of the shell half of `web/app/_play/CasePlayer.tsx`. In the browser it
## is DOM around a canvas, and that is a decision rather than an accident: the
## chrome belongs to the *container*, not to any one game, so it is drawn in the
## container's own plain type rather than in a package's generated interface.
## This keeps that — no nine-slice, no atlas, no package colours.
##
## Four surfaces, in the browser's own stacking order: the bar, the offer to
## continue, the closing card, and the backlog over all of it. And one rule that
## is easy to miss and matters: **while a curtain or the backlog is up, the leaf
## must not hear the keyboard.** The browser had to say so explicitly, because
## each leaf listens on the window and an overlay that covered only pixels would
## still let the space bar advance a scene nobody can see.

signal continued
signal started_over
signal finished_beat
signal backlog_toggled(open: bool)

const FG := Color(0.902, 0.902, 0.902)
const DIM := Color(0.4, 0.4, 0.4)
const CURTAIN := Color(0.0, 0.0, 0.0, 0.85)
const BACKLOG_GROUND := Color(0.0, 0.0, 0.0, 0.95)
const BUTTON_GROUND := Color(0.0, 0.0, 0.0, 0.8)

const BAR_HEIGHT := 44.0
const BAR_PADDING_X := 18.0
const BAR_TEXT := 18
const BODY_TEXT := 22
const HEAD_TEXT := 28
const SMALL_TEXT := 16

const BUTTON_HEIGHT := 44.0
const BUTTON_PADDING_X := 28.0
const BUTTON_GAP := 16.0
## The Continue affordance sits this far off the bottom of the stage.
const CONTINUE_LIFT := 24.0

const BACKLOG_ROW_GAP := 16.0
const BACKLOG_PADDING := 28.0

var _size: Vector2 = Vector2.ZERO
var _title: Label = null
var _backlog_button: CaseChromeButton = null
var _loading: Label = null
var _curtain: Control = null
var _curtain_head: Label = null
var _curtain_body: Label = null
var _curtain_extra: Label = null
var _curtain_buttons: HBoxContainer = null
var _continue_layer: Control = null
var _backlog_layer: Control = null
var _continue_button: CaseChromeButton = null
var _backlog_close: CaseChromeButton = null
var _backlog_lines: VBoxContainer = null
var _backlog_head: Label = null
var _open := false


static func of(canvas: Vector2) -> CaseChrome:
	var made := CaseChrome.new()
	made._size = canvas
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made.size = canvas
	made._build_bar()
	made._build_loading()
	made._build_continue()
	made._build_curtain()
	made._build_backlog()
	return made


## Anchored once there is a theme, because a control built outside the tree
## measures its own words against a font it will not be drawn in — and one
## right-aligned or centred from that measurement lands somewhere else.
func _ready() -> void:
	_anchor()
	# A control that later says a longer word re-anchors itself.
	_backlog_button.resized.connect(_anchor)
	_continue_button.resized.connect(_anchor)
	_backlog_close.resized.connect(_anchor)


func _anchor() -> void:
	var stage := stage_rect()
	_backlog_button.position = Vector2(
		_size.x - BAR_PADDING_X - _backlog_button.size.x,
		(BAR_HEIGHT - _backlog_button.size.y) / 2.0
	)
	_continue_button.position = Vector2(
		(_size.x - _continue_button.size.x) / 2.0,
		stage.position.y + stage.size.y - CONTINUE_LIFT - _continue_button.size.y
	)
	# In the backlog's own coordinates, which start at the stage.
	_backlog_close.position = Vector2(
		stage.size.x - BACKLOG_PADDING - _backlog_close.size.x, BACKLOG_PADDING
	)


## The rectangle the beat is played in: everything under the bar.
func stage_rect() -> Rect2:
	return Rect2(0.0, BAR_HEIGHT, _size.x, _size.y - BAR_HEIGHT)


## True while a curtain or the backlog is up, which is when the leaf must not
## hear a key.
func covers_leaf() -> bool:
	return _open or _curtain.visible


func backlog_is_open() -> bool:
	return _open


func show_backlog(open: bool) -> void:
	_open = open
	_backlog_layer.visible = open
	_backlog_button.set_label("close backlog" if open else _backlog_button.counted_label)


## One pass over the whole shell from the runtime's state.
func sync(document: Dictionary, state: Dictionary, beat: Dictionary, drawn: Variant) -> void:
	var phase := String(state["phase"])
	var backlog: Array = state["backlog"]
	_backlog_button.counted_label = "backlog (%d)" % backlog.size()
	_backlog_button.set_label("close backlog" if _open else _backlog_button.counted_label)

	var line := String(document["displayName"])
	if not beat.is_empty():
		line += " · %s · beat %d of %d" % [
			String(beat["displayName"]) if beat.has("displayName") else String(beat["beatId"]),
			CaseDocument.beat_number(document, String(beat["beatId"])),
			(document["beats"] as Array).size(),
		]
	_title.text = line

	# The beat's name while a stage and five full-height plates decode. It goes
	# on the beat's first moment rather than being covered, because the leaf
	# draws its own ground.
	_loading.visible = (
		phase == CaseRuntime.PHASE_PLAYING
		and not beat.is_empty()
		and (drawn == null or String(drawn) != String(beat["beatId"]))
	)
	if _loading.visible and not beat.is_empty():
		_loading.text = String(beat.get("displayName", beat["beatId"]))

	var pending: Variant = state["pending"]
	_continue_layer.visible = (
		phase == CaseRuntime.PHASE_PLAYING
		and pending != null
		and String((pending as Dictionary)["beatId"])
			== String((state["progress"] as Dictionary)["beatId"])
	)

	_sync_curtain(document, state)
	_sync_backlog(backlog)


func _sync_curtain(document: Dictionary, state: Dictionary) -> void:
	var phase := String(state["phase"])
	for child in _curtain_buttons.get_children():
		child.queue_free()
	_curtain_extra.visible = false
	if phase == CaseRuntime.PHASE_OFFERING_CONTINUE and state["resume"] != null:
		var save: Dictionary = state["resume"]
		var at := CaseDocument.beat(document, String(save["beatId"]))
		var name := String(at.get("displayName", save["beatId"])) if not at.is_empty() else String(save["beatId"])
		_curtain.visible = true
		_curtain_head.text = String(document["displayName"])
		_curtain_body.text = (
			"A save is waiting at %s." % name
			if save["statementId"] == null
			else "A save is waiting at %s, line %s." % [name, String(save["statementId"])]
		)
		_curtain_buttons.add_child(_button("Continue", func() -> void: continued.emit()))
		_curtain_buttons.add_child(_button("Start over", func() -> void: started_over.emit()))
		return
	if phase == CaseRuntime.PHASE_FINISHED:
		_curtain.visible = true
		_curtain_head.text = "The case is closed."
		_curtain_body.text = "It ended through %s." % String(state["ending"])
		var carried: PackedStringArray = state["carried"]
		if not carried.is_empty():
			var sorted := carried.duplicate()
			sorted.sort()
			_curtain_extra.visible = true
			_curtain_extra.text = "CARRIED OUT OF THE BUILDING · %d\n%s" % [
				carried.size(), " · ".join(sorted)
			]
		_curtain_buttons.add_child(_button("Play it again", func() -> void: started_over.emit()))
		return
	_curtain.visible = false


func _sync_backlog(backlog: Array) -> void:
	_backlog_head.text = "Backlog · the last %d %s" % [
		backlog.size(), "line" if backlog.size() == 1 else "lines"
	]
	for child in _backlog_lines.get_children():
		child.queue_free()
	if backlog.is_empty():
		_backlog_lines.add_child(_text("Nothing has been said yet.", BODY_TEXT, DIM))
		return
	for entry: Variant in backlog:
		var said: Dictionary = entry
		# An em dash for narration: a line nobody said still had a speaker's row.
		var who: Variant = said.get("speaker")
		var speaker := _text(
			("—" if who == null else String(who)).to_upper(), SMALL_TEXT, DIM
		)
		_backlog_lines.add_child(speaker)
		var body := _text(String(said.get("text", "")), BODY_TEXT, FG)
		body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		body.custom_minimum_size = Vector2(_size.x - BACKLOG_PADDING * 4.0, 0.0)
		_backlog_lines.add_child(body)


# --------------------------------------------------------------------- build


func _build_bar() -> void:
	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = Color(0.0, 0.0, 0.0)
	ground.size = Vector2(_size.x, BAR_HEIGHT)
	add_child(ground)

	_title = _text("", BAR_TEXT, DIM)
	_title.position = Vector2(BAR_PADDING_X, (BAR_HEIGHT - BAR_TEXT * 1.4) / 2.0)
	_title.size = Vector2(_size.x - BAR_PADDING_X * 2.0 - 260.0, BAR_TEXT * 1.4)
	_title.clip_text = true
	add_child(_title)

	_backlog_button = CaseChromeButton.of("backlog (0)", SMALL_TEXT)
	_backlog_button.pressed.connect(func() -> void: backlog_toggled.emit(not _open))
	add_child(_backlog_button)


func _build_loading() -> void:
	var stage := stage_rect()
	_loading = _text("", SMALL_TEXT, DIM)
	_loading.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_loading.position = stage.position
	_loading.size = stage.size
	_loading.visible = false
	add_child(_loading)


func _build_continue() -> void:
	var stage := stage_rect()
	_continue_layer = Control.new()
	_continue_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_continue_layer.visible = false
	add_child(_continue_layer)
	_continue_button = CaseChromeButton.of("Continue →", BODY_TEXT, BUTTON_GROUND)
	_continue_button.pressed.connect(func() -> void: finished_beat.emit())
	_continue_layer.add_child(_continue_button)


func _build_curtain() -> void:
	# Over the beat and not over the bar. The bar always says where the player is,
	# even while a curtain is asking them what to do about it.
	var stage := stage_rect()
	_curtain = Control.new()
	_curtain.mouse_filter = Control.MOUSE_FILTER_STOP
	_curtain.position = stage.position
	_curtain.size = stage.size
	_curtain.visible = false
	add_child(_curtain)

	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = CURTAIN
	ground.size = stage.size
	_curtain.add_child(ground)

	var column := VBoxContainer.new()
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_theme_constant_override("separation", 16)
	column.alignment = BoxContainer.ALIGNMENT_CENTER
	column.position = Vector2(stage.size.x * 0.15, 0.0)
	column.size = Vector2(stage.size.x * 0.7, stage.size.y)
	_curtain.add_child(column)

	_curtain_head = _text("", HEAD_TEXT, FG)
	_curtain_head.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(_curtain_head)
	_curtain_body = _text("", BODY_TEXT, DIM)
	_curtain_body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_curtain_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_curtain_body)
	_curtain_extra = _text("", SMALL_TEXT, DIM)
	_curtain_extra.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_curtain_extra.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(_curtain_extra)
	_curtain_buttons = HBoxContainer.new()
	_curtain_buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	_curtain_buttons.add_theme_constant_override("separation", int(BUTTON_GAP))
	column.add_child(_curtain_buttons)


func _build_backlog() -> void:
	var stage := stage_rect()
	_backlog_layer = Control.new()
	_backlog_layer.mouse_filter = Control.MOUSE_FILTER_STOP
	_backlog_layer.position = stage.position
	_backlog_layer.size = stage.size
	_backlog_layer.visible = false
	add_child(_backlog_layer)

	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = BACKLOG_GROUND
	ground.size = stage.size
	_backlog_layer.add_child(ground)

	_backlog_head = _text("", BODY_TEXT, DIM)
	_backlog_head.position = Vector2(BACKLOG_PADDING, BACKLOG_PADDING)
	_backlog_layer.add_child(_backlog_head)

	_backlog_close = CaseChromeButton.of("close", SMALL_TEXT)
	_backlog_close.pressed.connect(func() -> void: backlog_toggled.emit(false))
	_backlog_layer.add_child(_backlog_close)

	var scroll := ScrollContainer.new()
	scroll.position = Vector2(BACKLOG_PADDING, BACKLOG_PADDING * 2.5)
	scroll.size = Vector2(stage.size.x - BACKLOG_PADDING * 2.0, stage.size.y - BACKLOG_PADDING * 3.5)
	_backlog_layer.add_child(scroll)
	_backlog_lines = VBoxContainer.new()
	_backlog_lines.add_theme_constant_override("separation", int(BACKLOG_ROW_GAP))
	_backlog_lines.custom_minimum_size = Vector2(scroll.size.x, 0.0)
	scroll.add_child(_backlog_lines)


func _button(label: String, on_press: Callable) -> CaseChromeButton:
	var made := CaseChromeButton.of(label, BODY_TEXT)
	made.pressed.connect(on_press)
	return made


func _text(value: String, size: int, colour: Color) -> Label:
	var made := Label.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made.add_theme_font_size_override("font_size", size)
	made.add_theme_color_override("font_color", colour)
	made.text = value
	return made
