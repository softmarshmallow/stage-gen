extends Node2D

## The case host: several leaves played in order, with facts crossing between
## them.
##
##   Godot --path godot res://hosts/case/main.tscn -- \
##       --run <absolute case run directory> [--runs <directory holding the beats' runs>]
##
## It opens `case.json`, plays the beat the case enters at, and moves to the next
## on the outcome each leaf reports. It owns the beat order's *drawing* — the
## chrome, the curtains, the backlog and the save — and no rule: the order, the
## facts and what a save is are all in `genres/case/`, where a headless harness
## compares them against the browser action for action.
##
## The two leaves it plays are `hosts/common/`'s, the same objects the room host
## and the scene host play. That is the whole reason they live there.
##
## A case has no clock either. Every transition is a click or a key.

const CASE_REF := "case.json"
const CANVAS := Vector2(1672.0, 1024.0)
## Where the container's own chrome sits, above anything a leaf draws.
const CHROME_DEPTH := 1000

var package: HostRunDir = null
var document: Dictionary = {}
var state: Dictionary = {}
var chrome: CaseChrome = null
## The beat being played: a `HostRoomLeaf` or a `HostDialogueLeaf`, or null.
var leaf: Control = null
var tag: String = ""
var runs_dir: String = ""

var _root: Control = null
var _stage: Control = null
var _drawn: Variant = null
var _beat_id: String = ""


func _ready() -> void:
	var args := HostArgs.parse(OS.get_cmdline_user_args())
	if args.run.is_empty():
		_refuse("case host: pass the case run directory after `-- --run <dir>`")
		return
	package = HostRunDir.open(args.run, Callable(), "", CASE_REF)
	if package == null:
		_refuse("case host: %s has no readable %s" % [args.run, CASE_REF])
		return
	var parsed: Variant = CaseDocument.parse(package.manifest)
	if KernelRefusal.is_refusal(parsed):
		_refuse((parsed as KernelRefusal).line())
		return
	document = parsed
	tag = args.run.get_file()
	# A beat names a run by tag, and a tag is a directory beside this one unless
	# the caller says otherwise.
	runs_dir = args.runs if args.runs != "" else args.run.get_base_dir()

	_root = Control.new()
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	# The container's own ground. Each leaf draws in its own design space — a room
	# is taller than it is wide and a scene is wider than it is tall — so one of
	# them always letterboxes, and without this the bars are pixels nothing
	# painted.
	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = Color(0.0, 0.0, 0.0)
	ground.size = CANVAS
	_root.add_child(ground)
	_stage = Control.new()
	_stage.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_stage.clip_contents = true
	_root.add_child(_stage)
	chrome = CaseChrome.of(CANVAS)
	# Above every depth a leaf reaches for. A leaf draws its own furniture at up
	# to 200 — the scene's end card is there — and the container's curtains and
	# backlog are the browser's z-20 and z-30, which is to say: over all of it.
	chrome.z_index = CHROME_DEPTH
	chrome.continued.connect(_on_continue)
	chrome.started_over.connect(_on_start_over)
	chrome.finished_beat.connect(_on_pending_finish)
	chrome.backlog_toggled.connect(_on_backlog)
	_root.add_child(chrome)
	var stage_rect := chrome.stage_rect()
	_stage.position = stage_rect.position
	_stage.size = stage_rect.size

	state = CaseRuntime.initial(document)
	_reduce({"kind": "opened", "saved": CaseStore.read(tag)})
	_scale_to_window()
	get_viewport().size_changed.connect(_scale_to_window)


## Open on a named beat rather than playing to it, for a capture. A case walks
## forward and never back, and a sheet that had to play four hundred lines to
## photograph the fifth beat would spend them answering a question about the
## fifth beat.
func open_on(beat_id: String) -> void:
	var beat := CaseDocument.beat(document, beat_id)
	if beat.is_empty():
		push_error("case host: this case publishes no beat %s" % beat_id)
		return
	var moved := state.duplicate(true)
	moved["phase"] = CaseRuntime.PHASE_PLAYING
	moved["progress"] = {"beatId": beat_id, "facts": (state["progress"] as Dictionary)["facts"]}
	moved["resume"] = null
	moved["pending"] = null
	moved["lastLine"] = null
	state = moved
	_sync()


func toggle_backlog() -> void:
	_on_backlog(not chrome.backlog_is_open())


# --------------------------------------------------------------------- the case


func _reduce(action: Dictionary) -> void:
	var turn := CaseRuntime.reduce(document, tag, state, action, CaseStore.now())
	state = turn["state"]
	if turn["write"] != null:
		CaseStore.write(tag, turn["write"])
	if bool(turn["clear"]):
		CaseStore.clear(tag)
	if turn["result"] != null:
		CaseStore.write_result(tag, turn["result"])
	_sync()


func _on_continue() -> void:
	_reduce({"kind": "continue"})


func _on_start_over() -> void:
	_reduce({"kind": "start-over"})


func _on_pending_finish() -> void:
	var pending: Variant = state["pending"]
	if pending == null:
		return
	var owed: Dictionary = pending
	_reduce(
		{
			"kind": "finish",
			"beatId": owed["beatId"],
			"outcome": owed["outcome"],
			"flags": owed["flags"],
		}
	)


func _on_backlog(open: bool) -> void:
	chrome.show_backlog(open)
	_gate_leaf()


func _on_moment(
	playback: Dictionary, statement_id: Variant, line: Dictionary, outcome: Variant
) -> void:
	_drawn = (state["progress"] as Dictionary)["beatId"]
	_reduce(
		{
			"kind": "presented",
			"statementId": statement_id,
			# The runtime tells a line from no line by null, and a moment with
			# nothing said hands up an empty record rather than a null one.
			"line": null if line.is_empty() else line,
			"scenario": playback,
			"outcome": outcome,
		}
	)


func _on_room_changed(room: Dictionary, _events: Array) -> void:
	_drawn = (state["progress"] as Dictionary)["beatId"]
	_reduce({"kind": "room-changed", "room": room})


func _on_scene_finished(outcome: String, flags: PackedStringArray) -> void:
	# Inside a case the end card's gesture is "on to the next beat" rather than
	# "play it again", which is the whole of what `onFinish` being connected
	# means to a leaf.
	_reduce(
		{
			"kind": "finish",
			"beatId": (state["progress"] as Dictionary)["beatId"],
			"outcome": outcome,
			"flags": flags,
		}
	)


# ---------------------------------------------------------------------- the view


func _sync() -> void:
	var beat_id := String((state["progress"] as Dictionary)["beatId"])
	if beat_id != _beat_id or (String(state["phase"]) == CaseRuntime.PHASE_PLAYING and leaf == null):
		_beat_id = beat_id
		_drawn = null
		_enter_beat()
	chrome.sync(document, state, CaseDocument.beat(document, _beat_id), _drawn)
	_gate_leaf()


## Build the beat's leaf, replacing whatever was playing.
func _enter_beat() -> void:
	if leaf != null:
		if leaf.has_method("silence"):
			leaf.call("silence")
		leaf.queue_free()
		leaf = null
	if String(state["phase"]) != CaseRuntime.PHASE_PLAYING:
		return
	var beat := CaseDocument.beat(document, _beat_id)
	if beat.is_empty():
		return
	var built: Variant = _build_leaf(beat)
	if KernelRefusal.is_refusal(built):
		# The player is stopped here by design: a beat whose run is missing or
		# refused is a producer's fault, and there is nothing to press.
		_refuse("case host: %s cannot be read — %s" % [_beat_id, (built as KernelRefusal).line()])
		return
	leaf = built
	_stage.add_child(leaf)
	if leaf.has_signal("moment"):
		leaf.connect("moment", _on_moment)
		leaf.connect("finished", _on_scene_finished)
	else:
		leaf.connect("changed", _on_room_changed)
	_fit_leaf()
	# A leaf draws itself the moment it is built — that is what makes "what is
	# drawn" a pure function of the state — so its opening moment happens before
	# there is anybody listening for it. Asking for it again here is what gives
	# the beat a save from its first line rather than from its second: without it
	# a player who stopped in the first second of a beat would come back to the
	# one before it and replay a scene they had finished.
	leaf.call("report")


func _build_leaf(beat: Dictionary) -> Variant:
	var carried: PackedStringArray = (state["progress"] as Dictionary)["facts"]
	var saved: Variant = state["resume"]
	var resume: Variant = null
	if saved is Dictionary and String((saved as Dictionary)["beatId"]) == _beat_id:
		resume = saved
	var run := runs_dir.path_join(String(beat["runTag"]))
	# Each leaf opens its own run, reads its own document and refuses in its own
	# words. A container that parsed a room's manifest and a scene's bundle
	# itself would be a third consumer of two genres it does not own — which is
	# what `tests/contract/test_godot_boundaries.py` refuses, and rightly.
	if String(beat["kind"]) == "room":
		return HostRoomLeaf.open(
			run, carried, null if resume == null else (resume as Dictionary)["room"]
		)
	var scenario: Variant = beat["scenarioId"]
	return HostDialogueLeaf.open(
		run,
		"" if scenario == null else String(scenario),
		carried,
		null if resume == null else (resume as Dictionary)["scenario"]
	)


## The leaf, scaled whole into the stage under the bar. Each genre draws in its
## own design space — a room is taller than it is wide and a scene is wider than
## it is tall — so the case letterboxes each one rather than asking either to
## change shape for the container.
func _fit_leaf() -> void:
	if leaf == null:
		return
	var canvas: Dictionary = leaf.call("canvas")
	var design := Vector2(float(canvas["width"]), float(canvas["height"]))
	var factor := minf(_stage.size.x / design.x, _stage.size.y / design.y)
	leaf.scale = Vector2(factor, factor)
	leaf.position = Vector2(
		(_stage.size.x - design.x * factor) / 2.0, (_stage.size.y - design.y * factor) / 2.0
	)


## While a curtain or the backlog is up, the leaf hears nothing.
##
## The browser had to say this explicitly and so does a host: each leaf listens
## for keys on the whole window, so an overlay that covers only pixels would
## still let the space bar advance a scene nobody can see.
func _gate_leaf() -> void:
	if leaf == null:
		return
	var covered := chrome.covers_leaf()
	leaf.set_process_unhandled_key_input(not covered)
	leaf.mouse_filter = (
		Control.MOUSE_FILTER_IGNORE if covered else Control.MOUSE_FILTER_STOP
	)
	leaf.visible = String(state["phase"]) == CaseRuntime.PHASE_PLAYING


func _scale_to_window() -> void:
	if _root == null:
		return
	var size := Vector2(get_viewport().get_visible_rect().size)
	var factor := minf(size.x / CANVAS.x, size.y / CANVAS.y)
	_root.scale = Vector2(factor, factor)
	_root.position = Vector2(
		(size.x - CANVAS.x * factor) / 2.0, (size.y - CANVAS.y * factor) / 2.0
	)


## Say why, on screen, instead of drawing nothing.
func _refuse(line: String) -> void:
	push_error(line)
	var label := Label.new()
	label.add_theme_font_size_override("font_size", 20)
	label.text = line
	label.position = Vector2(40.0, 40.0)
	label.custom_minimum_size = Vector2(1500.0, 0.0)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var layer := CanvasLayer.new()
	layer.add_child(label)
	add_child(layer)
