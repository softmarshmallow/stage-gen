extends Node3D

## The frame owner: the host's one scene, and the only place that knows the
## order things happen in.
##
## It parses the command line, opens the run package, builds the world, builds
## every view module by script path, and runs the viewer's frame
## (`tick`, index.html:5461-5771) in that frame's order: yaw, simulation,
## shared uniforms, audio, weather, events, entities, fire, camera, HUD.
##
## It also owns what the viewer never had: the pointer (a click on a thing
## acts on it, a click on the ground walks there, a hover names the thing),
## the reset the death screen asks for (R, or its button), the borderless
## fullscreen toggle (F11), and the HUD scale that keeps the panels readable
## at any window size.
##
## Nothing here draws. Every module is a scene-less node created with `.new()`
## that implements the module contract:
##
##   setup(pkg, world, fu)                  build meshes and materials
##   update(world, delta, cam)              every frame
##   handle_event(event)                    optional, per drained world event
##   set_look(look)                         optional, "" or a season's look
##   set_mode(mode)                         optional, play | gallery | verdict
##
## A module that is not in the project yet is skipped with a warning, so the
## host runs while it is being built.

const FIXED_STEP := 1.0 / 60.0
const MAX_FRAME_DELTA := 0.25

## The view modules, in the order they are created. `update` runs in the
## viewer's own per-frame order (`UPDATE_ORDER`), which is not this one.
const MODULE_FILES := [
	"res://view/ground.gd",
	"res://view/water.gd",
	"res://view/decals.gd",
	"res://view/shadows.gd",
	"res://view/cards.gd",
	"res://view/pieces.gd",
	"res://view/plants.gd",
	"res://view/leaves.gd",
	"res://view/fire.gd",
	"res://view/puffs.gd",
	"res://view/splashes.gd",
	"res://view/strikes.gd",
	"res://view/weather_view.gd",
	"res://view/gallery.gd",
	"res://hud/hud.gd",
	"res://hud/craft_panel.gd",
	"res://hud/death_screen.gd",
	"res://hud/world_map.gd",
	"res://audio/music.gd",
	"res://audio/sfx.gd",
]

## Section 10 of the rendering map: audio, then the weather layers, then the
## ground and its decals, then the entities, then the fire, then the overlays.
## The camera follow and the vignette are the frame owner's own and run after.
const UPDATE_ORDER := [
	"music", "sfx",
	"weather_view", "water", "splashes", "decals", "ground", "strikes",
	"cards", "pieces", "plants", "leaves", "puffs", "shadows",
	"fire", "gallery", "hud", "craft_panel", "death_screen", "world_map",
]

## The HUD is laid out in 1600x900 units and scaled to the window: this height
## is scale 1, and `--ui-scale` multiplies what the window's height gives.
const UI_REFERENCE_HEIGHT := 900.0
## The pointer walks the world only in play, never in the gallery or the
## verdict framing.
const POINTER_MODES := ["play"]

## Trauma per event, from the viewer's drain (index.html:5576-5595). A landing
## trunk adds 0.75 and is not an event: the module animating it calls
## `add_trauma` instead.
const EVENT_TRAUMA := {"hit": 0.18, "hurt": 0.3, "strike": 0.35, "thunder": 0.12}

var args: RunArgs = null
var package: RunPackage = null
var world: World = null
var frame_uniforms: FrameUniforms = null
var rig: CameraRig = null
var vignette: CanvasLayer = null
var environment_node: WorldEnvironment = null
## Module id ("ground", "hud", …) -> node.
var modules: Dictionary = {}

var mode: String = "play"
var paused: bool = false
## The capture harness drives the frame itself.
var autostep: bool = true
## Set before the node enters the tree to override the command line.
var arg_overrides: Dictionary = {}

## Sum microseconds per module in `module_micros`. Off by default: it is a
## `Time.get_ticks_usec()` pair around every module's `update`, which is cheap
## but not free, and only the smoke run asks for it.
## Turning it on also profiles the simulation's fifteen systems (`Sim.profile`)
## and the frame owner's own three stretches, which arrive in `module_micros`
## under the reserved ids `~sim`, `~uniforms` and `~camera`.
var profile: bool = false:
	set(value):
		profile = value
		Sim.profile = value
## module id -> microseconds spent in `update` since `reset_profile`.
var module_micros: Dictionary = {}

var _look: String = ""
var _weather_script: GDScript = null
var _input_script: GDScript = null
var _input_sampler = null
var _booted: bool = false
## The pointer: where it was last seen, whether that is newer than the last
## pick, and what the last pick found (`{entity, target, point}` or empty).
var _mouse: Vector2 = Vector2(-1.0, -1.0)
var _hover_stale: bool = false
var _hover: Dictionary = {}
var _ui_scale: float = 0.0
var _ui_resolution: Vector2 = Vector2.ZERO
## How many worlds this scene has played: 1 after boot, +1 per reset.
var generation: int = 0

func _ready() -> void:
	args = RunArgs.from_command_line()
	for key: String in arg_overrides:
		args.set(key, arg_overrides[key])
	if args.run == "":
		push_error("main: no --run <run directory> was given; nothing to load")
		return
	package = RunPackage.open(args.run)
	if package == null:
		push_error("main: could not open the run at %s" % args.run)
		return
	_weather_script = _load_script("res://sim/systems/weather.gd")
	_input_script = _load_script("res://runtime/input_map.gd")
	if _input_script != null and _input_script.has_method("new"):
		_input_sampler = _input_script.new()
	if args.fullscreen:
		set_fullscreen(true)
	var layout: Dictionary = package.layout if not package.layout.is_empty() else package.manifest.get("layout", {})
	var seed_value: int = args.seed_value if args.seed_value != 0 else int(layout.get("seed", 1))
	_boot(World.create(package, seed_value, args.world_options()))

## Stand a world up: the environment, the rig, every module, the vignette.
## Boot and reset both come through here.
func _boot(next_world: World) -> void:
	world = next_world
	generation += 1
	frame_uniforms = FrameUniforms.from_manifest(package.manifest, resolution())
	frame_uniforms.set_static("u_night_floor", args.night_floor)
	_look = ""
	_hover = {}
	_hover_stale = true
	_ui_scale = 0.0
	if _input_sampler != null and _input_sampler.has_method("bind"):
		_input_sampler.bind(world)

	environment_node = load("res://view/environment.gd").new()
	environment_node.name = "Environment"
	add_child(environment_node)
	environment_node.setup(package, world, frame_uniforms)

	rig = CameraRig.new()
	rig.name = "CameraRig"
	add_child(rig)
	rig.setup(package, world, frame_uniforms)

	for path: String in MODULE_FILES:
		var id := path.get_file().get_basename()
		if not ResourceLoader.exists(path):
			push_warning("main: view module %s is not in the project yet; skipping it" % path)
			continue
		var script: GDScript = load(path)
		if script == null:
			push_warning("main: view module %s did not load; skipping it" % path)
			continue
		var node = script.new()
		node.name = id
		add_child(node)
		if node.has_method("setup"):
			node.setup(package, world, frame_uniforms)
		# A layer that wants the run started over (the death screen's button)
		# says so through this signal; the frame owner is the only one who can.
		if node.has_signal("restart_requested"):
			node.connect("restart_requested", reset)
		# A panel button for a key the frame owner binds (the HUD's Map, and
		# a reset) arrives here by name.
		if node.has_signal("action"):
			node.connect("action", _on_module_action)
		modules[id] = node

	vignette = load("res://view/vignette.gd").new()
	vignette.name = "Vignette"
	add_child(vignette)
	vignette.setup(package, world, frame_uniforms)

	_booted = true
	_sync_ui_scale()
	_apply_look(true)
	if args.mode != "play":
		set_mode(args.mode)
	else:
		_broadcast_mode("play")

## Take the world down: every module, the rig, the environment, the vignette,
## so a reset rebuilds them on the new world rather than teaching eighteen
## modules how to forget one. Textures and clips stay cached on the package.
func _teardown() -> void:
	_booted = false
	# Deferred frees: a reset can arrive from a button's own `pressed` signal,
	# and that button must not vanish under the call that is still on it.
	for id: String in modules:
		var node = modules[id]
		if node != null:
			remove_child(node)
			node.queue_free()
	modules.clear()
	for node in [vignette, rig, environment_node]:
		if node != null:
			remove_child(node)
			node.queue_free()
	vignette = null
	rig = null
	environment_node = null

## The viewer's R: a fresh world on the next seed, keeping the ground masks,
## the weather mode and the forced season (`World.reset`). The camera, the
## music and every card start over with it.
func reset() -> void:
	if world == null:
		return
	var next_world := World.reset(world)
	_teardown()
	_boot(next_world)
	if mode != "play":
		set_mode(mode)
	world.say("Day 1. Again.")

func _process(delta: float) -> void:
	if _booted and autostep:
		frame(minf(delta, MAX_FRAME_DELTA), true)

## One whole frame, the viewer's `tick`.
func frame(delta: float, _draw: bool = true) -> void:
	if not _booted:
		return
	# 0. The HUD scale follows the window; the pointer's hover is re-read
	#    once per frame it moved (never per motion event).
	_sync_ui_scale()
	if _hover_stale:
		_hover_stale = false
		_refresh_hover()

	# 1. Ease toward the detent Q/E selected, and publish the yaw: the one
	#    camera fact the simulation may know.
	var yaw_changed := rig.ease_yaw(delta)
	world.camera_yaw = rig.yaw

	# 2. The gallery pans instead of simulating; otherwise the fixed step runs.
	if mode == "gallery":
		var pan := _movement_axis()
		if pan != Vector2.ZERO:
			rig.pan(pan.x, pan.y, delta)
	elif not paused:
		_sample_held_input()
		if not profile:
			Sim.tick(world, delta)
		else:
			var sim_started := Time.get_ticks_usec()
			Sim.tick(world, delta)
			module_micros["~sim"] = int(module_micros.get("~sim", 0)) + (Time.get_ticks_usec() - sim_started)

	var owner_started := Time.get_ticks_usec() if profile else 0
	var cam := rig.cam_state(yaw_changed, resolution())

	# 3. The shared uniforms, verbatim (index.html:5520-5535).
	var weather: Dictionary = world.weather
	var flash := _flash_envelope(world.time - float(weather.get("flash_at", -99.0)))
	frame_uniforms.write_frame({
		"u_time": world.time,
		"u_night": world.night,
		"u_light_intensity": 1.0 if bool(world.light.get("on", false)) else 0.0,
		"u_light_pos": Vector3(float(world.light.get("x", 0.0)), 0.0, float(world.light.get("z", 0.0))),
		"u_light_radius": float(world.light.get("radius", 6.0)),
		"u_pool_pos": Vector3(world.player.x, 0.0, world.player.z),
		"u_rain": float(weather.get("rain", 0.0)),
		"u_snow": float(weather.get("snow", 0.0)),
		"u_flash": flash * 0.85,
	})
	_apply_look(false)
	if profile:
		module_micros["~uniforms"] = int(module_micros.get("~uniforms", 0)) + (Time.get_ticks_usec() - owner_started)

	# 4-8. The event drain, then every module in the viewer's order. The drain
	#      runs first here rather than between the weather layers and the
	#      entity sync: nothing a module does in `update` is read by the drain,
	#      and a spawn lands in the same frame either way.
	_drain_events()
	for id: String in UPDATE_ORDER:
		var node = modules.get(id)
		if node != null and node.has_method("update"):
			if not profile:
				node.update(world, delta, cam)
			else:
				var started := Time.get_ticks_usec()
				node.update(world, delta, cam)
				module_micros[id] = int(module_micros.get(id, 0)) + (Time.get_ticks_usec() - started)

	# 9. The camera follows and shakes after everything has been placed.
	var tail_started := Time.get_ticks_usec() if profile else 0
	rig.follow_and_shake(world, delta)
	# 10. And the night vignette, which is a 2D layer over the finished frame.
	vignette.update(world, delta, cam)
	rig.clear_changed()
	if profile:
		module_micros["~camera"] = int(module_micros.get("~camera", 0)) + (Time.get_ticks_usec() - tail_started)

func _drain_events() -> void:
	if world.events.is_empty():
		return
	var events: Array = world.events.duplicate()
	world.events.clear()
	for event: Dictionary in events:
		var type := String(event.get("type", ""))
		if EVENT_TRAUMA.has(type):
			rig.add_trauma(float(EVENT_TRAUMA[type]))
		for id: String in UPDATE_ORDER:
			var node = modules.get(id)
			if node != null and node.has_method("handle_event"):
				node.handle_event(event)

## `world.look` is an instant swap: the season's prop and plant sheets.
func _apply_look(force: bool) -> void:
	if not force and world.look == _look:
		return
	_look = world.look
	for id: String in UPDATE_ORDER:
		var node = modules.get(id)
		if node != null and node.has_method("set_look"):
			node.set_look(_look)

# ---------------------------------------------------------------- harness API

## The viewer's `window.__survival.advance(seconds)`: step the whole loop
## without waiting for the render loop, drawing only the last step.
func advance(seconds: float) -> void:
	var steps := maxi(1, int(round(seconds / FIXED_STEP)))
	for i in range(steps):
		frame(FIXED_STEP, i == steps - 1)

func get_world() -> World:
	return world

func set_mode(next: String) -> void:
	if not RunArgs.MODES.has(next):
		push_warning("main: unknown mode %s" % next)
		return
	mode = next
	rig.set_mode(next, world)
	_broadcast_mode(next)

func _broadcast_mode(next: String) -> void:
	for id: String in UPDATE_ORDER:
		var node = modules.get(id)
		if node != null and node.has_method("set_mode"):
			node.set_mode(next)
	# `view.root.visible = false` (index.html:5136): the gallery stands on its
	# own against the clear colour, with the whole world put away. Every 3D
	# module is that root here; the 2D layers and the gallery itself are not.
	var world_visible := next != "gallery"
	for id: String in modules:
		var node = modules[id]
		if id != "gallery" and node is Node3D:
			(node as Node3D).visible = world_visible

## The master weather control (index.html:4906-4911).
func force_weather(next: String) -> void:
	if not RunArgs.WEATHER_MODES.has(next):
		push_warning("main: weather mode must be one of %s" % ", ".join(RunArgs.WEATHER_MODES))
		return
	world.weather["mode"] = next
	if next == "auto":
		world.weather["spell_ends_at"] = world.time
	world.say("weather: %s" % next)

func hold_rain(value: float) -> void:
	if String(world.weather.get("mode", "")) != "hold":
		world.weather["hold_snow"] = world.weather.get("snow", 0.0)
	world.weather["mode"] = "hold"
	world.weather["hold"] = clampf(value, 0.0, 1.0)

func hold_snow(value: float) -> void:
	if String(world.weather.get("mode", "")) != "hold":
		world.weather["hold"] = world.weather.get("rain", 0.0)
	world.weather["mode"] = "hold"
	world.weather["hold_snow"] = clampf(value, 0.0, 1.0)

func force_strike() -> void:
	var condition := String(world.weather.get("condition", ""))
	if condition == "" or _weather_script == null:
		return
	var block: Variant = world.manifest.get("weather")
	if not (block is Dictionary):
		return
	var spec: Variant = (block as Dictionary).get(condition)
	if spec is Dictionary and (spec as Dictionary).get("strike") is Dictionary:
		_weather_script.strike_now(world, (spec as Dictionary)["strike"])

func force_season(id: String) -> void:
	world.season["force"] = id
	world.say("season: %s" % id)

## The dev clock: park the day where a shot wants it and stop it moving.
## Like the viewer's control it recomputes the night without the season's
## night_share (index.html:5399); at the phases the capture harness uses, the
## share makes no difference.
func set_clock(phase: float) -> void:
	world.day_phase = clampf(phase, 0.0, 1.0)
	world.night = Helpers.night_factor(world.day_phase)
	world.time_frozen = true

func set_paused(value: bool) -> void:
	paused = value

## The viewer's `dev.status()` (index.html:5438).
func status() -> String:
	if world == null:
		return "no world"
	var music_line := "-"
	var music_node = modules.get("music")
	if music_node != null and music_node.has_method("describe"):
		music_line = String(music_node.describe())
	return "%s | season %s | music %s | day %d phase %.3f night %.3f | player %.2f,%.2f" % [
		Helpers.describe_weather(world),
		Helpers.describe_season(world),
		music_line,
		world.day,
		world.day_phase,
		world.night,
		world.player.x,
		world.player.z,
	]

## Show or hide every 2D layer (the HUD, the map, the night vignette). The
## capture harness hides them: the web viewer's reference frames are the WebGL
## canvas alone, and its HUD was DOM.
func set_overlays(on: bool) -> void:
	for child in get_children():
		if child is CanvasLayer:
			(child as CanvasLayer).visible = on
	# A module carrying something the viewer drew in the DOM rather than on the
	# canvas — the gallery's labels are the one case — hides it here too, so a
	# reference frame taken off the canvas alone still compares.
	for id: String in modules:
		var node = modules[id]
		if node != null and node.has_method("set_overlays"):
			node.set_overlays(on)

func reset_profile() -> void:
	module_micros.clear()
	Sim.reset_profile()

## Scripted input: a test, a capture or the smoke run feeds the key set instead
## of the keyboard. The first fed key takes the sampler off the keyboard for
## good, so a scripted run is never disturbed by whatever is held on the
## machine (`HostInput.polling`).
func press_key(name: String) -> void:
	if _input_sampler != null:
		_input_sampler.press(name)

func release_key(name: String) -> void:
	if _input_sampler != null:
		_input_sampler.release(name)

func release_all_keys() -> void:
	if _input_sampler != null:
		_input_sampler.clear()

## A panel's button for a frame-owner key: `map` opens the overlay, `reset`
## starts over. `craft` is the sim's own toggle and the panel writes that
## input itself, so it is nothing to do here.
func _on_module_action(name: String) -> void:
	match name:
		"map":
			var map_node = modules.get("world_map")
			if map_node != null and map_node.has_method("toggle"):
				map_node.toggle()
		"reset":
			reset()

## The dev pack control: put items in the player's hands without crafting them
## (the viewer's console `inv.add`). Returns what did not fit.
func give(item_id: String, count: int = 1) -> int:
	if world == null:
		return count
	return Inventory.inv_add(world, item_id, count)

## For a module animating something the world does not know about (the landing
## trunk's 0.75, index.html:5651).
func add_trauma(amount: float) -> void:
	if rig != null:
		rig.add_trauma(amount)

## The pointer, for a test or a capture: a click at a screen point, in window
## pixels. What the mouse button does.
func click_at(screen: Vector2) -> void:
	_click(screen)

## The pointer's hover, for a test or a capture: what a motion event does,
## resolved at once rather than on the next frame. Returns the pick.
func hover_at(screen: Vector2) -> Dictionary:
	_mouse = screen
	_hover_stale = false
	_refresh_hover()
	return _hover

## What the pointer is over: `{entity, target, point}`, any of which may be
## null, or an empty Dictionary when the pointer is off the world.
func hover() -> Dictionary:
	return _hover

## The whole window, or back to the project's own size. F11.
func set_fullscreen(on: bool) -> void:
	DisplayServer.window_set_mode(
		DisplayServer.WINDOW_MODE_FULLSCREEN if on else DisplayServer.WINDOW_MODE_WINDOWED)

func is_fullscreen() -> bool:
	var window_mode := DisplayServer.window_get_mode()
	return window_mode == DisplayServer.WINDOW_MODE_FULLSCREEN \
		or window_mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN

## The scale every 2D layer is drawn at: the window's height over 900, never
## below 1, times `--ui-scale`.
func ui_scale() -> float:
	return maxf(1.0, resolution().y / UI_REFERENCE_HEIGHT) * args.ui_scale

## The render target's size in pixels, which is what `u_resolution` means.
func resolution() -> Vector2:
	var viewport := get_viewport()
	if viewport == null:
		return Vector2(CameraRig.VERDICT_SIZE)
	return viewport.get_visible_rect().size

# ------------------------------------------------------------------- pointer

## Push the HUD scale to every layer that takes one, when the window or the
## factor changed.
func _sync_ui_scale() -> void:
	var res := resolution()
	var s := ui_scale()
	if is_equal_approx(s, _ui_scale) and res == _ui_resolution:
		return
	_ui_scale = s
	_ui_resolution = res
	for id: String in modules:
		var node = modules[id]
		if node != null and node.has_method("set_ui_scale"):
			node.set_ui_scale(s)

## Resolve the pointer against the world: the card under it, else the ground
## point under it. The HUD is told, so it can name the thing at the cursor.
func _refresh_hover() -> void:
	var before_entity: Variant = _hover.get("entity")
	_hover = _pick(_mouse)
	var hud_node = modules.get("hud")
	if hud_node != null and hud_node.has_method("set_hover"):
		hud_node.set_hover(_hover, _mouse)
	var entity: Variant = _hover.get("entity")
	if not is_same(entity, before_entity):
		var shape := Input.CURSOR_ARROW
		if entity != null and _hover.get("target") != null:
			shape = Input.CURSOR_POINTING_HAND
		Input.set_default_cursor_shape(shape)

## `{entity, target, point}` for a screen point. `target` is what the click
## would do to the entity (`Targeting.target_for`), null when it offers
## nothing; `point` is where the pointer's ray meets the ground plane.
func _pick(screen: Vector2) -> Dictionary:
	if not _booted or rig == null or rig.camera == null or not POINTER_MODES.has(mode):
		return {}
	if screen.x < 0.0 or screen.y < 0.0:
		return {}
	var res := resolution()
	if screen.x > res.x or screen.y > res.y:
		return {}
	var camera: Camera3D = rig.camera
	var found := {"entity": null, "target": null, "point": null}
	var cards_node = modules.get("cards")
	if cards_node != null and cards_node.has_method("pick_entity"):
		var entity: Variant = cards_node.pick_entity(screen, camera, world)
		if entity is Dictionary:
			found["entity"] = entity
			found["target"] = Targeting.target_for(world, entity as Dictionary)
	var origin := camera.project_ray_origin(screen)
	var direction := camera.project_ray_normal(screen)
	if absf(direction.y) > 1e-6:
		var t := -origin.y / direction.y
		if t > 0.0:
			var hit := origin + direction * t
			found["point"] = {"x": hit.x, "z": hit.z}
	return found

## The left button: a thing under the pointer is clicked (the key's action, at
## any distance), else the ground under it is walked to. Nothing while the
## craft panel is open, the player is dead, or the framing is not play — the
## panels take their own clicks before this is reached.
func _click(screen: Vector2) -> void:
	if not _booted or world.craft_open or world.dead or not POINTER_MODES.has(mode):
		return
	var pick := _pick(screen)
	if pick.is_empty():
		return
	var entity: Variant = pick.get("entity")
	if entity != null:
		world.input["click_entity"] = entity
		return
	var point: Variant = pick.get("point")
	if point != null:
		var land: bool = world.is_land(float(point["x"]), float(point["z"]))
		if not land:
			world.say("That is water.")
			return
		world.input["click_point"] = point

## Every motion, whether or not a panel is under the pointer, so the hover
## clears when the mouse crosses onto a panel (a Control eats the motion
## events it is under, and they would never reach `_unhandled_input`).
func _input(event: InputEvent) -> void:
	if not _booted:
		return
	var motion := event as InputEventMouseMotion
	if motion != null:
		_mouse = motion.position
		_hover_stale = true

## Mouse buttons that no panel took: a click acts on the world under it.
func _unhandled_input(event: InputEvent) -> void:
	if not _booted:
		return
	var button := event as InputEventMouseButton
	if button == null or not button.pressed:
		return
	if button.button_index == MOUSE_BUTTON_LEFT:
		_click(button.position)
	elif button.button_index == MOUSE_BUTTON_RIGHT:
		# The right button takes a walk back, pointed or committed.
		world.player.goto = null
		world.player.approach = null

# ------------------------------------------------------------------- input

## Held keys, re-read every frame the way the viewer re-reads them every
## substep. A run without `runtime/input_map.gd` gets WASD and the arrows.
func _sample_held_input() -> void:
	if _input_sampler != null and _input_sampler.has_method("sample"):
		_input_sampler.sample(world, mode)
		return
	var still: bool = mode == "verdict" or world.craft_open
	var axis := _movement_axis()
	world.input["x"] = 0.0 if still else axis.x
	world.input["z"] = 0.0 if still else axis.y
	world.input["interact"] = (not still) and Input.is_physical_key_pressed(KEY_SPACE)

func _movement_axis() -> Vector2:
	var right := 1.0 if (Input.is_physical_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT)) else 0.0
	var left := 1.0 if (Input.is_physical_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT)) else 0.0
	var down := 1.0 if (Input.is_physical_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN)) else 0.0
	var up := 1.0 if (Input.is_physical_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP)) else 0.0
	return Vector2(right - left, down - up)

## The one-shot presses, and the host keys. A press lives for exactly one
## simulation step; `Sim` clears it after every step.
func _unhandled_key_input(event: InputEvent) -> void:
	if not _booted:
		return
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.physical_keycode:
		KEY_F:
			world.input["light"] = true
		KEY_C:
			world.input["craft_toggle"] = true
		KEY_ESCAPE:
			if world.craft_open:
				world.input["craft_toggle"] = true
		KEY_X:
			world.input["use"] = true
		KEY_Z:
			world.input["drop"] = true
		KEY_COMMA:
			world.input["cycle"] = -1
		KEY_PERIOD:
			world.input["cycle"] = 1
		KEY_ENTER, KEY_KP_ENTER:
			if world.craft_open:
				world.input["menu_confirm"] = true
		KEY_Q:
			rig.turn(-1)
		KEY_E:
			rig.turn(1)
		KEY_G:
			set_mode("play" if mode == "gallery" else "gallery")
		KEY_V:
			set_mode("play" if mode == "verdict" else "verdict")
		KEY_P:
			paused = not paused
		KEY_T:
			_cycle_weather()
		KEY_L:
			force_strike()
		KEY_K:
			_cycle_season()
		KEY_N:
			set_clock(0.12 if world.day_phase > 0.5 else 0.72)
			world.time_frozen = false
		KEY_MINUS:
			rig.zoom_by(-1.0)
		KEY_EQUAL:
			rig.zoom_by(1.0)
		KEY_R:
			reset()
		KEY_F11:
			set_fullscreen(not is_fullscreen())
	if world.craft_open and (key.physical_keycode == KEY_W or key.keycode == KEY_UP):
		world.input["menu_move"] = -1
	if world.craft_open and (key.physical_keycode == KEY_S or key.keycode == KEY_DOWN):
		world.input["menu_move"] = 1
	if key.physical_keycode >= KEY_0 and key.physical_keycode <= KEY_9:
		var digit: int = key.physical_keycode - KEY_0
		world.input["select"] = 9 if digit == 0 else digit - 1

func _cycle_weather() -> void:
	var modes := RunArgs.WEATHER_MODES
	var index: int = modes.find(String(world.weather.get("mode", "auto")))
	force_weather(modes[(index + 1) % modes.size()])

func _cycle_season() -> void:
	var order: Array = ["auto"]
	var seasons: Variant = world.manifest.get("seasons")
	if seasons is Dictionary and (seasons as Dictionary).get("calendar") is Dictionary:
		order.append_array(((seasons as Dictionary)["calendar"] as Dictionary).get("order", []))
	if order.size() < 2:
		world.say("This run has no calendar.")
		return
	var index: int = order.find(String(world.season.get("force", "auto")))
	force_season(String(order[(index + 1) % order.size()]))

func _flash_envelope(age: float) -> float:
	var seconds := 0.5
	var block: Variant = world.manifest.get("weather")
	if block is Dictionary and (block as Dictionary).get("rain") is Dictionary:
		var rain: Dictionary = (block as Dictionary)["rain"]
		if rain.get("strike") is Dictionary:
			seconds = float((rain["strike"] as Dictionary).get("flash_seconds", 0.5))
	if _weather_script != null:
		return float(_weather_script.flash_envelope(age, seconds))
	if age < 0.0 or age > seconds:
		return 0.0
	if age < 0.05:
		return 1.0
	if age < 0.09:
		return 0.3
	if age < 0.16:
		return 0.9
	return maxf(0.0, 0.9 * (1.0 - (age - 0.16) / maxf(0.01, seconds - 0.16)))

static func _load_script(path: String) -> GDScript:
	if not ResourceLoader.exists(path):
		return null
	var script = load(path)
	return script if script is GDScript else null
