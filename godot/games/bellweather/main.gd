extends Node2D

## The platformer host: one run in, a game out.
##
##   Godot --path godot/games/bellweather -- --run <absolute run directory>
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

const LOOKUP_PATH := "res://gameplay/support/sideview/terrain/lookup.json"

var package: HostRunDir = null
var world: PlatformerWorld = null
var input: PlatformerInput = null
var stage: PlatformerStage = null
var actors: PlatformerActors = null
var scenery: PlatformerScenery = null
var bars: PlatformerBodyBars = null
var numbers: PlatformerCombatText = null
var impacts: PlatformerImpacts = null
var hud: PlatformerHud = null
var defeat_card: PlatformerDefeatCard = null
var stat_log: PlatformerStatLog = null
var loading: PlatformerLoadingCard = null
var music: PlatformerMusic = null
## The map the stage has actually been built for, which is not the map the
## world is on during the frame the card goes up.
var _built_map_id: String = ""
## Wall time since the host opened, in milliseconds.
##
## The loading card's own clock, and it has to be a different one from the world's:
## the card stops the simulation while it is up, so the simulation's clock is
## frozen for exactly as long as the card needs to time itself against. Fed from
## the frame delta rather than read off the system, so it stays a number this file
## owns.
var _wall_ms: float = 0.0

var _banked: float = 0.0
var _now: float = 0.0
var _frame: int = 0
var _root: Node2D = null
## Everything drawn on the screen rather than in the world, under the same
## letterbox as the world.
##
## The furniture used to hang off the host directly, so it was laid out in the
## 1280x720 the manifest publishes rectangles in and *drawn* in whatever pixels the
## window happened to have. At the design size nothing looked wrong; at any other
## the banner sat left of centre, the conversation panel ran off its own frame and
## the veil behind the death card stopped short of the edge. Scaled with the world
## rather than beside it, one rectangle means one thing everywhere.
var _screen: Node2D = null
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
	var args := BellweatherOptions.parse(OS.get_cmdline_user_args())
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
	bars = PlatformerBodyBars.of()
	_root.add_child(bars)
	impacts = PlatformerImpacts.of()
	_root.add_child(impacts)
	numbers = PlatformerCombatText.of(_numeral_face)
	_root.add_child(numbers)
	_screen = Node2D.new()
	# Above every layer the world draws on, so a panel is never behind the fight it
	# is reporting on.
	_screen.z_index = 1000
	add_child(_screen)
	hud = PlatformerHud.of(package, package.manifest)
	hud.wear(_run_theme)
	_screen.add_child(hud)
	stat_log = PlatformerStatLog.of()
	stat_log.theme = _run_theme
	_screen.add_child(stat_log)
	loading = PlatformerLoadingCard.of()
	loading.theme = _run_theme
	_screen.add_child(loading)
	music = PlatformerMusic.of(package, package.manifest)
	if music != null:
		add_child(music)
	defeat_card = PlatformerDefeatCard.of(package, package.manifest)
	if defeat_card != null:
		defeat_card.theme = _run_theme
		_screen.add_child(defeat_card)

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
	_screen.add_child(_bot_badge)

	set_process(true)


func _process(delta: float) -> void:
	if world == null:
		return
	_wall_ms += delta * 1000.0
	var now_ms := _now * 1000.0
	# A map the stage has not been built for yet. The card goes up first and this
	# frame ends there: putting the new map up takes tens of milliseconds with the
	# textures warm and longer without, and doing it on the same frame the card was
	# created would draw the card for the first time only after the stall it exists
	# to explain.
	if world.map_id != _built_map_id:
		if not loading.settled():
			loading.raise_for(_place_name(), _wall_ms)
			loading.sync(_wall_ms)
			return
		stage.open_on(world)
		# Behind the card rather than during play. The stage itself is quick; what
		# is not is every strip and prop the new map will ask for, which used to be
		# decoded one at a time as each thing first appeared — so a map opened at
		# full speed and then stuttered its way through its own population, right
		# where the fight was starting.
		var warm_scroll := Vector2(
			float(world.camera["scrollX"]), float(world.camera["scrollY"])
		)
		actors.warm(world)
		actors.sync(world, warm_scroll, 0.0, _now * 1000.0)
		scenery.sync(world, warm_scroll, 0.0)
		_built_map_id = world.map_id
		loading.release(_wall_ms)
		# The stall is not gameplay time. Dropping the bank rather than banking it
		# is what stops the world spending the next frame in a burst of catch-up
		# steps the moment the card comes down.
		_banked = 0.0
	loading.sync(_wall_ms)
	# Before the card's early return, because music is furniture: it keeps running
	# while the simulation is held, and a silence behind a loading card is exactly
	# where one would be most obvious.
	if music != null:
		music.sync(world, _wall_ms)
	# Nothing steps behind the card. A player who cannot see the game cannot play
	# it, and a creature that walked up and hit them during a load landed a blow
	# they had no way to answer.
	if loading.showing():
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
	now_ms = _now * 1000.0
	stage.open_on(world)
	var scroll := Vector2(float(world.camera["scrollX"]), float(world.camera["scrollY"]))
	stage.sync(world, scroll)
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
	# Before the step, because the step is what the intent was sampled for and the
	# bag is the host's rather than the body's.
	if bool(world.intent.get("toggleInventory", false)):
		hud.toggle_inventory()
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
	var origin := Vector2(
		(size.x - PlatformerStage.VIEW_WIDTH * factor) / 2.0,
		(size.y - PlatformerStage.VIEW_HEIGHT * factor) / 2.0
	)
	# The world and the furniture take the same letterbox. They did not, and that
	# is why every rectangle the manifest publishes landed somewhere else on any
	# window that was not exactly the design size.
	for layer: Node2D in [_root, _screen]:
		if layer == null:
			continue
		layer.scale = Vector2(factor, factor)
		layer.position = origin


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


## The name of the map the world is on, as a player should read it.
func _place_name() -> String:
	var map: Dictionary = (world.package["maps"] as Dictionary).get(world.map_id, {})
	var named := str(map.get("displayName", "")).strip_edges()
	return world.map_id if named.is_empty() else named
