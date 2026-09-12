class_name EmberOptions
extends RefCounted

## Ember Hollow owns its world, presentation and capture options.
const MODES := ["play", "gallery", "verdict"]
const TIMES := ["noon", "night"]
const WEATHER_MODES := ["auto", "clear", "rain", "storm", "snow", "hold"]

## Absolute path of the run directory (the folder holding `manifest.json`).
var run: String = ""
var mode: String = "play"
var time: String = "noon"
## `auto` lets the calendar run; any `season_id` forces it from the first frame.
var season: String = "auto"
var weather: String = "auto"
## `0` means "the layout's seed", exactly as the viewer does it.
var seed_value: int = 0
## Capture harness: which framing to shoot, where to write it, how many frames.
var capture: String = ""
var out: String = ""
var frames: int = 0
## How much of the daylight colour the deep night keeps away from a fire. The
## game's default is 0 (dark is dark); the viewer's was 0.38, which the
## capture harness passes so the picture gate keeps measuring parity.
var night_floor: float = 0.0
## A multiplier on the HUD's automatic scale (the window's height over 900).
var ui_scale: float = 1.0
## Start in a borderless fullscreen window. F11 toggles it either way.
var fullscreen: bool = false
## Arguments that were not understood, kept so a host can complain about them.
var unknown: PackedStringArray = PackedStringArray()

static func parse(argv: PackedStringArray) -> EmberOptions:
	var args := EmberOptions.new()
	var parsed := HostArgs.tokens(argv, ["--run", "--mode", "--time", "--season", "--weather", "--seed", "--capture", "--out", "--frames", "--night-floor", "--ui-scale", "--fullscreen"])
	args.unknown = parsed.unknown
	for token: String in parsed.values:
		var value: String = parsed.values[token]
		match token:
			"--run":
				args.run = value
			"--mode":
				args.mode = value
			"--time":
				args.time = value
			"--season":
				args.season = value
			"--weather":
				args.weather = value
			"--seed":
				args.seed_value = int(value)
			"--capture":
				args.capture = value
			"--out":
				args.out = value
			"--frames":
				args.frames = int(value)
			"--night-floor":
				args.night_floor = clampf(float(value), 0.0, 1.0)
			"--ui-scale":
				args.ui_scale = float(value)
			"--fullscreen":
				# A bare flag; `--fullscreen=false` turns it off explicitly.
				args.fullscreen = value == "" or value == "1" or value == "true"
	args._normalise()
	return args

## Read the arguments this process was started with.
static func from_command_line() -> EmberOptions:
	return parse(OS.get_cmdline_user_args())

func _normalise() -> void:
	if not MODES.has(mode):
		push_warning("unknown --mode %s; using play" % mode)
		mode = "play"
	if not TIMES.has(time):
		push_warning("unknown --time %s; using noon" % time)
		time = "noon"
	if not WEATHER_MODES.has(weather):
		push_warning("unknown --weather %s; using auto" % weather)
		weather = "auto"
	if run != "":
		run = run.rstrip("/")
	if ui_scale <= 0.0:
		push_warning("--ui-scale must be positive; using 1")
		ui_scale = 1.0

## The option bag `SurvivalWorld.create` takes.
func world_options() -> Dictionary:
	return {"mode": mode, "time": time, "season": season, "weather": weather}

func _to_string() -> String:
	return "EmberOptions(run=%s mode=%s time=%s season=%s weather=%s seed=%d)" % [
		run, mode, time, season, weather, seed_value,
	]
