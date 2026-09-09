extends Node2D

## The platformer host: one run in, a game out.
##
##   Godot --path godot -- --run <absolute run directory>
##
## It opens a run directory, parses the manifest, builds the world and steps it
## at the genre's own fixed rate of thirty a second. It owns loading, the loop,
## the input, the camera and the drawing; it owns no rule the document already
## states, and every rule it does not own is under `genres/sideview_platformer/`
## where a headless harness can compare it against the browser frame for frame.
##
## The design space is 1280x720 and the whole canvas is scaled to the window, so
## a published rectangle lands where the producer drew it whatever the display
## does.
##
## A refusal is shown before anything is drawn. A run of another kind, or a block
## at a version this build does not read, is a card with a sentence on it rather
## than a black window.

## The platformer's step is not the runner's: thirty a second, and a host that
## assumed sixty would play the same rules over twice the world.
const FIXED_STEP := 1.0 / 30.0
## At most this many steps in one frame: a stall drops time rather than
## spiralling, because a frame that owed two seconds of simulation would take
## two seconds to render and would then owe more.
const MAX_SUBSTEPS := 5
## A frame delta longer than this is not gameplay time. A breakpoint, a window
## drag or a swapped-out process is not something the world should catch up on.
const MAX_FRAME_DELTA := 0.25

const LOOKUP_PATH := "res://families/sideview/terrain/lookup.json"

var package: HostRunDir = null
var world: PlatformerWorld = null
var input: PlatformerInput = null
var stage: PlatformerStage = null
var actors: PlatformerActors = null
var scenery: PlatformerScenery = null
var bars: PlatformerMobBars = null
var numbers: PlatformerCombatText = null
var impacts: PlatformerImpacts = null
var hud: PlatformerHud = null
var defeat_card: PlatformerDefeatCard = null
var stat_log: PlatformerStatLog = null

var _banked: float = 0.0
var _now: float = 0.0
var _frame: int = 0
var _root: Node2D = null
## A capture's held keys, so one picture can be taken of a body in motion. Empty
## for a person, who is holding the keys themselves.
var _forced_intent: PackedStringArray = PackedStringArray()

## Auto-play: the hunter, whether it is switched on, the graph it walks, and the
## map that graph was derived for. The graph is a property of the map, so it is
## rebuilt when a gate moves the body and never per frame.
var _bot: PlatformerBot = null
var _bot_on: bool = false
var _bot_graph: Dictionary = {}
var _bot_map_id: String = ""
## When a person last touched the keys, so a takeover lasts as long as it takes
## to think. Negative is "not this session".
var _human_input_at_ms: float = PlatformerBot.NEVER
var _bot_badge: Label = null

## The faces the package published, or null for the engine's own.
var _run_theme: Theme = null
var _numeral_face: FontFile = null


func _ready() -> void:
	var args := HostArgs.parse(OS.get_cmdline_user_args())
	if args.run.is_empty():
		_refuse("platformer host: pass the run directory after `-- --run <dir>`")
		return
	package = HostRunDir.open(args.run)
	if package == null:
		_refuse("platformer host: %s is not a readable run" % args.run)
		return
	var parsed: Variant = PlatformerMaps.parse(package.manifest)
	if KernelRefusal.is_refusal(parsed):
		_refuse((parsed as KernelRefusal).line())
		return
	var atlas: Variant = FamilyTerrainAtlas.lookup(_read_json(LOOKUP_PATH))
	if KernelRefusal.is_refusal(atlas):
		_refuse((atlas as KernelRefusal).line())
		return

	world = PlatformerWorld.create(parsed as Dictionary, package.manifest)
	if world.player.is_empty():
		_refuse("platformer host: this package opens on no spawn")
		return
	input = PlatformerInput.new()
	# The face the package published, applied once to the whole host rather than
	# per label. A package that declares none draws in the engine's default and
	# says which role it was missing — see decision 0063.
	var faces := HostTypeface.of(
		package, package.manifest.get("ui", {}), "platformer host"
	)
	# A theme reaches Controls and a Node2D is not one, so it is applied to the
	# screen furniture and the numbers take their face directly. Two places rather
	# than thirty overrides.
	_run_theme = HostTypeface.theme_of(faces["text"])
	_numeral_face = faces["numeral"]
	_bot = PlatformerBot.of(PlatformerBotHunter.profile())

	_root = Node2D.new()
	add_child(_root)
	stage = PlatformerStage.of(package, atlas as Dictionary)
	_root.add_child(stage)
	actors = PlatformerActors.of(package, package.manifest)
	_root.add_child(actors)
	scenery = PlatformerScenery.of(package, package.manifest)
	_root.add_child(scenery)
	bars = PlatformerMobBars.of()
	_root.add_child(bars)
	impacts = PlatformerImpacts.of()
	_root.add_child(impacts)
	numbers = PlatformerCombatText.of(_numeral_face)
	_root.add_child(numbers)
	hud = PlatformerHud.of(package, package.manifest)
	hud.wear(_run_theme)
	add_child(hud)
	stat_log = PlatformerStatLog.of()
	stat_log.theme = _run_theme
	add_child(stat_log)
	defeat_card = PlatformerDefeatCard.of(package, package.manifest)
	if defeat_card != null:
		defeat_card.theme = _run_theme
		add_child(defeat_card)

	stage.open_on(world)
	_scale_to_window()
	get_viewport().size_changed.connect(_scale_to_window)
	_bot_badge = Label.new()
	_bot_badge.add_theme_font_size_override("font_size", 16)
	# Said on screen rather than only in a log. A switch that looks like it did
	# nothing is indistinguishable from a broken one, and the key is the only way
	# to find out the bot is driving.
	_bot_badge.text = "AUTO-PLAY  ·  P to take over"
	_bot_badge.position = Vector2(16.0, PlatformerStage.VIEW_HEIGHT - 32.0)
	_bot_badge.theme = _run_theme
	_bot_badge.visible = false
	var badge_layer := CanvasLayer.new()
	badge_layer.add_child(_bot_badge)
	add_child(badge_layer)

	set_process(true)


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
		_tick()
	if steps >= MAX_SUBSTEPS:
		# The bank is dropped rather than carried: see MAX_SUBSTEPS.
		_banked = fmod(_banked, FIXED_STEP)
	stage.open_on(world)
	var scroll := Vector2(float(world.camera["scrollX"]), float(world.camera["scrollY"]))
	stage.sync(scroll)
	actors.sync(world, scroll, delta, _now * 1000.0)
	scenery.sync(world, scroll, delta)
	bars.sync(world, scroll)
	# Raised where the blow landed, a little above the drawn top of the body it
	# came off. The body's own height is the view's to know.
	for entry: Variant in world.blows:
		var blow: Dictionary = entry
		numbers.show_damage(
			int(blow["amount"]),
			bool(blow["critical"]),
			bool(blow["incoming"]),
			Vector2(
				float(blow["x"]),
				float(blow["y"]) - actors.drawn_height(bool(blow["incoming"]))
					- PlatformerCombatText.RISE_ABOVE
			),
			_now * 1000.0
		)
	# The sparks take the same list, and take it before it is cleared: a blow is
	# one event, and the number and the spark it throws are two readings of it.
	impacts.take(world.blows, _now * 1000.0)
	impacts.set_swing(world)
	world.blows = []
	impacts.sync(scroll, _now * 1000.0)
	numbers.sync(scroll, _now * 1000.0)
	# The lines the player gained, taken before the world clears them at the top
	# of the next frame.
	stat_log.say(world.notices, _now * 1000.0)
	stat_log.sync(_now * 1000.0)
	hud.sync(world, _now * 1000.0)
	if defeat_card != null:
		defeat_card.sync(world, _now * 1000.0)


## One frame of the world, in the order the genre declares it.
##
## The order itself moved to `PlatformerFrame`, and the move is the point: the
## parity harness ticks the same function, so a run that agrees with the browser
## for six hundred frames is a claim about this game rather than about a test.
func _tick() -> void:
	var now_ms := _now * 1000.0
	if bool(input.host_edges()["toggleBot"]):
		_bot_on = not _bot_on
		if not _bot_on:
			_bot.suspend()
		_bot_badge.visible = _bot_on
	world.intent = input.sample()
	for key in _forced_intent:
		world.intent[key] = true
	# Whatever is in the record at this point is a person's: the keys they are
	# holding, or the keys a capture is holding on their behalf. Either way it
	# outranks the bot, which is the whole rule — a touch of anything is a takeover
	# that lasts as long as it takes to think, and walking away hands control back
	# on its own.
	var control := PlatformerBot.resolve_control(
		world.intent, _bot_on, now_ms, _human_input_at_ms
	)
	_human_input_at_ms = float(control["humanInputAtMs"])
	if String(control["source"]) == PlatformerBot.SOURCE_BOT:
		world.intent = _bot_intent(now_ms)
	elif _bot_on:
		# It did not drive this frame, so it must not remember driving one.
		_bot.suspend()
	PlatformerFrame.step(
		world, {"dt": FIXED_STEP * 1000.0, "now": now_ms, "frame": _frame}
	)


## One frame of the hunter's thought, in the record the body reads.
func _bot_intent(now_ms: float) -> Dictionary:
	var terrain := PlatformerFrame.terrain(world)
	if world.map_id != _bot_map_id:
		_bot_map_id = world.map_id
		_bot_graph = PlatformerBotAdapter.nav_graph(
			terrain, PlatformerBotNavigation.capabilities()
		)
		_bot.reset()
	var view := PlatformerBotAdapter.world_view(
		world, terrain, _bot_graph, now_ms, FIXED_STEP * 1000.0
	)
	return _bot.decide(view)["intent"]


## The design space, scaled whole and centred, so the picture letterboxes rather
## than stretching.
func _scale_to_window() -> void:
	var size := Vector2(get_viewport().get_visible_rect().size)
	var factor := minf(size.x / PlatformerStage.VIEW_WIDTH, size.y / PlatformerStage.VIEW_HEIGHT)
	if _root != null:
		_root.scale = Vector2(factor, factor)
		_root.position = Vector2(
			(size.x - PlatformerStage.VIEW_WIDTH * factor) / 2.0,
			(size.y - PlatformerStage.VIEW_HEIGHT * factor) / 2.0
		)


func _read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed


## Say why, on screen, instead of drawing nothing.
func _refuse(line: String) -> void:
	push_error(line)
	var label := Label.new()
	label.add_theme_font_size_override("font_size", 20)
	label.text = line
	label.position = Vector2(40.0, 40.0)
	label.custom_minimum_size = Vector2(PlatformerStage.VIEW_WIDTH - 80.0, 0.0)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var layer := CanvasLayer.new()
	layer.add_child(label)
	add_child(layer)
