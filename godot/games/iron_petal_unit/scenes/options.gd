class_name RunnerOptions
extends RefCounted

## Options interpreted by this game; token syntax is private shared support.
var run: String = ""
var seed_value: int = 0
var unknown := PackedStringArray()

static func parse(argv: PackedStringArray) -> RunnerOptions:
	var args := RunnerOptions.new()
	var parsed := HostArgs.tokens(argv, ["--run", "--seed"])
	args.unknown = parsed.unknown
	for token: String in parsed.values:
		var value: String = parsed.values[token]
		match token:
			"--run": args.run = value
			"--seed": args.seed_value = int(value)
	args.run = args.run.rstrip("/")
	return args
