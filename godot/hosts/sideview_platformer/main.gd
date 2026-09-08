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
var bars: PlatformerMobBars = null
var numbers: PlatformerCombatText = null
var hud: PlatformerHud = null

var _banked: float = 0.0
var _now: float = 0.0
var _frame: int = 0
var _root: Node2D = null
## A capture's held keys, so one picture can be taken of a body in motion. Empty
## for a person, who is holding the keys themselves.
var _forced_intent: PackedStringArray = PackedStringArray()


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

	_root = Node2D.new()
	add_child(_root)
	stage = PlatformerStage.of(package, atlas as Dictionary)
	_root.add_child(stage)
	actors = PlatformerActors.of(package, package.manifest)
	_root.add_child(actors)
	bars = PlatformerMobBars.of()
	_root.add_child(bars)
	numbers = PlatformerCombatText.of()
	_root.add_child(numbers)
	hud = PlatformerHud.of(package, package.manifest)
	add_child(hud)

	stage.open_on(world)
	_scale_to_window()
	get_viewport().size_changed.connect(_scale_to_window)
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
	actors.sync(world, scroll, delta)
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
	world.blows = []
	numbers.sync(scroll, _now * 1000.0)
	hud.sync(world)


## One frame of the world, in the order `assemblePlatformerSystems` declares it.
##
## Written out rather than sealed, and the harness at `tools/platformer_parity.gd`
## keeps the same order for the same reason: the sealer derives an order from
## declarations, and until every system carries one, an order written down is an
## order that can be compared with the browser's.
func _tick() -> void:
	var step := {"dt": FIXED_STEP * 1000.0, "now": _now * 1000.0, "frame": _frame}
	world.events.begin_frame()
	world.blows = []
	world.intent = input.sample()
	for key in _forced_intent:
		world.intent[key] = true
	PlatformerSoundtrackSystem.update(world, step)
	PlatformerDialogueSystem.update(world, step)
	PlatformerClockSystem.update(world, step)
	if world.hold:
		PlatformerMapEntrySystem.apply(world, step)
		return
	PlatformerPlayer.update(
		world.player,
		_terrain(),
		world.simulation_dt,
		_now * 1000.0,
		world.intent,
		PlatformerWeapon.profile(world.weapon_class)
	)
	PlatformerMobsSystem.strike(world, step)
	PlatformerSessionSystem.update(world, step)
	PlatformerProjectilesSystem.throw_one(world, step)
	PlatformerMobsSystem.populate(world, step)
	PlatformerMobsSystem.step(world, step)
	PlatformerProjectilesSystem.update(world, step)
	PlatformerItemsSystem.update(world, step)
	PlatformerCameraSystem.carry_shake(world, step)
	PlatformerDialogueSystem.prompt(world, step)
	PlatformerMapEntrySystem.ask(world)
	PlatformerMapEntrySystem.apply(world, step)
	# Last, and deliberately: the browser's camera is the engine's own pre-render
	# pass, which runs after every system has written what it was going to.
	PlatformerCameraSystem.update(world, step)


## The ground the body walks on, for the map it is standing in.
func _terrain() -> Dictionary:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	return {
		"heights": map["heights"],
		"tilePx": PlatformerMaps.TILE_PX,
		"baselineY": PlatformerMaps.BASELINE_Y,
		"worldWidthPx": map["worldWidthPx"],
		"platforms": world.platforms,
		"climbables": world.climbables,
		"maximumAirJumps": PlatformerVertical.AIR_JUMPS_MAX,
		"combatEnabled": world.package["combatEnabled"],
	}


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
