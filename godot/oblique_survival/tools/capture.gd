class_name Capture
extends SceneTree

## The picture gate: render one of the validation framings into a SubViewport
## and write it as a PNG.
##
##   Godot --path godot/oblique_survival --rendering-driver metal \
##       --disable-render-loop --audio-driver Dummy -s res://tools/capture.gd -- \
##       --run <absolute run dir> --capture <shot> --out <png> \
##       [--frames N] [--dpr N] [--overlays on|off]
##
## `--capture all` writes every shot beside `--out`, named after the shot.
##
## Why a `SceneTree` script and not the main scene: a headless run can never
## produce a picture (`RenderingServer.frame_post_draw` never emits and
## `get_texture().get_image()` returns null under the dummy renderer), so the
## capture needs a real display server. This opens the smallest window macOS
## will give, minimises it once the main loop has iterated, and renders into an
## offscreen SubViewport that is sized independently of that window.
##
## The shots reproduce the web-viewer reference frames in
## `scratchpad/ref-v66-png` exactly — the same page mode, the same clock
## phases, the same forced season and weather, the same advance times — so the
## two compare 1:1 at 1600x900. Those references came out of
## `renderer.domElement.toBlob()`, which holds the WebGL canvas and none of the
## page's DOM — no HUD, no map, no night vignette — so every CanvasLayer is
## hidden by default here too. `--overlays on` puts them back.

## Logical size, before the device pixel ratio. The viewer's `VERDICT_SIZE`,
## and the window the play-mode reference shots were taken in.
const SHOT_SIZE := Vector2i(1600, 900)
## The like-for-like reference set (`ref-v66-png`) was re-taken at
## `devicePixelRatio` 1, and the diff rule is stated on 1600x900, so 1 is the
## default. The older 3200x1800 JPEG set needs `--dpr 2`.
const DEFAULT_DPR := 1
const DEFAULT_FRAMES := 3
const FIXED_STEP := 1.0 / 60.0

## How old the strike is when `storm-strike` is drawn.
##
## The reference recipe says `advance(0.05)`, but `flashEnvelope` is a step
## function — 1.0 below 0.05, 0.3 to 0.09, 0.9 to 0.16 — so 0.05 lands exactly
## on a discontinuity and the frame comes out on the 0.3 dip, and 0.10 (an
## earlier reading of the same evidence) lands on the 0.9 one. The reference is
## on neither: it stands 0.1049 of whole-frame mean over its own `storm-noon`,
## where the host's 0.10 frame stands 0.0967 over it, an implied envelope of
## 0.976 — the 1.0 plateau. Two sixtieths of a second is inside that plateau
## (it ends at 0.05) and a whole fixed step away from its edge, so a float
## wobble cannot flip it.
const STRIKE_AGE := 2.0 / 60.0

## The seconds each winter recipe waited for its textures, replayed as
## simulated time.
##
## Both winter reference frames were taken as "…, advance(130), set the clock,
## **wait 5 s for the winter textures to load**, advance(1)" — and the browser's
## render loop kept running through that wait, so the reference stands that many
## seconds further on than the recipe's advances alone. It shows: every card
## whose prop carries `motion_hint = sway_top` leans by
## `sin(u_time * 1.1 + phase) * width * 0.05`, a 5.71 s period, so a clock a few
## seconds out draws the same trees bent a different way — which is exactly the
## "winter props displaced up to 23 px, per prop, in both directions, while the
## same props under the summer look sit at dx 0" the integration report opened
## as O1 against the look's card geometry. The geometry is innocent: the
## manifest's `looks.winter` block carries the same `width_px`, `height_px` and
## `px_per_meter` as the summer state it overlays, so a winter card is the same
## quad in the same place; only the picture on it changes.
##
## Measured, not guessed: one drawn frame per shot, `u_time` swept over it and
## nothing else touched, scored against the reference. Whole-frame mean abs
## diff, unmasked — `winter-noon` 0.0494 at +0 s, 0.0233 at +2.75, **0.0134 at
## +3.00**, 0.0308 at +3.50; `winter-night` 0.0220 at +0 s, 0.0193 at +4.50,
## **0.0085 at +5.00**, 0.0185 at +5.50. Simulating those seconds for real (so
## the mobs, the snow and the fire move too) reproduces the swept frame to four
## digits: 0.0133 and 0.0083.
## The viewer's hard-coded deep-night floor (index.html NIGHT_CHUNK, `* 0.38`).
const VIEWER_NIGHT_FLOOR := 0.38
const WINTER_TEXTURE_WAIT := {"winter-noon": 3.0, "winter-night": 5.0, "winter-coast": 5.0}

## Every shot, with the page it is taken on: the mode `main` boots into and the
## time of day. `_run_shot` carries the rest of each recipe.
const SHOT_SPECS := {
	"camp-noon": {"mode": "verdict", "time": "noon"},
	"camp-night": {"mode": "verdict", "time": "night"},
	"camp-night-unlit": {"mode": "verdict", "time": "night"},
	"winter-noon": {"mode": "verdict", "time": "noon"},
	"winter-night": {"mode": "verdict", "time": "night"},
	"storm-noon": {"mode": "verdict", "time": "noon"},
	"storm-strike": {"mode": "verdict", "time": "noon"},
	"junction": {"mode": "play", "time": "noon"},
	"coast": {"mode": "play", "time": "noon"},
	"winter-coast": {"mode": "play", "time": "noon"},
	"ring": {"mode": "play", "time": "noon"},
	"gallery": {"mode": "gallery", "time": "noon"},
}
## The shot order `--capture all` writes, which is the reference sheet's order.
const SHOTS := [
	"camp-noon", "camp-night", "camp-night-unlit",
	"winter-noon", "winter-night",
	"storm-noon", "storm-strike",
	"junction", "coast", "winter-coast", "ring", "gallery",
]
## The names the first reference set used, kept so an older command still runs.
const SHOT_ALIASES := {"noon": "camp-noon", "night": "camp-night", "storm": "storm-noon"}

var _run := ""
var _out := ""
var _frames := DEFAULT_FRAMES
var _dpr := DEFAULT_DPR
var _overlays := false

func _initialize() -> void:
	var argv := OS.get_cmdline_user_args()
	_run = _arg(argv, "--run", "")
	_out = _arg(argv, "--out", "")
	var shot := _arg(argv, "--capture", "camp-noon")
	_frames = maxi(1, int(_arg(argv, "--frames", str(DEFAULT_FRAMES))))
	_dpr = clampi(int(_arg(argv, "--dpr", str(DEFAULT_DPR))), 1, 4)
	_overlays = _arg(argv, "--overlays", "off") == "on"
	if _run == "" or _out == "":
		printerr("capture: --run <run dir> and --out <png> are both required")
		quit(2)
		return
	_shrink_window()
	_capture_all(shot)

func _capture_all(shot: String) -> void:
	var wanted := SHOTS.duplicate() if shot == "all" else [SHOT_ALIASES.get(shot, shot)]
	for name: String in wanted:
		if not SHOT_SPECS.has(name):
			printerr("capture: unknown shot '%s'; one of %s, all" % [name, ", ".join(SHOTS)])
			quit(2)
			return
		var path := _out_path(name, wanted.size() > 1)
		var ok := await _capture_one(name, path)
		if not ok:
			quit(1)
			return
	quit(0)

func _capture_one(shot: String, out_path: String) -> bool:
	var started := Time.get_ticks_msec()
	var spec: Dictionary = SHOT_SPECS[shot]
	var viewport := SubViewport.new()
	# Mandatory: several SubViewports sharing the default World3D render each
	# other's contents and each other's cameras.
	viewport.own_world_3d = true
	viewport.size = SHOT_SIZE * _dpr
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.transparent_bg = false
	root.add_child(viewport)

	var main = load("res://main.tscn").instantiate()
	main.arg_overrides = {
		"run": _run,
		"mode": String(spec.get("mode", "verdict")),
		"time": String(spec.get("time", "noon")),
		# The references were rendered by the viewer, whose deep night kept
		# 0.38 of the daylight colour; the game's own night keeps none
		# (`--night-floor`, default 0). The gate measures the port, not the
		# game's darkness, so it renders the viewer's number.
		"night_floor": VIEWER_NIGHT_FLOOR,
	}
	main.autostep = false
	viewport.add_child(main)
	# Two idle frames: a node added from `_initialize` has its `_ready`
	# deferred to the first iteration of the main loop, and nothing is
	# registered with the rendering scenario until the loop has run either
	# (without this `force_draw` renders a fully black frame).
	await process_frame
	await process_frame
	_minimise_window()
	if main.world == null:
		printerr("capture: the run did not open; nothing to draw")
		return false
	main.set_overlays(_overlays)
	main.rig.pixel_ratio = float(_dpr)
	main.frame_uniforms.set_resolution(Vector2(viewport.size))

	_run_shot(main, shot)

	# Mandatory, and the whole reason a shot can frame the wrong place: a
	# `Node3D` transform set from script only reaches the rendering server when
	# the SceneTree flushes its transform-notification list, which happens on a
	# main-loop iteration. `RenderingServer.force_draw` is not one, so without
	# this idle frame every camera move, every card the shot walked and every
	# mesh a look swap re-laid is drawn where it was before `_run_shot` ran.
	await process_frame

	for _i in range(_frames):
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	if image == null:
		printerr("capture: no image came back (is this a headless run?)")
		return false
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	var error := image.save_png(out_path)
	if error != OK:
		printerr("capture: could not write %s (error %d)" % [out_path, error])
		return false
	# The camera is printed because the reference recipes name where it
	# settles: a shot that framed the wrong place says so on this line.
	var camera_position: Vector3 = main.rig.camera.position
	print("[capture] %s -> %s  %dx%d  %d ms  camera (%.2f, %.2f, %.2f) target (%.2f, %.2f)  %s" % [
		shot, out_path, image.get_width(), image.get_height(),
		Time.get_ticks_msec() - started,
		camera_position.x, camera_position.y, camera_position.z,
		main.rig.target.x, main.rig.target.z,
		main.status(),
	])
	viewport.queue_free()
	await process_frame
	return true

## The ten framings, step for step from `maps/validation-reference.md`.
##
## Each one boots on the page its reference was taken on (`SHOT_SPECS`), so the
## verdict shots stand the player at the camp and light the fire on the night
## pages exactly when entering verdict did there. A verdict shot ends by
## re-entering verdict, which re-pins the framing after a long advance; the
## play and gallery shots end on their own last frame.
func _run_shot(main, shot: String) -> void:
	match shot:
		"camp-noon":
			main.set_clock(0.02)
			main.advance(2.0)
			_verdict_finish(main)
		"camp-night":
			main.set_clock(0.73)
			main.advance(2.0)
			_verdict_finish(main)
		"camp-night-unlit":
			# The night page with the fire put out again: `light.on` false, so
			# the deep-night floor is what the frame shows.
			main.set_clock(0.73)
			main.advance(2.0)
			main.set_mode("verdict")
			_unlight_campfire(main)
			main.frame(FIXED_STEP, true)
		"winter-noon":
			main.force_season("winter")
			main.force_weather("auto")
			main.advance(130.0)
			main.set_clock(0.02)
			main.advance(float(WINTER_TEXTURE_WAIT[shot]))
			main.advance(1.0)
			_verdict_finish(main)
		"winter-night":
			main.force_season("winter")
			main.force_weather("auto")
			main.advance(130.0)
			main.set_clock(0.73)
			main.advance(float(WINTER_TEXTURE_WAIT[shot]))
			main.advance(1.0)
			_verdict_finish(main)
		"storm-noon":
			_storm_stage(main)
			_verdict_finish(main)
		"storm-strike":
			# The strike is the last thing that happens: the flash envelope is
			# read off `world.time - flash_at`, so one extra frame after the
			# advance would step the envelope past its 0.05 s plateau.
			_storm_stage(main)
			main.set_mode("verdict")
			main.force_strike()
			main.advance(STRIKE_AGE)
		"junction":
			# The middle of the road polyline, read off the record rather than
			# typed in, so the shot follows the world. Play mode: the camera
			# eases to the player.
			_clear_weather(main)
			var mid := _road_midpoint(main)
			_teleport(main, mid.x, mid.y)
			main.advance(3.0)
			main.advance(1.0)
		"coast":
			# The first water south of the spawn, found by walking -z on the
			# mask; standing 1.75 m short of it puts the water, the shore rim
			# and the cliff ray-march in frame.
			_clear_weather(main)
			var shore := _shore_south(main)
			_teleport(main, 0.0, shore + SHORE_STAND_METERS)
			main.advance(3.0)
			main.advance(1.0)
		"ring":
			# The first boulder ring, from the record's set pieces: a set
			# piece sited by the generator, not authored at the origin.
			_clear_weather(main)
			var site := _set_piece(main, "boulder_ring")
			_teleport(main, site.x, site.y + 3.0)
			main.advance(3.0)
			main.advance(1.0)
		"winter-coast":
			# The frozen shore: the ice plate mixed over the water by the snow
			# factor, the waves stilled, the cliff unchanged. Same stand as
			# `coast`, taken after the winter ramp with the clock parked at noon.
			main.force_season("winter")
			main.force_weather("auto")
			main.advance(130.0)
			main.set_clock(0.02)
			_teleport(main, 0.0, _shore_south(main) + SHORE_STAND_METERS)
			main.advance(3.0)
			main.advance(float(WINTER_TEXTURE_WAIT[shot]))
			main.advance(1.0)
		"gallery":
			main.set_mode("gallery")
			main.advance(1.0)
			main.advance(1.0)

## Summer, the snow decayed, the clock parked at noon, then a full storm.
func _storm_stage(main) -> void:
	main.force_season("summer")
	main.advance(140.0)
	main.set_clock(0.02)
	main.force_weather("storm")
	main.advance(45.0)

## The play shots were taken after the weather was forced clear and given time
## to drain, so neither carries a rain veil or a wet ground.
func _clear_weather(main) -> void:
	main.force_weather("clear")
	main.advance(30.0)

func _verdict_finish(main) -> void:
	main.set_mode("verdict")
	main.frame(FIXED_STEP, true)

## How far short of the water's edge the coast shots stand.
const SHORE_STAND_METERS := 1.75

## The middle point of the road polyline in the layout record.
func _road_midpoint(main) -> Vector2:
	var layout: Dictionary = main.package.layout
	var points: Array = layout.get("road", {}).get("points", []) if layout.get("road") != null else []
	if points.is_empty():
		return Vector2.ZERO
	var mid: Dictionary = points[points.size() / 2]
	return Vector2(float(mid.get("x", 0.0)), float(mid.get("z", 0.0)))

## The z of the first water south of the spawn along x = 0, on the walkable mask.
func _shore_south(main) -> float:
	var world = main.get_world()
	var z := -6.0
	var limit := -float(main.package.manifest.get("ground", {}).get("size_meters", 256.0)) * 0.5
	while z > limit and world.is_land(0.0, z):
		z -= 0.25
	return z

## Where the first instance of a set piece stands, from the record.
func _set_piece(main, set_piece_id: String) -> Vector2:
	var layout: Dictionary = main.package.layout
	for piece: Dictionary in layout.get("set_pieces", []):
		if String(piece.get("set_piece", "")) == set_piece_id:
			return Vector2(float(piece.get("x", 0.0)), float(piece.get("z", 0.0)))
	return Vector2.ZERO

## The reference recipe's `world.player.x = …; z = …`: a teleport, with the
## walk cycle left where it was.
func _teleport(main, x: float, z: float) -> void:
	var world = main.get_world()
	world.player.x = x
	world.player.z = z

## Put the campfire out after verdict lit it: state `unlit`, burn 0.
func _unlight_campfire(main) -> void:
	var world = main.get_world()
	for entity: Dictionary in world.entities:
		if String(entity.get("prop_id", "")) == "campfire":
			entity["state"] = "unlit"
			entity["burn"] = 0.0
			entity["dirty"] = true
			break
	world.light["on"] = false

func _out_path(shot: String, many: bool) -> String:
	if not many and _out.to_lower().ends_with(".png"):
		return _out
	if _out.to_lower().ends_with(".png"):
		return "%s/%s-%s.png" % [_out.get_base_dir(), _out.get_file().get_basename(), shot]
	return "%s/%s.png" % [_out.rstrip("/"), shot]

func _shrink_window() -> void:
	if DisplayServer.get_name() == "headless":
		return
	DisplayServer.window_set_size(Vector2i(160, 100))
	DisplayServer.window_set_position(Vector2i(0, 0))
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)

func _minimise_window() -> void:
	if DisplayServer.get_name() == "headless":
		return
	# Ignored before the first `process_frame`, which is why it happens here.
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)

static func _arg(argv: PackedStringArray, name: String, fallback: String) -> String:
	for i in range(argv.size()):
		if argv[i] == name and i + 1 < argv.size():
			return argv[i + 1]
		if argv[i].begins_with(name + "="):
			return argv[i].substr(name.length() + 1)
	return fallback
