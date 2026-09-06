class_name UiShots
extends SceneTree

## The HUD's own contact sheet: the real scene in a real window, overlays on,
## staged into the moments a player meets — the pack and a hovered tree at
## noon (lifted, named above itself), a slot's card, the worn places, a pickup
## in flight, a bush gathered by hand (its twigs flying from the bush), a
## held-button walk, a bite's red flood and the throb of starving, the
## crafting table, the pause menu and its how-to-play page, the whole-window
## map, the fire at night and the heat of standing too close, the dark away
## from it and the frost of a near-empty bar, the death sheet,
## the run begun again, and the same HUD in a 2560x1440 window to show the
## scale following the window.
##
##   Godot --path godot/oblique_survival --rendering-driver metal \
##       -s res://tools/ui_shots.gd -- --run <absolute run dir> --out <directory>
##
## Nothing here asserts; the headless suite does that. This is the picture
## the user judges the HUD by. The frames are the window's own, so the second
## window size is the real thing, not a scaled copy.

const STEP := 1.0 / 60.0
const WINDOW := Vector2i(1600, 900)
const BIG_WINDOW := Vector2i(2560, 1440)
## Frames to let the renderer settle before a grab.
const SETTLE_FRAMES := 3

var _run := ""
var _out := ""
var _main = null
var _saved: Array[String] = []


func _initialize() -> void:
	var argv := OS.get_cmdline_user_args()
	_run = _arg(argv, "--run", "")
	_out = _arg(argv, "--out", "").rstrip("/")
	if _run == "" or _out == "":
		printerr("ui_shots: --run <run dir> and --out <directory> are both required")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(_out)
	DisplayServer.window_set_size(WINDOW)
	_go()


func _go() -> void:
	_main = load("res://main.tscn").instantiate()
	_main.arg_overrides = {"run": _run, "mode": "play"}
	_main.autostep = false
	root.add_child(_main)
	await process_frame
	await process_frame
	if _main.world == null:
		printerr("ui_shots: the run did not open")
		quit(1)
		return
	_deafen()
	var world = _main.world

	# --- noon: the pack filled, a tree under the pointer, a walk clicked ---
	_fill_pack()
	_main.advance(1.0)
	var pine: Variant = _nearest_prop("pine", "grown")
	if pine != null:
		var at := _screen_of(float(pine["x"]), 2.2, float(pine["z"]))
		_main.hover_at(at)
	_main.advance(STEP)
	await _save("ui-noon-hover.png")

	# A slot rested on: its card stands above it, with Eat and Drop.
	var hud = _main.modules.get("hud")
	_main.hover_at(Vector2(-1.0, -1.0))
	hud._on_slot_hover(1, true)
	_main.advance(STEP)
	await _save("ui-slot-card.png")
	hud._on_slot_hover(1, false)

	# The worn places: the axe in hand, the cloak on, the pack on the back
	# (the hotbar grows), and the hand's card with Take off.
	_main.give("grass_cloak", 1)
	_main.give("backpack", 1)
	for item in ["axe", "grass_cloak", "backpack"]:
		for index in world.slots.size():
			if world.slots[index] != null and str((world.slots[index] as Dictionary)["item"]) == item:
				world.input["select"] = index
				_main.advance(STEP)
				world.input["equip"] = true
				_main.advance(STEP)
				break
	hud._on_equip_hover("hand", true)
	_main.advance(STEP)
	await _save("ui-equipment.png")
	hud._on_equip_hover("hand", false)

	# A pickup: a log dropped in the open a step from the player, clicked once
	# it has settled, the reach-and-lift, and the log's icon caught a third of
	# the way along its flight into the slot.
	SysDrops.spawn_drops(world, [{"item_id": "log", "count": 1}], world.player.x + 1.2, world.player.z, 1.0, 0.0, 0.0)
	var drop: Variant = null
	for entity in world.entities:
		if entity.get("kind", "") == "item":
			drop = entity
	if drop != null:
		for i in 300:
			_main.advance(STEP)
			if bool(drop.get("settled", false)):
				break
		_main.click_at(_screen_of(float(drop["x"]), 0.1, float(drop["z"])))
		for i in 360:
			_main.advance(STEP)
			if int(hud.flights_in_air()) > 0:
				break
		_main.advance(0.16)
		await _save("ui-pickup-flight.png")
		_main.advance(1.0)

	# A thing gathered by hand (`yield_to = "hand"`): a twig bush a step away,
	# clicked, its two twigs caught on their way from the bush into the slot.
	var bush: Variant = _nearest_prop("twig_bush", "full")
	if bush != null:
		_teleport(float(bush["x"]) + 0.9, float(bush["z"]) + 0.4)
		_main.advance(STEP)
		_main.hover_at(_screen_of(float(bush["x"]), 0.5, float(bush["z"])))
		_main.click_at(_screen_of(float(bush["x"]), 0.5, float(bush["z"])))
		for i in 360:
			_main.advance(STEP)
			if int(hud.flights_in_air()) > 0:
				break
		_main.advance(0.12)
		await _save("ui-hand-gather.png")
		_main.advance(1.0)
		_teleport(camp_x(), camp_z() + 2.0)
		_main.hover_at(Vector2(-1.0, -1.0))
		_main.advance(0.3)

	# A click on the ground four metres to the right: the walk is seen in the
	# next shot as a moved player and the walk's message.
	var walk_to := Vector3(world.player.x + 4.0, 0.0, world.player.z)
	_main.click_at(_screen_of(walk_to.x, 0.0, walk_to.z))
	_main.advance(0.6)
	await _save("ui-noon-walk.png")

	# The button held: the walk follows the pointer as it is dragged down
	# the screen, and is still following when the shot is taken.
	_main.hold_at(_screen_of(world.player.x + 3.0, 0.0, world.player.z))
	_main.advance(0.5)
	_main.drag_to(_screen_of(world.player.x + 1.0, 0.0, world.player.z + 4.0))
	_main.advance(0.5)
	await _save("ui-drag-walk.png")
	_main.release_pointer()
	_main.advance(0.2)

	# --- hurt: a bite's flood, and the slow throb of an empty belly ---------
	# The bite is the sim's `hurt` event with its ten points off, caught
	# 80 ms in; the throb is a second of starving, health going a little a
	# frame, caught on the beat's second peak (the beat starts with the drain;
	# a peak is at (k + 1/4) / THROB_HERTZ), the belly then refilled so the
	# shots after are unmarked.
	world.player.health -= 10.0
	Helpers.emit(world, {"type": "hurt", "x": world.player.x, "z": world.player.z})
	_main.advance(0.08)
	await _save("ui-hurt-bite.png")
	_main.advance(1.0)
	world.player.hunger = 0.0
	_main.advance(1.25 / HurtFlash.THROB_HERTZ)
	await _save("ui-hurt-starving.png")
	world.player.hunger = 80.0
	_main.advance(2.0)

	# The pause menu, and its how-to-play page.
	_main.set_paused(true)
	_main.advance(STEP)
	await _save("ui-pause-menu.png")
	_main.modules.get("pause_menu").show_page("help")
	_main.advance(STEP)
	await _save("ui-pause-help.png")
	_main.set_paused(false)
	_main.advance(STEP)

	# --- the world map: the recoloured plate, the camp, the set pieces ---
	var map_node = _main.modules.get("world_map")
	if map_node != null:
		map_node.set_open(true)
		_main.advance(STEP)
		await _save("ui-map.png")
		map_node.set_open(false)
		_main.advance(STEP)

	# --- the crafting table -------------------------------------------------
	world.input["craft_toggle"] = true
	_main.advance(STEP)
	world.input["menu_select"] = 2
	_main.advance(STEP)
	await _save("ui-craft.png")
	world.input["craft_toggle"] = true
	_main.advance(STEP)

	# --- night by the fire --------------------------------------------------
	var camp := _camp()
	_teleport(camp.x, camp.z + 1.8)
	_light_campfire(true)
	_main.set_clock(0.73)
	_main.hover_at(Vector2(-1.0, -1.0))
	_main.advance(0.5)
	await _save("ui-night-fire.png")

	# --- too hot: a full bar at the fire, two seconds in --------------------
	world.player.warmth = 100.0
	_main.advance(2.2)
	await _save("ui-night-hot.png")

	# --- the dark: the fire out, twelve metres off -------------------------
	_light_campfire(false)
	_teleport(camp.x + 12.0, camp.z + 6.0)
	_main.advance(2.0)
	await _save("ui-night-dark.png")

	# --- too cold: the bar nearly empty in the dark ------------------------
	world.player.warmth = 6.0
	_main.advance(1.5)
	await _save("ui-night-cold.png")
	world.player.warmth = 100.0
	_main.advance(1.5)

	# --- the end, and the beginning again ----------------------------------
	world.player.warmth = 0.0
	world.player.health = 0.5
	world.season["force"] = "winter"
	_main.advance(1.5)
	await _save("ui-death.png")
	_main.reset()
	await process_frame
	_main.set_clock(0.02)
	_main.advance(0.5)
	await _save("ui-reset.png")

	# --- the same HUD in a bigger window -----------------------------------
	DisplayServer.window_set_size(BIG_WINDOW)
	await process_frame
	await process_frame
	_fill_pack()
	_main.advance(0.5)
	var pine2: Variant = _nearest_prop("pine", "grown")
	if pine2 != null:
		_main.hover_at(_screen_of(float(pine2["x"]), 2.2, float(pine2["z"])))
	_main.advance(STEP)
	await _save("ui-2560-hover.png")
	world.input["craft_toggle"] = true
	_main.advance(STEP)
	await _save("ui-2560-craft.png")

	print("[ui_shots] wrote %d frames to %s" % [_saved.size(), _out])
	for name in _saved:
		print("[ui_shots]   %s" % name)
	quit(0)


## The window takes the keyboard when it opens, and a key typed at the desk
## while the sheet renders (an M, an R) would restage it. Nothing here listens.
func _deafen() -> void:
	_main.set_process_input(false)
	_main.set_process_unhandled_input(false)
	_main.set_process_unhandled_key_input(false)
	for id in ["hud", "world_map", "music"]:
		var node = _main.modules.get(id)
		if node != null and "owns_keys" in node:
			node.owns_keys = false


func _fill_pack() -> void:
	for pair in [["axe", 1], ["berry", 4], ["log", 6], ["torch", 1], ["twig", 3], ["flint", 2], ["cooked_berry", 2]]:
		_main.give(String(pair[0]), int(pair[1]))


func _nearest_prop(prop_id: String, state: String) -> Variant:
	var world = _main.world
	var best: Variant = null
	var best_d := INF
	for entity in world.entities:
		if entity.get("kind", "") != "prop" or entity.get("prop_id", "") != prop_id or entity.get("state", "") != state:
			continue
		var d: float = Vector2(float(entity["x"]) - world.player.x, float(entity["z"]) - world.player.z).length()
		if d < best_d and d > 1.5:
			best_d = d
			best = entity
	return best


func _nearest_forage() -> Variant:
	var world = _main.world
	var best: Variant = null
	var best_d := INF
	for entity in world.entities:
		if entity.get("kind", "") != "forage" or bool(entity.get("picked", false)) or bool(entity.get("hidden", false)):
			continue
		var d: float = Vector2(float(entity["x"]) - world.player.x, float(entity["z"]) - world.player.z).length()
		if d < best_d and d > 1.0:
			best_d = d
			best = entity
	return best


func _screen_of(x: float, y: float, z: float) -> Vector2:
	var camera: Camera3D = _main.rig.camera
	return camera.unproject_position(Vector3(x, y, z))


func camp_x() -> float:
	return _camp().x


func camp_z() -> float:
	return _camp().z


func _camp() -> Vector3:
	var layout: Dictionary = _main.package.layout if not _main.package.layout.is_empty() else _main.package.manifest.get("layout", {})
	var camp: Variant = layout.get("camp_position")
	if camp is Dictionary:
		return Vector3(float((camp as Dictionary).get("x", 0.0)), 0.0, float((camp as Dictionary).get("z", 0.0)))
	return Vector3.ZERO


func _teleport(x: float, z: float) -> void:
	var world = _main.world
	world.player.x = x
	world.player.z = z
	world.player.goto = null
	world.player.approach = null
	_main.rig.target = Vector3(x, 0.0, z)
	_main.rig.apply_rig()


func _light_campfire(on: bool) -> void:
	for entity in _main.world.entities:
		if entity.get("prop_id", "") == "campfire":
			entity["state"] = "lit" if on else "unlit"
			entity["burn"] = 1e6 if on else 0.0
			entity["dirty"] = true
			break


func _save(file_name: String) -> void:
	for i in SETTLE_FRAMES:
		await process_frame
	var image := root.get_viewport().get_texture().get_image()
	var path := "%s/%s" % [_out, file_name]
	var error := image.save_png(path)
	if error != OK:
		printerr("ui_shots: could not write %s (%d)" % [path, error])
	else:
		_saved.append("%s (%dx%d)" % [file_name, image.get_width(), image.get_height()])


static func _arg(argv: PackedStringArray, name: String, fallback: String) -> String:
	for i in range(argv.size()):
		if argv[i] == name and i + 1 < argv.size():
			return argv[i + 1]
		if argv[i].begins_with(name + "="):
			return argv[i].substr(name.length() + 1)
	return fallback
