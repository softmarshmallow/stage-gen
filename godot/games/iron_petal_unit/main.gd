extends Node2D

## The runner host: one run in, a game out.
##
##   Godot --path godot/games/iron_petal_unit --main-pack ... -- --run <absolute run directory>
##
## It opens a run directory, parses the manifest, seals the roster, and ticks it
## at a fixed step. It owns loading, the loop, input latching, the camera and
## the drawing; it owns no rule the document already states.
##
## The design space is the browser's 1280x720 and the whole canvas is scaled to
## the window, so a published rectangle lands where the manifest says it does.
##
## A refusal is shown before anything is drawn. A run of another kind, or a block
## at a version this build does not read, is a card with a sentence on it rather
## than a black window.

const FIXED_STEP := 1.0 / 60.0
## At most this many steps in one frame: a stall drops time rather than
## spiralling, because a frame that owed two seconds of simulation would take two
## seconds to render and would then owe more.
const MAX_SUBSTEPS := 5
## A frame delta longer than this is not gameplay time. A breakpoint, a window
## drag or a swapped-out process is not something the world should catch up on.
const MAX_FRAME_DELTA := 0.25
## The cut-in paints over the interface, so it sits a layer above it.
const CUT_IN_LAYER := 2
## And a cut between runs goes over the cut-in as well: a restart during a
## moment is still a restart.
const TRANSITION_LAYER := 3

var args: RunnerOptions = null
var package: HostRunDir = null
var config: Dictionary = {}
var world: RunnerWorld = null
var sealed: KernelSealed = null
var latch: FamilyIntent = null
var input: RunnerInput = null
var stage: RunnerStage = null
var hud: RunnerHud = null
var cut_in: HostCutInView = null
var dust: RunnerDustView = null
var audio: RunnerAudioView = null
var transition: HostTransitionView = null

var _banked: float = 0.0
var _now: float = 0.0
var _frame: int = 0
var _refusal: String = ""
var _root: Node2D = null


func _ready() -> void:
	args = RunnerOptions.parse(OS.get_cmdline_user_args())
	var run_dir := args.run
	if run_dir.is_empty():
		_refuse("runner host: pass the run directory after `-- --run <dir>`")
		return
	package = HostRunDir.open(run_dir)
	if package == null:
		_refuse("runner host: %s is not a readable run" % run_dir)
		return
	var parsed: Variant = RunnerContract.parse(package.manifest)
	if KernelRefusal.is_refusal(parsed):
		_refuse((parsed as KernelRefusal).line())
		return
	config = parsed

	var order: Variant = RunnerRoster.seal()
	if KernelRefusal.is_refusal(order):
		_refuse((order as KernelRefusal).line())
		return
	sealed = order

	var shape: Variant = FamilyIntent.of(
		RunnerWorld.neutral_intent(),
		PackedStringArray(["jump", "action"]),
		PackedStringArray(["duck", "thrust"])
	)
	if KernelRefusal.is_refusal(shape):
		_refuse((shape as KernelRefusal).line())
		return
	latch = shape
	input = RunnerInput.of(latch)
	RunnerIntentSystem.latch = latch
	RunnerSessionSystem.pending_seed = -1

	# The design space, scaled whole. Everything below it is authored in the
	# 1280x720 the manifest publishes its rectangles in.
	_root = Node2D.new()
	add_child(_root)
	stage = RunnerStage.new()
	_root.add_child(stage)
	hud = RunnerHud.new()
	add_child(hud)
	cut_in = HostCutInView.of(
		package, RunnerContract.VIEW_WIDTH, RunnerContract.VIEW_HEIGHT, CUT_IN_LAYER
	)
	if cut_in != null:
		add_child(cut_in)
	transition = HostTransitionView.of(TRANSITION_LAYER)
	add_child(transition)

	# Three systems carry a view hook and are wired here, because each of them
	# reads the frame's *events* — a moment asked for, a foot landing, a coin
	# taken. Events live one frame, and the loop below may take several
	# simulation steps per rendered frame, so a view driven from the render
	# instead of from the roster sees only the last step's and silently drops
	# the rest.
	#
	# The stage and the interface are not wired, and that is the other half of
	# the same rule rather than an omission: both are mirrors of whatever the
	# world says now, they read no event, and drawing them once per picture is
	# both correct and four fewer passes.
	#
	# Every one of the five was null before this. Nothing played a sound, threw
	# a puff, or drew a cut-in — the moment still ran, on schedule, over a
	# picture that was not there.
	RunnerFxSystem.view = cut_in
	dust = RunnerDustView.of(package, RunnerStage.DEPTHS["dust"])
	_root.add_child(dust)
	RunnerDustSystem.view = dust
	audio = RunnerAudioView.of(package)
	if audio != null:
		add_child(audio)
	RunnerAudioSystem.view = audio

	# A boss needs a measured atlas before it can have a hit box, so a run whose
	# boss cannot be measured plays without fights rather than with a guessed
	# one — and says so.
	var binding := _bind_encounter()
	world = RunnerWorld.create(config, _boot_seed(), not (config["introMoment"] as Dictionary).is_empty(), binding)
	stage.build(package, config)
	hud.build(config)
	_scale_to_window()
	get_viewport().size_changed.connect(_scale_to_window)
	set_process(true)
	set_process_input(true)


func _process(delta: float) -> void:
	if world == null:
		return
	_banked += minf(delta, MAX_FRAME_DELTA)
	var steps := 0
	while _banked >= FIXED_STEP and steps < MAX_SUBSTEPS:
		_banked -= FIXED_STEP
		steps += 1
		_frame += 1
		_now += FIXED_STEP
		world.events.begin_frame()
		sealed.tick(world, {"dt": FIXED_STEP, "now": _now, "frame": _frame})
		if not world.events.of_type("run-restarted").is_empty():
			sealed.reset(world, FamilySession.SCOPE_RUN)
			world.events.discard_frames()
			# The cut is made under the cover rather than in the open. The
			# choreography is named here because no run publishes one yet; when
			# a `transitions` block exists this is where its binding is read.
			transition.begin(FamilyTransition.FADE_BLACK)
	if steps >= MAX_SUBSTEPS:
		# The bank is dropped rather than carried: see MAX_SUBSTEPS.
		_banked = fmod(_banked, FIXED_STEP)
	stage.sync(world, delta)
	hud.sync(world)
	transition.advance(delta)


func _input(event: InputEvent) -> void:
	if input == null:
		return
	if input.handle(event, float(get_viewport().get_visible_rect().size.y)):
		get_viewport().set_input_as_handled()


func _notification(what: int) -> void:
	# A key held through an alt-tab is not still held when the window returns.
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and input != null:
		input.release_all()


## The whole picture scales together, never one part of it.
func _scale_to_window() -> void:
	var size := get_viewport().get_visible_rect().size
	var factor := minf(size.x / RunnerContract.VIEW_WIDTH, size.y / RunnerContract.VIEW_HEIGHT)
	if _root != null:
		_root.scale = Vector2(factor, factor)
		_root.position = Vector2(
			(size.x - RunnerContract.VIEW_WIDTH * factor) / 2.0,
			(size.y - RunnerContract.VIEW_HEIGHT * factor) / 2.0
		)
	if hud != null:
		hud.transform = Transform2D(0.0, Vector2(factor, factor), 0.0, _root.position)
	if cut_in != null:
		cut_in.transform = Transform2D(0.0, Vector2(factor, factor), 0.0, _root.position)
	# The cover takes no scale: it hides the whole window, letterbox included.
	if transition != null:
		transition.fit(size)


## The two numbers only a loaded boss atlas can supply.
func _bind_encounter() -> Dictionary:
	if (config["encounter"] as Dictionary).is_empty():
		return {}
	var authored: Dictionary = config["encounter"]
	for entry: Variant in (package.manifest.get("bosses", []) as Array):
		var boss: Dictionary = entry
		if String(boss["boss_id"]) != String(authored["bossId"]):
			continue
		var hover := {}
		for motion: Variant in (boss.get("motions", []) as Array):
			if String((motion as Dictionary)["state"]) == "hover":
				hover = motion
		if hover.is_empty():
			break
		var texture := package.texture(String(hover["atlas"]))
		if texture == null:
			break
		var columns := maxi(1, int(hover["columns"]))
		var cell_aspect := (float(texture.get_width()) / float(columns)) / float(texture.get_height())
		var calibration: Dictionary = boss.get("calibration", {})
		var height_rows := float(calibration.get("height_units", 1.0)) * float(config["playerHeightTiles"])
		return RunnerRoster.bind_encounter(config, height_rows, cell_aspect)
	push_warning(
		"runner host: this run declares an encounter but its boss cannot be measured; "
		+ "playing without fights rather than guessing a hit box"
	)
	return {}


## A seed from the command line when one is given, and otherwise from the clock.
##
## This is the one unseeded draw a host is allowed, and it is allowed precisely
## because it is the *source* of the seed rather than anything downstream of it:
## every draw after this one comes from the run's own generator.
func _boot_seed() -> int:
	if args.seed_value != 0:
		return args.seed_value & 0xFFFFFFFF
	return int(Time.get_unix_time_from_system() * 1000.0) & 0xFFFFFFFF


func _refuse(line: String) -> void:
	_refusal = line
	push_error(_refusal)
	var layer := CanvasLayer.new()
	add_child(layer)
	var label := Label.new()
	label.text = _refusal
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.position = Vector2(48.0, 48.0)
	label.size = Vector2(RunnerContract.VIEW_WIDTH - 96.0, RunnerContract.VIEW_HEIGHT - 96.0)
	label.add_theme_font_size_override("font_size", 18)
	layer.add_child(label)
	set_process(false)
