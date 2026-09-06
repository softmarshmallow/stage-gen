class_name RunArgs
extends RefCounted

## The host's command line, parsed once.
##
## Godot swallows its own flags, so every host setting is passed after `--`:
##
##   Godot --path godot/oblique_survival -- --run <absolute run dir> \
##       [--mode play|gallery|verdict] [--time noon|night] \
##       [--season auto|<season_id>] [--weather auto|clear|rain|storm|snow] \
##       [--seed <int>] [--capture <shot>] [--out <png path>] [--frames <n>]
##
## These mirror the web viewer's query string (`?run=&mode=&time=&season=`),
## plus the capture harness's three. `--reach` / `--approach` are deliberately
## not carried over: they were viewer-only tuning knobs.

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
## Arguments that were not understood, kept so a host can complain about them.
var unknown: PackedStringArray = PackedStringArray()

static func parse(argv: PackedStringArray) -> RunArgs:
	var args := RunArgs.new()
	var index := 0
	while index < argv.size():
		var token := argv[index]
		var value := ""
		var inline := false
		# Both `--flag value` and `--flag=value` are accepted.
		var equals := token.find("=")
		if token.begins_with("--") and equals > 0:
			value = token.substr(equals + 1)
			token = token.substr(0, equals)
			inline = true
		var next_is_value := index + 1 < argv.size() and not argv[index + 1].begins_with("--")
		if not inline and next_is_value:
			value = argv[index + 1]
		var known := true
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
			_:
				known = false
		if not known:
			args.unknown.append(token)
			index += 1
		elif inline or not next_is_value:
			index += 1
		else:
			index += 2
	args._normalise()
	return args

## Read the arguments this process was started with.
static func from_command_line() -> RunArgs:
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

## The option bag `World.create` takes.
func world_options() -> Dictionary:
	return {"mode": mode, "time": time, "season": season, "weather": weather}

func _to_string() -> String:
	return "RunArgs(run=%s mode=%s time=%s season=%s weather=%s seed=%d)" % [
		run, mode, time, season, weather, seed_value,
	]
