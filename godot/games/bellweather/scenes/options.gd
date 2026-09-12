class_name BellweatherOptions
extends RefCounted

## Options interpreted by this game; token syntax is private shared support.
var run: String = ""
var unknown := PackedStringArray()

static func parse(argv: PackedStringArray) -> BellweatherOptions:
	var args := BellweatherOptions.new()
	var parsed := HostArgs.tokens(argv, ["--run"])
	args.unknown = parsed.unknown
	for token: String in parsed.values:
		var value: String = parsed.values[token]
		match token:
			"--run": args.run = value
	args.run = args.run.rstrip("/")
	return args
